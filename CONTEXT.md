# Self-Healing Network

Context for an RL agent that detects failing links/nodes in an emulated on-premises network and reroutes traffic onto backup paths, controlling the network through an SDN controller.

## Language

**Self-Healing**:
The network's ability to detect a Failure and restore its Traffic Demands onto alternate paths without human intervention.
_Avoid_: auto-remediation, auto-failover (failover = the traditional protocol mechanism, not this)

**QoS**:
The measurable service metrics per link or path: latency, jitter, packet loss, throughput, utilization.
_Avoid_: network health (vague)

**Failure**:
An event that removes or degrades a network element. Hard failure: a link or node goes fully down. Soft failure: the element stays up with degraded QoS (added delay or loss).
_Avoid_: outage (that is the consequence on a Demand, not the event)

**Traffic Demand**:
A host-to-host traffic requirement with source, destination, and rate that the network must serve.
_Avoid_: flow (collides with OpenFlow flow rule), session, connection

**Path**:
An ordered sequence of links serving a Traffic Demand.
_Avoid_: route (protocol-table concept)

**Active Path**:
The Path currently assigned to a Traffic Demand.

**Backup Path**:
A Path other than the Active Path that can take over a Traffic Demand's traffic after a Failure.
_Avoid_: secondary path

**Candidate Path**:
A Path precomputed from the topology that the Agent may select as the Active Path for a Traffic Demand.
_Avoid_: alternative path

**Recovery**:
The state where a Traffic Demand disrupted by a Failure is again served with acceptable QoS on a Backup Path, sustained across consecutive Decision Intervals.
_Avoid_: convergence (IGP terminology)

**Decision Interval**:
The fixed wall-clock period between Agent decisions; the telemetry window and reward accounting unit.
_Avoid_: tick

**Availability**:
The fraction of an episode's Decision Intervals in which all Traffic Demands meet the acceptable-QoS definition.
_Avoid_: uptime

**Agent**:
The trained RL policy that observes network state and chooses reroute actions.
_Avoid_: controller (that is OpenDaylight's role), model (ambiguous)

**Emulated Network**:
The Mininet topology of OpenFlow switches and hosts that forms the training and test environment.
_Avoid_: simulation (Mininet emulates real packet forwarding; it does not simulate it)

**Controller**:
OpenDaylight, the SDN controller that programs the Emulated Network and exposes topology and telemetry to the Agent.
