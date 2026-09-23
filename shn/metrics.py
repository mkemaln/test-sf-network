from dataclasses import dataclass


@dataclass(frozen=True)
class DemandQoS:
    delivered_ratio: float
    loss: float
    rtt_s: float
    valid: bool = True


@dataclass(frozen=True)
class RecoveryConfig:
    loss_threshold: float
    rtt_factor: float
    sustain_intervals: int


def meets_acceptable(qos: DemandQoS, rtt_ref_s: float, config: RecoveryConfig) -> bool:
    if not qos.valid:
        return False
    return qos.loss < config.loss_threshold and qos.rtt_s <= config.rtt_factor * rtt_ref_s


class RecoveryTracker:
    def __init__(self, demand_ids: list[str], config: RecoveryConfig) -> None:
        self.config = config
        self.consecutive = {demand_id: 0 for demand_id in demand_ids}
        self.recovered = {demand_id: False for demand_id in demand_ids}

    def update(self, demand_id: str, qos: DemandQoS, rtt_ref_s: float) -> None:
        if self.recovered[demand_id]:
            return
        if not qos.valid:
            return
        if meets_acceptable(qos, rtt_ref_s, self.config):
            self.consecutive[demand_id] += 1
        else:
            self.consecutive[demand_id] = 0
        if self.consecutive[demand_id] >= self.config.sustain_intervals:
            self.recovered[demand_id] = True

    def is_recovered(self, demand_id: str) -> bool:
        return self.recovered[demand_id]

    @property
    def all_recovered(self) -> bool:
        return all(self.recovered.values())


class AvailabilityTracker:
    def __init__(self) -> None:
        self.good_intervals = 0
        self.total_intervals = 0

    def update(self, acceptable: bool) -> None:
        self.total_intervals += 1
        self.good_intervals += int(acceptable)

    @property
    def availability(self) -> float:
        if self.total_intervals == 0:
            return 0.0
        return self.good_intervals / self.total_intervals


def compute_reward(
    qos_by_demand: dict[str, DemandQoS],
    rtt_refs: dict[str, float],
    changed: bool,
    weights: dict,
    failed: bool = False,
) -> float:
    reward = 0.0
    for demand_id, qos in qos_by_demand.items():
        if qos.valid:
            reward += weights["w_throughput"] * qos.delivered_ratio
            reward -= weights["w_loss"] * qos.loss
        reward += weights["w_rtt"] * max(0.0, 1.0 - qos.rtt_s / max(rtt_refs[demand_id], 1e-9))
    if changed:
        reward -= weights["w_switch"]
    if failed:
        reward -= weights.get("w_fail", 0.0)
    return float(reward)
