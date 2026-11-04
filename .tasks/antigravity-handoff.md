# Antigravity / Gemini Handoff (`2026-11-03 18:12 PT`)

## Clean Handoff Baseline
- **Git (`origin/main`):** `6f4d66f` pushed (`100 passed` in `pytest`, `0` ruff errors).
- **Working Tree Note:** Codex currently has active unstaged edits in `.gitignore`, `AGENTS.md`, `README.md`, `docs/DEMO_VIDEO_SCRIPT.md`, and `src/api/static/index.html`. **Do not `git checkout` or overwrite those files.**
- **Local Dev Server:** `uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --reload` has been serving `http://localhost:8000/`. If the Antigravity session closes, restart locally with `make dev`.
- **Obsidian Vault (`/Users/nav/Documents/Obsidian Vault`):** Updated `Welcome.md`, `Meta Hackathon.md`, `nPlus1 Ventures.md`, and `Log.md` with `6f4d66f` (`100 passed`). Remember to keep updating `[[Log]]` and `[[Meta Hackathon]]` after Vercel deploy and video recording.

## Role Reassignments (Zero File Collisions)
1. **Codex (Lead Integrator — owns `src/api/static/index.html`, `README.md`, `docs/DEMO_VIDEO_SCRIPT.md`, `AGENTS.md`):**
   - Finish committing and pushing current working-tree edits, run `make check`, and record final Vercel URL in Obsidian `[[Meta Hackathon]]` + `[[Log]]`.
2. **Claude Code (P0 Release & Browser QA — owns Vercel CLI deploy + Playwright browser verification):**
   - Complete `npx vercel login` / `npx vercel deploy --prod --yes --env DEMO_MODE=true` from an authenticated terminal (note: strip or lower `maxDuration: 300` in `vercel.json` if deploying on Vercel Hobby tier, which caps serverless functions at 60s).
   - Run real browser smoke checks on the production URL (`/`, `/api/v1/health`, `/api/v1/demo-presets`, all `/samples/*` images, workspace switch, Phase 1 -> Phase 2 cached preview, CSV upload, and `403` spending guard on `/api/v1/audit-screenshot` & `/api/v1/transcribe-voice`), and write `.tasks/claude-status.md`.
3. **Gemini CLI / Lighter Gemini Model (Backend & Submission Packaging — owns `tests/`, `scripts/`, and submission copy):**
   - Keep `make check` (`100+ passed`) green as Codex/Claude land commits.
   - Draft the Cerebral Valley submission form text (project summary, judging-criteria bullets, architecture notes) into `docs/SUBMISSION_FORM_COPY.md` so Nav can paste it in 60 seconds tomorrow before 6:00 PM PT / 9:00 PM ET.
4. **Hermes on Mac Studio (P1 Optional Local ComfyUI Reel & Local Model Routing — owns `data/samples/*.mp4` & `workflows/`):**
   - `git pull --rebase origin main` (`6f4d66f`+).
   - If local ComfyUI (`127.0.0.1:8188`) is up on the Mac Studio, render a 5-second collector reel (`data/samples/ek_onkar_collector_reel.mp4`) from `data/samples/ek_onkar_collector_room_live.webp` using `workflows/ltx2_5_dfr_i2v.json` or `workflows/minimax_h3_i2v.json`, and write `.tasks/hermes-status.md`. Never block recording.
