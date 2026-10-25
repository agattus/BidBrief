# Sanatri Studio

Web app that turns your **Legends of Bharat** scene script into a downloadable episode.

## What it does

1. Parses your script (`Scene` / `[Visual Prompt]` / `[Audio]` / `[Voiceover]`)
2. Generates cinematic stills per scene
3. Generates English narration (edge-tts)
4. Burns subtitles + quiet original drone
5. Composes a 1080p cut + **phone MP4**
6. Gives a **Download** button (`Content-Disposition: attachment`)

## Run

```bash
cd sanatri-studio
pip install -r requirements.txt
# needs ffmpeg on PATH
uvicorn app.main:app --host 0.0.0.0 --port 8787
```

Open `http://localhost:8787` (or the forwarded port).

1. Paste script (or use **Load Jalandhara sample**)
2. **Generate episode**
3. Tap **Download phone MP4**

## Notes

- Image provider: Pollinations (no key). Swap later for your preferred API.
- Voice: edge-tts stand-in. Wire ElevenLabs George for channel house voice.
- Scene `[Audio]` cues are stored in the parse; richer SFX beds can be layered in a later version — download narration video and add BGM yourself if needed.
