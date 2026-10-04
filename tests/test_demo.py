import json
from pathlib import Path

import pytest

from scripts.demo import compile_request


ROOT = Path(__file__).resolve().parents[1]
LIBRARY = json.loads((ROOT / "examples/library.json").read_text(encoding="utf-8"))


def test_text_request_compiles_script_to_grounded_timeline():
    script = (ROOT / "examples/screenplay.txt").read_text(encoding="utf-8")
    result = compile_request({"script": script, "format": "txt", "library": LIBRARY})
    assert result["schema"] == "paperreach.asap.timeline.v1"
    assert result["duration"] > 0
    assert {"scene", "move", "action", "speech", "gesture", "emotion"}.issubset({e["kind"] for e in result["events"]})
    assert any(e["kind"] == "move" and e["payload"]["target"] == "lamp" for e in result["events"])
    assert any(e["kind"] == "speech" and e["payload"]["gaze"] == "RED" for e in result["events"])


def test_fdx_request_uses_paragraph_types_and_speaker():
    script = """<?xml version="1.0"?><FinalDraft><Content>
    <Paragraph Type="Scene Heading"><Text>INT. ROOM - DAY</Text></Paragraph>
    <Paragraph Type="Character"><Text>WOLF</Text></Paragraph>
    <Paragraph Type="Dialogue"><Text>Hello RED.</Text></Paragraph>
    <Paragraph Type="Action"><Text>WOLF walks to the lamp.</Text></Paragraph>
    </Content></FinalDraft>"""
    result = compile_request({"script": script, "format": "fdx", "library": LIBRARY})
    speech = next(e for e in result["events"] if e["kind"] == "speech")
    assert speech["actor"] == "WOLF" and speech["payload"]["text"] == "Hello RED."
    assert any(e["kind"] == "move" and e["payload"]["target"] == "lamp" for e in result["events"])


@pytest.mark.parametrize("payload", [
    [],
    {"script": "", "library": LIBRARY},
    {"script": "ACTION: walks", "format": "pdf", "library": LIBRARY},
    {"script": "ACTION: walks", "library": {"characters": []}},
    {"script": "unlabeled paragraph", "library": LIBRARY},
])
def test_invalid_requests_fail_before_timeline_output(payload):
    with pytest.raises(ValueError):
        compile_request(payload)
