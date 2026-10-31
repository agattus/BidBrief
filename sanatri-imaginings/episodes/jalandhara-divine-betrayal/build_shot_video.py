#!/usr/bin/env python3
"""Compose shot-by-shot Jalandhara episode: one still + VO per shot."""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
from pathlib import Path

import edge_tts

ROOT = Path(__file__).resolve().parent
STUDIO = Path("/workspace/sanatri-studio")
sys.path.insert(0, str(STUDIO))

from pipeline.compose import (  # noqa: E402
    concat_wavs,
    compose_video,
    make_score,
    mix_voice_score,
    probe_dur,
    run,
    write_subs,
    INTRO,
)

SHOTS_META = ROOT / "shots.json"
SHOTS_DIR = ROOT / "shots"
BUILD = ROOT / "build_shots"
OUT = ROOT / "out"
VOICE = "en-US-AndrewNeural"
RATE = "-6%"


async def synth(text: str, out: Path) -> None:
    spoken = text.replace("—", ", ").replace("–", ", ").replace("...", ", ")
    for attempt in range(4):
        try:
            await edge_tts.Communicate(spoken, VOICE, rate=RATE).save(str(out))
            if out.exists() and out.stat().st_size > 400:
                return
        except Exception:
            await asyncio.sleep(1.0 * (attempt + 1))
    raise RuntimeError(f"TTS failed: {text[:60]}")


def pause_for(text: str, shot_id: str) -> float:
    t = text.strip()
    if t.endswith("?"):
        return 1.8
    if shot_id.startswith("1."):
        return 1.0
    if any(k in t.lower() for k in ("betrayal", "immortal", "curse", "tulsi", "jalandhara", "annihilation")):
        return 1.1
    return 0.55


def main() -> None:
    shots = json.loads(SHOTS_META.read_text())
    if BUILD.exists():
        shutil.rmtree(BUILD)
    vo_dir = BUILD / "vo"
    audio_dir = BUILD / "audio"
    out_dir = BUILD / "out"
    for d in (vo_dir, audio_dir, out_dir, OUT):
        d.mkdir(parents=True, exist_ok=True)

    image_paths: list[Path] = []
    all_parts: list[Path] = []
    all_pauses: list[float] = []
    all_sentences: list[str] = []

    async def make_all_vo() -> None:
        for i, shot in enumerate(shots, 1):
            img = SHOTS_DIR / shot["file"]
            if not img.exists():
                raise FileNotFoundError(img)
            image_paths.append(img)
            mp3 = vo_dir / f"{i:02d}_{shot['id'].replace('.', '-')}.mp3"
            print(f"VO {shot['id']}: {shot['vo'][:56]}…")
            await synth(shot["vo"], mp3)
            all_parts.append(mp3)
            all_pauses.append(pause_for(shot["vo"], shot["id"]))
            all_sentences.append(shot["vo"])

    asyncio.run(make_all_vo())
    # longer hold after last shot of each scene
    for i, shot in enumerate(shots):
        if i + 1 == len(shots) or shots[i + 1]["scene"] != shot["scene"]:
            all_pauses[i] = max(all_pauses[i], 1.15)

    # Build voice with intro silence + per-line pauses (reuse studio helpers)
    work = audio_dir / "vo_parts"
    work.mkdir(parents=True, exist_ok=True)
    chunks: list[Path] = []
    for i, (mp3, pause) in enumerate(zip(all_parts, all_pauses), 1):
        wav = work / f"{i:02d}.wav"
        run(["ffmpeg", "-y", "-i", str(mp3), "-ar", "48000", "-ac", "1", str(wav)])
        sil = work / f"sil_{i:02d}.wav"
        run(
            [
                "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono",
                "-t", str(pause), "-c:a", "pcm_s16le", str(sil),
            ]
        )
        chunks += [wav, sil]

    story = audio_dir / "voice_story.wav"
    concat_wavs(chunks, story)
    intro = audio_dir / "intro_silence.wav"
    end = audio_dir / "end_silence.wav"
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", str(INTRO), "-c:a", "pcm_s16le", str(intro)])
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", "6", "-c:a", "pcm_s16le", str(end)])
    voice = audio_dir / "voice.wav"
    concat_wavs([intro, story, end], voice)
    total = probe_dur(voice)

    # cues
    t = INTRO
    cues = []
    for sentence, part, pause in zip(all_sentences, all_parts, all_pauses):
        d = probe_dur(part)
        cues.append((t, t + d, sentence))
        t = t + d + pause

    srt = out_dir / "episode.srt"
    ass = out_dir / "episode.ass"
    write_subs(cues, srt, ass)

    print("Mixing score…")
    score = audio_dir / "score.wav"
    mix = audio_dir / "mix.wav"
    make_score(total, score)
    mix_voice_score(voice, score, mix)

    print(f"Composing video ({total:.1f}s, {len(image_paths)} shots)…")
    mp4 = out_dir / "episode.mp4"
    compose_video(
        title="The Demon Born From Shiva's Third Eye",
        image_paths=image_paths,
        mix=mix,
        ass=ass,
        out_mp4=mp4,
        total=total,
    )

    phone = out_dir / "episode-phone.mp4"
    run(
        [
            "ffmpeg", "-y", "-i", str(mp4), "-vf", "scale=1280:720",
            "-c:v", "libx264", "-crf", "26", "-preset", "fast",
            "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(phone),
        ]
    )

    final = OUT / "jalandhara-shot-by-shot.mp4"
    final_phone = OUT / "jalandhara-shot-by-shot-phone.mp4"
    shutil.copy2(mp4, final)
    shutil.copy2(phone, final_phone)
    shutil.copy2(srt, OUT / "jalandhara-shot-by-shot.srt")

    art = Path("/opt/cursor/artifacts")
    shutil.copy2(final, art / "DOWNLOAD-jalandhara-shot-by-shot-full.mp4")
    shutil.copy2(final_phone, art / "DOWNLOAD-jalandhara-shot-by-shot-phone.mp4")
    shutil.copy2(srt, art / "DOWNLOAD-jalandhara-shot-by-shot.srt")
    dl = Path("/workspace/Downloads")
    dl.mkdir(exist_ok=True)
    shutil.copy2(final, dl / "jalandhara-shot-by-shot-full.mp4")
    shutil.copy2(final_phone, dl / "jalandhara-shot-by-shot-phone.mp4")

    # also zip stills for optional DIY
    shots_zip = art / "DOWNLOAD-jalandhara-30-shots.zip"
    if shots_zip.exists():
        shots_zip.unlink()
    run(["zip", "-j", "-9", str(shots_zip), *[str(SHOTS_DIR / s["file"]) for s in shots]])

    meta = {
        "title": "The Demon Born From Shiva's Third Eye (shot-by-shot)",
        "shots": len(shots),
        "duration": round(total, 2),
        "full": str(final),
        "phone": str(final_phone),
    }
    (BUILD / "result.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
