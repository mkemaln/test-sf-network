import argparse
import json
import time
from pathlib import Path

from stable_baselines3 import PPO
from stable_baselines3.common.utils import set_random_seed

from shn.candidates import compute_candidates
from shn.config import ROOT, load_topology, load_training
from shn.env.healing_env import HealingEnv


def build_env(seed):
    topology = load_topology()
    training = load_training()
    candidates = compute_candidates(topology, int(training["candidates"]["k"]))
    return HealingEnv(topology, training, candidates, seed=seed)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", type=int, default=None)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--name", type=str, default=None)
    args = parser.parse_args()

    training = load_training()
    steps = args.steps if args.steps is not None else int(training["budget"]["pilot_steps"])
    set_random_seed(args.seed)
    env = build_env(args.seed)

    run_dir = Path("results") / (args.name or f"ppo_seed{args.seed}")
    run_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()
    cfg = training["ppo"]
    try:
        model = PPO(
            "MlpPolicy",
            env,
            policy_kwargs={"net_arch": cfg["policy"]},
            learning_rate=float(cfg["learning_rate"]),
            gamma=float(cfg["gamma"]),
            n_steps=int(cfg["n_steps"]),
            gae_lambda=float(cfg["gae_lambda"]),
            clip_range=float(cfg["clip_range"]),
            n_epochs=int(cfg["n_epochs"]),
            ent_coef=float(cfg["ent_coef"]),
            tensorboard_log="runs/ppo",
            seed=args.seed,
            verbose=1,
        )
        model.learn(total_timesteps=steps)
        model.save(run_dir / "model")
    finally:
        env.close()

    summary = {
        "algorithm": "ppo",
        "seed": args.seed,
        "steps": steps,
        "wall_seconds": time.time() - started,
        "hyperparameters": cfg,
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
