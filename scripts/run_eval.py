import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stable_baselines3 import DQN, PPO

from shn.candidates import compute_candidates
from shn.config import ROOT, load_topology, load_training
from shn.env.healing_env import HealingEnv


def build_env(seed):
    topology = load_topology()
    training = load_training()
    candidates = compute_candidates(topology, int(training["candidates"]["k"]))
    return HealingEnv(topology, training, candidates, seed=seed)


def run_model(model, scenarios):
    env = build_env(12345)
    results = []
    for scenario in scenarios:
        observation, _ = env.reset(options={"scenario": scenario})
        done = False
        total_reward = 0.0
        while not done:
            action, _ = model.predict(observation, deterministic=True)
            observation, reward, terminated, truncated, info = env.step(int(action))
            total_reward += float(reward)
            done = terminated or truncated
        results.append(
            {
                "link": list(scenario["link"]),
                "onset_s": scenario["onset_s"],
                "recovered": info.get("recovered", False),
                "recovery_time_s": info.get("recovery_time_s"),
                "availability": info.get("availability", 0.0),
                "episode_reward": total_reward,
            }
        )
    env.close()
    return results


def seed_summary(results):
    total = len(results)
    recovered = [r for r in results if r["recovered"]]
    recovery_times = [r["recovery_time_s"] for r in recovered if r["recovery_time_s"] is not None]
    availability = [r["availability"] for r in results]
    rewards = [r["episode_reward"] for r in results]
    return {
        "n_scenarios": total,
        "recovery_rate": len(recovered) / total if total else 0.0,
        "availability_mean": statistics.mean(availability) if availability else 0.0,
        "ttr_mean": statistics.mean(recovery_times) if recovery_times else None,
        "reward_mean": statistics.mean(rewards) if rewards else 0.0,
    }


def across_seeds(summaries):
    def aggregate(key):
        values = [s[key] for s in summaries if s.get(key) is not None]
        if not values:
            return None
        return {
            "mean": statistics.mean(values),
            "std": statistics.pstdev(values) if len(values) > 1 else 0.0,
        }

    return {key: aggregate(key) for key in ["recovery_rate", "availability_mean", "ttr_mean", "reward_mean"]}


def per_scenario(all_results):
    scenarios = len(all_results[0])
    output = []
    for index in range(scenarios):
        rows = [seed[index] for seed in all_results]
        recovered = [r for r in rows if r["recovered"]]
        recovery_times = [r["recovery_time_s"] for r in recovered if r["recovery_time_s"] is not None]
        output.append(
            {
                "link": rows[0]["link"],
                "onset_s": rows[0]["onset_s"],
                "recovery_rate": len(recovered) / len(rows),
                "ttr_mean": statistics.mean(recovery_times) if recovery_times else None,
                "availability_mean": statistics.mean([r["availability"] for r in rows]),
                "reward_mean": statistics.mean([r["episode_reward"] for r in rows]),
            }
        )
    return output


def evaluate(loader, paths, scenarios):
    seed_results = []
    for path in paths:
        model = loader.load(path)
        seed_results.append(run_model(model, scenarios))
    summaries = [seed_summary(results) for results in seed_results]
    return {
        "seeds": [{"path": path, **summary} for path, summary in zip(paths, summaries)],
        "across_seeds": across_seeds(summaries),
        "per_scenario": per_scenario(seed_results),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dqn", nargs="+", required=True)
    parser.add_argument("--ppo", nargs="+", required=True)
    parser.add_argument("--out", type=str, default="results/eval_comparison.json")
    args = parser.parse_args()

    scenarios = json.loads((ROOT / load_training()["eval"]["manifest"]).read_text())
    output = {
        "dqn": evaluate(DQN, args.dqn, scenarios),
        "ppo": evaluate(PPO, args.ppo, scenarios),
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2))
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
