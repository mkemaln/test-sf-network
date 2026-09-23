#!/usr/bin/env bash
set -euo pipefail

sudo apt-get update
sudo apt-get install -y mininet openvswitch-switch openvswitch-common iperf3 openjdk-17-jdk curl python3.12-venv python3-pip git
sudo systemctl enable --now openvswitch-switch

ODL_VERSION="${ODL_VERSION:-0.21.4}"
curl -fL -o odl-karaf.tar.gz "https://nexus.opendaylight.org/content/repositories/opendaylight.release/org/opendaylight/integration/karaf/${ODL_VERSION}/karaf-${ODL_VERSION}.tar.gz"
mkdir -p odl
tar -xzf odl-karaf.tar.gz -C odl --strip-components=1
./odl/bin/start
sleep 30
./odl/bin/client -u karaf "feature:install odl-openflowplugin-flow-services odl-restconf"

python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python scripts/freeze_eval_scenarios.py

curl -s -u "admin:${ODL_PASSWORD:-admin}" -o /dev/null -w "ODL RESTCONF status: %{http_code}\n" http://localhost:8181/restconf/operational/network-topology:network-topology
