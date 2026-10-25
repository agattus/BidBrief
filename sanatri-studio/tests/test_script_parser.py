"""Regression tests for Sanatri Studio script parsing."""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.script_parser import parse_script, validate_parsed  # noqa: E402


def _load_jalandhara_sample() -> str:
    html = (ROOT / "app" / "templates" / "index.html").read_text()
    m = re.search(r"const SAMPLE = `(.*)`;", html, re.S)
    assert m, "SAMPLE script missing from index.html"
    return m.group(1)


class ScriptParserTests(unittest.TestCase):
    def test_jalandhara_sample_has_seven_full_scenes(self) -> None:
        script = _load_jalandhara_sample()
        parsed = parse_script(script)
        validate_parsed(parsed)

        self.assertEqual(
            parsed.title,
            "The Demon Born From Shiva’s Third Eye (The Greatest Divine Betrayal)",
        )
        self.assertEqual(len(parsed.scenes), 7)

        for scene in parsed.scenes:
            self.assertTrue(scene.visual.strip(), f"scene {scene.index} missing visual")
            self.assertTrue(scene.audio.strip(), f"scene {scene.index} missing audio")
            self.assertTrue(
                scene.voiceover.strip(), f"scene {scene.index} missing voiceover"
            )

        joined = " ".join(s.voiceover for s in parsed.scenes)
        for needle in ("Jalandhara", "Vrinda", "Tulsi"):
            self.assertIn(needle, joined)

    def test_empty_voiceover_fails_validation(self) -> None:
        broken = """Video Title: Broken
Scene 1: Hook
[Visual Prompt]: Something visual
[Audio]: Drums
[Voiceover]:

Scene 2: End
[Visual Prompt]: End visual
[Audio]: Bells
[Voiceover]: Real line here.
"""
        parsed = parse_script(broken)
        with self.assertRaises(ValueError):
            validate_parsed(parsed)


if __name__ == "__main__":
    unittest.main()
