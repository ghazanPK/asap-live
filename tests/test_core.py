import json, tempfile, unittest
from pathlib import Path
from asap_multi.core import compile_timeline, extract_action, parse_screenplay, render_outputs

class CoreTest(unittest.TestCase):
    def test_pipeline(self):
        root = Path(__file__).parents[1]
        data = compile_timeline(parse_screenplay(root / "examples/screenplay.txt"), json.loads((root / "examples/library.json").read_text()))
        self.assertTrue({"speech", "emotion", "move", "action"} <= {e["kind"] for e in data["events"]})
        with tempfile.TemporaryDirectory() as d:
            render_outputs(data, Path(d))
            self.assertTrue((Path(d) / "live.html").exists())
            self.assertTrue((Path(d) / "storyboard.html").exists())
        self.assertEqual(extract_action("WOLF turns the lamp off", ["WOLF"], ["lamp"])["verb"], "turn off")

if __name__ == "__main__": unittest.main()
