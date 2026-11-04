# Claude five-hour sprint status: release-risk audit (first pass)

- **Base SHA:** `f245d51b16718a50103c45fef5a2a8747ec9937c` (main), with the shared tree dirty:
  - `src/api/media_delivery.py`: the pending fix under review here.
  - `creator.html` / `creator.js`: import UX.
  - `README.md` and `docs/DEMO_VIDEO_SCRIPT.md`: my earlier wording edits, uncommitted.
  - AGENTS/CODEX/Hermes docs.
- **Owned file:** this one only. There were no runtime edits, commits, pushes, paid calls, `.env` reads, limiter changes or deployments.
- **Method:** code reading only (git diff, grep, sed). I ran no tests and started no server.

## Summary

| # | Risk | Severity | Status |
|---|---|---|---|
| 1 | Live `/create` can be billed but deliver no image (double-prefixed output path) | Release blocker for any live segment | The pending working-tree fix resolves the default local case. It is untested, and it still fails when the server's cwd is not the repo root |
| 2 | With `DEMO_MODE=false` locally, every `/` portal button is a billed call, while the portal text says "demo mode / 0 credits" | Credit-safety gate violation | Open. Workaround: run with `DEMO_MODE=true` |
| 3 | Other paid-but-no-image or wasted-credit paths in live `/create` | Medium | Open. Bounded fixes are listed below |

Credit safety holds when `DEMO_MODE=true` or `VERCEL` is set:
- Every Muse-calling route is gated.
- `/create` saved mode never sends a generate request.
- Anonymous `?live=true` gets 403.

Details are under item 2.

---

## 1. Paid-but-no-image: double-prefixed output path

**Code evidence**
- `src/services/ad_creative.py:404`: `out_dir = Path(get_settings().output_dir)`. The default is `"outputs"` (`src/config.py`, `.env.example:28`), which is relative to the process cwd.
- `src/services/ad_creative.py:154-156`: `_save_artifact` returns `str(output_dir / name)`, for example `outputs/<slug>-<token>.png`. That is cwd-relative, not absolute.
- `src/api/media_delivery.py:51-56` (committed in `f245d51`): `output_root()` resolves a relative `output_dir` against the repo root, giving `<repo>/outputs`.
- `src/api/media_delivery.py` in committed `f245d51` (`_resolve_inside`): `root / candidate`, so the lookup is `<repo>/outputs/outputs/<file>.png`. That path doesn't exist, so the function returns `None` and `media_data_url` stays null.
- `src/api/static/creator.js:160`: with no inline data, it shows "Muse completed the request, but this server has not delivered a usable inline image". By then both billed calls have finished: SAM 3.1 at `ad_creative.py:424-430` and Muse Image at `ad_creative.py:454-459`.
- Why the tests missed it: `tests/test_live_media_delivery.py` only passes absolute `image_path` values (grep finds no relative-path case).

**Repro (committed f245d51; do not run live without a spending allowance)**
1. `OUTPUT_DIR` unset or `outputs`, `DEMO_MODE=false`, provider key set. Start with `make dev` from the repo root.
2. `/create` → Ek Onkar → write copy → presenter settings → live on → **Create my image**.
3. Expected: 2 billed calls, then the creator error at `creator.js:160`. The file exists at `<repo>/outputs/<file>.png`.
4. Offline equivalent (no spend):
   - Set `OUTPUT_DIR=outputs`.
   - `chdir` to a temp dir containing `outputs/x.png` with PNG magic bytes.
   - Set the root to `<tmp>/outputs`.
   - Call `_resolve_inside("outputs/x.png", root)`. Committed code returns `None`.

**Pending working-tree fix** (`src/api/media_delivery.py:59-76`, uncommitted, author not recorded)
- It tries the cwd-relative path first, then the root-relative one, and keeps the `is_relative_to(root)` containment check on each.
- Correct for the default `make dev` case (cwd is the repo root), and the traversal/symlink protection is preserved.
- Residual gap: if uvicorn starts from another cwd, the service writes to `<cwd>/outputs`, which is outside `<repo>/outputs`, and returns `None` again. In that case `/outputs` static serving (`src/api/main.py`, repo-root based) also misses the file. Vercel is unaffected because `/tmp/outputs` is absolute.

**Smallest proposed fixes**
- **Required:** add one offline test to `tests/test_live_media_delivery.py` with `monkeypatch.chdir(tmp_path)`, `OUTPUT_DIR=outputs`, `image_path="outputs/x.png"`, and an assertion that `media_mime_type == "image/png"`. This locks in the pending fix.
- **Optional root-cause fix (one line, owner Codex):** in `ad_creative.py:404`, use `media_delivery.output_root()` (or the same repo-root resolution) so the service always writes and returns absolute paths. Writer, reader and `/outputs` mount then agree regardless of cwd.
- **Operator workaround with no code change:** set `OUTPUT_DIR` to the absolute repo `outputs` path.

## 2. Saved/live credit safety

**Gate**
- `src/api/demo.py:48-49` returns `True` (live) for every request when `DEMO_MODE=false` and the app is not hosted. No `?live=true` and no key are needed.
- Otherwise:
  - Without `?live=true`, the request gets saved results.
  - `?live=true` without a valid `X-Demo-Key` gets 403 (`demo.py:52-57`), checked with `hmac.compare_digest`.
  - A valid key consumes one hourly slot (`demo.py:58`).

**Paid routes** (every Muse call path found by grepping `get_meta_client`), all gated by `LiveMode`:
- `analyze-competitors`: `intel.py:67-71`.
- `audit-seller`: `intel.py:77-79`, deterministic fallback.
- `audit-screenshot`: `intel.py:190-192`, 403 in demo.
- `transcribe-voice`: `creative.py:64-66`.
- `generate-ads` draft and generate: `creative.py:86-95`.
- `bid-advice`: `bids.py:37-41`.
- `bid-advice/csv`: `bids.py:48-66`, deterministic branch first.
- `ingest-storefront` (`intel.py:87-`) only crawls and calls no Muse model.
- No ungated Muse caller found.

**`/create` is safe in saved mode**
- `creator.js:146` (draft) and `creator.js:152` (generate) return before any fetch when `state.live` is false.
- Its only other fetches are free: `ingest-storefront`, `demo-presets` and `readiness` (`creator.js:91,180`).
- `creator.js:159` rejects a `demo-cache` result when live was expected.

**Issue 2a: `/` bills silently and is labelled "demo"**
- Evidence:
  - `index.html` never sends `?live=true` or a key: its `portalFetch` calls are at lines 1890, 1921, 2033, 2072, 2099, 2190 and 2331.
  - With `DEMO_MODE=false` locally, each of those button clicks is billed because of `demo.py:48`.
  - The visible text still says "Demo mode uses saved sample copy (0 image credits used)" (`index.html:1947`). Lines 1294 and 1460 say no new image and samples only.
  - Page load is free: `loadPresets` at `index.html:1862-1879` only calls `demo-presets`.
- Repro (no spend needed to confirm by reading):
  1. Run with `DEMO_MODE=false` and a key.
  2. Open `/`, then Step 1 → **Load competitor brief**.
  3. The server logs `Meta API call: chat …` (`src/clients/meta.py`) and the portal shows the result as if saved.
  4. `GET /api/v1/readiness` reports `default_mode: "live"` (`main.py:53-58`), but `/` never reads it.
- Smallest fix (Codex owns `index.html`): fetch `/api/v1/readiness` once and, when `default_mode === "live"`, show a persistent "Live server: buttons make billed Muse calls" banner and drop the "0 credits" text.
- Stricter alternative, server-side and one line (needs Nav's sign-off because it changes the local workflow): require `?live=true` even when `DEMO_MODE=false` (`demo.py:48-49`). `/` then always gets saved results, and only `/create`'s explicit toggle spends.
- **Operator gate for today:** record and rehearse with `DEMO_MODE=true` (plus a blank provider key for offline rehearsal, as the sprint plan says). This makes `/` saved-only by construction.

**Issue 2b: the hourly cap counts requests, not Muse calls**
- `demo.py:58` reserves one slot per HTTP request.
- One live `/create` generate makes at least 2 billed calls: SAM at `ad_creative.py:424-430` and Muse Image at `ad_creative.py:454`.
- One draft makes 1 Spark call, plus up to one validation retry (`meta.py:237-251`).
- So `LIVE_CALLS_PER_HOUR=5` allows about 10 billed calls. Documentation only; I am not proposing a limiter change.

## 3. Other paid-but-no-image or wasted-credit paths (live `/create`)

- **a. SAM call wasted in `product_visuals` mode.** `ad_creative.py:424-430` always runs SAM when a photo is supplied, but the `muse_workflow_mode != "default"` branch (`:454-459`) never uses `mask_bytes`. That is one billed call per generate with no effect on the image.
  - Smallest fix (Codex/service owner): guard segmentation with `if artwork_bytes is not None and (request.muse_workflow_mode == "default" or request.use_comfyui)`.
  - Then update `estimated_paid_calls: 2` in `creator.js` to 1.
- **b. 413 after billing.** `creative.py` raises 413 from `attach_inline_media` after Muse has already been paid. Generated files over about 2.9 MB raw exceed the 4,000,000-byte budget.
  - The file stays on disk, but the 413 body omits `image_path`, so a local presenter cannot recover it.
  - Smallest fix: add `image_paths` to the 413 detail (local recovery only).
- **c. Client timeout.** `creator.js:133` aborts at 285 s. The server call continues and is billed, and the UI message already says so. No fix; the rehearsal should measure real latency.
- **d. Non-image bytes.** If Muse returned non-PNG/JPEG/WebP bytes, inline delivery is skipped and `creator.js:160` errors after billing. Unlikely; no fix proposed.

## Checks I could not perform

- No test run, `make check` or server start. The pending fix is verified by reading only, and no test covers the cwd-relative case.
- No live or paid probe of `/create`, so real Muse output size, latency and MIME type are unmeasured.
- I did not read `.env`, so I can't confirm which `DEMO_MODE` or `OUTPUT_DIR` the existing local server is running with.
- No browser check of `/` or `/create`. No Vercel check of the deployed revision.
- I did not review the uncommitted `creator.js`/`creator.html` import diff beyond the fetch and live paths.

## Next packet (when ownership clears)

1. Codex: add the cwd-relative regression test and commit the pending `media_delivery.py` fix.
2. Codex: add the readiness-aware live banner on `/`, or Nav approves the `demo.py:48` change.
3. Optional: the SAM guard (3a), saving one billed call per live generate.
4. Nav: any live rehearsal needs a separate spending allowance. Run it with `DEMO_MODE=true` plus the unlock key, not `DEMO_MODE=false`.
