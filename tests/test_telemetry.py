import pytest

from shn.env.telemetry import Telemetry


def test_parse_ping_success():
    output = (
        "4 packets transmitted, 4 received, 0% packet loss, time 603ms\n"
        "rtt min/avg/max/mdev = 1.0/2.0/3.0/0.5 ms"
    )
    loss, rtt = Telemetry._parse_ping(output, 0.2)
    assert loss == 0.0
    assert rtt == pytest.approx(0.002)


def test_parse_ping_total_loss():
    output = "4 packets transmitted, 0 received, 100% packet loss"
    loss, rtt = Telemetry._parse_ping(output, 0.2)
    assert loss == 1.0
    assert rtt == 0.2


def test_parse_ping_no_rtt_line():
    output = "4 packets transmitted, 4 received, 0% packet loss"
    loss, rtt = Telemetry._parse_ping(output, 0.2)
    assert loss == 0.0
    assert rtt == 0.2


def test_parse_iperf_interval_takes_last_line():
    output = (
        "[  5]   0.00-1.00   sec   596 KBytes  4.88 Mbits/sec   0.012 ms  0/416 (0%)\n"
        "[  5]   1.00-2.00   sec   610 KBytes  5.00 Mbits/sec   0.010 ms  42/426 (10%)"
    )
    delivered, loss = Telemetry._parse_iperf_interval(output)
    assert delivered == pytest.approx(1.0 - 42 / 426)
    assert loss == pytest.approx(42 / 426)


def test_parse_iperf_interval_total_loss():
    output = "[  5]   0.00-1.00   sec   0.00 Bytes  0.00 Mbits/sec   0.000 ms  426/426 (100%)"
    delivered, loss = Telemetry._parse_iperf_interval(output)
    assert delivered == pytest.approx(0.0)
    assert loss == pytest.approx(1.0)


def test_parse_iperf_interval_empty():
    assert Telemetry._parse_iperf_interval("") is None
    assert Telemetry._parse_iperf_interval("no interval lines here") is None
