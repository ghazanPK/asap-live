"""Run the included screenplay through the real compiler and renderer."""
import json
from pathlib import Path

from asap_multi.core import compile_timeline, parse_screenplay, render_outputs

ROOT = Path(__file__).parents[1]
OUT = ROOT / "outputs" / "smoke"
library = json.loads((ROOT / "examples" / "library.json").read_text(encoding="utf-8"))
timeline = compile_timeline(parse_screenplay(ROOT / "examples" / "screenplay.txt"), library)
render_outputs(timeline, OUT)
expected = {"timeline.json", "storyboard.html", "live.html"}
missing = expected.difference(path.name for path in OUT.iterdir())
if missing:
    raise RuntimeError(f"missing outputs: {sorted(missing)}")
print(json.dumps({"schema": timeline["schema"], "events": len(timeline["events"]), "duration_seconds": timeline["duration"], "outputs": sorted(expected)}, indent=2))
