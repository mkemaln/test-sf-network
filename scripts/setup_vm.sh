#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────────────────────
# Self-Healing Network — VM provisioning script
# Target: Ubuntu 22.04 LTS Server, 4 GB RAM
# ─────────────────────────────────────────────────────────────────────────

ODL_VERSION="${ODL_VERSION:-0.24.0}"
ODL_PASSWORD="${ODL_PASSWORD:-admin}"

echo "========================================"
echo "  Self-Healing Network — VM setup"
echo "  ODL ${ODL_VERSION}  |  $(date)"
echo "========================================"

# ── 1. System packages ───────────────────────────────────────────────────
echo ""
echo "[1/5] Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y \
  mininet openvswitch-switch openvswitch-common \
  iperf3 openjdk-17-jdk curl git ca-certificates \
  python3-venv python3-pip
sudo systemctl enable --now openvswitch-switch

# ── 2. OpenDaylight — download and start ─────────────────────────────────
echo ""
echo "[2/5] Downloading OpenDaylight ${ODL_VERSION}..."
# curl -fkL -o odl-karaf.tar.gz \
#   "https://nexus.opendaylight.org/content/repositories/opendaylight.release/org/opendaylight/integration/karaf/${ODL_VERSION}/karaf-${ODL_VERSION}.tar.gz"
curl -fkL -o odl-karaf.tar.gz \
  "https://nexus.opendaylight.org/content/repositories/opendaylight.release/org/opendaylight/integration/karaf/0.24.0/karaf-0.24.0.tar.gz"
mkdir -p odl
tar -xzf odl-karaf.tar.gz -C odl --strip-components=1
./odl/bin/start

# ── 3. Wait for ODL RESTCONF, then install features ──────────────────────
echo ""
echo "[3/5] Waiting for ODL RESTCONF..."

wait_for_odl() {
  local deadline=$((SECONDS + 180))
  local code
  while true; do
    code=$(curl -s -u "admin:${ODL_PASSWORD}" -o /dev/null -w "%{http_code}" \
      "http://localhost:8181/restconf/operational/network-topology:network-topology" || true)
    if [ "$code" = "200" ]; then
      return 0
    fi
    if [ $SECONDS -ge $deadline ]; then
      echo "  ODL RESTCONF not ready after 180s (status: ${code})."
      echo "  Last 40 karaf.log lines:"
      tail -n 40 odl/data/log/karaf.log 2>/dev/null || echo "  (no karaf.log)"
      return 1
    fi
    sleep 5
  done
}

wait_for_odl
echo "  ODL RESTCONF is up."

echo "  Installing OpenFlow + RESTCONF features..."
./odl/bin/client -u karaf "feature:install odl-openflowplugin-flow-services odl-restconf"
wait_for_odl

# ── 4. Python venv + dependencies ────────────────────────────────────────
echo ""
echo "[4/5] Creating Python venv and installing dependencies..."
python3 -m venv --system-site-packages .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -r requirements-dev.txt

# ── 5. Freeze eval manifest + final smoke test ───────────────────────────
echo ""
echo "[5/5] Freezing eval scenarios and running smoke test..."
.venv/bin/python scripts/freeze_eval_scenarios.py

curl -s -u "admin:${ODL_PASSWORD}" -o /dev/null -w "ODL RESTCONF status: %{http_code}\n" \
  http://localhost:8181/restconf/operational/network-topology:network-topology

# ── Summary ──────────────────────────────────────────────────────────────
echo ""
echo "========================================"
echo "  Setup complete!"
echo "========================================"
echo ""
echo "  ODL:     http://localhost:8181/restconf  (admin:${ODL_PASSWORD})"
echo "  Venv:    .venv/bin/python"
echo "  Tests:   .venv/bin/python -m pytest tests -q"
echo "  Train:   .venv/bin/python train_dqn.py --seed 0 --steps 50000"
echo ""
echo "  Next: complete M0 — verify ODL sees the 6-switch topology."
