"""Scene still generation with Pollinations + local fallback."""
from __future__ import annotations

import asyncio
import hashlib
import subprocess
from pathlib import Path
from urllib.parse import quote

import aiohttp

FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
if not Path(FONT).exists():
    FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _prompt_for_scene(visual: str, title: str) -> str:
    base = visual.strip() or f"Cinematic mythological scene for {title}"
    suffix = (
        ", cinematic 16:9 Hindu mythology short film still, jeweled mukut, "
        "dramatic lighting, devotion atmosphere, no watermark, no text overlay"
    )
    return (base + suffix)[:900]


async def _download(url: str, dest: Path) -> None:
    timeout = aiohttp.ClientTimeout(total=90)
    headers = {"User-Agent": "SanatriStudio/1.0"}
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        async with session.get(url) as resp:
            resp.raise_for_status()
            data = await resp.read()
            if len(data) < 1000:
                raise RuntimeError("image too small")
            dest.write_bytes(data)


def _placeholder(dest: Path, title: str) -> Path:
    """Local cinematic placeholder so jobs never hard-fail on image APIs."""
    safe = title.replace(":", " -").replace("'", "")[:40]
    vf = (
        f"color=c=0x141c33:s=1280x720:d=1,"
        f"drawtext=fontfile={FONT}:text='SANATRI IMAGININGS':fontsize=36:"
        f"fontcolor=0xf3e6c8:x=(w-text_w)/2:y=h*0.38,"
        f"drawtext=fontfile={FONT}:text='{safe}':fontsize=28:"
        f"fontcolor=0xd4a017:x=(w-text_w)/2:y=h*0.38+50"
    )
    subprocess.check_call(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            vf,
            "-frames:v",
            "1",
            str(dest),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return dest


def generate_scene_image(visual: str, title: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    prompt = _prompt_for_scene(visual, title)
    seed = int(hashlib.md5(prompt.encode()).hexdigest()[:8], 16) % 100000
    urls = [
        "https://image.pollinations.ai/prompt/"
        + quote(prompt)
        + f"?width=1280&height=720&nologo=true&seed={seed}",
        "https://pollinations.ai/p/"
        + quote(prompt)
        + f"?width=1280&height=720&nologo=true&seed={seed}",
    ]

    async def try_all() -> bool:
        for url in urls:
            for attempt in range(2):
                try:
                    await _download(url, dest)
                    return True
                except Exception:
                    await asyncio.sleep(1.2 * (attempt + 1))
        return False

    ok = asyncio.run(try_all())
    if not ok or not dest.exists() or dest.stat().st_size < 1000:
        return _placeholder(dest, title)
    return dest
