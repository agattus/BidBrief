"""Parse Sanatri / Legends of Bharat owner scripts into scenes."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass


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


# Scene body runs until next Scene / Production Notes / EOF — do NOT stop at "[" tags.
_SCENE_HEADER_RE = re.compile(r"^Scene\s+(\d+)\s*:\s*(.*)$", re.IGNORECASE | re.MULTILINE)
_TITLE_RE = re.compile(r"(?:Video\s+Title|Title)\s*:\s*(.+)", re.IGNORECASE)
_VISUAL_RE = re.compile(
    r"\[Visual Prompt\]\s*:\s*(.+?)(?=\n\s*\[|\Z)", re.IGNORECASE | re.DOTALL
)
_AUDIO_RE = re.compile(
    r"\[Audio\]\s*:\s*(.+?)(?=\n\s*\[|\Z)", re.IGNORECASE | re.DOTALL
)
_VO_RE = re.compile(
    r"\[Voiceover[^\]]*\]\s*:\s*(.+?)(?=\Z)",
    re.IGNORECASE | re.DOTALL,
)
_NOTES_RE = re.compile(r"Production Notes.*?:\s*(.+)\Z", re.IGNORECASE | re.DOTALL)
_NEXT_SCENE_OR_NOTES = re.compile(
    r"\n(?=Scene\s+\d+\s*:|Production Notes)", re.IGNORECASE
)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def split_voiceover_sentences(vo: str) -> list[str]:
    """One subtitle cue per sentence."""
    parts = re.split(r"(?<=[.!?])\s+", vo.strip())
    return [p.strip() for p in parts if p.strip()]


def _split_scene_blocks(text: str) -> list[tuple[int, str, str]]:
    """Return list of (index, title, body_after_title)."""
    headers = list(_SCENE_HEADER_RE.finditer(text))
    if not headers:
        return []

    blocks: list[tuple[int, str, str]] = []
    for i, m in enumerate(headers):
        idx = int(m.group(1))
        title = (m.group(2) or "").strip()
        start = m.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        body = text[start:end]
        body = _NEXT_SCENE_OR_NOTES.split(body, maxsplit=1)[0]
        if not title:
            lines = body.lstrip("\n").split("\n", 1)
            title = lines[0].strip()
            body = lines[1] if len(lines) > 1 else ""
        blocks.append((idx, title, body.strip()))
    return blocks


def parse_script(raw: str) -> ParsedScript:
    text = raw.replace("\r\n", "\n").strip()
    title_m = _TITLE_RE.search(text)
    title = title_m.group(1).strip() if title_m else "Untitled Legend"

    notes_m = _NOTES_RE.search(text)
    notes = notes_m.group(1).strip() if notes_m else ""

    scenes: list[Scene] = []
    for idx, scene_title, rest in _split_scene_blocks(text):
        visual_m = _VISUAL_RE.search(rest)
        audio_m = _AUDIO_RE.search(rest)
        vo_m = _VO_RE.search(rest)

        voiceover = ""
        if vo_m:
            voiceover = vo_m.group(1).strip()
        else:
            chunks = re.split(r"\[Audio\]\s*:.+", rest, flags=re.IGNORECASE | re.DOTALL)
            if len(chunks) > 1:
                voiceover = chunks[-1].strip()

        voiceover = re.split(
            r"\nProduction Notes", voiceover, maxsplit=1, flags=re.IGNORECASE
        )[0].strip()

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


def validate_parsed(parsed: ParsedScript) -> None:
    """Raise ValueError if any scene is missing voiceover (incomplete parse)."""
    empty = [s.index for s in parsed.scenes if not (s.voiceover or "").strip()]
    if empty:
        raise ValueError(
            "Script parse incomplete: empty voiceover for scene(s) "
            + ", ".join(str(i) for i in empty)
            + ". Check that each Scene includes a [Voiceover] block."
        )
