from __future__ import annotations

import heapq
import html
import json
import math
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

TOKEN_RE = re.compile(r"[A-Za-z0-9']+")
STAGE_SCALE = 140.0  # stage pixels per metre, shared with the browser stage
WALK_SPEED = 1.0  # metres per second for approach paths
CLEARANCE = 0.35  # metres between a prop's bounding box and a derived stand point
DEFAULT_PROP_SIZE = (0.55, 0.65, 0.55)  # width, height, depth in metres
GRID_STEP = 0.1  # metres per walking-grid cell
ACTOR_RADIUS = 0.2  # metres of body clearance kept from prop footprints while walking

# Ekman's seven categories. Each keyword records the intensity level it implies
# (1 weak, 2 medium, 3 strong); libraries may replace this dictionary.
EMOTION_NAMES = ("anger", "disgust", "fear", "neutral", "joy", "sadness", "surprise")
EMOTION_KEYWORDS: dict[str, dict[str, int]] = {
    "anger": {"annoyed": 1, "irritated": 1, "frustrated": 1, "angry": 2, "angrily": 2, "mad": 2, "hostile": 2,
              "furious": 3, "enraged": 3, "rage": 3, "seething": 3},
    "disgust": {"distaste": 1, "displeased": 1, "disgusted": 2, "grossed out": 2, "repulsed": 3, "revolted": 3,
                "sickened": 3},
    "fear": {"uneasy": 1, "nervous": 1, "anxious": 1, "worried": 1, "afraid": 2, "fear": 2, "fearful": 2,
             "scared": 2, "frightened": 2, "terrified": 3, "panicked": 3, "horrified": 3},
    "neutral": {"neutral": 1, "calm": 1, "flat": 1, "composed": 1, "deadpan": 1, "matter-of-fact": 1, "evenly": 1},
    "joy": {"pleased": 1, "glad": 1, "smiling": 2, "happy": 2, "cheerful": 2, "joy": 2, "joyful": 2,
            "laughing": 3, "delighted": 3, "elated": 3, "overjoyed": 3, "excited": 3},
    "sadness": {"wistful": 1, "downcast": 1, "sad": 2, "sadly": 2, "sorrowful": 2, "tearful": 2, "gloomy": 2,
                "crying": 3, "sobbing": 3, "heartbroken": 3, "grieving": 3},
    "surprise": {"puzzled": 1, "surprised": 2, "startled": 2, "amazed": 2, "shocked": 3, "astonished": 3,
                 "stunned": 3},
}
EMOTION_ALIASES = {"angry": "anger", "happy": "joy", "happiness": "joy", "sad": "sadness", "afraid": "fear",
                   "scared": "fear", "surprised": "surprise", "disgusted": "disgust", "calm": "neutral"}
INTENSIFY = re.compile(r"\b(very|extremely|really|utterly|deeply|completely|incredibly|absolutely|terribly|wildly)\b")
SOFTEN = re.compile(r"\b(slightly|somewhat|faintly|mildly|barely|a little|a bit|a hint of)\b")
OVERRIDE_TAG = re.compile(r"\[\s*(?:emotion|face|expression)\s*[:=]\s*([A-Za-z]+)\s*(?:[ ,:/]\s*([1-3]))?\s*\]", re.I)

STOPWORDS = {"the", "a", "an", "to", "of", "and", "it", "its", "his", "her", "their", "at", "in", "into", "with",
             "then", "is", "are", "was", "be", "this", "that", "for", "from", "by", "as", "s"}
SUFFIXES = ("ingly", "edly", "fully", "ness", "ing", "ful", "ous", "ly", "ed", "es", "s")
IRREGULAR = {"sit": {"sat", "seated"}, "stand": {"stood"}, "take": {"took", "taken"}, "go": {"went", "gone", "goes"},
             "run": {"ran"}, "light": {"lit"}, "put": {"put"}, "eat": {"ate", "eaten"}, "get": {"got"}}
DEFAULT_VERB_SYNONYMS = {"turn on": ["switch on"], "turn off": ["switch off"], "sit": ["take a seat", "sit down"],
                         "walk": ["approach", "go", "move", "step"], "greet": ["wave"],
                         "stand": ["stand up", "get up", "rise"]}
LOCOMOTION = {"walk"}
POSITION_WORDS = {"left": "left", "right": "right", "center": "center", "centre": "center", "middle": "center",
                  "front": "front", "behind": "behind"}
CONTINUATION = re.compile(r"(?:\s*\((?:[^()]*)\))+\s*$")
GAP = r"(?:\s+(?!and\b|then\b|but\b|while\b)[\w']+){0,3}?"


@dataclass
class Paragraph:
    kind: str
    text: str
    scene: int = 0
    speaker: str | None = None
    language: str | None = None
    emotion: dict[str, Any] | None = None


@dataclass
class Event:
    id: str
    scene: int
    start: float
    duration: float
    actor: str | None
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)


def _tokens(text: str) -> list[str]:
    return [x.lower() for x in TOKEN_RE.findall(text)]


def _stem(word: str) -> str:
    """Light suffix stripping so inflections (angrily/angry, sits/sit) meet."""
    w = word.lower().strip("'")
    for _ in range(2):
        for suffix in SUFFIXES:
            if w.endswith(suffix) and len(w) - len(suffix) >= 3:
                w = w[: -len(suffix)]
                break
        else:
            break
    if w.endswith("y") and len(w) > 3:
        w = w[:-1] + "i"
    if w.endswith("e") and len(w) > 3:
        w = w[:-1]
    return w


def _stems(text: str, drop_stopwords: bool = True) -> list[str]:
    return [_stem(t) for t in _tokens(text) if not (drop_stopwords and t in STOPWORDS)]


def character_name(text: str) -> str:
    """Strip screenplay extensions such as (CONT'D), (V.O.) or (O.S.) and dual-dialogue carets."""
    return CONTINUATION.sub("", text).strip().lstrip("^").strip().upper()


def normalize_emotion(name: str, level: Any = 2) -> dict[str, Any]:
    key = str(name).strip().lower()
    key = EMOTION_ALIASES.get(key, key)
    if key not in EMOTION_NAMES:
        raise ValueError(f"Unknown emotion {name!r}; use one of {', '.join(EMOTION_NAMES)}")
    level = int(level or 2)
    if level not in (1, 2, 3):
        raise ValueError("Emotion level must be 1, 2 or 3")
    return {"emotion": key, "level": level}


def _split_override(text: str) -> tuple[str, dict[str, Any] | None]:
    match = OVERRIDE_TAG.search(text)
    if not match:
        return text, None
    return (text[: match.start()] + text[match.end():]).strip(), normalize_emotion(match.group(1), match.group(2) or 2)


def parse_screenplay(path: Path) -> list[Paragraph]:
    if path.suffix.lower() == ".fdx":
        root = ET.parse(path).getroot()
        out: list[Paragraph] = []
        scene = 0
        speaker: str | None = None
        for node in root.iter():
            if node.tag.split("}")[-1] != "Paragraph":
                continue
            kind = node.attrib.get("Type", "").strip().lower().replace(" ", "_")
            # Final Draft splits styled runs into adjacent <Text> nodes; their own
            # whitespace is authoritative, so join without inserting separators.
            runs = "".join(t.text or "" for t in node if t.tag.split("}")[-1] == "Text")
            text, override = _split_override(re.sub(r"\s+", " ", runs).strip())
            if not text:
                continue
            if kind == "scene_heading":
                scene += 1
            if kind == "character":
                text = speaker = character_name(text)
            out.append(Paragraph(kind, text, scene, speaker if kind in {"dialogue", "parenthetical"} else None, None, override))
        return out
    out = []
    scene = 0
    speaker = None
    language: str | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        label, sep, text = raw.partition(":")
        if not sep:
            raise ValueError(f"Expected LABEL: text, got {raw!r}")
        kind = label.strip().lower().replace(" ", "_")
        text, override = _split_override(text.strip())
        if kind == "language":
            language = text.strip() or None
            continue
        if kind in {"scene", "scene_heading"}:
            kind = "scene_heading"
            scene += 1
        if kind == "character":
            text = speaker = character_name(text)
        lang = language if kind == "dialogue" else None
        out.append(Paragraph(kind, text, scene, speaker if kind in {"dialogue", "parenthetical"} else None, lang, override))
    return out


# --------------------------------------------------------------------------
# Text encoders. Sentence-BERT models are loaded once per process and their
# embeddings are memoised, so recompiling a scene does not reload weights.
_MODEL_CACHE: dict[str, Any] = {}
_EMBED_CACHE: dict[tuple[str, str], list[float]] = {}


def _sentence_model(name: str) -> Any:
    if not name:
        raise RuntimeError("Semantic mode needs a local Sentence-BERT model directory")
    if name not in _MODEL_CACHE:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise RuntimeError("install the optional 'semantic' extra") from e
        _MODEL_CACHE[name] = SentenceTransformer(name, local_files_only=True)
    return _MODEL_CACHE[name]


def _embed(name: str, texts: list[str]) -> list[list[float]]:
    missing = [t for t in dict.fromkeys(texts) if (name, t) not in _EMBED_CACHE]
    if missing:
        if len(_EMBED_CACHE) > 50000:
            _EMBED_CACHE.clear()
        vectors = _sentence_model(name).encode(missing, normalize_embeddings=True)
        for text, vec in zip(missing, vectors):
            _EMBED_CACHE[(name, text)] = [float(x) for x in vec]
    return [_EMBED_CACHE[(name, t)] for t in texts]


def _dot(a: list[float], b: list[float]) -> float:
    return float(sum(x * y for x, y in zip(a, b)))


class LexicalEncoder:
    """Stemmed TF-IDF cosine over a fixed phrase set (offline fallback)."""

    name = "tfidf-stemmed"

    def __init__(self, phrases: list[str]):
        docs = [set(_stems(p)) for p in phrases]
        self.idf = {term: math.log((1 + len(docs)) / (1 + sum(term in d for d in docs))) + 1
                    for term in set().union(*docs)} if docs else {}

    def _vec(self, text: str) -> dict[str, float]:
        counts: dict[str, int] = {}
        for t in _stems(text):
            counts[t] = counts.get(t, 0) + 1
        return {t: c * self.idf.get(t, 1.0) for t, c in counts.items()}

    def similarity(self, query: str, phrases: list[str]) -> list[float]:
        q = self._vec(query)
        qn = math.sqrt(sum(v * v for v in q.values())) or 1.0
        out = []
        for phrase in phrases:
            d = self._vec(phrase)
            dn = math.sqrt(sum(v * v for v in d.values())) or 1.0
            out.append(sum(v * d.get(t, 0.0) for t, v in q.items()) / (qn * dn))
        return out


class SentenceEncoder:
    """Sentence-BERT cosine similarity with local model folders only."""

    name = "sentence-transformer-cache-only"

    def __init__(self, model: str):
        self.model = model
        _sentence_model(model)

    def similarity(self, query: str, phrases: list[str]) -> list[float]:
        q, *rows = _embed(self.model, [query, *phrases])
        return [_dot(q, r) for r in rows]


def _semantic(cfg: dict[str, Any]) -> bool:
    return cfg.get("backend") == "sentence-transformer"


# --------------------------------------------------------------------------
# Emotion: zero-shot keyword dictionary (paper Section 3.1.3).
def _keyword_dictionary(custom: dict[str, Any] | None) -> dict[str, dict[str, int]]:
    source = custom or EMOTION_KEYWORDS
    out: dict[str, dict[str, int]] = {}
    for name, words in source.items():
        key = normalize_emotion(name)["emotion"]
        if isinstance(words, dict):
            out[key] = {str(w): int(v) for w, v in words.items()}
        else:
            out[key] = {str(w): 2 for w in words}
    return out


def _adjust_level(level: int, text: str) -> int:
    low = text.lower()
    if INTENSIFY.search(low):
        level += 1
    if SOFTEN.search(low):
        level -= 1
    return max(1, min(3, level))


def analyze_emotion(text: str, keywords: dict[str, Any] | None = None, model: str | None = None,
                    floor: float = 0.25, top_k: int = 3, minimum: float = 0.2) -> dict[str, Any]:
    """Score a parenthetical against every emotion keyword and return name + level 1-3.

    Stemmed keyword hits give each emotion a lexical collective score (the
    offline fallback). With a Sentence-BERT model, each emotion additionally
    sums its top-k keyword cosine similarities above ``floor``. Scores below
    ``minimum`` mean no emotional cue, which maps to neutral.
    """
    dictionary = _keyword_dictionary(keywords)
    scores: dict[str, float] = {}
    best_level: dict[str, int] = {}
    first_hit: dict[str, int] = {}
    stems = _stems(text, drop_stopwords=False)
    for name, entries in dictionary.items():
        seen: set[tuple[str, ...]] = set()
        for word, level in entries.items():
            pattern = tuple(_stems(word, drop_stopwords=False))
            hits = [i for i in range(len(stems) - len(pattern) + 1) if tuple(stems[i:i + len(pattern)]) == pattern]
            if pattern and hits:
                best_level[name] = max(best_level.get(name, 0), level)
                first_hit[name] = min(first_hit.get(name, 10**6), hits[0])
                if pattern not in seen:  # angrily/angry are one piece of evidence
                    seen.add(pattern)
                    scores[name] = scores.get(name, 0.0) + 1.0
        scores.setdefault(name, 0.0)
    method = "lexical-keywords"
    weak = False
    if model:
        words = [w for name in dictionary for w in dictionary[name]]
        q, *vectors = _embed(model, [text, *words])
        sims = dict(zip(words, (_dot(q, v) for v in vectors)))
        for name, entries in dictionary.items():
            ranked = sorted(((sims[w], w) for w in entries), reverse=True)
            scores[name] = round(scores[name] + sum(max(0.0, s - floor) for s, _ in ranked[:top_k]), 4)
            if ranked and name not in best_level:
                best_level[name] = entries[ranked[0][1]]
        method = "sbert-keywords"
    top = max(scores.values(), default=0.0)
    if top < minimum:
        return {"emotion": "neutral", "level": 1, "scores": scores, "method": method}
    tied = [n for n, s in scores.items() if s == top]
    name = min(tied, key=lambda n: first_hit.get(n, 10**6))
    if model and name not in first_hit:
        weak = max(sims[w] for w in dictionary[name]) < 0.5
    level = 1 if name == "neutral" else _adjust_level(best_level.get(name, 2) - int(weak), text)
    return {"emotion": name, "level": level, "scores": scores, "method": method}


# --------------------------------------------------------------------------
# Actions: subject + plausible action-object-position combinations (Section 3.1.4).
def _verb_forms(word: str) -> set[str]:
    w = word.lower()
    forms = {w, w + "s", w + "es", w + "ed", w + "d", w + "ing"}
    if w.endswith("e"):
        forms.add(w[:-1] + "ing")
    if w.endswith("y"):
        forms |= {w[:-1] + "ies", w[:-1] + "ied"}
    if re.search(r"[^aeiou][aeiou][bdgmnprt]$", w):
        forms |= {w + w[-1] + "ing", w + w[-1] + "ed"}
    return forms | IRREGULAR.get(w, set())


def _verb_pattern(phrase: str) -> re.Pattern[str]:
    words = phrase.lower().split()
    head = "(?:" + "|".join(sorted(map(re.escape, _verb_forms(words[0])), key=len, reverse=True)) + ")"
    tail = "".join(GAP + r"\s+" + re.escape(w) for w in words[1:])
    return re.compile(rf"(?<![\w']){head}{tail}(?![\w'])", re.I)


def _verb_lexicon(combos: list[dict[str, Any]], extra: dict[str, list[str]] | None = None) -> list[tuple[str, re.Pattern[str]]]:
    synonyms: dict[str, set[str]] = {}
    for verb, words in {**DEFAULT_VERB_SYNONYMS, **(extra or {})}.items():
        synonyms.setdefault(verb, set()).update(words)
    for combo in combos:
        if combo.get("verb"):
            synonyms.setdefault(combo["verb"], set()).update(combo.get("synonyms", []))
    return [(verb, _verb_pattern(p)) for verb, words in synonyms.items() for p in [verb, *sorted(words)]]


def _name_pattern(name: str) -> re.Pattern[str]:
    # Case-sensitive and whole-word: "The red lamp" never selects RED.
    return re.compile(rf"(?<![\w']){re.escape(name)}(?![\w'])")


def _mentions(text: str, characters: dict[str, Any] | Iterable[str]) -> list[tuple[int, str, int]]:
    found = []
    items = characters.items() if isinstance(characters, dict) else ((c, {}) for c in characters)
    for name, info in items:
        for alias in [name, *((info or {}).get("aliases", []) if isinstance(info, dict) else [])]:
            for m in _name_pattern(alias).finditer(text):
                found.append((m.start(), name, m.end()))
    return sorted(found)


def prop_class(name: str, prop: dict[str, Any]) -> str:
    return str(prop.get("class") or re.sub(r"[_\-\s]*\d+$", "", name)).lower()


def extract_action(text: str, characters: Iterable[str] | dict[str, Any], props: Iterable[str],
                   verbs: list[tuple[str, re.Pattern[str]]] | None = None) -> dict[str, Any]:
    """Regex hints only: subject, verbs, object classes and position found in the text.

    The plausible-combination dictionary decides the action; these hints only
    veto contradictory combinations and supply verb evidence.
    """
    lexicon = verbs or _verb_lexicon([{"verb": v} for v in DEFAULT_VERB_SYNONYMS] +
                                     [{"verb": v} for v in ("open", "close", "pick up", "put down", "dance")])
    verb_hits = sorted((m.start(), verb) for verb, pattern in lexicon for m in pattern.finditer(text))
    verbs_found: list[str] = []
    for _, verb in verb_hits:
        if verb not in verbs_found:
            verbs_found.append(verb)
    first_verb = verb_hits[0][0] if verb_hits else len(text)
    mentions = _mentions(text, characters)
    before = [m for m in mentions if m[0] < first_verb]
    subject = (before or mentions or [(0, None, 0)])[0][1]
    low = text.lower()
    objects = [p for p in dict.fromkeys(str(x).lower() for x in props)
               if re.search(rf"(?<![\w']){re.escape(p)}(?:s|es)?(?![\w'])", low)]
    position = next((POSITION_WORDS[w] for w in _tokens(text) if w in POSITION_WORDS), None)
    return {"actor": subject, "verb": verbs_found[0] if verbs_found else None, "verbs": verbs_found,
            "object": objects[0] if objects else None, "objects": objects, "position": position}


def action_dictionary(library: dict[str, Any]) -> list[dict[str, Any]]:
    """The plausible action-object-position combinations: the single action source of truth."""
    rows = library.get("actions")
    if rows is None:  # legacy catalogs kept action combinations in "motions"
        rows = [m for m in library.get("motions", []) if m.get("kind") == "action"]
    out = []
    for row in rows:
        if not row.get("id") or not row.get("verb"):
            raise ValueError("Every plausible action combination needs an id and a verb")
        obj = row.get("object")
        pos = row.get("position")
        canonical = " ".join(x for x in (row["verb"], f"the {obj}" if obj else "", f"{pos} side" if pos else "") if x)
        out.append({**row, "object": obj.lower() if obj else None, "position": POSITION_WORDS.get(str(pos).lower()) if pos and str(pos).lower() != "none" else None,
                    "phrases": list(dict.fromkeys([*row.get("phrases", []), canonical]))})
    return out


def _size(prop: dict[str, Any]) -> tuple[float, float, float]:
    size = prop.get("size") or DEFAULT_PROP_SIZE
    return float(size[0]), float(size[1]), float(size[2])


def stand_point(prop: dict[str, Any], position: str | None) -> list[float]:
    """Interaction stand point for a prop, shifted by a left/right/front/behind position."""
    anchors = prop.get("anchors") or {}
    if position and position in anchors:
        return [float(v) for v in anchors[position]]
    x, y = float(prop.get("x", 480)), float(prop.get("y", 350))
    w, _, d = _size(prop)
    gap = CLEARANCE * STAGE_SCALE
    base = [float(v) for v in prop.get("anchor") or [x, y + d / 2 * STAGE_SCALE + gap]]
    offsets = {"left": [x - w / 2 * STAGE_SCALE - gap, base[1]], "right": [x + w / 2 * STAGE_SCALE + gap, base[1]],
               "front": [x, y + d / 2 * STAGE_SCALE + gap], "behind": [x, y - d / 2 * STAGE_SCALE - gap]}
    return offsets.get(position or "", base)


def _distance(a: list[float], b: list[float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


# --------------------------------------------------------------------------
# Obstacle-aware walking: grid A* over the stage floor. Props are axis-aligned
# footprints inflated by the actor's body radius; moves are 8-connected with an
# octile heuristic and diagonals only when both orthogonal neighbours are free
# (no corner cutting). The cell path is shortened by line-of-sight checks
# against the exact inflated footprints.
def obstacle_boxes(props: dict[str, Any], radius: float = ACTOR_RADIUS) -> list[tuple[float, float, float, float]]:
    """Inflated prop footprints in stage pixels: (x0, y0, x1, y1)."""
    boxes = []
    for prop in props.values():
        if prop.get("walkable"):
            continue
        w, _, d = _size(prop)
        x, y = float(prop.get("x", 480)), float(prop.get("y", 350))
        hw, hd = (w / 2 + radius) * STAGE_SCALE, (d / 2 + radius) * STAGE_SCALE
        boxes.append((x - hw, y - hd, x + hw, y + hd))
    return boxes


def _inside(point: list[float], box: tuple[float, float, float, float]) -> bool:
    return box[0] < point[0] < box[2] and box[1] < point[1] < box[3]


def _segment_hits(a: list[float], b: list[float], box: tuple[float, float, float, float]) -> bool:
    """Liang-Barsky clip: does the open segment a-b pass through the box interior?"""
    t0, t1 = 0.0, 1.0
    dx, dy = b[0] - a[0], b[1] - a[1]
    for p, q in ((-dx, a[0] - box[0]), (dx, box[2] - a[0]), (-dy, a[1] - box[1]), (dy, box[3] - a[1])):
        if abs(p) < 1e-12:
            if q <= 0:
                return False
            continue
        t = q / p
        if p < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 >= t1 - 1e-9:
            return False
    return True


def _clear(a: list[float], b: list[float], boxes: list[tuple[float, float, float, float]]) -> bool:
    return not any(_segment_hits(a, b, box) for box in boxes)


def plan_path(start: list[float], goal: list[float], props: dict[str, Any], stage: dict[str, Any] | None = None,
              step: float = GRID_STEP, radius: float = ACTOR_RADIUS) -> tuple[list[list[float]], str]:
    """Shortest obstacle-free walking path in stage pixels and the planner that produced it.

    A start or goal inside an inflated footprint (a seat, or an actor leaving one)
    connects to its nearest free cell, so only that short entry/exit leg overlaps the prop.
    """
    stage = stage or {}
    boxes = obstacle_boxes(props, radius)
    start, goal = [float(start[0]), float(start[1])], [float(goal[0]), float(goal[1])]
    if _clear(start, goal, boxes) and not any(_inside(start, b) or _inside(goal, b) for b in boxes):
        return [start, goal], "grid-astar-octile"
    cell = step * STAGE_SCALE
    width, height = float(stage.get("width", 960)), float(stage.get("height", 540))
    cols, rows = max(2, int(math.ceil(width / cell))), max(2, int(math.ceil(height / cell)))
    center = lambda c, r: [(c + 0.5) * cell, (r + 0.5) * cell]  # noqa: E731
    blocked = [[any(_inside(center(c, r), b) for b in boxes) for c in range(cols)] for r in range(rows)]

    def to_cell(p: list[float]) -> tuple[int, int]:
        return min(cols - 1, max(0, int(p[0] // cell))), min(rows - 1, max(0, int(p[1] // cell)))

    def nearest_free(p: list[float]) -> tuple[int, int] | None:
        c0, r0 = to_cell(p)
        if not blocked[r0][c0]:
            return c0, r0
        free = [(c, r) for r in range(rows) for c in range(cols) if not blocked[r][c]]
        return min(free, key=lambda cr: _distance(center(*cr), p)) if free else None

    a, b = nearest_free(start), nearest_free(goal)
    if a is None or b is None:
        return [start, goal], "straight-fallback"
    diagonal = math.sqrt(2.0)

    def octile(c: int, r: int) -> float:
        dx, dy = abs(c - b[0]), abs(r - b[1])
        return (dx + dy) + (diagonal - 2) * min(dx, dy)

    best = {a: 0.0}
    parent: dict[tuple[int, int], tuple[int, int]] = {}
    frontier = [(octile(*a), 0.0, a)]
    closed: set[tuple[int, int]] = set()
    while frontier:
        _, cost, node = heapq.heappop(frontier)
        if node in closed:
            continue
        if node == b:
            break
        closed.add(node)
        c, r = node
        for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            nc, nr = c + dc, r + dr
            if not (0 <= nc < cols and 0 <= nr < rows) or blocked[nr][nc]:
                continue
            if dc and dr and (blocked[r][nc] or blocked[nr][c]):
                continue  # no corner cutting
            new = cost + (diagonal if dc and dr else 1.0)
            if new < best.get((nc, nr), math.inf):
                best[(nc, nr)] = new
                parent[(nc, nr)] = node
                heapq.heappush(frontier, (new + octile(nc, nr), new, (nc, nr)))
    if b not in best:
        return [start, goal], "straight-fallback"
    cells = [b]
    while cells[-1] != a:
        cells.append(parent[cells[-1]])
    points = [center(*cr) for cr in reversed(cells)]
    # An endpoint in its own free cell replaces that cell centre; an enclosed or
    # snapped endpoint keeps the forced entry/exit leg to its nearest free cell.
    if to_cell(start) == a and len(points) > 1:
        points[0] = start
    else:
        points.insert(0, start)
    if to_cell(goal) == b and len(points) > 1 and points[-1] != start:
        points[-1] = goal
    else:
        points.append(goal)
    path = [points[0]]
    i = 0
    while i < len(points) - 1:
        j = next((k for k in range(len(points) - 1, i + 1, -1) if _clear(points[i], points[k], boxes)), i + 1)
        path.append(points[j])
        i = j
    return [[round(v, 2) for v in p] for p in path], "grid-astar-octile"


def path_length(path: list[list[float]]) -> float:
    return sum(_distance(p, q) for p, q in zip(path, path[1:]))


class ActionResolver:
    def __init__(self, library: dict[str, Any], cfg: dict[str, Any]):
        self.combos = action_dictionary(library)
        self.props = library.get("props", {})
        self.characters = library.get("characters", {})
        self.semantic = _semantic(cfg) and bool(cfg.get("action_model"))
        phrases = [p for c in self.combos for p in c["phrases"]]
        self.encoder = SentenceEncoder(cfg["action_model"]) if self.semantic else LexicalEncoder(phrases)
        self.threshold = float(cfg.get("action_threshold", 0.45 if self.semantic else 0.3))
        self.paraphrase = float(cfg.get("action_paraphrase_threshold", 0.7)) if self.semantic else math.inf
        self.lexicon = _verb_lexicon(self.combos, library.get("verb_synonyms"))
        self.classes = sorted({prop_class(n, p) for n, p in self.props.items()} | {c["object"] for c in self.combos if c["object"]})

    def _query(self, text: str) -> str:
        # Character names are not action evidence; drop them before similarity.
        for start, _, end in reversed(_mentions(text, self.characters)):
            text = text[:start] + " " + text[end:]
        return re.sub(r"\s+", " ", text).strip()

    def _instance(self, combo: dict[str, Any], position: str | None, origin: list[float]) -> tuple[str, dict[str, Any]] | None:
        instances = [(n, p) for n, p in self.props.items() if prop_class(n, p) == combo["object"]]
        if not instances:
            return None
        if position in {"left", "right"} and len(instances) > 1 and not any(position in (p.get("anchors") or {}) for _, p in instances):
            return (min if position == "left" else max)(instances, key=lambda item: float(item[1].get("x", 0)))
        return min(instances, key=lambda item: _distance(origin, stand_point(item[1], position)))

    def resolve(self, text: str, context_actor: str | None, positions: dict[str, list[float]]) -> dict[str, Any]:
        hints = extract_action(text, self.characters, self.classes, self.lexicon)
        subject, source = hints["actor"], "proper-noun"
        if subject is None:
            subject, source = context_actor, "context"
        query = self._query(text)
        scores = [max(self.encoder.similarity(query, combo["phrases"]), default=0.0) for combo in self.combos]
        candidates = []
        verb_hints, interact = set(hints["verbs"]), set(hints["verbs"]) - LOCOMOTION
        for combo, score in zip(self.combos, scores):
            if verb_hints and combo["verb"] not in verb_hints:
                continue
            if hints["objects"] and combo["object"] and combo["object"] not in hints["objects"]:
                continue
            if hints["position"] and combo["position"] and combo["position"] != hints["position"]:
                continue
            adjusted = score
            if combo["position"] and not hints["position"]:
                adjusted *= 0.9
            if combo["verb"] in LOCOMOTION and interact:
                adjusted *= 0.8
            evidence = combo["verb"] in verb_hints or score >= self.paraphrase
            candidates.append((round(adjusted, 4), combo, evidence))
        candidates.sort(key=lambda item: item[0], reverse=True)
        trace = {"hints": hints, "subject_source": source, "resolver": self.encoder.name, "threshold": self.threshold,
                 "candidates": [{"id": c["id"], "score": s} for s, c, _ in candidates[:3]]}
        reject = None
        if not candidates:
            reject = "no plausible combination"
        elif not candidates[0][2]:
            reject = "no verb evidence"
        elif candidates[0][0] < self.threshold:
            reject = "below similarity threshold"
        elif subject is None:
            reject = "no subject"
        if reject:
            return {"accepted": False, "subject": hints["actor"], "reason": reject, **trace}
        score, combo, _ = candidates[0]
        result = {"accepted": True, "subject": subject, "combination": combo, "score": score, **trace}
        if combo["object"]:
            origin = positions.get(subject, [480.0, 350.0])
            chosen = self._instance(combo, hints["position"] or combo["position"], origin)
            if chosen is None:
                return {**result, "accepted": False, "reason": f"no {combo['object']} in the scene"}
            result["instance"] = chosen
        return result


# --------------------------------------------------------------------------
def _overrides(library: dict[str, Any]) -> dict[int, dict[str, Any]]:
    out = {}
    for key, value in (library.get("emotion_overrides") or {}).items():
        if isinstance(value, str):
            name, _, level = value.partition(":")
            value = {"emotion": name, "level": level or 2}
        out[int(key)] = normalize_emotion(value.get("emotion", ""), value.get("level", 2))
    return out


def _gaze(text: str, actor: str | None, chars: dict[str, Any], positions: dict[str, list[float]]) -> tuple[str, list[float] | None]:
    named = next((name for _, name, _ in _mentions(text, chars) if name != actor), None)
    if named:
        return named, positions.get(named)
    others = [positions[n] for n in chars if n != actor and n in positions]
    if not others:
        return "group", None
    return "group", [round(sum(p[0] for p in others) / len(others), 2), round(sum(p[1] for p in others) / len(others), 2)]


def _speech_seconds(text: str, language: str) -> float:
    if language.lower()[:2] in {"ko", "ja", "zh"}:
        return max(1.2, len(re.sub(r"\s|[.,!?…]", "", text)) / 6.5)
    return max(1.2, len(_tokens(text)) / 2.7)


def compile_timeline(paragraphs: list[Paragraph], library: dict[str, Any]) -> dict[str, Any]:
    chars = library.get("characters", {})
    props = library.get("props", {})
    cfg = library.get("resolver") or {"backend": "tfidf"}
    semantic = _semantic(cfg)
    emotion_model = (cfg.get("emotion_model") or cfg.get("model")) if semantic else None
    actions = ActionResolver(library, cfg)
    overrides = _overrides(library)
    positions = {n: [float(c.get("x", 480)), float(c.get("y", 350))] for n, c in chars.items()}
    events: list[Event] = []
    t = 0.0
    current_actor: str | None = None
    context_actor: str | None = None
    seq = 1

    def add(scene: int, start: float, duration: float, actor: str | None, kind: str, payload: dict[str, Any]) -> None:
        nonlocal seq
        events.append(Event(f"e{seq}", scene, round(start, 3), round(duration, 3), actor, kind, payload))
        seq += 1

    for index, p in enumerate(paragraphs):
        manual = overrides.get(index) or p.emotion
        if p.kind == "character":
            current_actor = context_actor = character_name(p.text)
            if manual:
                add(p.scene, t, 0.0, current_actor, "emotion", {**manual, "intensity": round(manual["level"] / 3, 3), "method": "manual", "paragraph": index, "source": p.text})
            continue
        if p.kind == "scene_heading":
            add(p.scene, t, 1.0, None, "scene", {"heading": p.text})
            t += 1.0
        elif p.kind == "dialogue":
            actor = p.speaker or current_actor
            language = p.language or (chars.get(actor) or {}).get("language") or library.get("source_language") or "en"
            duration = _speech_seconds(p.text, language)
            if manual:
                add(p.scene, t, 0.0, actor, "emotion", {**manual, "intensity": round(manual["level"] / 3, 3), "method": "manual", "paragraph": index, "source": p.text})
            target, point = _gaze(p.text, actor, chars, positions)
            add(p.scene, t, duration, actor, "speech", {"text": p.text, "language": language, "gaze": target, "gaze_point": point,
                                                        "lip_sync": "word-timing-estimate", "paragraph": index})
            t += duration
        elif p.kind == "parenthetical":
            actor = p.speaker or current_actor
            if manual:
                result = {**manual, "method": "manual"}
            else:
                result = analyze_emotion(p.text, library.get("emotions"), emotion_model)
            add(p.scene, t, 1.1, actor, "emotion", {**result, "intensity": round(result["level"] / 3, 3), "paragraph": index, "source": p.text})
            t += 1.1
        elif p.kind == "action":
            res = actions.resolve(p.text, context_actor, positions)
            actor = res["subject"] if res["accepted"] else (res.get("subject") or None)
            if manual and actor:
                add(p.scene, t, 0.0, actor, "emotion", {**manual, "intensity": round(manual["level"] / 3, 3), "method": "manual", "paragraph": index, "source": p.text})
            trace = {"resolver": res["resolver"], "subject_source": res["subject_source"], "candidates": res["candidates"], "hints": res["hints"]}
            if not res["accepted"]:
                # Fig. 8 left endpoint: the paragraph has no source for a physical action.
                add(p.scene, t, 1.0, actor, "narration", {"text": p.text, "rejected": res["reason"], "paragraph": index, **trace})
                t += 1.0
                continue
            context_actor = actor
            combo = res["combination"]
            payload: dict[str, Any] = {"combination": combo["id"], "motion": combo["id"], "verb": combo["verb"], "object": combo["object"],
                                       "position": res["hints"]["position"] or combo["position"], "subject": actor, "text": p.text,
                                       "score": res["score"], "paragraph": index, **trace}
            if "instance" in res:
                name, prop = res["instance"]
                position = payload["position"]
                anchor = stand_point(prop, position)
                center = [float(prop.get("x", 480)), float(prop.get("y", 350))]
                start = positions.get(actor, anchor)
                face = None if combo["verb"] == "sit" else center
                if _distance(start, anchor) / STAGE_SCALE > 0.05:
                    path, planner = plan_path(start, anchor, props, library.get("stage"))
                    distance = path_length(path) / STAGE_SCALE
                    walk = max(0.6, distance / WALK_SPEED)
                    add(p.scene, t, walk, actor, "move", {"target": name, "class": combo["object"], "from": [round(v, 2) for v in start],
                                                          "anchor": [round(v, 2) for v in anchor], "face": face, "distance_m": round(distance, 3),
                                                          "path": path, "planner": planner})
                    t += walk
                positions[actor] = anchor
                height = _size(prop)[1]
                payload.update(target=name, anchor=[round(v, 2) for v in anchor], face=face,
                               interaction=[float(v) for v in prop.get("interaction") or [*center, height]])
                if combo["verb"] == "sit":
                    payload["seat_height"] = float(prop.get("seat_height", height))
                if combo.get("effect"):
                    payload["effect"] = {"prop": name, **combo["effect"]}
            add(p.scene, t, float(combo.get("duration", 1.4)), actor, "action", payload)
            t += float(combo.get("duration", 1.4))
    return {"schema": "paperreach.asap.timeline.v1", "stage": library.get("stage", {}), "characters": chars, "props": props,
            "paragraphs": [asdict(p) for p in paragraphs], "events": [asdict(e) for e in events], "duration": round(t, 3),
            "resolvers": {"action": actions.encoder.name, "emotion": "sbert-keywords" if emotion_model else "lexical-keywords"}}


def _page(title: str, body: str, data: dict[str, Any], autoplay: bool = False, immersive: bool = False) -> str:
    packed = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    mode = "immersive" if immersive else "stage"
    return f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'><title>{html.escape(title)}</title>
<style>body{{margin:0;background:#111827;color:#eef2ff;font:15px system-ui}}header{{padding:18px 24px}}#wrap{{display:grid;grid-template-columns:minmax(0,3fr) minmax(280px,1fr);gap:16px;padding:0 24px 24px}}svg{{width:100%;height:auto;background:#243047;border-radius:16px}}aside{{background:#182033;padding:16px;border-radius:16px;max-height:540px;overflow:auto}}button,input{{accent-color:#f59e0b}}.active{{color:#fbbf24}}@media(max-width:780px){{#wrap{{grid-template-columns:1fr}}}} .immersive svg{{border-radius:50%/18%}} </style></head>
<body class='{mode}'><header><h1>{html.escape(title)}</h1><button id='play'>Play / pause</button> <input id='scrub' type='range' min='0' max='{data['duration']}' value='0' step='.05'> <span id='clock'>0.0s</span></header><div id='wrap'><svg id='stage' viewBox='0 0 960 540' aria-label='schematic previz stage'></svg><aside><h2>Timeline</h2><ol id='events'></ol></aside></div><script>const D={packed};let now=0,playing={str(autoplay).lower()},last=0;const S=document.querySelector('#stage'),L=document.querySelector('#events'),R=document.querySelector('#scrub');
function along(P,k){{let L=0;for(let i=1;i<P.length;i++)L+=Math.hypot(P[i][0]-P[i-1][0],P[i][1]-P[i-1][1]);let d=k*L;for(let i=1;i<P.length;i++){{const s=Math.hypot(P[i][0]-P[i-1][0],P[i][1]-P[i-1][1]);if(d<=s||i===P.length-1){{const f=s?Math.min(1,d/s):1;return [P[i-1][0]+(P[i][0]-P[i-1][0])*f,P[i-1][1]+(P[i][1]-P[i-1][1])*f]}}d-=s}}return P[P.length-1]}};function esc(s){{return String(s).replace(/[&<>\"]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}}[c]))}};
function draw(){{let e=D.events.filter(x=>x.start<=now&&now<x.start+x.duration);let bg=`<rect width='960' height='540' fill='#27354f'/><path d='M0 410 L960 410' stroke='#94a3b8'/><text x='24' y='40' fill='white'>${{esc(D.stage.background||'user stage')}}</text>`;for(const [n,p] of Object.entries(D.props))bg+=`<rect x='${{p.x-35}}' y='${{p.y-25}}' width='70' height='50' rx='8' fill='#64748b'/><text x='${{p.x}}' y='${{p.y+5}}' text-anchor='middle' fill='white'>${{esc(n)}}</text>`;for(const [n,c] of Object.entries(D.characters)){{let mv=[...D.events].reverse().find(x=>x.actor===n&&x.kind==='move'&&x.start<=now),k=mv?Math.min(1,(now-mv.start)/Math.max(.001,mv.duration)):1,[x,y]=mv?along(mv.payload.path||[mv.payload.from,mv.payload.anchor],k):[c.x,c.y];let a=e.find(x=>x.actor===n);bg+=`<circle cx='${{x}}' cy='${{y-65}}' r='24' fill='${{c.color||'#38bdf8'}}'/><path d='M${{x}} ${{y-40}}v70m-28-45h56m-56 75l28-30 28 30' stroke='${{c.color||'#38bdf8'}}' stroke-width='12' fill='none'/><text x='${{x}}' y='${{y+48}}' text-anchor='middle' fill='white'>${{esc(n)}}</text>${{a?`<text x='${{x}}' y='${{y-105}}' text-anchor='middle' fill='#fbbf24'>${{esc(a.kind)}}</text>`:''}}`}}S.innerHTML=bg;document.querySelector('#clock').textContent=now.toFixed(1)+'s';R.value=now;[...L.children].forEach((li,i)=>li.className=(D.events[i].start<=now&&now<D.events[i].start+D.events[i].duration)?'active':'')}}
D.events.forEach(x=>{{let li=document.createElement('li');li.textContent=`${{x.start.toFixed(1)}}s · ${{x.actor||'SCENE'}} · ${{x.kind}}`;L.appendChild(li)}});function tick(ts){{if(playing){{if(last)now+=(ts-last)/1000;if(now>D.duration)now=0}}last=ts;draw();requestAnimationFrame(tick)}}document.querySelector('#play').onclick=()=>playing=!playing;R.oninput=()=>{{now=+R.value;draw()}};requestAnimationFrame(tick);</script></body></html>"""


def render_outputs(data: dict[str, Any], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "timeline.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "live.html").write_text(_page("ASAP real-time live playback", "", data, autoplay=True), encoding="utf-8")
    panels = []
    for i, e in enumerate(data["events"]):
        if e["kind"] in {"scene", "speech", "emotion", "action", "narration"}:
            label = e["payload"].get("text") or e["payload"].get("heading") or (f"{e['payload'].get('emotion')} {e['payload'].get('level', '')}" if e["kind"] == "emotion" else "")
            panels.append(f"<article><svg viewBox='0 0 320 180'><rect width='320' height='180' fill='#27354f'/><text x='16' y='28' fill='white'>{html.escape(e['actor'] or 'SCENE')}</text><text x='16' y='58' fill='#fbbf24'>{html.escape(e['kind'])}</text><text x='16' y='90' fill='white'>{html.escape(str(label)[:42])}</text></svg><p>{e['start']:.1f}s</p></article>")
    doc = "<!doctype html><meta charset='utf-8'><title>Storyboard</title><style>body{font:14px system-ui;background:#111827;color:white;display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px;padding:20px}article{background:#182033;padding:12px;border-radius:12px}svg{width:100%}</style>" + "".join(panels)
    (out / "storyboard.html").write_text(doc, encoding="utf-8")
