"""End-to-end job runner."""
from __future__ import annotations

import json
import traceback
from pathlib import Path

from .compose import (
    build_voice_track,
    compose_video,
    make_cues,
    make_score,
    mix_voice_score,
    probe_dur,
    write_subs,
)
from .images import generate_scene_image
from .script_parser import parse_script, validate_parsed
from .tts import generate_scene_vo


def run_job(job_dir: Path, script_text: str, progress_cb=None) -> Path:
    def progress(pct: int, msg: str) -> None:
        status = {"percent": pct, "message": msg, "state": "running"}
        (job_dir / "status.json").write_text(json.dumps(status))
        if progress_cb:
            progress_cb(pct, msg)

    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "script.txt").write_text(script_text)

    try:
        progress(2, "Parsing script…")
        parsed = parse_script(script_text)
        validate_parsed(parsed)
        (job_dir / "parsed.json").write_text(json.dumps(parsed.to_dict(), indent=2))

        images_dir = job_dir / "images"
        vo_root = job_dir / "vo"
        audio_dir = job_dir / "audio"
        out_dir = job_dir / "out"
        images_dir.mkdir(exist_ok=True)
        audio_dir.mkdir(exist_ok=True)
        out_dir.mkdir(exist_ok=True)

        all_parts: list[Path] = []
        all_pauses: list[float] = []
        all_sentences: list[str] = []
        image_paths: list[Path] = []

        n = max(1, len(parsed.scenes))
        for i, scene in enumerate(parsed.scenes):
            base = 5 + int(70 * i / n)
            progress(base, f"Scene {scene.index}: generating image — {scene.title}")
            img = images_dir / f"scene_{scene.index:02d}.jpg"
            generate_scene_image(scene.visual, scene.title, img)
            image_paths.append(img)

            progress(base + 2, f"Scene {scene.index}: generating narration…")
            parts, pauses, sentences = generate_scene_vo(
                scene.voiceover, vo_root / f"scene_{scene.index:02d}"
            )
            # Slightly longer pause between scenes
            if pauses:
                pauses[-1] = max(pauses[-1], 1.1)
            all_parts.extend(parts)
            all_pauses.extend(pauses)
            all_sentences.extend(sentences)

        progress(78, "Building voice track…")
        voice = audio_dir / "voice.wav"
        total, _, intro = build_voice_track(all_parts, all_pauses, voice)
        cues = make_cues(all_sentences, all_parts, all_pauses, intro=intro)
        # Recalculate total from actual voice file
        total = probe_dur(voice)

        srt = out_dir / "episode.srt"
        ass = out_dir / "episode.ass"
        write_subs(cues, srt, ass)

        progress(84, "Mixing original score bed…")
        score = audio_dir / "score.wav"
        mix = audio_dir / "mix.wav"
        make_score(total, score)
        mix_voice_score(voice, score, mix)

        progress(88, "Composing video…")
        mp4 = out_dir / "episode.mp4"
        compose_video(
            title=parsed.title,
            image_paths=image_paths,
            mix=mix,
            ass=ass,
            out_mp4=mp4,
            total=total,
        )

        # Phone-friendly copy
        progress(96, "Creating phone download…")
        phone = out_dir / "episode-phone.mp4"
        from .compose import run as _run

        _run(
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

        meta = {
            "title": parsed.title,
            "scenes": len(parsed.scenes),
            "duration": total,
            "files": {
                "full": "out/episode.mp4",
                "phone": "out/episode-phone.mp4",
                "srt": "out/episode.srt",
            },
        }
        (job_dir / "result.json").write_text(json.dumps(meta, indent=2))
        (job_dir / "status.json").write_text(
            json.dumps(
                {
                    "percent": 100,
                    "message": "Ready to download",
                    "state": "done",
                    "result": meta,
                }
            )
        )
        return mp4
    except Exception as e:
        (job_dir / "status.json").write_text(
            json.dumps(
                {
                    "percent": 0,
                    "message": str(e),
                    "state": "error",
                    "trace": traceback.format_exc(),
                }
            )
        )
        raise
