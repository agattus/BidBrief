"""Voiceover generation (edge-tts stand-in; optional ElevenLabs later)."""
from __future__ import annotations

import asyncio
from pathlib import Path

import edge_tts

from .script_parser import split_voiceover_sentences


DEFAULT_VOICE = "en-US-AndrewNeural"
DEFAULT_RATE = "-6%"


async def _synth(text: str, out: Path, voice: str, rate: str) -> None:
    spoken = text.replace("—", ", ").replace("–", ", ")
    for attempt in range(4):
        try:
            await edge_tts.Communicate(spoken, voice, rate=rate).save(str(out))
            if out.exists() and out.stat().st_size > 400:
                return
        except Exception:
            await asyncio.sleep(1.0 * (attempt + 1))
    raise RuntimeError(f"TTS failed for: {text[:80]}")


def generate_scene_vo(
    voiceover: str,
    out_dir: Path,
    *,
    voice: str = DEFAULT_VOICE,
    rate: str = DEFAULT_RATE,
    pause_after_question: float = 1.6,
    pause_weighty: float = 1.0,
    pause_default: float = 0.45,
) -> tuple[list[Path], list[float], list[str]]:
    """Return (mp3_parts, pauses_after_each, sentences)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    sentences = [s for s in split_voiceover_sentences(voiceover) if s and s.strip()]
    if not sentences:
        sentences = [voiceover.strip()] if voiceover.strip() else ["The legend continues."]

    paths: list[Path] = []
    pauses: list[float] = []

    async def run_all() -> None:
        for i, sentence in enumerate(sentences, 1):
            path = out_dir / f"{i:02d}.mp3"
            await _synth(sentence, path, voice, rate)
            paths.append(path)
            if sentence.strip().endswith("?"):
                pauses.append(pause_after_question)
            elif any(
                k in sentence.lower()
                for k in ("betrayal", "immortal", "curse", "tulsi", "jalandhara")
            ):
                pauses.append(pause_weighty)
            else:
                pauses.append(pause_default)

    asyncio.run(run_all())
    return paths, pauses, sentences
