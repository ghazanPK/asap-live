"""ASAP Live: wild-pose matching with multilingual support (owner lineage)."""
import json
import re
import sys
from pathlib import Path

from scripts.demo import compile_request, example

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "beat_deps"))


def test_live_server_and_browser_use_multilingual_gesture_route():
    assert re.findall(r"serve_beat\(self,ROOT,'(\w+)'\)", (ROOT / "scripts/demo.py").read_text(encoding="utf-8")) == ["multilingual"] * 2
    assert "live:'multilingual'" in (ROOT / "static/demo.js").read_text(encoding="utf-8")


def test_korean_example_lines_carry_language_and_explicit_translations():
    from multilingual_gesture.pipeline import require_english

    bundled = example("ko")
    timeline = compile_request({"script": bundled["script"], "format": "txt", "library": bundled["library"]})
    speech = [e["payload"] for e in timeline["events"] if e["kind"] == "speech"]
    translations = json.loads((ROOT / "examples/beat-translations.json").read_text(encoding="utf-8"))
    assert speech and all(p["language"] == "ko" for p in speech)
    english = [require_english(p["text"], p["language"], translations) for p in speech]
    assert english == ["RED, you should not be here tonight.", "I only came to bring this basket."]
    assert {"move", "action", "emotion"} <= {e["kind"] for e in timeline["events"]}
