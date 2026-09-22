import yaml
import pytest

from shn.config import load_topology, load_training


def test_load_default_configs():
    topology = load_topology()
    training = load_training()
    assert len(topology["links"]) == 9
    assert len(topology["demands"]) == 2
    assert training["candidates"]["k"] == 4
    assert training["reward"]["w_fail"] == 1.0


def test_topology_validation_rejects_unknown_switch(tmp_path):
    data = {
        "switches": ["s1", "s2"],
        "hosts": [{"name": "h1", "switch": "s1"}],
        "links": [{"a": "s1", "b": "s99", "bw_mbps": 10, "delay_ms": 2}],
        "demands": [{"id": "d1", "src": "h1", "dst": "h1", "rate_mbps": 5, "initial_path": 0}],
    }
    path = tmp_path / "topology.yaml"
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError):
        load_topology(path)


def test_training_validation_rejects_missing_section(tmp_path):
    data = {"candidates": {"k": 4}}
    path = tmp_path / "training.yaml"
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError):
        load_training(path)


def test_training_validation_rejects_bad_loss_threshold(tmp_path):
    training = load_training()
    training["recovery"]["loss_threshold"] = 5.0
    path = tmp_path / "training.yaml"
    path.write_text(yaml.safe_dump(training))
    with pytest.raises(ValueError):
        load_training(path)
