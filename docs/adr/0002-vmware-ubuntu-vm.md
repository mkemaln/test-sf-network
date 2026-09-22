---
status: accepted
---

# All-in-one Ubuntu VM on VMware

The dev machine is Windows; Mininet, Open vSwitch and OpenDaylight require Linux. We run everything (Mininet, ODL, Python env, SB3 training) inside a single Ubuntu 22.04 LTS VM on VMware Workstation.

## Considered Options

- **WSL2**: lighter and integrates with Windows files; rejected — user prefers a full VM, and a VM gives whole-environment snapshots for reproducibility.
- **Split (VM for network, training on Windows host)**: rejected — an RPC hop per `step()` adds latency and flakiness to millions of steps.

## Consequences

- VM snapshots become the reproducible environment artifact; pin them per experiment phase.
- ODL wants ~4 GB heap: allocate ≥8 GB RAM and ≥2 vCPUs to the VM.
- Code lives in the VM (shared-folder performance is poor for training loops).
