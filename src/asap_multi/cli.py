from __future__ import annotations
import argparse, json
from pathlib import Path
from .core import compile_timeline, parse_screenplay, render_outputs

def main() -> None:
    p = argparse.ArgumentParser(description="Compile a screenplay into an auto-playing ASAP live demonstration")
    p.add_argument("screenplay", type=Path); p.add_argument("--library", type=Path, required=True); p.add_argument("--out", type=Path, default=Path("outputs"))
    a = p.parse_args(); library = json.loads(a.library.read_text(encoding="utf-8")); data = compile_timeline(parse_screenplay(a.screenplay), library); render_outputs(data, a.out)
    print(json.dumps({"events": len(data["events"]), "duration": data["duration"], "outputs": str(a.out)}, indent=2))

if __name__ == "__main__": main()
