# Codex → Claude: Muse demo release ready

Date: November 3, 2026
Owner: Claude — Vercel deployment and public smoke verification.

The Muse-first demo refinements are ready on main. Pull origin/main before deploying;
record the deployed commit with `git rev-parse HEAD` in your status report.

Files: src/api/static/index.html, README.md, docs/DEMO_VIDEO_SCRIPT.md.
Quality gate: make check passes 100 tests; lint and formatting clean.
The main recording path features Muse Spark research and creative planning, Muse Image
Product Visuals / Multi-Image Combine / Restore & Enhance, then Spark budget advice.
ComfyUI is optional. Vision and Voice remain outside the cached recording path.
No billed Muse requests were made for this release.

Deployment handoff:
- Deploy this main release using your authenticated Vercel session and intended team/project.
- Keep DEMO_MODE=true, with live unlock disabled. Cached-only hosting needs no Muse API key.
- Upgrade the installed Vercel CLI (62.2.0) to the current release before deployment when possible.
- Verify GET /, /portal, /api/v1/health, /api/v1/demo-presets, and the saved sample images.
- Verify cached competitor / draft / creative / bid responses without paid API calls;
  verify ?live=true without X-Demo-Key is rejected.
- Rehearse the three-minute script in docs/DEMO_VIDEO_SCRIPT.md: research → three image
  workflows → edit/preview → budget recommendation → planning pack.
- Report the public URL, deployed commit and smoke results in .tasks/claude-status.md.
- Do not edit the portal during deployment. Coordinate any blocker with Codex.

This handoff records readiness and assignments, not a deployment confirmation.
