import re
import subprocess
import time

import numpy as np

from shn.metrics import DemandQoS


class Telemetry:
    def __init__(self, network, topology: dict, training: dict, adapter, link_specs: list[tuple]) -> None:
        self.network = network
        self.demands = topology["demands"]
        self.training = training
        self.adapter = adapter
        self.link_specs = link_specs
        self.hosts = {host.name: host for host in network.hosts}
        self.previous_stats: dict | None = None

    def start_servers(self) -> None:
        for destination in {demand["dst"] for demand in self.demands}:
            host = self.hosts[destination]
            host.cmd("pkill -x iperf3 2>/dev/null; true")
            host.cmd("iperf3 -s -D")

    def start_clients(self, duration_s: float) -> None:
        self.stop_clients()
        interval = float(self.training["telemetry"].get("iperf_interval_s", 1.0))
        for demand in self.demands:
            source = self.hosts[demand["src"]]
            destination_ip = self.hosts[demand["dst"]].IP()
            command = (
                f"iperf3 -c {destination_ip} -u -b {demand['rate_mbps']}M "
                f"-t {int(duration_s)} -i {interval} "
                f"> /tmp/shn_{demand['id']}.log 2>&1 &"
            )
            source.cmd(command)

    def stop_clients(self) -> None:
        for demand in self.demands:
            source = self.hosts[demand["src"]]
            source.cmd("pkill -f 'iperf3 -c' 2>/dev/null; true")

    def set_baseline_stats(self, stats: dict) -> None:
        self.previous_stats = stats

    def sample(self, duration_s: float) -> tuple[np.ndarray, dict[str, DemandQoS]]:
        before = self.previous_stats or self.adapter.get_port_stats()
        started = time.monotonic()
        telemetry_config = self.training["telemetry"]
        ping_processes = []
        for demand in self.demands:
            source = self.hosts[demand["src"]]
            destination_ip = self.hosts[demand["dst"]].IP()
            ping = f"ping -c {int(telemetry_config['ping_count'])} -i {telemetry_config['ping_interval']} -W 1 {destination_ip}"
            ping_processes.append((demand, source.popen(ping, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)))

        ping_outputs: dict[str, str] = {}
        deadline = time.monotonic() + duration_s + float(telemetry_config.get("probe_grace_s", 5))
        for demand, process in ping_processes:
            try:
                process.wait(timeout=max(0.1, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            ping_outputs[demand["id"]] = process.stdout.read().decode("utf-8", "replace") if process.stdout else ""

        iperf_outputs: dict[str, str] = {}
        for demand in self.demands:
            source = self.hosts[demand["src"]]
            iperf_outputs[demand["id"]] = source.cmd(f"tail -n 5 /tmp/shn_{demand['id']}.log 2>/dev/null")

        after = self.adapter.get_port_stats()
        elapsed = max(time.monotonic() - started, duration_s)
        topology_links = self.adapter.get_topology_links()
        self.previous_stats = after
        return self._link_features(before, after, topology_links, elapsed), self._demand_qos(ping_outputs, iperf_outputs)

    def _link_features(self, before: dict, after: dict, topology_links: set, elapsed: float) -> np.ndarray:
        features = np.zeros(3 * len(self.link_specs), dtype=np.float32)
        for index, (node_a, port_a, node_b, port_b, bandwidth) in enumerate(self.link_specs):
            up = float(frozenset((node_a, node_b)) in topology_links)
            previous_a = before.get((node_a, port_a), {})
            previous_b = before.get((node_b, port_b), {})
            current_a = after.get((node_a, port_a), {})
            current_b = after.get((node_b, port_b), {})
            byte_delta = max(0, current_a.get("bytes", 0) - previous_a.get("bytes", 0)) + max(0, current_b.get("bytes", 0) - previous_b.get("bytes", 0))
            packet_delta = max(0, current_a.get("packets", 0) - previous_a.get("packets", 0)) + max(0, current_b.get("packets", 0) - previous_b.get("packets", 0))
            drop_delta = max(0, current_a.get("drops", 0) - previous_a.get("drops", 0)) + max(0, current_b.get("drops", 0) - previous_b.get("drops", 0))
            utilization = min(1.0, (byte_delta / 2) * 8 / max(1.0, elapsed * bandwidth * 1_000_000))
            loss = min(1.0, drop_delta / packet_delta) if packet_delta else 0.0
            features[index * 3:index * 3 + 3] = (up, utilization, loss)
        return features

    def _demand_qos(self, ping_outputs: dict[str, str], iperf_outputs: dict[str, str]) -> dict[str, DemandQoS]:
        result = {}
        cap = float(self.training["telemetry"]["rtt_cap_s"])
        for demand in self.demands:
            ping_loss, rtt_s = self._parse_ping(ping_outputs.get(demand["id"], ""), cap)
            iperf = self._parse_iperf_interval(iperf_outputs.get(demand["id"], ""))
            if iperf is None:
                delivered_ratio, loss = 0.0, 1.0
            else:
                delivered_ratio, loss = iperf
            result[demand["id"]] = DemandQoS(delivered_ratio, max(loss, ping_loss), rtt_s)
        return result

    @staticmethod
    def _parse_ping(output: str, cap: float) -> tuple[float, float]:
        loss_match = re.search(r"(\d+(?:\.\d+)?)% packet loss", output)
        rtt_match = re.search(r"= [\d.]+/([\d.]+)/", output)
        loss = float(loss_match.group(1)) / 100 if loss_match else 1.0
        rtt = float(rtt_match.group(1)) / 1000 if rtt_match else cap
        return min(1.0, loss), min(cap, rtt)

    @staticmethod
    def _parse_iperf_interval(output: str) -> tuple[float, float] | None:
        matches = re.findall(r"(\d+)/(\d+)\s+\(([\d.]+)%\)", output)
        if not matches:
            return None
        lost, total, _percent = matches[-1]
        total_int = int(total)
        if total_int == 0:
            return None
        loss = int(lost) / total_int
        return max(0.0, 1.0 - loss), min(1.0, loss)
