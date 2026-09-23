# PLAN — Self-Healing Network (RL Agent over SDN)

Working plan for the thesis-scale system. Glossary lives in `CONTEXT.md`; irreversible decisions live in `docs/adr/`. Everything in this file that is a number is a config constant — see §12.

## 1. Goal

Train an RL Agent (DQN and PPO, compared) that detects link Failures in an Emulated Network and reroutes Traffic Demands onto Backup Paths to maximize Availability and minimize time-to-Recovery, controlling the network through the OpenDaylight Controller.

## 2. Architecture

```
┌─────────────────────── Ubuntu 22.04 VM (VMware) ───────────────────────────┐
│                                                                             │
│  ┌─────────────┐  RESTCONF (topology, port stats, flows)  ┌─────────────┐   │
│  │  OpenDaylight│ ◄──────────────────────────────────────► │ shn package │   │
│  │  (Titanium)  │                                          │  (Python)   │   │
│  └──────┬───────┘                                          └──────┬──────┘   │
│         │ OpenFlow 13 (port 6653)                                 │ in-proc │
│  ┌──────┴───────┐                                          ┌──────▼──────┐   │
│  │   Mininet     │ ◄── configLinkStatus / iperf / ping ──► │ Gymnasium   │   │
│  │ (OVS, 6 sw,   │            (env controls emulated net)  │ HealingEnv  │   │
│  │  3 hosts)     │                                          └──────┬──────┘   │
│  └───────────────┘                                                 │          │
│                                                             ┌──────▼──────┐   │
│                                                             │ SB3: DQN /  │   │
│                                                             │      PPO    │   │
│                                                             └─────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

| Component | Responsibility |
|---|---|
| Mininet (in-process) | Emulated Network; hosts run iperf3 + ping; env brings links up/down |
| OpenDaylight (out-of-process) | Controller: owns topology view, port stats, OpenFlow rule push |
| `shn.env.odl_adapter` | Thin RESTCONF client; the *only* code that talks to ODL |
| `shn.env.telemetry` | Measures per-Demand RTT/loss/throughput; builds state vector |
| `shn.env.failure_injector` | Hard link-down at random t; v2: netem soft degradation |
| `shn.env.healing_env` | Gymnasium env: `reset()`/`step()`, reward, Recovery detection |
| `train_dqn.py` / `train_ppo.py` | Separate entry files sharing `shn` — never fork the env (ADR 0005) |

## 3. Pinned stack

| Layer | Choice |
|---|---|
| VM | Ubuntu 22.04 LTS, ≥8 GB RAM, ≥2 vCPU, VMware Workstation |
| Controller | OpenDaylight Vanadium (karaf 0.21.x), features: `odl-openflowplugin-flow-services`, `odl-restconf` |
| Emulation | Mininet 2.3+, Open vSwitch (OF1.3) |
| RL interface | Gymnasium |
| Training | Stable-Baselines3 ≥ 2.3, PyTorch (CPU build is sufficient) |
| Python | 3.10 (venv in VM, `requirements.txt` pinned) |
| Traffic / probes | iperf3 (UDP), ping |

## 4. Topology (v1)

6 switches, 9 links, 3 hosts. Per-link delay is fixed and heterogeneous so Backup Path choice is a real QoS trade-off.

| Link | Bandwidth | Delay |
|---|---|---|
| s1–s2 | 10 Mbps | 3 ms |
| s1–s3 | 10 Mbps | 6 ms |
| s1–s6 | 10 Mbps | 2 ms |
| s2–s3 | 10 Mbps | 2 ms |
| s2–s4 | 10 Mbps | 5 ms |
| s3–s5 | 10 Mbps | 3 ms |
| s4–s5 | 10 Mbps | 7 ms |
| s4–s6 | 10 Mbps | 4 ms |
| s5–s6 | 10 Mbps | 5 ms |

Hosts: `h1@s1`, `h2@s5`, `h3@s6`.

Traffic Demands (v1, fixed UDP rates):
- `D1: h1→h2 @ 5 Mbps`
- `D2: h1→h3 @ 3 Mbps`

## 5. Candidate Paths and action space

- k-shortest (hop count, then delay) per Demand, **k = 4** (tunable).
- Precomputed at startup from the topology; validated for reachability and capacity at precompute time.
- Actions: `0 = no-op`; `1–4 = D1 → candidate path 1..4`; `5–8 = D2 → candidate path 1..4`. **|A| = 9.**
- Selecting the currently-active path = no-op semantics (no flow churn, no switch penalty).
- One (Demand, Path) change per Decision Interval; rerouting both Demands takes ≥2 intervals (deliberate — see ADR 0003).

## 6. Observation (41 dims, `Box`)

Realistic sensing only, no oracle (ADR 0006):

| Block | Features | Dims |
|---|---|---|
| Per-link × 9 | up/down (0/1), utilization (0–1, port-stats delta), loss rate (0–1, drop counters) | 27 |
| Per-Demand × 2 | RTT (normalized by 200 ms cap), loss (0–1), delivered-throughput ratio (0–1), current path one-hot (4) | 14 |

Source: link block from ODL RESTCONF (topology operational state + port statistics); Demand block from receiver-side iperf3 sampling + ping series within the interval.

## 7. Reward (dense, shaped — ADR 0004)

Per Decision Interval:

```
r = Σ_d [ w_thr·delivered_ratio_d
        + w_rtt·max(0, 1 − rtt_d/rtt_ref_d)
        − w_loss·loss_d ]
    − w_switch·1[Agent changed a Demand's path this interval]
```

Default weights: `w_thr = 1.0`, `w_rtt = 0.25`, `w_loss = 2.0`, `w_switch = 0.1`. `rtt_ref_d` = mean pre-failure RTT for Demand d (measured in the first quiet intervals of the episode). A hard failure collapses `delivered_ratio` to ≈0 until reroute — the primary learning signal.

## 8. Episode protocol

| Parameter | Default |
|---|---|
| Episode length | 60 s |
| Decision Interval Δ | 1 s (60 steps/episode) |
| Failure onset | uniform random t ∈ [10, 40] s, single hard link down, chosen among links on an Active Path |
| Soft reset (every episode) | restore all links, re-push baseline flows (overlap-first), restart iperf/ping |
| Hard rebuild | every 50 episodes: `net.stop()` → rebuild topology → re-register with ODL |

Failure mechanics: Mininet Python API `net.configLinkStatus(a, b, 'down')` — OVS interfaces go down, ODL sees port-status/LLDP loss and updates topology. Recovery detection constants (§9) are frozen before evaluation.

## 9. Recovery & metrics

A Demand is **Recovered** when loss < 2% AND RTT ≤ 150% of `rtt_ref`, sustained for **3 consecutive Decision Intervals**.

An interval whose iperf sample has not been measured yet is marked invalid telemetry: it neither advances nor resets Recovery counters, contributes neutrally to reward, and counts as not-acceptable for Availability — never as 100% loss.

| Metric | Definition |
|---|---|
| Time-to-Recovery | seconds from Failure onset to Recovery (per Demand; episode-level max) |
| Availability | fraction of Decision Intervals in the episode where all Demands meet acceptable QoS |
| Cumulative reward | per episode, training-side only |
| Sample efficiency | metric vs. environment-steps curve |

Evaluation never reads training reward as "performance."

## 10. Flow programming

At episode start: baseline Active Path rules pre-installed. On reroute action (ADR 0007):
1. Push new path's rules via ODL RESTCONF at priority +10.
2. Verify the new rules are present on their switches (operational flow inventory, per-node).
3. Delete old path's rules.
Never delete-then-add. The adapter enforces ordering internally. If installing the new path fails, it rolls back the new rules and the action is penalized; if rollback also fails the environment terminates the episode as an unsafe controller state.

## 11. Training protocol

Two entry files, one shared env package (ADR 0005):
- `train_dqn.py` — DQN, MLP policy
- `train_ppo.py` — PPO, MLP policy

| Hyperparameter | DQN | PPO |
|---|---|---|
| Policy net | MLP [128, 128] | MLP [128, 128] |
| Learning rate | 3e-4 | 3e-4 |
| γ | 0.99 | 0.99 |
| Buffer / batch | 50k / 128 | — |
| ε schedule | 1.0 → 0.05 over 60% of budget | — |
| Rollout (n_steps) | — | 2048 |
| GAE λ / clip / epochs | — | 0.95 / 0.2 / 10 |
| Entropy coef | — | 0.01 |

**Budget & wall-clock arithmetic** (know this before committing):
- Wall-clock = total emulated time. 60 s/episode × Δ=1 s → 60 steps/episode.
- 100k steps = 1,667 episodes ≈ **28 h per run**.
- 2 algorithms × 5 seeds = 10 runs ≈ **280 h ≈ 12 days sequential** on one VM.
- Mitigations: start with 50k-step pilot runs to validate learning before committing; run overnight; only scale to 300–500k if curves demand it. Parallel Mininet+ODL instance pairs inside one VM is possible later but out of scope for v1.

Evaluation is not run inside training: it is a separate process (`scripts/run_eval.py`) executed after training, replaying the full frozen manifest with a deterministic policy. This avoids resetting the live training environment mid-run (which would desynchronize SB3's internal state).

## 12. Evaluation protocol (comparison chapter)

- **Held-out manifest** (`configs/eval_scenarios.json`), frozen before any eval run: 9 links × 4 onsets {12, 20, 30, 38} = 36 scenarios, none duplicated in training distribution (training onsets are random; the specific grid is fixed and declared).
- ≥5 seeds per algorithm (0–4), budget matched on environment steps.
- `run_eval.py` accepts one model path per seed and reports, per algorithm: per-seed summaries, mean ± std across seeds, and per-scenario aggregates — for time-to-Recovery, Availability, recovery rate, and cumulative reward. Sample-efficiency curves come from TensorBoard.
- Stats: per-metric two-sample comparison (e.g., Welch's t-test or Mann–Whitney U) across seeds — decide when writing the chapter.
- Tracking: TensorBoard from day one; adopt MLflow at M5 (comparison chapter) for run tables and the two policies as registered artifacts.

## 13. Project layout

```
test-sf-network/
├── CONTEXT.md
├── docs/
│   ├── PLAN.md                     ← this file
│   └── adr/0001…0007
├── configs/
│   ├── topology.yaml               ← §4 numbers live here
│   ├── training.yaml               ← §7, §8, §11 constants
│   └── eval_scenarios.json         ← frozen at M4
├── shn/
│   ├── __init__.py
│   ├── config.py                   ← schema-validating config loaders
│   ├── candidates.py               ← k-shortest + validation
│   ├── metrics.py                  ← Recovery detection, Availability, reward
│   └── env/
│       ├── __init__.py
│       ├── mininet_topo.py         ← topology + Mininet bootstrap
│       ├── odl_adapter.py          ← RESTCONF client (sole ODL surface)
│       ├── telemetry.py            ← continuous iperf/ping → state vector
│       ├── failure_injector.py
│       └── healing_env.py          ← Gymnasium env
├── scripts/
│   ├── setup_vm.sh
│   ├── freeze_eval_scenarios.py
│   └── run_eval.py
├── tests/
│   ├── test_candidates.py
│   ├── test_metrics.py
│   ├── test_config.py
│   ├── test_odl_adapter.py
│   └── test_telemetry.py
├── train_dqn.py
├── train_ppo.py
├── README.md
├── requirements.txt                ← pinned runtime deps
└── requirements-dev.txt            ← pinned test deps
```

## 14. VM setup (ordered)

1. Ubuntu 22.04 VM, 8 GB / 2 vCPU, VMware.
2. `sudo apt install mininet openvswitch-switch iperf3 openjdk-17-jdk python3.10-venv git`.
3. Download ODL Vanadium karaf (`ODL_VERSION=0.21.4`, confirm the Vanadium→karaf artifact mapping at M0); `feature:install odl-openflowplugin-flow-services odl-restconf`; verify `curl -u "admin:${ODL_PASSWORD}" http://localhost:8181/restconf/operational/network-topology:network-topology`.
4. Smoke test: Mininet `--controller=remote,ip=127.0.0.1` → topology appears in ODL.
4. Python venv; `pip install -r requirements.txt` (gymnasium, stable-baselines3, torch CPU, requests, networkx, pyyaml).
5. M0 gate (below) before any env code.

## 15. Risks

| Risk | Mitigation |
|---|---|
| ODL RESTCONF push latency > ~300 ms pollutes the Decision Interval | Measure at M0; if bad, batch pushes or reconsider pre-installed candidates (ADR 0007 alternative) |
| Flow-install verification JSON shape differs across ODL releases | `odl.verify_flows` is a config flag; confirm the operational `flow-node-inventory:table` shape at M0, or disable verification until fixed |
| Port-stat polling interval granularity | Verify ODL stats refresh rate at M0; calibrate Δ |
| Wall-clock budget blows the thesis timeline | §11 arithmetic is explicit; pilot at 50k first |
| Soft-reset state drift (stale flows, zombie iperf) | Hard rebuild every 50 episodes; assert flow-table state at reset |
| ODL JVM memory pressure alongside Mininet | 8 GB VM floor; monitor; bump to 12 GB if GC thrashes |
| Wrong Vanadium→karaf artifact version | `ODL_VERSION` is parameterized; M0 confirms the exact nexus artifact before training |

## 16. Milestones

- **M0 — Control plane hello world**: ODL sees the 6-switch topology; manually push one flow via RESTCONF; measure push latency and stats refresh rate. *Gate: numbers recorded here set final Δ.*
- **M1 — Data plane under control**: baseline Candidate Paths installed; iperf D1/D2 flow; telemetry produces the 41-dim vector; a manual RESTCONF reroute redirects traffic (verify via iperf receiver).
- **M2 — Env v1**: failure injection, reward, Recovery detection, soft/hard reset; random-agent smoke test recovers by chance within an episode.
- **M3 — Training smoke**: `train_dqn.py` + `train_ppo.py`, 50k-step pilot runs, TensorBoard curves show reward above random baseline.
- **M4 — Full runs**: freeze eval manifest; 5 seeds × 2 algorithms at agreed budget.
- **M5 — Comparison chapter**: metrics tables, plots, significance tests; MLflow adopted.
- **v2 (stretch)**: soft failures via netem, node-down scenarios, unseen-topology generalization.
