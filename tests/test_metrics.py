import pytest

from shn.metrics import (
    AvailabilityTracker,
    DemandQoS,
    RecoveryConfig,
    RecoveryTracker,
    compute_reward,
    meets_acceptable,
)


def test_recovery_requires_sustain():
    config = RecoveryConfig(0.02, 1.5, 3)
    tracker = RecoveryTracker(["d1"], config)
    good = DemandQoS(0.9, 0.01, 0.03)
    tracker.update("d1", good, 0.02)
    tracker.update("d1", good, 0.02)
    assert not tracker.is_recovered("d1")
    tracker.update("d1", good, 0.02)
    assert tracker.is_recovered("d1")


def test_recovery_resets_on_degradation():
    config = RecoveryConfig(0.02, 1.5, 3)
    tracker = RecoveryTracker(["d1"], config)
    good = DemandQoS(0.9, 0.01, 0.03)
    bad = DemandQoS(0.0, 1.0, 0.2)
    tracker.update("d1", good, 0.02)
    tracker.update("d1", bad, 0.02)
    tracker.update("d1", good, 0.02)
    tracker.update("d1", good, 0.02)
    assert not tracker.is_recovered("d1")
    tracker.update("d1", good, 0.02)
    assert tracker.is_recovered("d1")


def test_recovery_latches():
    config = RecoveryConfig(0.02, 1.5, 3)
    tracker = RecoveryTracker(["d1"], config)
    good = DemandQoS(0.9, 0.01, 0.03)
    for _ in range(3):
        tracker.update("d1", good, 0.02)
    tracker.update("d1", DemandQoS(0.0, 1.0, 0.2), 0.02)
    assert tracker.is_recovered("d1")


def test_meets_acceptable():
    config = RecoveryConfig(0.02, 1.5, 3)
    assert meets_acceptable(DemandQoS(0.9, 0.01, 0.02), 0.02, config)
    assert not meets_acceptable(DemandQoS(0.9, 0.05, 0.02), 0.02, config)
    assert not meets_acceptable(DemandQoS(0.9, 0.01, 0.04), 0.02, config)


def test_availability_tracker():
    tracker = AvailabilityTracker()
    tracker.update(True)
    tracker.update(False)
    tracker.update(True)
    assert tracker.availability == pytest.approx(2 / 3)
    assert AvailabilityTracker().availability == 0.0


def test_reward_failure_penalty():
    weights = {"w_throughput": 1.0, "w_rtt": 0.25, "w_loss": 2.0, "w_switch": 0.1, "w_fail": 1.0}
    qos = {"d1": DemandQoS(0.9, 0.01, 0.03)}
    base = compute_reward(qos, {"d1": 0.02}, False, weights)
    failed = compute_reward(qos, {"d1": 0.02}, False, weights, failed=True)
    assert failed == pytest.approx(base - 1.0)


def test_reward_switch_penalty():
    weights = {"w_throughput": 1.0, "w_rtt": 0.25, "w_loss": 2.0, "w_switch": 0.1, "w_fail": 1.0}
    qos = {"d1": DemandQoS(0.9, 0.01, 0.03)}
    base = compute_reward(qos, {"d1": 0.02}, False, weights)
    switched = compute_reward(qos, {"d1": 0.02}, True, weights)
    assert switched == pytest.approx(base - 0.1)


def test_invalid_qos_not_acceptable():
    config = RecoveryConfig(0.02, 1.5, 3)
    invalid = DemandQoS(0.0, 0.0, 0.02, valid=False)
    assert not meets_acceptable(invalid, 0.02, config)


def test_reward_invalid_telemetry_is_neutral():
    weights = {"w_throughput": 1.0, "w_rtt": 0.25, "w_loss": 2.0, "w_switch": 0.1, "w_fail": 1.0}
    invalid = DemandQoS(0.0, 0.0, 0.02, valid=False)
    reward = compute_reward({"d1": invalid}, {"d1": 0.02}, False, weights)
    assert reward == pytest.approx(0.0)


def test_recovery_ignores_invalid_telemetry():
    config = RecoveryConfig(0.02, 1.5, 3)
    tracker = RecoveryTracker(["d1"], config)
    good = DemandQoS(0.9, 0.01, 0.03)
    invalid = DemandQoS(0.0, 0.0, 0.02, valid=False)
    tracker.update("d1", invalid, 0.02)
    tracker.update("d1", good, 0.02)
    tracker.update("d1", good, 0.02)
    assert not tracker.is_recovered("d1")
    tracker.update("d1", good, 0.02)
    assert tracker.is_recovered("d1")
