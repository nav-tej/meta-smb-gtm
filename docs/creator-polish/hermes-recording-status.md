# Muse Growth Studio — Demo Video Recording Status v2

## Video: `muse-demo-final-v2.mp4`

| Field | Value |
|-------|-------|
| Duration | 1:36 (voiceover-limited; content is 1:46) |
| Resolution | 1920×1080 |
| Video Codec | H.264 High, yuv420p, 25 fps, 415 kb/s |
| Audio Codec | AAC, 24kHz, mono, 98 kb/s |
| Size | 5.9 MB |
| Muse Models Used | `muse-image-1.0` (6 generated scenes) |
| Voiceover | OpenAI TTS (1:30 narration) |

### Scene Sequence

| Time | Image | Caption |
|------|-------|---------|
| 0:00 | Hero living room (Muse) | "My mom makes the art..." |
| 0:14 | Art studio (Muse) | "300 competitor pages analyzed..." |
| 0:28 | Research dashboard (Muse) | "Research: competitor watchlist..." |
| 0:42 | Research dashboard (Muse) | "Muse Spark: tell the story they skip..." |
| 0:56 | Creative brief (Muse) | "Create: Muse writes audience..." |
| 1:10 | Instagram phone (Muse) | "Share: social-ready image..." |
| 1:24 | Gallery display (Muse) | "Iterate: SAM 3.1 product isolation..." |
| 1:38 | Hero living room (Muse) | "Research. Create. Improve. Iterate..." |

### Source Images (generated via `muse-image-1.0`)

| File | Description | Size |
|------|-------------|------|
| `hero_living_room.png` | Warm collector living room with framed Ek Onkar, saffron/clay tones | 438KB |
| `art_studio.png` | Ek Onkar on easel in rustic studio, "Ek Onkar" text visible, paint cans | 777KB |
| `competitor_research.png` | Laptop dashboard with art market pricing charts | 333KB |
| `creative_brief.png` | Creative brief document + tablet showing ad copy draft | 533KB |
| `social_phone.png` | Instagram post on phone, colorful artwork, 12,458 likes | 445KB |
| `gallery_display.png` | Ek Onkar (red/gold) in museum with track lighting, gallery label | 391KB |

### Build Process

1. **Muse Image API** (`muse-image-1.0` via `api.meta.ai/v1`) generated 6 scene images
2. **ffmpeg** scaled images to 1920×1080, added captions
3. **Concatenated** 8 clips into 1:46 video
4. **Merged** with OpenAI TTS voiceover (1:30, `-shortest` → 1:36 final)

### Files

| Path | Description |
|------|-------------|
| `/Users/nav/meta-smb-gtm/docs/muse-demo-final-v2.mp4` | Final video (with voiceover) |
| `/Users/nav/.hermes/cache/scratch/muse-demo-final-v2.mp4` | Copy |
| `/Users/nav/.hermes/cache/scratch/demo-v2-scenes/` | All source images and intermediate clips |

### v3 Plan (requires ComfyCloud auth)

**Goal:** Convert static Muse images into animated video clips using image-to-video models.

| Step | Model | Purpose |
|------|-------|---------|
| 1. Animate hero | `luma-i2v` or `kling-i2v` | Subtle camera movement on living room scene |
| 2. Animate studio | `pika-i2v` | Slow pan across paint-covered easel |
| 3. Animate dashboard | `seedance` i2v | Subtle chart animation |
| 4. Animate brief | `luma-i2v` | Pan across tablet showing ad copy |
| 5. Animate phone | `runway-i2v` | Subtle screen glow |
| 6. Animate gallery | `moonvalley-i2v` | Slow dolly toward Ek Onkar |

**Auth needed:** `comfy cloud login` to access partner-model proxy.

### Future Iterations

- **Voice:** Use ElevenLabs emotional TTS for more engaging narration
- **Music:** Add subtle ambient background music (ACE-Step or ElevenLabs music)
- **Transitions:** Crossfade between clips (ffmpeg `xfade` filter)
- **Length:** Stretch to 3:00 by adding intro card + outro card + slower pacing
- **Animation:** ComfyCloud I2V for actual motion on key frames
- **Voice sync:** Lip-sync the artist using kling-lipsync
- **Gemini Veo 3:** When available, use for higher-quality video clips
- **Muse Video:** Direct video generation via Muse (future model)

### Muse Products Used

| Model | Purpose | Endpoint |
|-------|---------|----------|
| `muse-image-1.0` | Generated all 6 scene images | `/v1/images/generations` |
| `muse-spark-1.3` | *Not used in v2* (web app's built-in) | `/v1/responses` |
| `sam-3.1` | *Not used in v2* (web app's built-in) | `/v1/responses` |

**v3 recommendation:** Use Muse Image for still generation → Comfy partner I2V for animation → Ace-Step for music → Kling lipsync for narrator sync.

---

## v4 Status Update (Cinematic Neural Cut)

| Field | Value |
|-------|-------|
| Target File | `/Users/nav/meta-smb-gtm/docs/demo/muse-demo-hf-final.mp4` (and `docs/muse-demo-final.mp4`) |
| Duration | 1:52 (112.2s) |
| Resolution | 1920×1080 @ 30 fps |
| Video Codec | H.264 High Profile 4.1, `yuv420p` |
| Audio Codec | AAC 48 kHz stereo, 192 kbps |
| Container | `mp42` with `+faststart` (instant web & YouTube streaming) |
| Voiceover | Microsoft Azure Neural TTS (`en-US-AndrewNeural`) — documentary cadence |
| Music | Ambient chord bed (48 kHz stereo, low-pass 2 kHz, ducked under VO) |
| Transitions | 0.6s cross-dissolve (`xfade`) on all 8 scene boundaries |
| Motion | Continuous Ken Burns pan & zoom across UI elements |
| Captions | Frosted dark glass lower thirds + top-right `Saved demo outputs · no live calls` badge |
| HyperFrames Skills | Synced to `~/.agents/skills/` and `meta-smb-gtm/.agents/skills/` (`hyperframes`, `hyperframes-cli`, `hyperframes-registry`, `media-use`) |

