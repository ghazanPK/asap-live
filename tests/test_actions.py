"""Regression tests for the action, emotion, gaze and screenplay-parsing modules."""
import json
import math
import sys
import types
from pathlib import Path

import pytest

from asap_multi import core
from asap_multi.core import ActionResolver, analyze_emotion, compile_timeline, extract_action, parse_screenplay

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = json.loads((ROOT / "examples/library.json").read_text(encoding="utf-8"))
START = {"WOLF": [180.0, 360.0], "RED": [700.0, 360.0]}


def resolve(text, context="RED", library=LIBRARY):
    return ActionResolver(library, {"backend": "tfidf"}).resolve(text, context, dict(START))


def compile_text(tmp_path, script, library=LIBRARY, name="scene.txt"):
    path = tmp_path / name
    path.write_text(script, encoding="utf-8")
    return compile_timeline(parse_screenplay(path), library)


@pytest.mark.parametrize("text", ["RED eats the sofa", "The lamp flickers", "Thunder rumbles outside", "RED sits on the lamp"])
def test_implausible_or_sourceless_actions_are_rejected(text):
    assert resolve(text)["accepted"] is False


def test_rejected_action_paragraph_emits_no_physical_action(tmp_path):
    data = compile_text(tmp_path, "CHARACTER: RED\nDIALOGUE: Hello.\nACTION: Thunder rumbles outside.\n")
    kinds = [(e["kind"], e["actor"]) for e in data["events"]]
    assert ("narration", None) in kinds
    assert not any(k in {"action", "move"} for k, _ in kinds)


def test_particle_after_object_selects_turn_on():
    result = resolve("WOLF turns the lamp on")
    assert result["accepted"] and result["combination"]["id"] == "turn_on_lamp" and result["subject"] == "WOLF"
    assert resolve("WOLF walks to the lamp and turns it off.")["combination"]["id"] == "turn_off_lamp"


def test_position_selects_combination_and_anchor():
    result = resolve("sits on the right side")
    assert result["accepted"] and result["combination"]["id"] == "sit_sofa_right"
    assert result["subject"] == "RED" and result["subject_source"] == "context"
    left = resolve("RED sits on the left side of the sofa.")
    assert left["combination"]["id"] == "sit_sofa_left"


def test_subject_is_case_sensitive_whole_word_proper_noun():
    assert extract_action("The red lamp glows near WOLF", LIBRARY["characters"], ["lamp"])["actor"] == "WOLF"
    assert extract_action("The red lamp glows", LIBRARY["characters"], ["lamp"])["actor"] is None
    assert extract_action("RED hands WOLF the basket", LIBRARY["characters"], [])["actor"] == "RED"
    assert extract_action("WOLF turns the lamp off", ["WOLF"], ["lamp"])["verb"] == "turn off"


def test_nearest_prop_instance_and_interaction_stand_point(tmp_path):
    wolf = compile_text(tmp_path, "ACTION: WOLF walks to the lamp and turns it on.\n")
    move = next(e for e in wolf["events"] if e["kind"] == "move")
    action = next(e for e in wolf["events"] if e["kind"] == "action")
    assert move["payload"]["target"] == "lamp_2"  # WOLF starts nearer the second lamp
    assert move["payload"]["anchor"] == LIBRARY["props"]["lamp_2"]["anchor"]
    assert move["payload"]["from"] == START["WOLF"]
    assert action["payload"]["interaction"] == LIBRARY["props"]["lamp_2"]["interaction"]
    assert action["payload"]["effect"] == {"prop": "lamp_2", "state": "on"}
    red = compile_text(tmp_path, "ACTION: RED turns the lamp off.\n")
    assert next(e for e in red["events"] if e["kind"] == "move")["payload"]["target"] == "lamp"


def test_sit_targets_seat_with_height_and_derived_anchor_without_offset(tmp_path):
    data = compile_text(tmp_path, "ACTION: RED sits on the left side of the sofa.\n")
    move = next(e for e in data["events"] if e["kind"] == "move")
    action = next(e for e in data["events"] if e["kind"] == "action")
    assert move["payload"]["anchor"] == LIBRARY["props"]["sofa"]["anchors"]["left"]
    assert action["payload"]["seat_height"] == 0.45 and action["payload"]["face"] is None
    assert move["duration"] == pytest.approx(max(0.6, math.dist(START["RED"], move["payload"]["anchor"]) / 140), abs=1e-3)
    point = core.stand_point({"x": 400, "y": 300, "size": [1.0, 1.0, 1.0]}, "right")
    assert point == [400 + 70 + 49, 300 + 70 + 49]


def test_actions_dictionary_is_the_single_source_of_truth():
    library = {**LIBRARY, "actions": [a for a in LIBRARY["actions"] if a["id"] != "turn_on_lamp"]}
    assert resolve("WOLF turns the lamp on", library=library)["accepted"] is False


def test_fdx_strips_extensions_and_joins_styled_runs(tmp_path):
    fdx = """<?xml version="1.0"?><FinalDraft><Content>
    <Paragraph Type="Character"><Text>WOLF (CONT'D)</Text></Paragraph>
    <Paragraph Type="Parenthetical"><Text>(sad</Text><Text Style="Italic">ly)</Text></Paragraph>
    <Paragraph Type="Dialogue"><Text>Hello </Text><Text Style="Bold">RED</Text><Text>.</Text></Paragraph>
    <Paragraph Type="Character"><Text>RED (V.O.)</Text></Paragraph>
    <Paragraph Type="Dialogue"><Text>Who is there?</Text></Paragraph>
    </Content></FinalDraft>"""
    data = compile_text(tmp_path, fdx, name="scene.fdx")
    speech = [e for e in data["events"] if e["kind"] == "speech"]
    assert [(e["actor"], e["payload"]["text"]) for e in speech] == [("WOLF", "Hello RED."), ("RED", "Who is there?")]
    emotion = next(e for e in data["events"] if e["kind"] == "emotion")
    assert emotion["actor"] == "WOLF" and emotion["payload"]["emotion"] == "sadness"
    assert speech[0]["payload"]["gaze"] == "RED"


def test_text_character_extension_is_stripped(tmp_path):
    data = compile_text(tmp_path, "CHARACTER: RED (O.S.)\nPARENTHETICAL: (furious)\nDIALOGUE: Out!\n")
    assert {e["actor"] for e in data["events"]} == {"RED"}


@pytest.mark.parametrize("text,name,level", [
    ("(angrily)", "anger", 2), ("(furious)", "anger", 3), ("(slightly annoyed)", "anger", 1),
    ("(disgusted)", "disgust", 2), ("(terrified)", "fear", 3), ("(very happy)", "joy", 3),
    ("(sadly)", "sadness", 2), ("(shocked)", "surprise", 3), ("(calmly)", "neutral", 1), ("(beat)", "neutral", 1),
])
def test_lexical_emotion_covers_seven_categories_and_three_levels(text, name, level):
    result = analyze_emotion(text)
    assert (result["emotion"], result["level"]) == (name, level)


def test_manual_emotion_override_from_tag_and_library(tmp_path):
    script = "CHARACTER: RED\nPARENTHETICAL: (sadly) [emotion: joy 1]\nDIALOGUE: I am fine. [emotion: sadness 3]\n"
    data = compile_text(tmp_path, script)
    emotions = [e["payload"] for e in data["events"] if e["kind"] == "emotion"]
    assert [(p["emotion"], p["level"], p["method"]) for p in emotions] == [("joy", 1, "manual"), ("sadness", 3, "manual")]
    assert next(e for e in data["events"] if e["kind"] == "speech")["payload"]["text"] == "I am fine."
    library = {**LIBRARY, "emotion_overrides": {"1": {"emotion": "surprise", "level": 2}}}
    first = next(e for e in compile_text(tmp_path, script, library)["events"] if e["kind"] == "emotion")
    assert (first["payload"]["emotion"], first["payload"]["level"]) == ("surprise", 2)
    with pytest.raises(ValueError):
        compile_text(tmp_path, "PARENTHETICAL: (x) [emotion: smug 2]\n")


def test_gaze_targets_named_listener_or_group_centroid(tmp_path):
    data = compile_text(tmp_path, "CHARACTER: WOLF\nDIALOGUE: The red lamp is broken.\nDIALOGUE: RED, come here.\n")
    speech = [e["payload"] for e in data["events"] if e["kind"] == "speech"]
    assert speech[0]["gaze"] == "group" and speech[0]["gaze_point"] == START["RED"]
    assert speech[1]["gaze"] == "RED" and speech[1]["gaze_point"] == START["RED"]


def test_language_directive_reaches_speech_events(tmp_path):
    data = compile_text(tmp_path, "LANGUAGE: ko\nCHARACTER: RED\nDIALOGUE: 주말에는 햇빛을 즐기며 산책할 수 있어요\nLANGUAGE: en\nDIALOGUE: Hello.\n")
    speech = [e for e in data["events"] if e["kind"] == "speech"]
    assert [e["payload"]["language"] for e in speech] == ["ko", "en"]
    assert speech[0]["duration"] > 2


def test_sentence_bert_models_are_loaded_once_across_compiles(tmp_path, monkeypatch):
    loads = []

    class FakeModel:
        def __init__(self, name, local_files_only=False):
            assert local_files_only is True
            loads.append(name)

        def encode(self, texts, normalize_embeddings=True):
            out = []
            for text in texts:
                vec = [0.0] * 64
                for stem in core._stems(text):
                    vec[sum(map(ord, stem)) % 64] += 1.0
                norm = math.sqrt(sum(v * v for v in vec)) or 1.0
                out.append([v / norm for v in vec])
            return out

    monkeypatch.setitem(sys.modules, "sentence_transformers", types.SimpleNamespace(SentenceTransformer=FakeModel))
    monkeypatch.setattr(core, "_MODEL_CACHE", {})
    monkeypatch.setattr(core, "_EMBED_CACHE", {})
    library = {**LIBRARY, "resolver": {"backend": "sentence-transformer", "emotion_model": "local/emotion", "action_model": "local/action"}}
    script = (ROOT / "examples/screenplay.txt").read_text(encoding="utf-8")
    for _ in range(2):
        data = compile_text(tmp_path, script, library)
    assert sorted(loads) == ["local/action", "local/emotion"]
    assert data["resolvers"] == {"action": "sentence-transformer-cache-only", "emotion": "sbert-keywords"}
    assert next(e for e in data["events"] if e["kind"] == "emotion")["payload"]["method"] == "sbert-keywords"
