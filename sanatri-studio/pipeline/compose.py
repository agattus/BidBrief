"""Compose 1080p Legends of Bharat episode from stills + VO."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
W, H, FPS = 1920, 1080, 30
XFADE = 0.25
INTRO = 8.0


def run(cmd: list[str]) -> None:
    subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def probe_dur(path: Path) -> float:
    return float(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=nw=1:nk=1",
                str(path),
            ]
        ).decode()
    )


def concat_wavs(paths: list[Path], out: Path) -> None:
    if len(paths) == 1:
        run(["ffmpeg", "-y", "-i", str(paths[0]), "-c:a", "pcm_s16le", str(out)])
        return
    # hierarchical batches
    tmp = out.parent / "tmp_concat"
    tmp.mkdir(parents=True, exist_ok=True)
    batch_outs: list[Path] = []
    B = 8
    for bi in range(0, len(paths), B):
        batch = paths[bi : bi + B]
        bout = tmp / f"b{bi:02d}.wav"
        inputs: list[str] = []
        for p in batch:
            inputs += ["-i", str(p)]
        n = len(batch)
        filt = "".join(f"[{i}:a]" for i in range(n)) + f"concat=n={n}:v=0:a=1[a]"
        run(["ffmpeg", "-y", *inputs, "-filter_complex", filt, "-map", "[a]", "-c:a", "pcm_s16le", str(bout)])
        batch_outs.append(bout)
    if len(batch_outs) == 1:
        bout = batch_outs[0]
        run(["ffmpeg", "-y", "-i", str(bout), "-c:a", "pcm_s16le", str(out)])
    else:
        inputs = []
        for p in batch_outs:
            inputs += ["-i", str(p)]
        n = len(batch_outs)
        filt = "".join(f"[{i}:a]" for i in range(n)) + f"concat=n={n}:v=0:a=1[a]"
        run(["ffmpeg", "-y", *inputs, "-filter_complex", filt, "-map", "[a]", "-c:a", "pcm_s16le", str(out)])


def build_voice_track(
    parts: list[Path],
    pauses: list[float],
    out_voice: Path,
) -> tuple[float, list[tuple[float, float, str]], float]:
    """Returns (total_duration, cues[(start,end,text)], intro_len)."""
    work = out_voice.parent / "vo_parts"
    work.mkdir(parents=True, exist_ok=True)
    chunks: list[Path] = []
    for i, (mp3, pause) in enumerate(zip(parts, pauses), 1):
        wav = work / f"{i:02d}.wav"
        run(["ffmpeg", "-y", "-i", str(mp3), "-ar", "48000", "-ac", "1", str(wav)])
        sil = work / f"sil_{i:02d}.wav"
        run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=48000:cl=mono",
                "-t",
                str(pause),
                "-c:a",
                "pcm_s16le",
                str(sil),
            ]
        )
        chunks += [wav, sil]

    story = out_voice.parent / "voice_story.wav"
    concat_wavs(chunks, story)

    intro = out_voice.parent / "intro_silence.wav"
    end = out_voice.parent / "end_silence.wav"
    run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=48000:cl=mono",
            "-t",
            str(INTRO),
            "-c:a",
            "pcm_s16le",
            str(intro),
        ]
    )
    run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=48000:cl=mono",
            "-t",
            "8",
            "-c:a",
            "pcm_s16le",
            str(end),
        ]
    )
    concat_wavs([intro, story, end], out_voice)

    # cues with intro offset — need sentence texts from caller via parts naming; rebuild times
    # We'll recompute using mp3 durations
    return probe_dur(out_voice), [], INTRO


def make_cues(
    sentences: list[str],
    parts: list[Path],
    pauses: list[float],
    intro: float = INTRO,
) -> list[tuple[float, float, str]]:
    t = intro
    cues = []
    for sentence, part, pause in zip(sentences, parts, pauses):
        d = probe_dur(part)
        cues.append((t, t + d, sentence))
        t = t + d + pause
    return cues


def write_subs(cues: list[tuple[float, float, str]], srt: Path, ass: Path) -> None:
    def ts(s: float) -> str:
        h = int(s // 3600)
        m = int((s % 3600) // 60)
        sec = int(s % 60)
        ms = int(round((s - int(s)) * 1000))
        if ms == 1000:
            sec += 1
            ms = 0
        return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"

    def ts_ass(s: float) -> str:
        h = int(s // 3600)
        m = int((s % 3600) // 60)
        sec = s % 60
        return f"{h}:{m:02d}:{sec:05.2f}"

    def wrap(text: str) -> str:
        if len(text) < 60:
            return text
        mid = len(text) // 2
        for i in range(mid, min(len(text), mid + 30)):
            if text[i] in " ,;":
                return text[:i].rstrip(" ,;") + "\\N" + text[i:].lstrip(" ,;")
        return text

    srt_lines = []
    for i, (a, b, text) in enumerate(cues, 1):
        srt_lines.append(f"{i}\n{ts(a)} --> {ts(b)}\n{text}\n")
    srt.write_text("\n".join(srt_lines) + "\n")

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Liberation Sans,40,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3.5,0,2,80,80,64,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = [
        f"Dialogue: 0,{ts_ass(a)},{ts_ass(b)},Default,,0,0,0,,{wrap(text)}"
        for a, b, text in cues
    ]
    ass.write_text(header + "\n".join(events) + "\n")


def make_score(duration: float, out: Path) -> None:
    """Quiet original drone under VO (no copyrighted music)."""
    run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=65:sample_rate=48000:duration={duration}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=98:sample_rate=48000:duration={duration}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=130:sample_rate=48000:duration={duration}",
            "-filter_complex",
            "[0:a]volume=0.12,lowpass=f=200[a0];"
            "[1:a]volume=0.07,lowpass=f=300[a1];"
            "[2:a]volume=0.04,lowpass=f=500,tremolo=f=0.2:d=0.4[a2];"
            "[a0][a1][a2]amix=inputs=3:duration=longest,volume=0.8[a]",
            "-map",
            "[a]",
            "-ac",
            "1",
            str(out),
        ]
    )


def mix_voice_score(voice: Path, score: Path, out: Path) -> None:
    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(voice),
            "-i",
            str(score),
            "-filter_complex",
            "[1:a]volume=0.45[d];"
            "[0:a]asplit=2[v][side];"
            "[d][side]sidechaincompress=threshold=0.02:ratio=5:attack=25:release=400:makeup=1.3[dd];"
            "[v]volume=1.05[vv];"
            "[vv][dd]amix=inputs=2:duration=first,alimiter=limit=0.95[a]",
            "-map",
            "[a]",
            "-ar",
            "48000",
            "-ac",
            "1",
            str(out),
        ]
    )


def compose_video(
    *,
    title: str,
    image_paths: list[Path],
    mix: Path,
    ass: Path,
    out_mp4: Path,
    total: float,
) -> Path:
    clips_dir = out_mp4.parent / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    # intro card + one clip per image + end card (reuse last/first atmosphere)
    assets = image_paths[:]
    if not assets:
        raise RuntimeError("No scene images")

    # Approximate equal share of story time after intro for each image
    story = max(8.0, total - INTRO - 6.0)
    per = story / len(assets)
    segments: list[tuple[Path, float, str | None]] = [
        (assets[0], INTRO, "intro"),
    ]
    for img in assets:
        segments.append((img, per, None))
    segments.append((assets[-1], 6.0, "end"))

    raw = sum(d for _, d, _ in segments)
    n = len(segments)
    needed = total + (n - 1) * XFADE
    scale = needed / raw
    segments = [(a, round(d * scale, 3), k) for a, d, k in segments]

    font = FONT if Path(FONT).exists() else "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    safe_title = title.replace(":", " -").replace("'", "")[:48]

    clip_paths: list[tuple[Path, float]] = []
    for i, (asset, dur, kind) in enumerate(segments):
        frames = int(dur * FPS) + 2
        if i % 2 == 0:
            z = f"min(1.35,1+0.35*on/{frames})"
            x = "(iw-ow)/2"
            y = f"(ih-oh)/2*(1-0.1*on/{frames})"
        else:
            z = f"min(1.35,1+0.35*on/{frames})"
            x = f"(iw-ow)/2*(0.9+0.1*on/{frames})"
            y = "(ih-oh)/2"
        if kind in ("intro", "end"):
            z = f"min(1.12,1+0.12*on/{frames})"
            x = "(iw-ow)/2"
            y = "(ih-oh)/2"
        vf = (
            f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
            f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={W}x{H}:fps={FPS},"
            f"trim=duration={dur},setpts=PTS-STARTPTS,format=yuv420p"
        )
        if kind == "intro":
            vf += (
                f",drawtext=fontfile={font}:text='SANATRI IMAGININGS':fontsize=64:"
                f"fontcolor=white:borderw=3:bordercolor=black@0.85:x=(w-text_w)/2:y=(h-text_h)/2-40,"
                f"drawtext=fontfile={font}:text='Presents':fontsize=40:"
                f"fontcolor=white@0.92:borderw=2:bordercolor=black@0.8:x=(w-text_w)/2:y=(h-text_h)/2+36"
            )
        if kind == "end":
            vf += (
                f",drawtext=fontfile={font}:text='SANATRI IMAGININGS':fontsize=52:"
                f"fontcolor=white:borderw=3:bordercolor=black@0.85:x=(w-text_w)/2:y=h*0.68,"
                f"drawtext=fontfile={font}:text='Legends of Bharat':fontsize=34:"
                f"fontcolor=white@0.92:borderw=2:bordercolor=black@0.8:x=(w-text_w)/2:y=h*0.68+56"
            )
        clip = clips_dir / f"c{i:02d}.mp4"
        run(
            [
                "ffmpeg",
                "-y",
                "-loop",
                "1",
                "-i",
                str(asset),
                "-vf",
                vf,
                "-t",
                str(dur),
                "-an",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-preset",
                "veryfast",
                "-crf",
                "22",
                str(clip),
            ]
        )
        clip_paths.append((clip, dur))

    inputs: list[str] = []
    for p, _ in clip_paths:
        inputs += ["-i", str(p)]
    offset = clip_paths[0][1] - XFADE
    offsets = [offset]
    for _, d in clip_paths[1:-1]:
        offset = offset + d - XFADE
        offsets.append(offset)

    fc = []
    prev = "[0:v]"
    for i in range(1, n):
        lab = f"[v{i}]" if i < n - 1 else "[vx]"
        fc.append(
            f"{prev}[{i}:v]xfade=transition=fade:duration={XFADE}:offset={offsets[i-1]:.3f}{lab}"
        )
        prev = lab
    # soft title sting
    fc_str = ";".join(fc) + f";[vx]ass={ass}[vout]"

    run(
        [
            "ffmpeg",
            "-y",
            *inputs,
            "-i",
            str(mix),
            "-filter_complex",
            fc_str,
            "-map",
            "[vout]",
            "-map",
            f"{n}:a",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "fast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-t",
            str(total),
            "-movflags",
            "+faststart",
            str(out_mp4),
        ]
    )
    return out_mp4
