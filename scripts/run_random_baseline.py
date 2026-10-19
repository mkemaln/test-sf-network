import argparse
import json
import statistics
import time
from pathlib import Path

from stable_baselines3.common.utils import set_random_seed

from shn.candidates import compute_candidates
from shn.config import load_topology, load_training
from shn.env.healing_env import HealingEnv


def build_env(seed):
    topology = load_topology()
    training = load_training()
    candidates = compute_candidates(topology, int(training["candidates"]["k"]))
    return HealingEnv(topology, training, candidates, seed=seed)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--episodes", type=int, default=20)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--name", type=str, default=None)
    args = parser.parse_args()

    set_random_seed(args.seed)
    env = build_env(args.seed)

    run_dir = Path("results") / (args.name or "random_baseline")
    run_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()

    episode_rewards = []
    try:
        for ep in range(args.episodes):
            obs, _ = env.reset()
            terminated = False
            truncated = False
            ep_reward = 0.0
            while not (terminated or truncated):
                action = env.action_space.sample()
                obs, reward, terminated, truncated, _ = env.step(action)
                ep_reward += reward
            episode_rewards.append(ep_reward)
            print(f"episode {ep + 1}/{args.episodes}: reward={ep_reward:.3f}")
    finally:
        env.close()

    summary = {
        "algorithm": "random",
        "seed": args.seed,
        "episodes": args.episodes,
        "wall_seconds": time.time() - started,
        "episode_rewards": episode_rewards,
        "mean_reward": sum(episode_rewards) / len(episode_rewards) if episode_rewards else 0.0,
        "std_reward": statistics.pstdev(episode_rewards) if len(episode_rewards) > 1 else 0.0,
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"mean reward = {summary['mean_reward']:.3f} +/- {summary['std_reward']:.3f} over {args.episodes} episodes")


if __name__ == "__main__":
    main()