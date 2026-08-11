# AI Video Studio - Backend

Production backend/API for an AI video generation platform. A user submits
one natural-language prompt; the backend orchestrates story planning,
character design, scene breakdown, video/voice/music/SFX generation, and
final FFmpeg assembly into a downloadable MP4.

The frontend (built separately, e.g. with Lovable) talks to this backend
over a stable REST API - see [`API.md`](./API.md) for the full contract.

This has been built and verified end-to-end in `MOCK_MODE` (full pipeline
run: project creation → story → characters → scenes → video → audio →
render → a real, ffprobe-verified, playable H.264/AAC MP4).

---

## 1. Architecture

```
USER PROMPT
  -> STORY (story_service + LLMProvider)
  -> CHARACTER BIBLE (character_service + LLMProvider)
  -> SCENE PLAN (scene_service + LLMProvider)
  -> SHOT PROMPTS (built deterministically in code from the Character Bible,
                    NOT by the LLM - guarantees identical character
                    descriptions across every scene that references them)
  -> VIDEO GENERATION (video_service + VideoProvider)
  -> VOICE / DIALOGUE (voice_service + VoiceProvider)
  -> MUSIC (music_service + MusicProvider)
  -> SOUND EFFECTS (music_service + SoundEffectProvider)
  -> VIDEO EDITING / RENDERING (render_service, pure FFmpeg)
  -> FINAL MP4
```

Everything above is driven by `services/orchestration_service.py`, which is
invoked from a background task (`workers/generation_worker.py`) so
`POST /generate` returns immediately (`202 Accepted`) and the frontend
polls `GET /status`.

### Provider abstraction

No part of the application talks to Hugging Face (or any other AI vendor)
directly except the `providers/<kind>/*.py` adapters, all implementing the
interfaces in `providers/base.py`:

- `LLMProvider` - text generation (story/character/scene planning)
- `VideoProvider` - text-to-video / image-to-video
- `VoiceProvider` - speech + dialogue synthesis
- `MusicProvider` / `SoundEffectProvider` - mood-driven music and SFX
- `StorageProvider` - where generated files live

Swapping a provider (e.g. moving off Hugging Face, or onto a paid video
model) means adding a new class implementing the relevant interface and
registering it in that provider kind's `__init__.py` factory - no changes
anywhere else in the codebase.

### Directory layout

```
backend/
  app/
    main.py                  FastAPI app, middleware, error handlers
    config.py                All configuration (env-var driven)
    database.py               SQLAlchemy engine/session, ProjectRecord
    api/                      HTTP routers (projects, scenes, health)
    models/                   Pydantic request/response + domain models
    providers/
      base.py                 Abstract provider interfaces
      llm/                    HuggingFaceLLMProvider, MockLLMProvider
      video/                  HuggingFaceVideoProvider, MockVideoProvider
      voice/                  HuggingFaceVoiceProvider, MockVoiceProvider
      music/                  Procedural music/SFX provider (+ HF stub)
      storage/                LocalStorageProvider
    services/                 Business logic (story/character/scene/
                               video/voice/music/render/orchestration)
    workers/                  Background job runner (asyncio-based)
    utils/                    ffmpeg.py, logging.py, errors.py
  requirements.txt
  .env.example
  README.md                  (this file)
  API.md                     Full endpoint reference
```

---

## 2. Quick start (MOCK_MODE - no API keys needed)

`MOCK_MODE=true` runs the **entire** pipeline - story, characters, scenes,
video, voice, music, SFX, and final FFmpeg render - with zero external API
calls and zero cost. Every generated file is a real, playable MP4/WAV
produced locally by FFmpeg, so you can build and test the frontend against
a fully functional API before spending anything on real generation.

### Prerequisites

- Python 3.11+
- FFmpeg (with `ffmpeg` and `ffprobe` on your PATH)

### Install FFmpeg

**macOS (Homebrew):**
```bash
brew install ffmpeg
```

**Windows:**
1. Download a build from https://www.gyan.dev/ffmpeg/builds/ (the "essentials" or "full" release build).
2. Extract it, e.g. to `C:\ffmpeg`.
3. Add `C:\ffmpeg\bin` to your `PATH` environment variable (System Properties → Environment Variables → Path → New).
4. Open a new terminal and confirm: `ffmpeg -version`

**Linux (Ubuntu/Debian):**
```bash
sudo apt update && sudo apt install -y ffmpeg
```

**Linux (Fedora):**
```bash
sudo dnf install -y ffmpeg
```

Verify installation on any OS:
```bash
ffmpeg -version
ffprobe -version
```

### Set up the backend

**macOS / Linux:**
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Windows (PowerShell):**
```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The API is now live at `http://localhost:8000`. Interactive docs (Swagger
UI) are at `http://localhost:8000/docs`.

### Try it

```bash
# Create a project
curl -X POST http://localhost:8000/api/projects \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Create a cinematic fantasy story about a young warrior who discovers an ancient kingdom hidden beneath a mountain. Make it emotional, mysterious and action-packed.",
    "duration": 20,
    "style": "cinematic",
    "aspect_ratio": "16:9",
    "language": "en",
    "voice": "auto"
  }'
# -> {"id": "...", "status": "planned", ...}

# Start generation (returns immediately, runs in the background)
curl -X POST http://localhost:8000/api/projects/{id}/generate

# Poll status
curl http://localhost:8000/api/projects/{id}/status

# Once status == "completed", download the final MP4
curl http://localhost:8000/api/projects/{id}/download -o final.mp4
```

---

## 3. Running with real Hugging Face providers

Set `MOCK_MODE=false` and configure:

```env
MOCK_MODE=false
HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
HF_VIDEO_MODEL=Lightricks/LTX-Video-0.9.8-13B-distilled
HF_PROVIDER=auto
HF_LLM_MODEL=meta-llama/Llama-3.3-70B-Instruct
```

Create a token with **Inference Providers** permission at:
https://huggingface.co/settings/tokens/new?ownUserPermissions=inference.serverless.write&tokenType=fineGrained

### What's real vs. what's a documented stub

This backend was built by reading Hugging Face's current Inference
Providers documentation (not by guessing endpoints):

| Capability | Status | Notes |
|---|---|---|
| LLM (story/character/scene planning) | **Real** | Uses the documented OpenAI-compatible `POST https://router.huggingface.co/v1/chat/completions` endpoint directly over HTTPS. |
| Video (text-to-video) | **Real** | Uses the official `huggingface_hub.InferenceClient.text_to_video()` SDK method - there is no stable, provider-agnostic raw REST contract documented for this task, since each backing provider (fal-ai, Replicate, etc.) has its own job/polling shape that the SDK normalizes. |
| Video (image-to-video) | **Partial / documented limitation** | HF's Inference Providers task catalog does not currently document a generic `image-to-video` task. The adapter folds the reference description into the text prompt as a best-effort fallback and logs a warning; it does not claim true image conditioning. |
| Voice (text-to-speech) | **Real** | Uses `huggingface_hub.InferenceClient.text_to_speech()`. |
| Music / SFX | **Documented limitation, not implemented against HF** | No `text-to-music`/`text-to-audio` task is exposed via HF Inference Providers today (MusicGen etc. require `transformers` or a dedicated Inference Endpoint, not the serverless router this backend targets). `HuggingFaceMusicProvider` raises a clear, actionable error explaining this. The backend defaults to a procedural FFmpeg-based music/SFX provider instead - see `providers/music/mock_music.py` - which is genuinely functional, just not AI-generated. Swap in a real provider by implementing `MusicProvider`/`SoundEffectProvider` against your backend of choice and updating `providers/music/__init__.py`. |

**Character consistency**: no text- or even image-conditioned open video
model available today guarantees pixel-identical characters across
independently generated clips. This backend does everything it reasonably
can on the prompting side - every scene's `generation_prompt` is built by
deterministically concatenating the same `Character.visual_descriptor()`
string from the Character Bible - but it does not claim perfect
consistency, and `VideoProvider` is designed so a reference image can be
wired in for true image-to-video conditioning once you pick a provider
that supports it.

### Important operational notes for real mode

- The HF video/voice calls are **synchronous/blocking on the SDK side**
  (the call returns raw bytes once generation finishes - there's no
  documented generic polling endpoint at this task level). This backend
  runs those blocking calls in a worker thread with a timeout
  (`PROVIDER_TIMEOUT_SECONDS`, default 120s) so the async event loop never
  blocks.
- Retries, timeouts, and auth/rate-limit errors are normalized into the
  standard error envelope (`VIDEO_PROVIDER_ERROR`, `PROVIDER_TIMEOUT`,
  `PROVIDER_AUTH_ERROR`, `PROVIDER_RATE_LIMIT`, etc.) - see `API.md`.
- Generation is never silently marked successful on provider failure.

---

## 4. Database

SQLite by default (`DATABASE_URL=sqlite:///./data/app.db`), zero setup
required. A project (with its story, characters, and scenes) is stored as
one JSON document per row - this keeps the repository layer trivial while
still going through SQLAlchemy, so moving to Postgres is a one-line change:

```env
DATABASE_URL=postgresql+psycopg2://user:password@host:5432/ai_video_studio
```
```bash
pip install psycopg2-binary
```

If you later need to query *inside* scenes at the SQL level, promote
`scenes` to its own table - `services/project_repository.py` is the only
place that would need to change.

---

## 5. Background jobs

Generation runs as an in-process `asyncio` task (see
`workers/generation_worker.py`) - no Redis/Celery required to run this
locally. `OrchestrationService.run_pipeline()` always reloads project
state from the database at each stage rather than trusting in-memory
object identity, specifically so this can be swapped for a real task
queue (Celery/RQ/Arq) in a multi-process deployment without touching
business logic - a worker process just needs to call
`OrchestrationService().run_pipeline(project_id)`.

Per-scene video/audio generation runs with bounded concurrency
(`SCENE_CONCURRENCY = 3`) and each scene's persistence step is guarded by
a per-project `asyncio.Lock` to prevent lost updates when multiple scenes
finish at nearly the same time.

---

## 6. Security

- All secrets (`HF_TOKEN`, etc.) are environment-variable only, loaded via
  `app/config.py`, and never included in any API response.
- Structured logs redact any field whose name looks like a secret
  (`token`, `key`, `secret`, `password`, `authorization`) as
  defense-in-depth (see `utils/logging.py`).
- Request body size is capped (`MAX_REQUEST_BODY_BYTES`, default 2MB).
- A basic in-memory sliding-window rate limiter is applied per client IP
  (`RATE_LIMIT_REQUESTS` / `RATE_LIMIT_WINDOW_SECONDS`). This is
  process-local - for a multi-instance deployment, replace with a shared
  store (Redis) behind the same middleware interface.
- CORS origins are explicitly allow-listed via `CORS_ORIGINS` - update
  this with your Lovable frontend's origin(s) before deploying.
- Local storage paths are validated against path traversal
  (`LocalStorageProvider._resolve`).
- All errors return the standard JSON envelope and never leak internal
  stack traces or secrets.

---

## 7. Connecting the Lovable frontend

Point the frontend at this backend via:

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

(or your deployed backend URL). The full endpoint contract, request/response
shapes, and status values are documented in [`API.md`](./API.md). Add the
frontend's origin to `CORS_ORIGINS` in `.env`.

---

## 8. Deploying (Railway / Render)

The repo is deploy-ready as-is via the included `Dockerfile` - both
platforms build directly from it, so FFmpeg is installed correctly (their
default non-Docker buildpacks do **not** include FFmpeg, which would break
rendering).

### Render

1. Push this repo to GitHub (see below if you need help with that step).
2. In the Render dashboard: **New +** → **Blueprint**, then select the repo.
   Render reads `render.yaml` and provisions the service, a 5GB persistent
   disk mounted at `/app/storage` (needed because Render's default
   filesystem is ephemeral - without it, every redeploy wipes your SQLite
   DB and generated videos), and the env vars listed there.
3. In the service's **Environment** tab, set:
   - `HF_TOKEN` - your Hugging Face token (leave `MOCK_MODE=true` if you
     don't have one yet - the full pipeline still works, see README §2)
   - `PUBLIC_BASE_URL` - Render assigns your URL only after the first
     deploy (something like `https://ai-video-studio-backend.onrender.com`);
     copy it from the top of the service page and paste it in here, then
     redeploy so `/media` links in API responses resolve correctly.
   - `CORS_ORIGINS` - your actual Lovable frontend origin (the blueprint
     defaults to `*`, which is fine for testing but should be tightened
     before going live).
4. Render builds and deploys automatically on every push to your default
   branch. First build takes a few minutes (FFmpeg install + Python deps).

The disk requires at least the **Starter** plan - Render's free tier
doesn't support persistent disks, so on the free tier your data resets
on every redeploy/restart.

### Railway

1. Push this repo to GitHub.
2. In the Railway dashboard: **New Project** → **Deploy from GitHub repo**,
   select this repo. Railway detects `Dockerfile`/`railway.json`
   automatically and builds it.
3. Add a **Volume** (Project → your service → **Settings** → **Volumes**)
   mounted at `/app/storage` - same reasoning as Render: without it,
   generated videos and the SQLite DB don't survive a redeploy.
4. Set environment variables under **Variables**:
   ```
   MOCK_MODE=true                 (or false, with HF_TOKEN set below)
   ENVIRONMENT=production
   DEBUG=false
   DATABASE_URL=sqlite:////app/storage/data/app.db
   LOCAL_STORAGE_PATH=/app/storage
   HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxx
   CORS_ORIGINS=https://your-frontend-domain.com
   ```
   Railway auto-injects `PORT` (the Dockerfile's `CMD` already reads it)
   and a public domain - after the first deploy, go to **Settings** →
   **Networking** → **Generate Domain**, copy the resulting URL, and set:
   ```
   PUBLIC_BASE_URL=https://your-service.up.railway.app
   ```
   then redeploy.
5. Railway builds and deploys automatically on every push.

### If you need the repo on GitHub first

I can push this code to a GitHub repository for you if you create an
empty repo and either add me as a collaborator or share a fine-grained
personal access token with `contents:write` scoped to that repo - I can
then commit and push directly. Otherwise, the quickest path is:
```bash
cd backend
git init
git add .
git commit -m "AI Video Studio backend"
git branch -M main
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main
```

### Post-deploy checklist

- [ ] `GET https://<your-url>/health` returns `{"status": "ok", ...}`
- [ ] `PUBLIC_BASE_URL` matches the actual deployed URL exactly (scheme + host, no trailing slash)
- [ ] `CORS_ORIGINS` includes your frontend's real origin
- [ ] A persistent disk/volume is attached at `/app/storage` (or you've
      migrated to Postgres + S3 - see §4 and the `StorageProvider`
      interface - for a fully stateless, horizontally-scalable deployment)
- [ ] `HF_TOKEN` is set and `MOCK_MODE=false` if you want real generation
- [ ] Run through the smoke test in §2 ("Try it") against the deployed URL

---

## 9. Known limitations (by design, documented rather than hidden)

- Music/SFX generation is procedural (FFmpeg tones), not AI-generated,
  because no Hugging Face Inference Providers task for this exists today.
  See section 3.
- Image-to-video is a prompt-folding fallback, not true image
  conditioning, for the same reason.
- The in-memory rate limiter and background job runner are appropriate
  for a single-instance deployment; both have a documented upgrade path
  to shared infrastructure (Redis, a real task queue) for horizontal
  scaling.
- FFmpeg concatenation assumes all scene clips share codec/resolution
  (guaranteed by `render_service.py` normalizing every clip first).
