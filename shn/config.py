from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "configs"


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"configuration must be a mapping: {path}")
    return data


def _require_top(data: dict[str, Any], keys: set[str]) -> None:
    missing = keys - data.keys()
    if missing:
        raise ValueError(f"configuration missing keys: {sorted(missing)}")


def _require_section(data: dict[str, Any], section: str, keys: set[str]) -> None:
    missing = keys - data.get(section, {}).keys()
    if missing:
        raise ValueError(f"configuration section '{section}' missing keys: {sorted(missing)}")


def load_topology(path: str | Path | None = None) -> dict[str, Any]:
    data = _load_yaml(Path(path) if path else CONFIG_DIR / "topology.yaml")
    _require_top(data, {"switches", "hosts", "links", "demands"})
    switches = set(data["switches"])
    hosts = {host["name"]: host for host in data["hosts"]}
    for link in data["links"]:
        if link["a"] not in switches or link["b"] not in switches:
            raise ValueError(f"link references unknown switch: {link}")
        if float(link["bw_mbps"]) <= 0 or float(link["delay_ms"]) < 0:
            raise ValueError(f"link QoS values must be valid: {link}")
    for host in data["hosts"]:
        if host["switch"] not in switches:
            raise ValueError(f"host references unknown switch: {host}")
    for demand in data["demands"]:
        if demand["src"] not in hosts or demand["dst"] not in hosts:
            raise ValueError(f"demand references unknown host: {demand}")
        if float(demand["rate_mbps"]) <= 0:
            raise ValueError(f"demand rate must be positive: {demand}")
    return data


def load_training(path: str | Path | None = None) -> dict[str, Any]:
    data = _load_yaml(Path(path) if path else CONFIG_DIR / "training.yaml")
    _require_top(data, {"candidates", "episode", "recovery", "reward", "telemetry", "odl", "eval", "dqn", "ppo"})
    _require_section(data, "candidates", {"k"})
    _require_section(data, "episode", {"length_s", "decision_interval_s", "failure_onset_min_s", "failure_onset_max_s", "ref_intervals", "hard_rebuild_every"})
    _require_section(data, "recovery", {"loss_threshold", "rtt_factor", "sustain_intervals"})
    _require_section(data, "reward", {"w_throughput", "w_rtt", "w_loss", "w_switch", "w_fail"})
    _require_section(data, "telemetry", {"ping_count", "ping_interval", "iperf_interval_s", "rtt_cap_s", "rtt_ref_default_s"})
    _require_section(data, "odl", {"base_url", "username", "password_env", "timeout_s", "retries", "flow_priority_baseline", "flow_priority_reroute"})
    _require_section(data, "eval", {"manifest"})
    if int(data["candidates"]["k"]) < 1:
        raise ValueError("candidate path count must be positive")
    if float(data["episode"]["decision_interval_s"]) <= 0:
        raise ValueError("decision interval must be positive")
    if int(float(data["episode"]["length_s"]) / float(data["episode"]["decision_interval_s"])) < 1:
        raise ValueError("episode must contain at least one decision interval")
    if not 0 < float(data["recovery"]["loss_threshold"]) <= 1:
        raise ValueError("loss threshold must be in (0, 1]")
    return data
