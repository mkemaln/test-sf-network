---
status: accepted
---

# Discrete action space over precomputed Candidate Paths

The Agent's action each step is a single selection: one (Traffic Demand, Candidate Path) pair, or no-op. Candidate Paths are k-shortest precomputed per Demand (k=4 as initial config, a tunable constant), so |A| = D·k + 1.

## Considered Options

- **Per-link weight setting + central SPF recompute**: rejected — noisy credit assignment (one action changes many paths).
- **Raw OpenFlow rule push**: rejected — combinatorially explosive and cannot be pre-validated for loops/blackholes.

## Consequences

- Identical discrete action set for DQN and PPO, keeping the comparison fair.
- Every Candidate Path is validated at precompute time; reroute reduces to swapping path id → flow push, never on-line path discovery.
- k, D, and topology changes resize the action space; treat them as config constants, not magic numbers.
