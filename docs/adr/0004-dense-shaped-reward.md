---
status: accepted
---

# Dense shaped reward with path-switch penalty

Training reward per Decision Interval is dense and shaped: delivered-throughput ratio per Traffic Demand, minus penalties for added delay and loss, minus a path-switch penalty to discourage flapping. Time-to-Recovery is reported as the headline *evaluation* metric, not as the training reward.

## Considered Options

- **Sparse (−1 per step until Recovery)**: rejected — too slow to train DQN/PPO at this scale.
- **Terminal recovery bonus only**: rejected — same sparsity problem, and it hides flapping.

## Consequences

- Reward weights (throughput/delay/loss/switch) are config constants; sweep them, never hardcode silently.
- Evaluations must not read training reward as "performance" — availability and time-to-recovery carry that meaning.
