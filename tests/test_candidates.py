import pytest

from shn.candidates import action_space_size, compute_candidates, decode_action


TOPOLOGY = {
    "switches": ["s1", "s2", "s3", "s4"],
    "hosts": [
        {"name": "h1", "switch": "s1"},
        {"name": "h2", "switch": "s4"},
    ],
    "links": [
        {"a": "s1", "b": "s2", "bw_mbps": 10, "delay_ms": 2},
        {"a": "s2", "b": "s4", "bw_mbps": 10, "delay_ms": 2},
        {"a": "s1", "b": "s3", "bw_mbps": 10, "delay_ms": 5},
        {"a": "s3", "b": "s4", "bw_mbps": 10, "delay_ms": 5},
        {"a": "s2", "b": "s3", "bw_mbps": 10, "delay_ms": 2},
    ],
    "demands": [{"id": "d1", "src": "h1", "dst": "h2", "rate_mbps": 5, "initial_path": 0}],
}


def test_compute_candidates_shape():
    candidates = compute_candidates(TOPOLOGY, 3)
    assert len(candidates) == 1
    assert len(candidates[0]) == 3
    assert candidates[0][0].switches[0] == "s1"
    assert candidates[0][0].switches[-1] == "s4"


def test_compute_candidates_orders_by_delay():
    candidates = compute_candidates(TOPOLOGY, 2)
    assert candidates[0][0].delay_ms <= candidates[0][1].delay_ms


def test_decode_action():
    assert decode_action(0, 2, 4) is None
    assert decode_action(1, 2, 4) == (0, 0)
    assert decode_action(4, 2, 4) == (0, 3)
    assert decode_action(5, 2, 4) == (1, 0)
    with pytest.raises(ValueError):
        decode_action(9, 2, 4)


def test_action_space_size():
    assert action_space_size(2, 4) == 9
    assert action_space_size(1, 4) == 5
