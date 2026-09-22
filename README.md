# Self-Healing Network

An RL agent (DQN and PPO, compared) that detects link Failures in an emulated on-premises network and reroutes Traffic Demands onto Backup Paths, controlling the network through the OpenDaylight SDN controller.

Stack: Mininet + OpenDaylight (Vanadium) + Gymnasium + Stable-Baselines3.

See [`CONTEXT.md`](CONTEXT.md) for the glossary, [`docs/PLAN.md`](docs/PLAN.md) for the full design, and [`docs/adr/`](docs/adr/) for the recorded decisions.

## Prerequisites

Everything runs inside a single Ubuntu 22.04 VM on VMware (ADR 0002):

- ≥8 GB RAM, ≥2 vCPU
- Internet access (to download OpenDaylight and Python packages)

The host OS is not used for anything except editing files.

## Setup

```bash
git clone <this-repo> sf-network
cd sf-network
bash scripts/setup_vm.sh
```

`setup_vm.sh` installs Mininet, Open vSwitch, iperf3, OpenDaylight, creates the Python venv, installs pinned dependencies, and freezes the evaluation manifest. The OpenDaylight release is selected by its karaf artifact version:

```bash
ODL_VERSION=0.21.4 bash scripts/setup_vm.sh
```

`0.21.4` corresponds to the Vanadium release line — confirm the exact artifact at M0 (see below) before the first control-plane test.

### Controller credentials

The controller password is read from the `ODL_PASSWORD` environment variable and **must be set** before training or evaluation — there is no fallback:

```bash
export ODL_PASSWORD=<password>
```

`setup_vm.sh` uses this variable for its one-time smoke check too.

## Run training

All constants live in `configs/topology.yaml` and `configs/training.yaml`; edit there, not in code.

```bash
export ODL_PASSWORD=<password>

# DQN — pilot run
.venv/bin/python train_dqn.py --seed 0 --steps 50000

# PPO — pilot run
.venv/bin/python train_ppo.py --seed 0 --steps 50000
```

Arguments:

| Flag | Default | Meaning |
|---|---|---|
| `--seed` | `0` | reproducibility seed (use 0–4 per ADR 0005) |
| `--steps` | `training.yaml → budget.pilot_steps` | environment steps to train for |
| `--name` | `dqn_seed<seed>` / `ppo_seed<seed>` | results subdirectory |

Artifacts per run (under `results/<name>/`): `model.zip` and `summary.json` (hyperparameters). Training curves go to `runs/dqn` and `runs/ppo` (view with `tensorboard --logdir runs`).

## Run the comparison

Evaluation runs in a separate process after training, replaying the frozen 36-scenario manifest with a deterministic policy. Pass one model path per seed to compare across seeds:

```bash
export ODL_PASSWORD=<password>

.venv/bin/python scripts/run_eval.py \
  --dqn results/dqn_seed0/model.zip results/dqn_seed1/model.zip results/dqn_seed2/model.zip \
  --ppo results/ppo_seed0/model.zip results/ppo_seed1/model.zip results/ppo_seed2/model.zip \
  --out results/eval_comparison.json
```

Output includes, per algorithm: per-seed summaries, mean ± std **across seeds**, and per-scenario aggregates, for recovery rate, availability, time-to-Recovery, and cumulative reward.

## Tests

```bash
.venv/bin/python -m pytest tests -q
```

## Milestones

The project follows the staged plan in `docs/PLAN.md` §16. Before any training, complete **M0**: confirm OpenDaylight (Vanadium) discovers the 6-switch topology and that one manual RESTCONF flow push works — this validates the integration details flagged in §15: the `flow-node-capability:table` REST path, the operational flow-inventory JSON shape, and the Vanadium→karaf artifact mapping.
