#!/usr/bin/env python3
"""Build original per-scene score/SFX beds (no copyrighted music) and mix under vocals."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BEDS = ROOT / "audio" / "beds"
SFX = ROOT / "audio" / "sfx"
STEMS = ROOT / "audio" / "stems" / "htdemucs" / "old_mix"
BEDS.mkdir(parents=True, exist_ok=True)
SFX.mkdir(parents=True, exist_ok=True)

TOTAL = json.loads((ROOT / "audio" / "timeline.json").read_text())["total"]
SCENES = [
    ("intro", 0.0, 8.0),
    ("hook", 8.0, 47.24),
    ("birth", 47.24, 90.474),
    ("secret", 90.474, 132.344),
    ("war", 132.344, 174.476),
    ("deception", 174.476, 212.296),
    ("fall", 212.296, 245.466),
    ("outro", 245.466, TOTAL),
]


def run(cmd: list[str]) -> None:
    subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def dur(path: Path) -> float:
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


def lavfi_wav(out: Path, duration: float, filter_complex: str, inputs: list[str]) -> None:
    cmd = ["ffmpeg", "-y", *inputs, "-t", f"{duration:.3f}", "-filter_complex", filter_complex, "-map", "[a]", "-ac", "1", "-ar", "48000", str(out)]
    run(cmd)


def silence(out: Path, duration: float) -> None:
    run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=48000:cl=mono",
            "-t",
            f"{duration:.3f}",
            "-c:a",
            "pcm_s16le",
            str(out),
        ]
    )


def fix_len(src: Path, out: Path, need: float) -> None:
    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-af",
            f"atrim=0:{need:.3f},apad=whole_dur={need:.3f},aresample=48000",
            "-ac",
            "1",
            str(out),
        ]
    )


def make_intro(d: float) -> Path:
    out = BEDS / "intro.wav"
    lavfi_wav(
        out,
        d,
        "[0:a]volume=0.08,lowpass=f=200[a0];[1:a]volume=0.05,lowpass=f=300[a1];"
        "[a0][a1]amix=inputs=2,afade=t=in:st=0:d=2,afade=t=out:st={fade}:d=1.5[a]".format(fade=max(0.5, d - 1.5)),
        [
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=55:sample_rate=48000:duration={d}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=82:sample_rate=48000:duration={d}",
        ],
    )
    return out


def make_hook(d: float) -> Path:
    base = BEDS / "hook_base.wav"
    lavfi_wav(
        base,
        d,
        # deep bass + ocean noise + heartbeat tremolo
        "[0:a]volume=0.7,lowpass=f=70,afade=t=in:st=0:d=0.12[b1];"
        "[1:a]volume=0.28,lowpass=f=110[b2];"
        "[2:a]highpass=f=60,lowpass=f=1000,volume=0.28[waves];"
        "[3:a]lowpass=f=100,tremolo=f=1.05:d=0.85,volume=0.45[hb];"
        "[waves][b1][b2][hb]amix=inputs=4:duration=first,volume=1.2,alimiter=limit=0.95[a]",
        [
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=36:sample_rate=48000:duration={d}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=48:sample_rate=48000:duration={d}",
            "-f",
            "lavfi",
            "-i",
            f"anoisesrc=color=brown:sample_rate=48000:duration={d}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=55:sample_rate=48000:duration={d}",
        ],
    )
    # tick
    tick = SFX / "tick.wav"
    lavfi_wav(
        tick,
        d,
        "[0:a]volume=0,aeval=0.2*gte(mod(t\\,1.0)\\,0)*lt(mod(t\\,1.0)\\,0.015)*sin(2*PI*1700*t):c=mono,volume=0.5[a]",
        ["-f", "lavfi", "-i", f"anullsrc=r=48000:cl=mono:d={d}"],
    )
    # thunder hits
    layers = [base, tick]
    for i, at in enumerate([0.25, 5.0, 14.0, 24.0, 34.0]):
        hit = SFX / f"thunder_{i}.wav"
        run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "anoisesrc=color=brown:sample_rate=48000:duration=1.6",
                "-af",
                "highpass=f=35,lowpass=f=650,volume=2.4,afade=t=in:st=0:d=0.03,afade=t=out:st=0.35:d=1.2",
                str(hit),
            ]
        )
        delayed = SFX / f"thunder_{i}_d.wav"
        sil = SFX / f"sil_{i}.wav"
        silence(sil, at)
        run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(sil),
                "-i",
                str(hit),
                "-filter_complex",
                f"[0:a][1:a]concat=n=2:v=0:a=1,apad=whole_dur={d}[a]",
                "-map",
                "[a]",
                str(delayed),
            ]
        )
        layers.append(delayed)

    out = BEDS / "hook.wav"
    inputs: list[str] = []
    for p in layers:
        inputs += ["-i", str(p)]
    n = len(layers)
    filt = "".join(f"[{i}:a]" for i in range(n)) + f"amix=inputs={n}:duration=first:normalize=0,volume=0.85,alimiter=limit=0.95[a]"
    run(["ffmpeg", "-y", *inputs, "-filter_complex", filt, "-map", "[a]", str(out)])
    return out


def make_birth(d: float) -> Path:
    out = BEDS / "birth.wav"
    half = d / 2
    lavfi_wav(
        out,
        d,
        "[0:a][1:a][2:a][3:a]amix=inputs=4,tremolo=f=3.2:d=0.4,volume=0.2,lowpass=f=2200,"
        f"afade=t=out:st={half}:d=3[choir];"
        "[4:a]lowpass=f=160,tremolo=f=3.1:d=0.9,volume=0.9,"
        f"afade=t=in:st={half-1.2}:d=2[drums];"
        "[choir][drums]amix=inputs=2:duration=first,volume=1.05,alimiter=limit=0.95[a]",
        [
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=220:sample_rate=48000:duration={d}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=277:sample_rate=48000:duration={d}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=330:sample_rate=48000:duration={d}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:sample_rate=48000:duration={d}",
            "-f",
            "lavfi",
            "-i",
            f"anoisesrc=color=pink:sample_rate=48000:duration={d}",
        ],
    )
    return out


def make_secret(d: float) -> Path:
    out = BEDS / "secret.wav"
    lavfi_wav(
        out,
        d,
        "[0:a]tremolo=f=5:d=0.45,volume=0.14,highpass=f=450,lowpass=f=2800[flute];"
        "[1:a]tremolo=f=4.6:d=0.35,volume=0.05,lowpass=f=3200[flute2];"
        "[2:a][3:a]amix=inputs=2,volume=0.18,lowpass=f=220[dark];"
        "[flute][flute2][dark]amix=inputs=3:duration=first,volume=1.05,alimiter=limit=0.9[a]",
        [
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=523.25:sample_rate=48000:duration={d}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=659.25:sample_rate=48000:duration={d}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=58:sample_rate=48000:duration={d}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=87:sample_rate=48000:duration={d}",
        ],
    )
    return out


def make_war(d: float) -> Path:
    out = BEDS / "war.wav"
    lavfi_wav(
        out,
        d,
        "[0:a][1:a][2:a]amix=inputs=3,tremolo=f=6.5:d=0.5,volume=0.38,lowpass=f=900[orch];"
        "[3:a]highpass=f=1500,lowpass=f=7000,tremolo=f=2.5:d=0.85,volume=0.35[metal];"
        "[4:a]highpass=f=250,lowpass=f=4500,tremolo=f=0.65:d=0.95,volume=0.45[light];"
        "[orch][metal][light]amix=inputs=3:duration=first,volume=1.2,alimiter=limit=0.95[a]",
        [
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=65:sample_rate=48000:duration={d}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=98:sample_rate=48000:duration={d}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=196:sample_rate=48000:duration={d}",
            "-f",
            "lavfi",
            "-i",
            f"anoisesrc=color=white:sample_rate=48000:duration={d}",
            "-f",
            "lavfi",
            "-i",
            f"anoisesrc=color=brown:sample_rate=48000:duration={d}",
        ],
    )
    return out


def make_deception(d: float) -> Path:
    """2s musical silence, then haunting strings."""
    out = BEDS / "deception.wav"
    lavfi_wav(
        out,
        d,
        "[0:a][1:a][2:a][3:a]amix=inputs=4,tremolo=f=4.0:d=0.55,volume=0.22,lowpass=f=1700,"
        f"afade=t=in:st=2.0:d=2.8,afade=t=out:st={max(3.0, d-2.2)}:d=2[a]",
        [
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=146.83:sample_rate=48000:duration={d}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=220:sample_rate=48000:duration={d}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=293.66:sample_rate=48000:duration={d}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=349.23:sample_rate=48000:duration={d}",
        ],
    )
    return out


def make_fall(d: float) -> Path:
    thunder = SFX / "fall_thunder.wav"
    run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anoisesrc=color=brown:sample_rate=48000:duration=2.4",
            "-af",
            "highpass=f=25,lowpass=f=700,volume=3.2,afade=t=in:st=0:d=0.02,afade=t=out:st=0.25:d=2.0",
            str(thunder),
        ]
    )
    out = BEDS / "fall.wav"
    lavfi_wav(
        out,
        d,
        "[0:a][1:a][2:a][3:a]amix=inputs=4,tremolo=f=5.2:d=0.6,vibrato=f=5.2:d=0.55,volume=0.2,lowpass=f=2600,"
        "afade=t=in:st=0.7:d=1.4[wail];"
        f"[4:a]apad=whole_dur={d}[th];"
        "[th][wail]amix=inputs=2:duration=first,volume=1.15,alimiter=limit=0.95[a]",
        [
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=349:sample_rate=48000:duration={d}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=415:sample_rate=48000:duration={d}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=523:sample_rate=48000:duration={d}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=622:sample_rate=48000:duration={d}",
            "-i",
            str(thunder),
        ],
    )
    return out


def make_outro(d: float) -> Path:
    out = BEDS / "outro.wav"
    lavfi_wav(
        out,
        d,
        "[0:a][1:a][2:a]amix=inputs=3,tremolo=f=0.3:d=0.7,volume=0.28,afade=t=out:st={bell_fade}:d=9[bells];"
        "[3:a][4:a]amix=inputs=2,volume=0.16,lowpass=f=180,afade=t=out:st={drone_fade}:d=11[drone];"
        "[bells][drone]amix=inputs=2:duration=first,volume=1.0[a]".format(
            bell_fade=max(1.0, d - 10), drone_fade=max(1.0, d - 12)
        ),
        [
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=528:sample_rate=48000:duration={d}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=792:sample_rate=48000:duration={d}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=1056:sample_rate=48000:duration={d}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=60:sample_rate=48000:duration={d}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=90:sample_rate=48000:duration={d}",
        ],
    )
    return out


MAKERS = {
    "intro": make_intro,
    "hook": make_hook,
    "birth": make_birth,
    "secret": make_secret,
    "war": make_war,
    "deception": make_deception,
    "fall": make_fall,
    "outro": make_outro,
}


def main() -> None:
    fixed: list[Path] = []
    for name, a, b in SCENES:
        need = b - a
        print(f"building {name} ({need:.2f}s)")
        raw = MAKERS[name](need)
        out = BEDS / f"{name}_fix.wav"
        fix_len(raw, out, need)
        fixed.append(out)

    inputs: list[str] = []
    for p in fixed:
        inputs += ["-i", str(p)]
    n = len(fixed)
    filt = "".join(f"[{i}:a]" for i in range(n)) + f"concat=n={n}:v=0:a=1[a]"
    score = BEDS / "full_score.wav"
    run(["ffmpeg", "-y", *inputs, "-filter_complex", filt, "-map", "[a]", str(score)])
    print("score", dur(score))

    vocals = STEMS / "vocals.wav"
    if not vocals.exists():
        raise SystemExit(f"missing vocals stem: {vocals}")

    # Mix: narration + scene audio with ducking under VO
    mixed = ROOT / "audio" / "mix_scene.wav"
    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(vocals),
            "-i",
            str(score),
            "-filter_complex",
            "[1:a]volume=0.72[score];"
            "[0:a]aformat=channel_layouts=mono,volume=1.15,asplit=2[v][side];"
            "[score][side]sidechaincompress=threshold=0.02:ratio=6:attack=20:release=420:makeup=1.4[ducked];"
            "[v][ducked]amix=inputs=2:duration=first:dropout_transition=0,loudnorm=I=-16:TP=-1.5:LRA=11[a]",
            "-map",
            "[a]",
            "-ar",
            "48000",
            "-ac",
            "1",
            str(mixed),
        ]
    )
    print("mix", dur(mixed), mixed)


if __name__ == "__main__":
    main()
