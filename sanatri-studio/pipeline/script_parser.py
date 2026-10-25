"""Parse Sanatri / Legends of Bharat owner scripts into scenes."""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict


@dataclass
class Scene:
    index: int
    title: str
    visual: str
    audio: str
    voiceover: str


@dataclass
class ParsedScript:
    title: str
    scenes: list[Scene]
    production_notes: str

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "scenes": [asdict(s) for s in self.scenes],
            "production_notes": self.production_notes,
        }


_SCENE_RE = re.compile(
    r"Scene\s+(\d+)\s*:\s*(.+?)(?=\n\[|\nScene\s+\d+\s*:|\nProduction Notes|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_TITLE_RE = re.compile(
    r"(?:Video\s+Title|Title)\s*:\s*(.+)", re.IGNORECASE
)
_VISUAL_RE = re.compile(
    r"\[Visual Prompt\]\s*:\s*(.+?)(?=\n\[|\Z)", re.IGNORECASE | re.DOTALL
)
_AUDIO_RE = re.compile(
    r"\[Audio\]\s*:\s*(.+?)(?=\n\[|\Z)", re.IGNORECASE | re.DOTALL
)
_VO_RE = re.compile(
    r"\[Voiceover[^\]]*\]\s*:\s*(.+?)(?=\nScene\s+\d+\s*:|\nProduction Notes|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_NOTES_RE = re.compile(
    r"Production Notes.*?:\s*(.+)\Z", re.IGNORECASE | re.DOTALL
)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def split_voiceover_sentences(vo: str) -> list[str]:
    """One subtitle cue per sentence."""
    parts = re.split(r"(?<=[.!?])\s+", vo.strip())
    return [p.strip() for p in parts if p.strip()]


def parse_script(raw: str) -> ParsedScript:
    text = raw.replace("\r\n", "\n").strip()
    title_m = _TITLE_RE.search(text)
    title = title_m.group(1).strip() if title_m else "Untitled Legend"

    notes_m = _NOTES_RE.search(text)
    notes = notes_m.group(1).strip() if notes_m else ""

    scenes: list[Scene] = []
    for m in _SCENE_RE.finditer(text):
        idx = int(m.group(1))
        body = m.group(2).strip()
        # first line is title; rest may include tags
        lines = body.split("\n", 1)
        scene_title = lines[0].strip()
        rest = lines[1] if len(lines) > 1 else body

        visual_m = _VISUAL_RE.search(rest)
        audio_m = _AUDIO_RE.search(rest)
        vo_m = _VO_RE.search(rest)
        # Fallback: if VO tag missing, take text after last tag block
        voiceover = ""
        if vo_m:
            voiceover = vo_m.group(1).strip()
        else:
            # try unlabeled paragraphs after audio
            chunks = re.split(r"\[Audio\]\s*:.+", rest, flags=re.IGNORECASE | re.DOTALL)
            if len(chunks) > 1:
                voiceover = chunks[-1].strip()

        scenes.append(
            Scene(
                index=idx,
                title=scene_title,
                visual=_clean(visual_m.group(1)) if visual_m else "",
                audio=_clean(audio_m.group(1)) if audio_m else "",
                voiceover=voiceover.strip(),
            )
        )

    if not scenes:
        # Treat whole body as one scene VO
        scenes.append(
            Scene(
                index=1,
                title="Story",
                visual="Cinematic Hindu mythological short-film still, dramatic lighting",
                audio="Quiet original drone under voice",
                voiceover=text,
            )
        )

    return ParsedScript(title=title, scenes=scenes, production_notes=notes)
