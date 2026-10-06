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
    path = move["payload"]["path"]
    assert path[0] == START["RED"] and path[-1] == LIBRARY["props"]["sofa"]["anchors"]["left"]
    assert move["duration"] == pytest.approx(max(0.6, core.path_length(path) / 140), abs=1e-3)
    point = core.stand_point({"x": 400, "y": 300, "size": [1.0, 1.0, 1.0]}, "right")
    assert point == [400 + 70 + 49, 300 + 70 + 49]


def _blocked_legs(path, props):
    boxes = core.obstacle_boxes(props)
    return [i for i, (a, b) in enumerate(zip(path, path[1:])) if any(core._segment_hits(a, b, box) for box in boxes)]


def test_walk_path_goes_around_props_instead_of_through_them(tmp_path):
    # RED's straight line to the left seat crosses the sofa; the planned path walks around it.
    sofa = LIBRARY["props"]["sofa"]
    assert core._segment_hits(START["RED"], sofa["anchors"]["left"], core.obstacle_boxes({"sofa": sofa})[0])
    data = compile_text(tmp_path, "ACTION: RED opens the curtains.\nACTION: RED sits on the left side of the sofa.\n")
    moves = [e["payload"] for e in data["events"] if e["kind"] == "move"]
    assert [m["planner"] for m in moves] == ["grid-astar-octile"] * 2
    to_window, to_seat = moves[0]["path"], moves[1]["path"]
    assert _blocked_legs(to_window, LIBRARY["props"]) == []
    # Only the final step into the seat may overlap the sofa footprint.
    assert _blocked_legs(to_seat, LIBRARY["props"]) == [len(to_seat) - 2]
    assert to_seat[-2][1] > sofa["y"] + sofa["size"][2] / 2 * 140  # entered from the front
    assert core.path_length(to_seat) > math.dist(to_seat[0], to_seat[-1])


def test_starter_scene_drives_prop_effects_and_path_following_previz(tmp_path):
    data = compile_timeline(parse_screenplay(ROOT / "examples/screenplay.txt"), LIBRARY)
    effects = [e["payload"]["effect"] for e in data["events"] if e["kind"] == "action" and "effect" in e["payload"]]
    assert effects == [{"prop": "lamp_2", "state": "off"}, {"prop": "window", "state": "open"}, {"prop": "tv", "state": "on"}]
    assert all(e["payload"]["path"][0] == e["payload"]["from"] for e in data["events"] if e["kind"] == "move")
    core.render_outputs(data, tmp_path)
    pages = [p for p in tmp_path.glob("*.html") if p.name != "storyboard.html"]  # previz, immersive or live page
    assert pages and all("mv.payload.path" in p.read_text(encoding="utf-8") for p in pages)


def test_astar_open_floor_is_straight_and_no_corner_cutting():
    assert core.plan_path([100, 100], [400, 300], {}) == ([[100.0, 100.0], [400.0, 300.0]], "grid-astar-octile")
    # Two boxes touching at a corner leave only a diagonal grid gap between two
    # blocked orthogonal cells; the planner must walk around instead of squeezing through.
    props = {"a": {"x": 300, "y": 200, "size": [1.0, 0.65, 1.0]}, "b": {"x": 440, "y": 340, "size": [1.0, 0.65, 1.0]}}
    start, goal = [300.0, 330.0], [440.0, 200.0]
    boxes = core.obstacle_boxes(props, 0.0)
    assert any(core._segment_hits(start, goal, box) for box in boxes)
    path, planner = core.plan_path(start, goal, props, radius=0.0)
    assert planner == "grid-astar-octile" and path[0] == start and path[-1] == goal
    assert not any(core._segment_hits(a, b, box) for a, b in zip(path, path[1:]) for box in boxes)
    assert core.path_length(path) > 2 * math.dist(start, goal)
    # A walled-in goal has no path: the move falls back to a straight line and says so.
    cage = {f"w{i}": {"x": x, "y": y, "size": [s, 1, t]} for i, (x, y, s, t) in enumerate(
        [(480, 200, 3, .2), (480, 400, 3, .2), (300, 300, .2, 3), (660, 300, .2, 3)])}
    assert core.plan_path([60, 60], [480, 300], cage) == ([[60.0, 60.0], [480.0, 300.0]], "straight-fallback")



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


def test_semantic_mode_defaults_to_the_downloaded_minilm(tmp_path, monkeypatch):
    """Owner decision 2026-10-06: with no model folder named, actions and emotions use models/all-MiniLM-L6-v2."""
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

    for name in core.SBERT_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(core, "REPO_ROOT", tmp_path)
    assert core.resolve_sentence_model(None) is None  # nothing downloaded yet: lexical matching
    (tmp_path / "models" / core.SBERT_NAME).mkdir(parents=True)
    minilm = str(tmp_path / "models" / core.SBERT_NAME)
    assert core.resolve_sentence_model("") == core.resolve_sentence_model("auto") == minilm
    monkeypatch.setenv("SBERT_MODEL", "/elsewhere/model")
    assert core.resolve_sentence_model(None) == "/elsewhere/model" and core.resolve_sentence_model("local/x") == "local/x"
    monkeypatch.delenv("SBERT_MODEL")
    monkeypatch.setitem(sys.modules, "sentence_transformers", types.SimpleNamespace(SentenceTransformer=FakeModel))
    monkeypatch.setattr(core, "_MODEL_CACHE", {})
    monkeypatch.setattr(core, "_EMBED_CACHE", {})
    library = {**LIBRARY, "resolver": {"backend": "sentence-transformer"}}
    data = compile_text(tmp_path, (ROOT / "examples/screenplay.txt").read_text(encoding="utf-8"), library)
    assert loads == [minilm]
    assert data["resolvers"] == {"action": "sentence-transformer-cache-only", "emotion": "sbert-keywords"}
