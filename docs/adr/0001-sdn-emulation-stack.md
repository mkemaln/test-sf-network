---
status: accepted
---

# SDN emulation stack: Mininet + OpenDaylight + Gymnasium + SB3

The agent must be trained against a controllable network without touching real gear, and must support both a value-based algorithm (DQN) and a policy-gradient algorithm (PPO) for comparison. We chose Mininet for topology emulation, OpenDaylight as the SDN controller, Gymnasium as the RL environment interface, and Stable-Baselines3 for training.

## Considered Options

- **Ryu instead of OpenDaylight**: Python-native, far lighter, direct in-process API to the agent. Rejected in favour of ODL's enterprise-grade controller with a standard RESTCONF northbound, matching the on-prem production narrative of the thesis. Accepted trade-off: ODL is a heavyweight Java application and all agent integration goes over REST.
- **GNS3/Containerlab with real router images**: realistic, but slow to rebuild and router control-plane integration (NETCONF) is slower than OpenFlow flow programming.
- **ns-3**: full packet simulation; rejected for simulation-speed/fidelity mismatch with a real SDN data plane.
- **Ray RLlib instead of SB3**: scales better, but SB3 covers DQN/PPO with less ceremony for a single-node study.

## Consequences

- Everything the Agent does to the Emulated Network passes through ODL's northbound API (or a thin Python adapter over it).
- Training is single-node; no distributed rollout infrastructure.
- Mininet requires Linux — the runtime environment (WSL2 vs VM) is a follow-up ADR once decided.
