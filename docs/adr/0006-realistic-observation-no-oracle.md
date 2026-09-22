---
status: accepted
---

# Observation from realistic sensing, no oracle failure flag

The Agent's observation contains only signals a real SDN deployment could produce: per-link up/down status and QoS counters from the Controller, plus end-to-end RTT/loss/throughput measured per Traffic Demand. There is no "a Failure is happening now" oracle bit.

## Considered Options

- **Oracle in-failure flag in the state**: easier learning (detection is trivialized), rejected — it is not deployable knowledge, and it would force a full state-representation change and retrain once soft failures (v2) make detection the actual challenge.

## Consequences

- Detection must be inferred from counters/RTT degradations; with v1 hard failures the link-up/down signal is strong, so learning remains tractable.
- Any future oracle experiments are additive features, not a redesign.
