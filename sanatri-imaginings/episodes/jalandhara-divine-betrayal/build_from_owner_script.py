#!/usr/bin/env python3
"""Build Jalandhara episode from owner script + locked high-quality stills."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STUDIO = Path("/workspace/sanatri-studio")
sys.path.insert(0, str(STUDIO))

from pipeline.compose import (  # noqa: E402
    build_voice_track,
    compose_video,
    make_cues,
    make_score,
    mix_voice_score,
    probe_dur,
    run,
    write_subs,
)
from pipeline.script_parser import parse_script, validate_parsed  # noqa: E402
from pipeline.tts import generate_scene_vo  # noqa: E402

SCRIPT = ROOT / "owner-script-full.txt"
ASSETS = ROOT / "assets"
BUILD = ROOT / "build"
OUT = ROOT / "out"

# Rich visual mapping: multiple locked stills per scene (good Cursor gens)
SCENE_IMAGES = {
    1: ["jal-01-third-eye.jpg", "jal-02-fire-ocean.jpg"],
    2: ["jal-03-indra.jpg", "jal-04-shiva-fury.jpg", "jal-05-birth.jpg"],
    3: ["jal-06-emperor.jpg", "jal-07-vrinda.jpg"],
    4: ["jal-08-war.jpg", "jal-09-shiva-duel.jpg", "jal-10-shield.jpg"],
    5: ["jal-11-forest.jpg", "jal-12-reveal.jpg"],
    6: ["jal-13-vrinda-rage.jpg", "jal-14-fall.jpg", "jal-15-curse.jpg"],
    7: ["jal-16-tulsi-shaligram.jpg", "jal-17-logo-bg.jpg"],
}


def main() -> None:
    script_text = SCRIPT.read_text()
    parsed = parse_script(script_text)
    validate_parsed(parsed)
    print(f"Parsed {len(parsed.scenes)} scenes — {parsed.title}")

    if BUILD.exists():
        shutil.rmtree(BUILD)
    vo_root = BUILD / "vo"
    audio_dir = BUILD / "audio"
    images_dir = BUILD / "images"
    out_dir = BUILD / "out"
    for d in (vo_root, audio_dir, images_dir, out_dir, OUT):
        d.mkdir(parents=True, exist_ok=True)

    (BUILD / "parsed.json").write_text(json.dumps(parsed.to_dict(), indent=2))

    all_parts: list[Path] = []
    all_pauses: list[float] = []
    all_sentences: list[str] = []
    image_paths: list[Path] = []

    for scene in parsed.scenes:
        names = SCENE_IMAGES.get(scene.index) or [f"jal-{scene.index:02d}.jpg"]
        for name in names:
            src = ASSETS / name
            if not src.exists():
                raise FileNotFoundError(src)
            dest = images_dir / f"s{scene.index:02d}_{src.stem}.jpg"
            shutil.copy2(src, dest)
            image_paths.append(dest)
        print(f"  Scene {scene.index}: {len(names)} stills + VO…")
        parts, pauses, sentences = generate_scene_vo(
            scene.voiceover, vo_root / f"scene_{scene.index:02d}"
        )
        if pauses:
            pauses[-1] = max(pauses[-1], 1.2)
        # Extra breath after rhetorical questions in the hook
        if scene.index == 1:
            for i, s in enumerate(sentences):
                if s.strip().endswith("?"):
                    pauses[i] = max(pauses[i], 1.8)
        all_parts.extend(parts)
        all_pauses.extend(pauses)
        all_sentences.extend(sentences)

    print("Building voice track…")
    voice = audio_dir / "voice.wav"
    _, _, intro = build_voice_track(all_parts, all_pauses, voice)
    total = probe_dur(voice)
    cues = make_cues(all_sentences, all_parts, all_pauses, intro=intro)

    srt = out_dir / "episode.srt"
    ass = out_dir / "episode.ass"
    write_subs(cues, srt, ass)

    print("Mixing score…")
    score = audio_dir / "score.wav"
    mix = audio_dir / "mix.wav"
    make_score(total, score)
    mix_voice_score(voice, score, mix)

    print(f"Composing video ({total:.1f}s, {len(image_paths)} stills)…")
    mp4 = out_dir / "episode.mp4"
    compose_video(
        title=parsed.title,
        image_paths=image_paths,
        mix=mix,
        ass=ass,
        out_mp4=mp4,
        total=total,
    )

    phone = out_dir / "episode-phone.mp4"
    print("Phone export…")
    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(mp4),
            "-vf",
            "scale=1280:720",
            "-c:v",
            "libx264",
            "-crf",
            "26",
            "-preset",
            "fast",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(phone),
        ]
    )

    # Publish into episode out/ and artifacts
    final = OUT / "jalandhara-divine-betrayal.mp4"
    final_phone = OUT / "jalandhara-divine-betrayal-phone.mp4"
    shutil.copy2(mp4, final)
    shutil.copy2(phone, final_phone)
    shutil.copy2(srt, OUT / "jalandhara-divine-betrayal.srt")
    shutil.copy2(ass, OUT / "jalandhara-divine-betrayal.ass")

    artifacts = Path("/opt/cursor/artifacts")
    artifacts.mkdir(parents=True, exist_ok=True)
    shutil.copy2(final, artifacts / "DOWNLOAD-jalandhara-full.mp4")
    shutil.copy2(final_phone, artifacts / "DOWNLOAD-jalandhara-phone.mp4")
    shutil.copy2(srt, artifacts / "DOWNLOAD-jalandhara.srt")
    downloads = Path("/workspace/Downloads")
    downloads.mkdir(parents=True, exist_ok=True)
    shutil.copy2(final, downloads / "jalandhara-divine-betrayal-full.mp4")
    shutil.copy2(final_phone, downloads / "jalandhara-divine-betrayal-phone.mp4")
    shutil.copy2(srt, downloads / "jalandhara-divine-betrayal.srt")

    meta = {
        "title": parsed.title,
        "scenes": len(parsed.scenes),
        "stills": len(image_paths),
        "duration": round(total, 2),
        "full": str(final),
        "phone": str(final_phone),
    }
    (BUILD / "result.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
