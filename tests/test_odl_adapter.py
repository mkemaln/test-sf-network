import pytest

from shn.env.odl_adapter import FlowRule, ODLAdapter, ODLRequestError


class FakeResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


def make_adapter(retries=3):
    return ODLAdapter("http://127.0.0.1:8181", "admin", "admin", 5.0, retries)


def test_request_retries_transient_then_succeeds(monkeypatch):
    adapter = make_adapter()
    calls = []

    def fake_request(method, url, json=None, headers=None, timeout=None):
        calls.append(method)
        if len(calls) < 3:
            return FakeResponse(503)
        return FakeResponse(200)

    monkeypatch.setattr(adapter.session, "request", fake_request)
    response = adapter._request("GET", "/x")
    assert response.status_code == 200
    assert len(calls) == 3


def test_request_does_not_retry_client_error(monkeypatch):
    adapter = make_adapter()
    calls = []

    def fake_request(method, url, json=None, headers=None, timeout=None):
        calls.append(method)
        return FakeResponse(400, text="bad request")

    monkeypatch.setattr(adapter.session, "request", fake_request)
    with pytest.raises(ODLRequestError):
        adapter._request("PUT", "/x", {})
    assert len(calls) == 1


def test_delete_404_is_success(monkeypatch):
    adapter = make_adapter()
    monkeypatch.setattr(adapter.session, "request", lambda *args, **kwargs: FakeResponse(404))
    response = adapter._request("DELETE", "/x")
    assert response.status_code == 404


def test_install_rules_adds_then_deletes(monkeypatch):
    adapter = make_adapter()
    sequence = []

    def fake_request(method, path, body=None):
        sequence.append((method, path.split("/flow/")[-1]))
        return FakeResponse(200)

    monkeypatch.setattr(adapter, "_request", fake_request)
    new = [FlowRule("openflow:1", "a", {}), FlowRule("openflow:1", "b", {})]
    old = [FlowRule("openflow:1", "old", {})]
    adapter.install_rules(new, old, verify=False, timeout_s=1.0)
    assert sequence == [("PUT", "a"), ("PUT", "b"), ("DELETE", "old")]


def test_install_rules_rolls_back_on_failure(monkeypatch):
    adapter = make_adapter()
    sequence = []

    def fake_request(method, path, body=None):
        flow_id = path.split("/flow/")[-1]
        if flow_id == "b":
            raise ODLRequestError("boom")
        sequence.append((method, flow_id))
        return FakeResponse(200)

    monkeypatch.setattr(adapter, "_request", fake_request)
    new = [FlowRule("openflow:1", "a", {}), FlowRule("openflow:1", "b", {})]
    old = [FlowRule("openflow:1", "old", {})]
    with pytest.raises(ODLRequestError):
        adapter.install_rules(new, old, verify=False, timeout_s=1.0)
    assert sequence == [("PUT", "a"), ("DELETE", "a")]


def test_get_topology_links_filters_hosts(monkeypatch):
    adapter = make_adapter()
    payload = {
        "network-topology": {
            "topology": [
                {
                    "link": [
                        {"source": {"source-node": "openflow:1"}, "destination": {"dest-node": "openflow:2"}},
                        {"source": {"source-node": "openflow:1"}, "destination": {"dest-node": "host:xx"}},
                    ]
                }
            ]
        }
    }
    monkeypatch.setattr(adapter, "_request", lambda *a, **k: FakeResponse(200, payload))
    assert adapter.get_topology_links() == {frozenset({"openflow:1", "openflow:2"})}


def test_get_port_stats(monkeypatch):
    adapter = make_adapter()
    payload = {
        "nodes": {
            "node": [
                {
                    "id": "openflow:1",
                    "node-connector": [
                        {
                            "id": "openflow:1:2",
                            "opendaylight-port-statistics:flow-capable-node-connector-statistics": {
                                "bytes": {"transmission": 100, "receive": 50},
                                "drop": {"in": 1, "out": 2},
                                "packets": {"transmission": 10, "receive": 5},
                            },
                        }
                    ],
                }
            ]
        }
    }
    monkeypatch.setattr(adapter, "_request", lambda *a, **k: FakeResponse(200, payload))
    assert adapter.get_port_stats()[("openflow:1", 2)] == {"bytes": 150, "drops": 3, "packets": 15}


def test_extract_flow_ids():
    data = {"flow-node-inventory:table": [{"flow": [{"id": "a"}, {"id": "b"}]}]}
    assert ODLAdapter._extract_flow_ids(data) == {"a", "b"}
