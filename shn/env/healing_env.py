import os
import time

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from shn.candidates import CandidatePath, decode_action
from shn.env.failure_injector import FailureInjector
from shn.env.mininet_topo import build_network
from shn.env.odl_adapter import FlowRule, ODLAdapter, ODLRequestError, ODLUnsafeStateError
from shn.env.telemetry import Telemetry
from shn.metrics import (
    AvailabilityTracker,
    DemandQoS,
    RecoveryConfig,
    RecoveryTracker,
    compute_reward,
    meets_acceptable,
)


def _flow_body(flow_id: str, priority: int, source_mac: str, destination_mac: str, output_port: int) -> dict:
    return {
        "flow": {
            "id": flow_id,
            "table_id": 0,
            "priority": priority,
            "idle-timeout": 0,
            "hard-timeout": 0,
            "match": {
                "ethernet-match": {
                    "ethernet-source": {"address": source_mac},
                    "ethernet-destination": {"address": destination_mac},
                }
            },
            "instructions": {
                "instruction": [
                    {
                        "order": 0,
                        "apply-actions": {
                            "action": [
                                {
                                    "order": 0,
                                    "output-action": {
                                        "output-node-connector": str(output_port),
                                        "max-length": 65535,
                                    },
                                }
                            ]
                        },
                    }
                ]
            },
        }
    }


class HealingEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self, topology: dict, training: dict, candidates: list[list[CandidatePath]], seed: int | None = None) -> None:
        self.topology = topology
        self.training = training
        self.candidates = candidates
        self.demands = topology["demands"]
        self.k = int(training["candidates"]["k"])
        self.n_demands = len(self.demands)
        self.n_links = len(topology["links"])
        self.delta_s = float(training["episode"]["decision_interval_s"])
        self.episode_steps = int(float(training["episode"]["length_s"]) / self.delta_s)
        self.recovery_config = RecoveryConfig(
            loss_threshold=float(training["recovery"]["loss_threshold"]),
            rtt_factor=float(training["recovery"]["rtt_factor"]),
            sustain_intervals=int(training["recovery"]["sustain_intervals"]),
        )
        self.odl_config = training["odl"]
        self.verify_flows = bool(self.odl_config.get("verify_flows", True))
        self.flow_verify_timeout_s = float(self.odl_config.get("flow_verify_timeout_s", 5))
        password = os.environ.get(self.odl_config["password_env"])
        if not password:
            raise RuntimeError(
                f"missing controller credential: set {self.odl_config['password_env']} in the environment"
            )
        self._password = password
        self.action_space = spaces.Discrete(self.n_demands * self.k + 1)
        self.observation_space = spaces.Box(
            low=0.0,
            high=1.0,
            shape=(self.n_links * 3 + self.n_demands * 7,),
            dtype=np.float32,
        )
        self.rng = np.random.default_rng(seed)
        self.episode_count = 0
        self.network = None
        self.adapter = None
        self.telemetry = None
        self.injector = None
        self.dpid_map: dict[str, str] = {}
        self.mac_map: dict[str, str] = {}
        self.link_specs: list[tuple] = []
        self.current_paths: list[CandidatePath] = []
        self.scenario: dict = {}
        self.scenario_disrupts = False
        self.step_index = 0
        self.failure_injected = False
        self.failure_time_s: float | None = None
        self.recovery_time_s: float | None = None
        self.unsafe_state = False
        self.rtt_refs: dict[str, float] = {}
        self.rtt_samples: dict[str, list[float]] = {}
        self.recovery_tracker = RecoveryTracker([], self.recovery_config)
        self.availability_tracker = AvailabilityTracker()

    def _build_network(self) -> None:
        self.network = build_network(self.topology)
        self.dpid_map = {
            switch: f"openflow:{int(self.network.get(switch).dpid, 16)}"
            for switch in self.topology["switches"]
        }
        self.mac_map = {
            host["name"]: self.network.get(host["name"]).MAC()
            for host in self.topology["hosts"]
        }
        self.adapter = ODLAdapter(
            self.odl_config["base_url"],
            self.odl_config["username"],
            self._password,
            float(self.odl_config["timeout_s"]),
            int(self.odl_config["retries"]),
        )
        self.link_specs = []
        for link in self.topology["links"]:
            port_a, port_b = self.network.topo.port(link["a"], link["b"])
            self.link_specs.append(
                (
                    self.dpid_map[link["a"]],
                    port_a,
                    self.dpid_map[link["b"]],
                    port_b,
                    float(link["bw_mbps"]),
                )
            )
        self.telemetry = Telemetry(self.network, self.topology, self.training, self.adapter, self.link_specs)
        self.telemetry.start_servers()
        self.injector = FailureInjector(self.network)
        self._wait_for_topology()

    def _wait_for_topology(self, timeout_s: float = 60.0) -> None:
        expected = {
            frozenset((self.dpid_map[link["a"]], self.dpid_map[link["b"]]))
            for link in self.topology["links"]
        }
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if expected.issubset(self.adapter.get_topology_links()):
                return
            time.sleep(2.0)
        discovered = len(expected.intersection(self.adapter.get_topology_links()))
        raise RuntimeError(f"OpenDaylight discovered {discovered}/{len(expected)} expected links")

    def _reset_flows(self) -> None:
        all_rules = []
        for demand_index, demand in enumerate(self.demands):
            for path in self.candidates[demand_index]:
                all_rules.extend(self._path_rules(demand, path, 0))
        self.adapter.delete_rules(all_rules)
        for demand_index, demand in enumerate(self.demands):
            path = self.candidates[demand_index][int(demand["initial_path"])]
            rules = self._path_rules(
                demand,
                path,
                int(self.odl_config["flow_priority_baseline"]),
            )
            self.adapter.install_rules(rules, [], self.verify_flows, self.flow_verify_timeout_s)

    def _path_rules(self, demand: dict, path: CandidatePath, priority: int) -> list[FlowRule]:
        source_mac = self.mac_map[demand["src"]]
        destination_mac = self.mac_map[demand["dst"]]
        rules: list[FlowRule] = []
        switches = path.switches
        for index, switch in enumerate(switches):
            next_hop = switches[index + 1] if index + 1 < len(switches) else demand["dst"]
            output_port = self.network.topo.port(switch, next_hop)[0]
            node = self.dpid_map[switch]
            rules.append(
                FlowRule(
                    node,
                    f"{demand['id']}-p{path.index}-f",
                    _flow_body(
                        f"{demand['id']}-p{path.index}-f",
                        priority,
                        source_mac,
                        destination_mac,
                        output_port,
                    ),
                )
            )
        for index in reversed(range(len(switches))):
            switch = switches[index]
            next_hop = switches[index - 1] if index > 0 else demand["src"]
            output_port = self.network.topo.port(switch, next_hop)[0]
            node = self.dpid_map[switch]
            rules.append(
                FlowRule(
                    node,
                    f"{demand['id']}-p{path.index}-r",
                    _flow_body(
                        f"{demand['id']}-p{path.index}-r",
                        priority,
                        destination_mac,
                        source_mac,
                        output_port,
                    ),
                )
            )
        return rules

    def _install_path(self, demand_index: int, path_index: int) -> None:
        demand = self.demands[demand_index]
        old_path = self.current_paths[demand_index]
        new_path = self.candidates[demand_index][path_index]
        priority = int(self.odl_config["flow_priority_reroute"])
        self.adapter.install_rules(
            self._path_rules(demand, new_path, priority),
            self._path_rules(demand, old_path, priority),
            self.verify_flows,
            self.flow_verify_timeout_s,
        )
        self.current_paths[demand_index] = new_path

    def _link_disrupts(self, link: tuple[str, str]) -> bool:
        a, b = link
        return any((a, b) in path.links or (b, a) in path.links for path in self.current_paths)

    def _sample_scenario(self) -> dict:
        initial_links = {
            link
            for demand_index, demand in enumerate(self.demands)
            for link in self.candidates[demand_index][int(demand["initial_path"])].links
        }
        link = FailureInjector.choose_link(initial_links, self.rng)
        episode = self.training["episode"]
        onset = self.rng.uniform(float(episode["failure_onset_min_s"]), float(episode["failure_onset_max_s"]))
        return {"link": link, "onset_s": float(onset)}

    def _build_observation(self, link_features: np.ndarray, qos: dict[str, DemandQoS]) -> np.ndarray:
        values = [*link_features.tolist()]
        cap = float(self.training["telemetry"]["rtt_cap_s"])
        for index, demand in enumerate(self.demands):
            demand_qos = qos[demand["id"]]
            path_index = self.current_paths[index].index
            values.extend(
                [
                    min(1.0, demand_qos.rtt_s / cap),
                    demand_qos.loss,
                    demand_qos.delivered_ratio,
                    *[float(path_index == candidate) for candidate in range(self.k)],
                ]
            )
        return np.asarray(values, dtype=np.float32)

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)
        if seed is not None:
            self.rng = np.random.default_rng(seed)
        if self.network is None:
            self._build_network()
        elif self.episode_count > 0 and self.episode_count % int(self.training["episode"]["hard_rebuild_every"]) == 0:
            self.telemetry.stop_clients()
            self.network.stop()
            self.network = None
            self._build_network()
        self.episode_count += 1
        self.injector.restore()
        self._wait_for_topology()
        self._reset_flows()
        self.current_paths = [
            self.candidates[index][int(demand["initial_path"])]
            for index, demand in enumerate(self.demands)
        ]
        self.telemetry.start_clients(self.episode_steps * self.delta_s + 5.0)
        self.telemetry.set_baseline_stats(self.adapter.get_port_stats())
        if options and "scenario" in options:
            scenario = options["scenario"]
            self.scenario = {"link": tuple(scenario["link"]), "onset_s": float(scenario["onset_s"])}
        else:
            self.scenario = self._sample_scenario()
        self.step_index = 0
        self.failure_injected = False
        self.failure_time_s = None
        self.recovery_time_s = None
        self.scenario_disrupts = False
        self.unsafe_state = False
        default_rtt = float(self.training["telemetry"]["rtt_ref_default_s"])
        self.rtt_refs = {demand["id"]: default_rtt for demand in self.demands}
        self.rtt_samples = {demand["id"]: [] for demand in self.demands}
        self.recovery_tracker = RecoveryTracker([demand["id"] for demand in self.demands], self.recovery_config)
        self.availability_tracker = AvailabilityTracker()
        link_features, qos = self.telemetry.sample(self.delta_s)
        return self._build_observation(link_features, qos), {"scenario": self.scenario}

    def step(self, action: int):
        elapsed_s = self.step_index * self.delta_s
        if not self.failure_injected and elapsed_s >= self.scenario["onset_s"]:
            self.injector.inject(self.scenario["link"])
            self.failure_injected = True
            self.failure_time_s = self.scenario["onset_s"]
            self.scenario_disrupts = self._link_disrupts(self.scenario["link"])
            if not self.scenario_disrupts:
                self.recovery_time_s = 0.0
        selected = decode_action(int(action), self.n_demands, self.k)
        changed = False
        action_failed = False
        if selected is not None:
            demand_index, path_index = selected
            if path_index != self.current_paths[demand_index].index:
                try:
                    self._install_path(demand_index, path_index)
                    changed = True
                except ODLUnsafeStateError:
                    action_failed = True
                    self.unsafe_state = True
                except ODLRequestError:
                    action_failed = True
        link_features, qos = self.telemetry.sample(self.delta_s)
        if not self.failure_injected and self.step_index < int(self.training["episode"]["ref_intervals"]):
            for demand in self.demands:
                self.rtt_samples[demand["id"]].append(qos[demand["id"]].rtt_s)
                self.rtt_refs[demand["id"]] = float(np.mean(self.rtt_samples[demand["id"]]))
        reward = compute_reward(qos, self.rtt_refs, changed, self.training["reward"], failed=action_failed)
        if self.failure_injected and self.scenario_disrupts:
            for demand in self.demands:
                self.recovery_tracker.update(demand["id"], qos[demand["id"]], self.rtt_refs[demand["id"]])
        acceptable = all(
            meets_acceptable(qos[demand["id"]], self.rtt_refs[demand["id"]], self.recovery_config)
            for demand in self.demands
        )
        self.availability_tracker.update(acceptable)
        if self.recovery_time_s is None and self.failure_injected and self.scenario_disrupts and self.recovery_tracker.all_recovered:
            self.recovery_time_s = (self.step_index + 1) * self.delta_s - float(self.failure_time_s)
        self.step_index += 1
        truncated = self.step_index >= self.episode_steps
        recovered = self.failure_injected and (not self.scenario_disrupts or self.recovery_tracker.all_recovered)
        info = {
            "scenario": self.scenario,
            "changed": changed,
            "action_failed": action_failed,
            "unsafe_state": self.unsafe_state,
            "qos": {key: value.__dict__ for key, value in qos.items()},
            "recovered": recovered,
            "recovery_time_s": self.recovery_time_s,
            "availability": self.availability_tracker.availability,
        }
        return self._build_observation(link_features, qos), reward, self.unsafe_state, truncated, info

    def close(self) -> None:
        if self.network is not None:
            self.telemetry.stop_clients()
            self.injector.restore()
            self.network.stop()
            self.network = None
