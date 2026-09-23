import time
from dataclasses import dataclass

import requests


class ODLRequestError(RuntimeError):
    pass


class ODLUnsafeStateError(ODLRequestError):
    pass


TRANSIENT_STATUS = {408, 429, 500, 502, 503, 504}


@dataclass(frozen=True)
class FlowRule:
    node: str
    flow_id: str
    body: dict


class ODLAdapter:
    def __init__(self, base_url: str, username: str, password: str, timeout_s: float, retries: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.retries = retries
        self.session = requests.Session()
        self.session.auth = (username, password)
        self.headers = {"Accept": "application/json", "Content-Type": "application/json"}

    def _request(self, method: str, path: str, body: dict | None = None) -> requests.Response:
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                response = self.session.request(
                    method,
                    f"{self.base_url}{path}",
                    json=body,
                    headers=self.headers,
                    timeout=self.timeout_s,
                )
            except requests.RequestException as error:
                last_error = error
                time.sleep(0.5 * (2**attempt))
                continue
            if response.status_code in {200, 201, 202, 204}:
                return response
            if method == "DELETE" and response.status_code == 404:
                return response
            if response.status_code in TRANSIENT_STATUS:
                last_error = ODLRequestError(f"{method} {path} returned {response.status_code}")
                time.sleep(0.5 * (2**attempt))
                continue
            raise ODLRequestError(f"{method} {path} returned {response.status_code}: {response.text[:300]}")
        raise ODLRequestError(f"{method} {path} failed after retries: {last_error}")

    def get_topology_links(self) -> set[frozenset[str]]:
        response = self._request(
            "GET",
            "/restconf/operational/network-topology:network-topology/topology/flow:1",
        )
        data = response.json()
        links: set[frozenset[str]] = set()
        for topology in data.get("network-topology", {}).get("topology", []):
            for link in topology.get("link", []):
                source = link.get("source", {}).get("source-node")
                destination = link.get("destination", link.get("dest", {})).get("dest-node")
                if source and destination and source.startswith("openflow:") and destination.startswith("openflow:"):
                    links.add(frozenset((source, destination)))
        return links

    def get_port_stats(self) -> dict[tuple[str, int], dict[str, int]]:
        response = self._request("GET", "/restconf/operational/opendaylight-inventory:nodes")
        data = response.json()
        result: dict[tuple[str, int], dict[str, int]] = {}
        for node in data.get("nodes", {}).get("node", []):
            node_id = node["id"]
            for connector in node.get("node-connector", []):
                raw = connector.get("opendaylight-port-statistics:flow-capable-node-connector-statistics")
                if raw is None:
                    continue
                port = int(connector["id"].rsplit(":", 1)[-1])
                result[(node_id, port)] = {
                    "bytes": int(raw.get("bytes", {}).get("transmission", 0)) + int(raw.get("bytes", {}).get("receive", 0)),
                    "drops": int(raw.get("drop", {}).get("in", 0)) + int(raw.get("drop", {}).get("out", 0)),
                    "packets": int(raw.get("packets", {}).get("transmission", 0)) + int(raw.get("packets", {}).get("receive", 0)),
                }
        return result

    def get_installed_flow_ids(self, node: str) -> set[str]:
        response = self._request(
            "GET",
            f"/restconf/operational/opendaylight-inventory:nodes/node/{node}/flow-node-inventory:table/0",
        )
        data = response.json()
        return self._extract_flow_ids(data)

    @staticmethod
    def _extract_flow_ids(data: dict) -> set[str]:
        ids: set[str] = set()
        for table in data.get("flow-node-inventory:table", []):
            for flow in table.get("flow", []):
                if isinstance(flow, dict) and flow.get("id"):
                    ids.add(flow["id"])
        return ids

    def install_rules(self, new_rules: list[FlowRule], old_rules: list[FlowRule], verify: bool, timeout_s: float) -> None:
        installed: list[FlowRule] = []
        try:
            for rule in new_rules:
                path = f"/restconf/config/opendaylight-inventory:nodes/node/{rule.node}/flow-node-capability:table/0/flow/{rule.flow_id}"
                self._request("PUT", path, rule.body)
                installed.append(rule)
            if verify:
                self._verify_installed(new_rules, timeout_s)
        except Exception as original_error:
            try:
                self.delete_rules(installed)
            except Exception as rollback_error:
                raise ODLUnsafeStateError(
                    f"flow installation failed ({original_error}); rollback failed ({rollback_error})"
                ) from original_error
            raise
        self.delete_rules(old_rules)

    def _verify_installed(self, rules: list[FlowRule], timeout_s: float) -> None:
        expected_by_node: dict[str, set[str]] = {}
        for rule in rules:
            expected_by_node.setdefault(rule.node, set()).add(rule.flow_id)
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if all(
                expected_ids.issubset(self.get_installed_flow_ids(node))
                for node, expected_ids in expected_by_node.items()
            ):
                return
            time.sleep(0.5)
        raise ODLRequestError("flow installation verification timed out")

    def delete_rules(self, rules: list[FlowRule]) -> None:
        for rule in rules:
            path = f"/restconf/config/opendaylight-inventory:nodes/node/{rule.node}/flow-node-capability:table/0/flow/{rule.flow_id}"
            self._request("DELETE", path)
