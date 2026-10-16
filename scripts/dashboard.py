"""Phone-friendly read-only dashboard for Self-Healing Network runs.

Serves a single HTML page that reads, with no external dependencies:
  - results/*/summary.json       (one per training run)
  - results/eval_comparison.json (DQN vs PPO comparison, optional)
  - configs/topology.yaml        (the emulated topology)
  - docs/PLAN.md                 (milestones, shown as plain text)

It never imports mininet, gymnasium, or stable-baselines3, so it runs on any
host that can read the repo directory -- including a laptop or the BB host.

Usage:
    python scripts/dashboard.py --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def collect_runs() -> list[dict]:
    runs = []
    results_dir = ROOT / "results"
    if not results_dir.is_dir():
        return runs
    for summary_path in sorted(results_dir.glob("*/summary.json")):
        summary = _read_json(summary_path)
        if summary is None:
            continue
        runs.append(
            {
                "name": summary_path.parent.name,
                "algorithm": summary.get("algorithm"),
                "seed": summary.get("seed"),
                "steps": summary.get("steps"),
                "wall_seconds": summary.get("wall_seconds"),
                "model_present": (summary_path.parent / "model.zip").exists(),
            }
        )
    return runs


def collect_eval() -> dict | None:
    return _read_json(ROOT / "results" / "eval_comparison.json")


def collect_topology() -> dict | None:
    try:
        import yaml  # type: ignore
    except ImportError:
        return None
    try:
        return yaml.safe_load((ROOT / "configs" / "topology.yaml").read_text(encoding="utf-8"))
    except (OSError, Exception):  # noqa: BLE001 - yaml errors are not worth surfacing
        return None


def collect_plan() -> str:
    try:
        return (ROOT / "docs" / "PLAN.md").read_text(encoding="utf-8")
    except OSError:
        return ""


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#0b1020">
<title>Self-Healing Network</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 16px 14px 48px;
    font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #0b1020; color: #e7ecff;
    -webkit-text-size-adjust: 100%;
  }
  h1 { font-size: 20px; margin: 4px 0 2px; }
  .sub { color: #8ea0c8; font-size: 13px; margin-bottom: 16px; }
  .card {
    background: #141b31; border: 1px solid #23304f; border-radius: 14px;
    padding: 14px; margin: 0 0 14px;
  }
  .card h2 { font-size: 14px; margin: 0 0 10px; text-transform: uppercase; letter-spacing: .06em; color: #9fb4e8; }
  .empty { color: #7f8db0; font-size: 14px; }
  table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
  th, td { text-align: left; padding: 7px 6px; border-bottom: 1px solid #1e2942; font-size: 13px; }
  th { color: #8ea0c8; font-weight: 600; }
  tr:last-child td { border-bottom: none; }
  .pill {
    display: inline-block; padding: 2px 9px; border-radius: 999px;
    font-size: 12px; font-weight: 700;
  }
  .dqn { background: #173a5e; color: #7fc4ff; }
  .ppo { background: #3a2a5e; color: #c4a3ff; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .metric { background: #0f1628; border: 1px solid #1e2942; border-radius: 10px; padding: 10px; }
  .metric .k { font-size: 11px; color: #8ea0c8; text-transform: uppercase; letter-spacing: .05em; }
  .metric .v { font-size: 20px; font-weight: 700; margin-top: 3px; }
  .bar { height: 6px; background: #1e2942; border-radius: 4px; overflow: hidden; margin-top: 6px; }
  .bar > i { display: block; height: 100%; background: linear-gradient(90deg,#2f7dff,#7fc4ff); }
  pre { white-space: pre-wrap; word-break: break-word; font-size: 12px; color: #b9c6e6; margin: 0; max-height: 260px; overflow: auto; }
  details summary { cursor: pointer; color: #9fb4e8; font-size: 13px; }
  .links a { display: block; color: #7fc4ff; text-decoration: none; padding: 9px 0; border-bottom: 1px solid #1e2942; font-size: 14px; }
  .links a:last-child { border-bottom: none; }
</style>
</head>
<body>
  <h1>Self-Healing Network</h1>
  <div class="sub">RL agent rerouting Traffic Demands over SDN &middot; read-only view</div>

  <div class="card">
    <h2>Training runs</h2>
    <div id="runs"></div>
  </div>

  <div class="card">
    <h2>DQN vs PPO</h2>
    <div id="eval"></div>
  </div>

  <div class="card">
    <h2>Topology</h2>
    <div id="topo"></div>
  </div>

  <div class="card">
    <h2>Plan &amp; milestones</h2>
    <details><summary>Show docs/PLAN.md</summary><pre id="plan"></pre></details>
  </div>

  <script>
  const DATA = __DATA__;

  const fmt = (n, d=1) => (n === null || n === undefined) ? "–" : Number(n).toFixed(d);
  const pct = (n) => (n === null || n === undefined) ? "–" : (100*Number(n)).toFixed(1) + "%";
  const hrs = (s) => (s === null || s === undefined) ? "–" : (Number(s)/3600).toFixed(1) + " h";

  function renderRuns(runs) {
    const el = document.getElementById("runs");
    if (!runs.length) {
      el.innerHTML = '<div class="empty">No runs yet. Artifacts appear under <code>results/&lt;name&gt;/summary.json</code>.</div>';
      return;
    }
    let html = '<table><tr><th>Run</th><th>Algo</th><th>Steps</th><th>Wall</th></tr>';
    for (const r of runs) {
      const cls = (r.algorithm === "dqn") ? "dqn" : "ppo";
      html += `<tr><td>${r.name}</td>` +
              `<td><span class="pill ${cls}">${(r.algorithm||"?").toUpperCase()}</span></td>` +
              `<td>${(r.steps??"–").toLocaleString()}</td>` +
              `<td>${hrs(r.wall_seconds)}</td></tr>`;
    }
    el.innerHTML = html + "</table>";
  }

  function metricCard(k, v, sub) {
    return `<div class="metric"><div class="k">${k}</div><div class="v">${v}</div>` +
           (sub === undefined ? "" : sub) + `</div>`;
  }

  function renderAlgo(name, block) {
    const a = block && block.across_seeds ? block.across_seeds : {};
    const rec = a.recovery_rate, av = a.availability_mean, ttr = a.ttr_mean, rw = a.reward_mean;
    let html = `<div style="margin-bottom:8px"><span class="pill ${name}">${name.toUpperCase()}</span></div><div class="grid">`;
    html += metricCard("Recovery rate", pct(rec && rec.mean),
      `<div class="bar"><i style="width:${rec&&rec.mean?100*rec.mean:0}%"></i></div>`);
    html += metricCard("Availability", pct(av && av.mean),
      `<div class="bar"><i style="width:${av&&av.mean?100*av.mean:0}%"></i></div>`);
    html += metricCard("Time-to-recovery", ttr && ttr.mean!=null ? fmt(ttr.mean,2)+" s" : "–");
    html += metricCard("Mean reward", rw ? fmt(rw.mean,2) : "–");
    html += "</div>";
    const seeds = (block && block.seeds) || [];
    if (seeds.length) {
      html += '<details style="margin-top:10px"><summary>' + seeds.length + ' seed(s)</summary>' +
        '<table><tr><th>Seed file</th><th>Rec.</th><th>Avail.</th></tr>';
      for (const s of seeds) {
        html += `<tr><td>${s.path.split(/[\\\\/]/).pop()}</td><td>${pct(s.recovery_rate)}</td><td>${pct(s.availability_mean)}</td></tr>`;
      }
      html += "</table></details>";
    }
    return html;
  }

  function renderEval(ev) {
    const el = document.getElementById("eval");
    if (!ev || (!ev.dqn && !ev.ppo)) {
      el.innerHTML = '<div class="empty">No comparison yet. Run <code>scripts/run_eval.py</code> to produce <code>results/eval_comparison.json</code>.</div>';
      return;
    }
    el.innerHTML = renderAlgo("dqn", ev.dqn) + '<div style="height:14px"></div>' + renderAlgo("ppo", ev.ppo);
  }

  function renderTopo(topo) {
    const el = document.getElementById("topo");
    if (!topo) {
      el.innerHTML = '<div class="empty">configs/topology.yaml not readable here (needs PyYAML).</div>';
      return;
    }
    let html = `<table><tr><th>Link</th><th>BW</th><th>Delay</th></tr>`;
    for (const l of (topo.links||[])) {
      html += `<tr><td>${l.a} – ${l.b}</td><td>${l.bw_mbps} Mbps</td><td>${l.delay_ms} ms</td></tr>`;
    }
    html += "</table>";
    html += `<div class="sub" style="margin:10px 0 0">Switches: ${(topo.switches||[]).join(", ")}<br>Hosts: ` +
            (topo.hosts||[]).map(h=>`${h.name}@${h.switch}`).join(", ") + "</div>";
    const d = (topo.demands||[]).map(x=>`${x.id}: ${x.src}→${x.dst} @ ${x.rate_mbps} Mbps`).join("<br>");
    html += `<div class="sub">Demands:<br>${d}</div>`;
    el.innerHTML = html;
  }

  renderRuns(DATA.runs || []);
  renderEval(DATA.eval);
  renderTopo(DATA.topology);
  document.getElementById("plan").textContent = DATA.plan || "(PLAN.md not found)";
  </script>
</body>
</html>
"""


def build_page() -> bytes:
    data = {
        "runs": collect_runs(),
        "eval": collect_eval(),
        "topology": collect_topology(),
        "plan": collect_plan(),
    }
    payload = json.dumps(data, separators=(",", ":"))
    return PAGE.replace("__DATA__", payload).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - http.server API
        if self.path in ("/", "/index.html"):
            body = build_page()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.rstrip("/") == "/health":
            body = b"ok"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, *args) -> None:  # quiet by default
        pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"dashboard on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
