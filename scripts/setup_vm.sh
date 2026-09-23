#!/usr/bin/env bash
set -euo pipefail

sudo apt-get update
sudo apt-get install -y mininet openvswitch-switch openvswitch-common iperf3 openjdk-17-jdk curl python3.12-venv python3-pip git
sudo systemctl enable --now openvswitch-switch

ODL_VERSION="${ODL_VERSION:-0.21.4}"
ODL_PASSWORD="${ODL_PASSWORD:-admin}"
curl -fL -o odl-karaf.tar.gz "https://nexus.opendaylight.org/content/repositories/opendaylight.release/org/opendaylight/integration/karaf/${ODL_VERSION}/karaf-${ODL_VERSION}.tar.gz"
mkdir -p odl
tar -xzf odl-karaf.tar.gz -C odl --strip-components=1
./odl/bin/start

wait_for_odl() {
  local deadline=$((SECONDS + 180))
  local code
  while true; do
    code=$(curl -s -u "admin:${ODL_PASSWORD}" -o /dev/null -w "%{http_code}" "http://localhost:8181/restconf/operational/network-topology:network-topology" || true)
    if [ "$code" = "200" ]; then
      return 0
    fi
    if [ $SECONDS -ge $deadline ]; then
      echo "OpenDaylight RESTCONF still not ready after 180s (last status: ${code}). Last 40 log lines:"
      tail -n 40 odl/data/log/karaf.log 2>/dev/null || echo "(no karaf.log found)"
      return 1
    fi
    sleep 5
  done
}

wait_for_odl

./odl/bin/client -u karaf "feature:install odl-openflowplugin-flow-services odl-restconf"
wait_for_odl

python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python scripts/freeze_eval_scenarios.py

curl -s -u "admin:${ODL_PASSWORD}" -o /dev/null -w "ODL RESTCONF status: %{http_code}\n" http://localhost:8181/restconf/operational/network-topology:network-topology
