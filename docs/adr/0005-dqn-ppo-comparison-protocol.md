---
status: accepted
---

# DQN vs PPO compared via separate training scripts under a matched protocol

DQN and PPO are implemented as separate entry files (`train_dqn.py`, `train_ppo.py`) sharing one environment package, per the user's requirement to keep the algorithms' code visually distinct. The comparison is matched on environment steps (not wall-clock), runs ≥5 seeds per algorithm, and evaluates on a held-out set of fixed Failure scenarios (unseen link × onset combinations). Reported: mean±std of time-to-recovery, per-episode availability, cumulative reward, and sample-efficiency curves.

## Consequences

- A change to the environment or reward must land in the shared package, never in one algorithm's script — otherwise the comparison silently diverges.
- Held-out scenarios are frozen in a JSON manifest before any evaluation run.
