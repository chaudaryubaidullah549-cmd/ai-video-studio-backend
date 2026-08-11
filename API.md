# API Reference

Base URL: `http://localhost:8000` (or your deployed backend URL, exposed to
the frontend via `NEXT_PUBLIC_API_URL`).

All request/response bodies are JSON. All errors follow the envelope in
[Error format](#error-format).

---

## `POST /api/projects`

Creates a project from a single natural-language prompt. Does **not**
start generation - call `POST /api/projects/{id}/generate` separately.

**Request body:**
```json
{
  "prompt": "Create a cinematic fantasy story about a young warrior who discovers an ancient kingdom hidden beneath a mountain. Make it emotional, mysterious and action-packed.",
  "duration": 20,
  "style": "cinematic",
  "aspect_ratio": "16:9",
  "language": "en",
  "voice": "auto"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `prompt` | string | yes | 10-4000 characters |
| `duration` | integer | no | Target total seconds, default 20, clamped to `MAX_PROJECT_DURATION_SECONDS` (default 180) |
| `style` | string | no | Free text, default `"cinematic"` |
| `aspect_ratio` | string | no | `"16:9"` \| `"9:16"` \| `"1:1"`, default `"16:9"` |
| `language` | string | no | ISO-ish language code, default `"en"` |
| `voice` | string | no | Voice preference passed to the voice provider, default `"auto"` |

**Response `201 Created`:**
```json
{
  "id": "df66e720-f014-4c44-8d5c-baf3adbe13f8",
  "status": "planned",
  "prompt": "...",
  "settings": {
    "duration": 20,
    "style": "cinematic",
    "aspect_ratio": "16:9",
    "language": "en",
    "voice": "auto"
  },
  "story": null,
  "characters": [],
  "scenes": [],
  "final_video_url": null,
  "error": null,
  "created_at": "2026-08-08T16:22:40.832547",
  "updated_at": "2026-08-08T16:22:40.832552"
}
```

---

## `GET /api/projects/{project_id}`

Returns the complete project, including story, character bible, and every
scene (with generation prompts, status, and media URLs once available).

**Response `200 OK`:** full `Project` object (same shape as creation
response, populated as the pipeline progresses).

**Errors:** `404 NOT_FOUND` if the project doesn't exist.

---

## `GET /api/projects/{project_id}/status`

Lightweight polling endpoint - use this instead of the full project object
for frequent polling.

**Response `200 OK`:**
```json
{
  "id": "df66e720-f014-4c44-8d5c-baf3adbe13f8",
  "status": "generating_scenes",
  "progress_percent": 46,
  "current_step": "Generating video clips",
  "scenes_total": 4,
  "scenes_completed": 3,
  "scenes_failed": 0,
  "error": null,
  "updated_at": "2026-08-08T16:24:43.080887"
}
```

### Project status values (in order)

| Status | Meaning |
|---|---|
| `planned` | Project created, generation not yet started |
| `analyzing` | Story planning in progress |
| `generating_characters` | Character bible being built |
| `planning_scenes` | Scene breakdown in progress |
| `generating_scenes` | Per-scene video clips generating |
| `generating_audio` | Voice, music, and SFX generating |
| `editing` | Assembling normalized clips |
| `rendering` | Final FFmpeg render in progress |
| `completed` | Final MP4 ready - call `/download` |
| `failed` | Pipeline failed - see `error` field |

### Scene status values

| Status | Meaning |
|---|---|
| `pending` | Not yet started |
| `generating` | In progress |
| `completed` | Clip/audio generated successfully |
| `failed` | Generation failed after retries - see the scene's `error` field |

**Errors:** `404 NOT_FOUND` if the project doesn't exist.

---

## `POST /api/projects/{project_id}/generate`

Starts the full generation pipeline as a background task. Returns
immediately - the HTTP request is never blocked on generation.

**Response `202 Accepted`:** a `ProjectStatusResponse` (see above), status
`planned` or already in progress.

**Errors:**
- `404 NOT_FOUND` - project doesn't exist
- `409 CONFLICT` (`code: "CONFLICT"`, `retryable: false`) - generation is
  already running for this project

---

## `POST /api/projects/{project_id}/scenes/{scene_id}/regenerate`

Regenerates a single scene (video + voice + music + SFX) without
re-running the whole pipeline. Returns immediately; poll
`GET /api/projects/{id}` to see the scene's updated status.

**Request body (optional):**
```json
{ "instructions": "Make the lighting darker and more ominous" }
```

**Response `202 Accepted`:** the `Scene` object (status will typically
still show `pending`/`generating` immediately after this call - poll the
project to see the final result).

**Errors:**
- `404 NOT_FOUND` - project or scene doesn't exist
- `409 CONFLICT` - a regeneration is already running for this scene

---

## `GET /api/projects/{project_id}/download`

Streams the final MP4 file.

**Response `200 OK`:** `video/mp4` binary, `Content-Disposition:
attachment; filename="{project_id}.mp4"`.

**Errors:**
- `404 NOT_FOUND` - project doesn't exist, or the final file is missing
  from storage
- `409 CONFLICT` (`code: "VIDEO_NOT_READY"`, `retryable: true`) - the
  pipeline hasn't completed yet; check `/status`

---

## `GET /health`

Unauthenticated liveness/readiness check.

```json
{ "status": "ok", "mock_mode": true, "environment": "development" }
```

---

## Error format

Every error response follows this shape:

```json
{
  "error": {
    "code": "VIDEO_PROVIDER_ERROR",
    "message": "Human readable message",
    "retryable": true,
    "details": { "...": "optional, present on validation errors" }
  }
}
```

### Error codes

| Code | HTTP status | Retryable | Meaning |
|---|---|---|---|
| `VALIDATION_ERROR` | 422 | no | Request body failed validation |
| `NOT_FOUND` | 404 | no | Project/scene doesn't exist |
| `CONFLICT` | 409 | no | Operation already in progress |
| `VIDEO_NOT_READY` | 409 | yes | Download requested before render completed |
| `RATE_LIMIT_EXCEEDED` | 429 | yes | Too many requests from this client |
| `PROVIDER_AUTH_ERROR` | 401 | no | Bad/missing provider API key (check `HF_TOKEN`) |
| `PROVIDER_RATE_LIMIT` | 429 | yes | Upstream AI provider rate-limited us |
| `PROVIDER_TIMEOUT` | 504 | yes | Upstream AI provider took too long |
| `PROVIDER_UNAVAILABLE` | 503 | yes | Upstream AI provider unreachable/down |
| `INVALID_PROMPT` | 422 | no | Provider rejected the prompt |
| `VIDEO_PROVIDER_ERROR` | 502 | yes | Video generation failed |
| `VOICE_PROVIDER_ERROR` | 502 | yes | Voice generation failed |
| `MUSIC_PROVIDER_ERROR` | 502 | yes | Music/SFX generation failed (or unsupported - see README §3) |
| `RENDER_ERROR` | 500 | yes | FFmpeg assembly failed |
| `STORAGE_ERROR` | 500 | yes | File read/write failed |
| `FILE_VALIDATION_ERROR` | 422 | no | Uploaded/generated file failed validation |
| `REQUEST_TOO_LARGE` | 413 | no | Request body exceeded `MAX_REQUEST_BODY_BYTES` |
| `INTERNAL_ERROR` | 500 | yes | Unexpected server error |

A generation pipeline failure is never silently swallowed: if a stage
fails, `project.status` becomes `failed` and `project.error` (and the
`/status` response's `error` field) contains the human-readable reason.
Failed generation is never reported as `completed`.

---

## Data model reference

### Character (part of the Character Bible)

```json
{
  "id": "uuid",
  "name": "Kael",
  "role": "protagonist",
  "age": "24",
  "gender": "male",
  "physical_appearance": "lean and weathered, sun-tanned skin",
  "face_description": "sharp jawline, intense green eyes, a scar above one eyebrow",
  "hair": "short, dark, windswept",
  "clothing": "worn leather armor over a dark traveling cloak",
  "body_type": "athletic",
  "personality": "determined, guarded, secretly compassionate",
  "voice": { "tone": "gravelly", "pitch": "low", "pace": "measured", "accent": "neutral" },
  "important_props": ["ancient pendant", "iron shortsword"],
  "reference_image_url": null
}
```

### Scene

```json
{
  "id": "uuid",
  "index": 0,
  "title": "The Discovery",
  "duration": 5.0,
  "location": "a hidden cave entrance beneath the mountain",
  "time_of_day": "afternoon",
  "character_ids": ["..."],
  "action": "The hero discovers a mysterious ancient entrance carved into stone.",
  "dialogue": [{ "character_id": "...", "character_name": "Kael", "text": "This wasn't here before.", "emotion": "wary" }],
  "narration": "What they found beneath the mountain would change everything.",
  "camera_movement": "dolly_in",
  "shot_type": "medium",
  "lighting": "dim, shafts of light through rock",
  "visual_style": "cinematic, cool color grade, mysterious atmosphere",
  "audio_mood": "suspense",
  "negative_prompt": "blurry, distorted, extra limbs, disfigured, low quality, watermark, text overlay",
  "generation_prompt": "cinematic style video shot. medium shot, camera movement: dolly in. Setting: a hidden cave entrance beneath the mountain, afternoon. ... Character - Kael, 24 years old, male, athletic build, ...",
  "status": "completed",
  "provider_task_id": "...",
  "retry_count": 0,
  "error": null,
  "media": {
    "video_url": "http://localhost:8000/media/projects/{project_id}/scenes/{scene_id}/clip_raw.mp4",
    "voice_track_urls": ["..."],
    "music_url": "...",
    "sfx_urls": ["..."],
    "thumbnail_url": null
  }
}
```
