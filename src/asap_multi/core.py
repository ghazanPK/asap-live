from __future__ import annotations

import html
import json
import math
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

TOKEN_RE = re.compile(r"[A-Za-z0-9']+")
EMOTIONS = {
    "anger": {"angry", "angrily", "furious", "irritated"},
    "disgust": {"disgusted", "revolted", "repulsed"},
    "fear": {"afraid", "fear", "fearful", "scared", "terrified"},
    "neutral": {"neutral", "calm", "plain"},
    "joy": {"happy", "joy", "joyful", "smiling", "excited"},
    "sadness": {"sad", "sadly", "crying", "sorrowful"},
    "surprise": {"surprised", "shocked", "astonished"},
}


@dataclass
class Paragraph:
    kind: str
    text: str
    scene: int = 0
    speaker: str | None = None


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
            text = " ".join((t.text or "").strip() for t in node.iter() if t.tag.split("}")[-1] == "Text").strip()
            if not text:
                continue
            if kind == "scene_heading":
                scene += 1
            if kind == "character":
                speaker = text.upper()
            out.append(Paragraph(kind, text, scene, speaker if kind in {"dialogue", "parenthetical"} else None))
        return out
    out = []
    scene = 0
    speaker = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        label, sep, text = raw.partition(":")
        if not sep:
            raise ValueError(f"Expected LABEL: text, got {raw!r}")
        kind = label.strip().lower().replace(" ", "_")
        text = text.strip()
        if kind in {"scene", "scene_heading"}:
            kind = "scene_heading"
            scene += 1
        if kind == "character":
            speaker = text.upper()
        out.append(Paragraph(kind, text, scene, speaker if kind in {"dialogue", "parenthetical"} else None))
    return out


class TfidfResolver:
    """Small deterministic cosine resolver; fitted to the user motion catalog."""

    def __init__(self, rows: list[dict[str, Any]]):
        self.rows = rows
        docs = [set(_tokens(" ".join(r.get("phrases", [])))) for r in rows]
        self.idf: dict[str, float] = {}
        for term in set().union(*docs) if docs else set():
            self.idf[term] = math.log((1 + len(docs)) / (1 + sum(term in d for d in docs))) + 1

    def _vec(self, text: str) -> dict[str, float]:
        counts: dict[str, int] = {}
        for t in _tokens(text):
            counts[t] = counts.get(t, 0) + 1
        return {t: c * self.idf.get(t, 1.0) for t, c in counts.items()}

    def match(self, text: str, kind: str) -> tuple[dict[str, Any] | None, float]:
        q = self._vec(text)
        qn = math.sqrt(sum(v * v for v in q.values())) or 1
        best, score = None, 0.0
        for row in self.rows:
            if row.get("kind") != kind:
                continue
            d = self._vec(" ".join(row.get("phrases", [])))
            dn = math.sqrt(sum(v * v for v in d.values())) or 1
            s = sum(v * d.get(t, 0.0) for t, v in q.items()) / (qn * dn)
            if s > score:
                best, score = row, s
        return best, round(score, 4)


class SentenceTransformerResolver:
    """Optional semantic resolver that refuses network downloads."""
    def __init__(self, rows: list[dict[str, Any]], model_name: str):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise RuntimeError("install the optional 'semantic' extra") from e
        self.rows = rows; self.model = SentenceTransformer(model_name, local_files_only=True)
        self.vectors = self.model.encode([" ".join(r.get("phrases", [])) for r in rows], normalize_embeddings=True)
    def match(self, text: str, kind: str) -> tuple[dict[str, Any] | None, float]:
        q = self.model.encode([text], normalize_embeddings=True)[0]; best, score = None, -1.0
        for row, vec in zip(self.rows, self.vectors):
            if row.get("kind") != kind: continue
            s = float(sum(float(a) * float(b) for a, b in zip(q, vec)))
            if s > score: best, score = row, s
        return best, round(max(0.0, score), 4)


def extract_action(text: str, characters: Iterable[str], props: Iterable[str]) -> dict[str, str | None]:
    low = text.lower()
    actor = next((c for c in characters if re.search(rf"\b{re.escape(c.lower())}\b", low)), None)
    obj = next((p for p in props if re.search(rf"\b{re.escape(p.lower())}\b", low)), None)
    verb_patterns = [("turn off", r"\bturn(?:s|ed|ing)?\b.*?\boff\b"), ("turn on", r"\bturn(?:s|ed|ing)?\b.*?\bon\b"), ("pick up", r"\bpick(?:s|ed|ing)?\b.*?\bup\b"), ("put down", r"\bput(?:s|ting)?\b.*?\bdown\b"), *[(v, rf"\b{v}(?:s|ed|ing)?\b") for v in ("walk", "open", "close", "sit", "stand", "greet", "dance")]]
    verb = next((name for name, pattern in verb_patterns if re.search(pattern, low)), None)
    position = next((x for x in ("left", "right", "center", "front", "behind") if re.search(rf"\b{x}\b", low)), None)
    return {"actor": actor, "verb": verb, "object": obj, "position": position}


def emotion(text: str) -> tuple[str, float]:
    ts = set(_tokens(text))
    scores = {name: len(ts & words) for name, words in EMOTIONS.items()}
    name = max(scores, key=scores.get)
    return (name, min(1.0, 0.34 + scores[name] * 0.33)) if scores[name] else ("neutral", 0.34)


def compile_timeline(paragraphs: list[Paragraph], library: dict[str, Any]) -> dict[str, Any]:
    chars = library.get("characters", {})
    props = library.get("props", {})
    cfg = library.get("resolver", {"backend": "tfidf"})
    resolver = SentenceTransformerResolver(library.get("motions", []), cfg["model"]) if cfg.get("backend") == "sentence-transformer" else TfidfResolver(library.get("motions", []))
    action_resolver = SentenceTransformerResolver(library.get("motions", []), cfg["action_model"]) if cfg.get("backend") == "sentence-transformer" and cfg.get("action_model") else resolver
    resolver_name = "sentence-transformer-cache-only" if cfg.get("backend") == "sentence-transformer" else "tfidf-baseline"
    events: list[Event] = []
    t = 0.0
    current_actor: str | None = None
    seq = 1
    for p in paragraphs:
        if p.kind == "character":
            current_actor = p.text.upper()
            continue
        if p.kind == "scene_heading":
            events.append(Event(f"e{seq}", p.scene, t, 1.0, None, "scene", {"heading": p.text}))
            seq += 1; t += 1.0
        elif p.kind == "dialogue":
            actor = p.speaker or current_actor
            words = len(_tokens(p.text)); duration = max(1.2, words / 2.7)
            target = next((c for c in chars if c != actor and re.search(rf"\b{re.escape(c)}\b", p.text, re.I)), "group")
            motion, score = resolver.match(p.text, "gesture")
            events.append(Event(f"e{seq}", p.scene, t, duration, actor, "speech", {"text": p.text, "gaze": target, "lip_sync": "word-timing-estimate"})); seq += 1
            events.append(Event(f"e{seq}", p.scene, t, duration, actor, "gesture", {"motion": motion.get("id") if motion else "beat_generic", "score": score, "resolver": resolver_name})); seq += 1
            t += duration
        elif p.kind == "parenthetical":
            actor = p.speaker or current_actor
            name, intensity = emotion(p.text)
            events.append(Event(f"e{seq}", p.scene, t, 1.1, actor, "emotion", {"emotion": name, "intensity": intensity, "source": p.text})); seq += 1; t += 1.1
        elif p.kind == "action":
            parsed = extract_action(p.text, chars, props)
            actor = parsed["actor"] or current_actor
            motion, score = action_resolver.match(p.text, "action")
            prop = props.get(parsed["object"] or "")
            if prop:
                events.append(Event(f"e{seq}", p.scene, t, 1.8, actor, "move", {"target": parsed["object"], "anchor": prop.get("anchor", [prop.get("x", 480), prop.get("y", 270)])})); seq += 1; t += 1.8
            events.append(Event(f"e{seq}", p.scene, t, 1.4, actor, "action", {**parsed, "text": p.text, "motion": motion.get("id") if motion else None, "score": score, "resolver": resolver_name})); seq += 1; t += 1.4
    return {"schema": "paperreach.asap.timeline.v1", "stage": library.get("stage", {}), "characters": chars, "props": props, "paragraphs": [asdict(p) for p in paragraphs], "events": [asdict(e) for e in events], "duration": round(t, 3)}


def _page(title: str, body: str, data: dict[str, Any], autoplay: bool = False, immersive: bool = False) -> str:
    packed = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    mode = "immersive" if immersive else "stage"
    return f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'><title>{html.escape(title)}</title>
<style>body{{margin:0;background:#111827;color:#eef2ff;font:15px system-ui}}header{{padding:18px 24px}}#wrap{{display:grid;grid-template-columns:minmax(0,3fr) minmax(280px,1fr);gap:16px;padding:0 24px 24px}}svg{{width:100%;height:auto;background:#243047;border-radius:16px}}aside{{background:#182033;padding:16px;border-radius:16px;max-height:540px;overflow:auto}}button,input{{accent-color:#f59e0b}}.active{{color:#fbbf24}}@media(max-width:780px){{#wrap{{grid-template-columns:1fr}}}} .immersive svg{{border-radius:50%/18%}} </style></head>
<body class='{mode}'><header><h1>{html.escape(title)}</h1><button id='play'>Play / pause</button> <input id='scrub' type='range' min='0' max='{data['duration']}' value='0' step='.05'> <span id='clock'>0.0s</span></header><div id='wrap'><svg id='stage' viewBox='0 0 960 540' aria-label='schematic previz stage'></svg><aside><h2>Timeline</h2><ol id='events'></ol></aside></div><script>const D={packed};let now=0,playing={str(autoplay).lower()},last=0;const S=document.querySelector('#stage'),L=document.querySelector('#events'),R=document.querySelector('#scrub');
function esc(s){{return String(s).replace(/[&<>\"]/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}}[c]))}};
function draw(){{let e=D.events.filter(x=>x.start<=now&&now<x.start+x.duration);let bg=`<rect width='960' height='540' fill='#27354f'/><path d='M0 410 L960 410' stroke='#94a3b8'/><text x='24' y='40' fill='white'>${{esc(D.stage.background||'user stage')}}</text>`;for(const [n,p] of Object.entries(D.props))bg+=`<rect x='${{p.x-35}}' y='${{p.y-25}}' width='70' height='50' rx='8' fill='#64748b'/><text x='${{p.x}}' y='${{p.y+5}}' text-anchor='middle' fill='white'>${{esc(n)}}</text>`;for(const [n,c] of Object.entries(D.characters)){{let mv=[...D.events].reverse().find(x=>x.actor===n&&x.kind==='move'&&x.start<=now),x=mv?mv.payload.anchor[0]:c.x,y=mv?mv.payload.anchor[1]:c.y;let a=e.find(x=>x.actor===n);bg+=`<circle cx='${{x}}' cy='${{y-65}}' r='24' fill='${{c.color||'#38bdf8'}}'/><path d='M${{x}} ${{y-40}}v70m-28-45h56m-56 75l28-30 28 30' stroke='${{c.color||'#38bdf8'}}' stroke-width='12' fill='none'/><text x='${{x}}' y='${{y+48}}' text-anchor='middle' fill='white'>${{esc(n)}}</text>${{a?`<text x='${{x}}' y='${{y-105}}' text-anchor='middle' fill='#fbbf24'>${{esc(a.kind)}}</text>`:''}}`}}S.innerHTML=bg;document.querySelector('#clock').textContent=now.toFixed(1)+'s';R.value=now;[...L.children].forEach((li,i)=>li.className=(D.events[i].start<=now&&now<D.events[i].start+D.events[i].duration)?'active':'')}}
D.events.forEach(x=>{{let li=document.createElement('li');li.textContent=`${{x.start.toFixed(1)}}s · ${{x.actor||'SCENE'}} · ${{x.kind}}`;L.appendChild(li)}});function tick(ts){{if(playing){{if(last)now+=(ts-last)/1000;if(now>D.duration)now=0}}last=ts;draw();requestAnimationFrame(tick)}}document.querySelector('#play').onclick=()=>playing=!playing;R.oninput=()=>{{now=+R.value;draw()}};requestAnimationFrame(tick);</script></body></html>"""


def render_outputs(data: dict[str, Any], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "timeline.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "live.html").write_text(_page("ASAP real-time live playback", "", data, autoplay=True), encoding="utf-8")
    panels = []
    for i, e in enumerate(data["events"]):
        if e["kind"] in {"scene", "speech", "emotion", "action"}:
            panels.append(f"<article><svg viewBox='0 0 320 180'><rect width='320' height='180' fill='#27354f'/><text x='16' y='28' fill='white'>{html.escape(e['actor'] or 'SCENE')}</text><text x='16' y='58' fill='#fbbf24'>{html.escape(e['kind'])}</text><text x='16' y='90' fill='white'>{html.escape(str(e['payload'].get('text') or e['payload'].get('heading') or e['payload'].get('emotion') or '')[:42])}</text></svg><p>{e['start']:.1f}s</p></article>")
    doc = "<!doctype html><meta charset='utf-8'><title>Storyboard</title><style>body{font:14px system-ui;background:#111827;color:white;display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px;padding:20px}article{background:#182033;padding:12px;border-radius:12px}svg{width:100%}</style>" + "".join(panels)
    (out / "storyboard.html").write_text(doc, encoding="utf-8")
