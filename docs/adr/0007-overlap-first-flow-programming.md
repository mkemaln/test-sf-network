---
status: accepted
---

# Overlap-first flow programming on reroute

When the Agent reroutes a Traffic Demand onto a Candidate Path, the Controller first installs the new path's rules at higher priority, then deletes the old path's rules. The old and new rules briefly overlap; there is never a blackhole window.

## Considered Options

- **Delete-then-add**: rejected — guarantees a transient blackhole on every reroute, which the QoS telemetry would punish and the availability metric would record.
- **Pre-install all Candidate Paths and switch by priority flip**: rejected for v1 — wastes flow-table space and complicates accounting; revisit if RESTCONF push latency proves harmful.

## Consequences

- Reroute correctness is order-dependent (add-before-delete); the adapter must enforce ordering, not the caller.
- Brief duplicate forwarding during the overlap is acceptable at these traffic rates.
