# VisuSync AI — online MVP

Dark creative workspace with a FastAPI/SQLite backend. The backend uses FFprobe/FFmpeg for real media inspection and audio extraction. Transcription is performed through OpenAI Whisper only when `OPENAI_API_KEY` exists; no placeholder transcript is returned. Topic-based visual opportunities are generated from actual transcript text. Accepted suggestions become persistent clip records and caption clips render to a real MP4 while preserving source audio.

## Run locally

```bash
cd /home/node/visusync-ai
/home/node/.venv/bin/pip install -r backend/requirements.txt
/home/node/.venv/bin/uvicorn backend.app:app --host 0.0.0.0 --port 8000
# in another shell
cd frontend && npm install && npm run dev
```

Open port 3000. For transcription set `OPENAI_API_KEY` in the backend process environment. Uploads are local under `data/`; do not deploy this no-auth prototype with sensitive video or API keys. MP4/MOV max 2 GB. The current render path fully supports timed caption/text clips; image-overlay clips require a valid backend-local file path, and unresolved stock imagery is deliberately not fabricated.

## MVP milestones

- Projects: create/list, durable SQLite records.
- Upload: extension and stream validation, FFprobe metadata, JPEG thumbnail, mono 16kHz WAV extraction.
- Analysis: timestamped Whisper segments; explainable transcript-driven suggestion rules, no invented numbers; explicit 503 without provider key.
- Editing: transcript/suggestion review, accept/reject, persistent timeline clips, edit boundaries, delete.
- Export: real FFmpeg MP4 with source audio and enabled text/caption overlays; downloadable artifact.
- Future: replace deterministic topic matcher with structured LLM, add asset providers and image/diagram generation, job queue and render progress, auth and isolated storage.

Tests: `/home/node/.venv/bin/python -m pytest backend/tests -q`.