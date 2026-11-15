# VisuSync AI — source map

Full editable source is committed in this repository, not embedded in an archive:

- `backend/app.py` — FastAPI API, SQLite models, upload/FFmpeg, Whisper API transcription, transcript-based visual suggestions, clip editing and MP4 render/export.
- `backend/tests/test_core.py` — API and media pipeline tests.
- `backend/requirements.txt` — Python backend dependencies.
- `frontend/src/app/page.tsx` — Next.js dashboard and editing workspace.
- `frontend/src/app/globals.css` — dark responsive workspace styling.
- `frontend/src/app/layout.tsx` — app root and metadata.
- `frontend/package.json` and `frontend/package-lock.json` — frontend scripts and pinned dependency tree.
- `frontend/next.config.ts` — API proxy configuration.
- `frontend/tsconfig.json`, `frontend/next-env.d.ts` — TypeScript/Next configuration.
- `.env.example` — environment variable example.

Set `OPENAI_API_KEY` in the backend environment to enable Whisper transcription. Without it, analysis returns a clear configuration error and does not fabricate transcript results.