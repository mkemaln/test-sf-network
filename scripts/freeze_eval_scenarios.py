import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shn.config import CONFIG_DIR, load_topology


def main():
    topology = load_topology()
    links = [[link["a"], link["b"]] for link in topology["links"]]
    onsets = [12, 20, 30, 38]
    scenarios = [{"link": link, "onset_s": onset} for link in links for onset in onsets]
    (CONFIG_DIR / "eval_scenarios.json").write_text(json.dumps(scenarios, indent=2))
    print(f"froze {len(scenarios)} scenarios to {CONFIG_DIR / 'eval_scenarios.json'}")


if __name__ == "__main__":
    main()
