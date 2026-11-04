# Codex live-safety follow-up

Reviewed November 4, 2026 against current shared working tree (including the pending media path fix and shop-import UI). Read-only source review; only this report was written. No tests, server startup, secret inspection, network/model calls, deployment or commit. Reproduction recipes below are offline recipes or gated operator actions, not actions performed.

## Reproducible remaining issues

### 1. Relative output directory still depends on startup cwd

- Evidence: `src/services/ad_creative.py:405` uses `Path(settings.output_dir)` directly; `src/api/media_delivery.py:51–56` resolves the same relative setting against the repo directory. `_resolve_inside:66–75` now handles `outputs/name.png` correctly when cwd is the repo, while retaining root containment.
- Offline reproduction: start a service fixture from a different temporary cwd, use `output_dir="outputs"`, let the fake provider return image bytes. Writer creates `<cwd>/outputs/name.png`; default media root is `<repo>/outputs`; inline media remains absent. `creator.js:160` then reports paid generation completed without usable delivery.
- Smallest fix: resolve the service output directory against the same canonical repo root as the reader. Avoid importing an API module into the service; use a shared utility or identical repo-root normalization. For recording, use an absolute OUTPUT_DIR.
- The old double-prefix default-cwd bug is addressed in the current pending fix; do not report it as still failing in that configuration.

### 2. Hourly live limit measures requests, not provider charges

- Evidence: `src/api/demo.py:58` reserves one slot per route. `/create` sends one render request with one variant (`creator.js:157`); `ad_creative.py:426–432` calls SAM, then `:456–462` calls Muse Image. Draft calls Spark and can make a second validation-repair call (`meta.py:227–265`).
- Reproduction without spend: inject fake Meta methods/counters, exercise draft (malformed then valid structured output) and render (one image); four provider invocations consume only two route slots. Five render slots permit ten provider invocations. Direct API clients can submit more brief variants than the one shown by the UI.
- Impact: the setting name is not a global billing ceiling; cold starts also reset it. Describe an allowance in actual provider invocations, including repair attempts and SAM, rather than equating it to LIVE_CALLS_PER_HOUR. Server-side variant/billed-call budgeting remains open.

### 3. SAM can cost a call and block the current native image workflow without influencing its result

- Evidence: `ad_creative.py:426–432` always segments uploaded/reference photos. `/create` requests `muse_workflow_mode="product_visuals"`, `use_comfyui=false` (`creator.js:157`); `ad_creative.py:456–462` supplies only reference images and prompt, not the SAM mask, to Muse Image.
- Offline reproduction: make a fake SAM client raise a missing-detection error and verify native generation never runs despite needing no mask. With successful SAM, compare the arguments to generate_image_workflow: no mask is present.
- Smallest functional fix: call segmentation only for a downstream branch that consumes it, with matching call estimates. Product/judging implication: native scene generation cannot honestly demonstrate useful SAM segmentation until it actually consumes that work. Do not silently add a token billed call to claim tool depth.

### 4. Oversized generated result is discarded from the browser after billing

- Evidence: generation completes at `src/api/creative.py:95`; response-size enforcement happens at `:97–107`. `media_delivery.py:113–116` rejects raw image content above the encoded response budget. `creator.js:132` suggests a smaller input photo, but input size does not reliably determine the generated output byte count.
- Offline reproduction: fake a valid generated image exceeding the ~3 MB raw budget. Route returns 413 after fake model calls; the file exists but response contains no recoverable asset. UI loses access to the result and may encourage another paid attempt.
- Smallest UX fix: state that generation completed but delivery failed, avoid recommending regeneration, and preserve an explicit operator recovery path. Do not expose arbitrary filesystem paths publicly. Longer-term delivery can transcode the existing result or store it durably without another model call.

### 5. Local unguarded configuration remains dangerous for the legacy portal

- Evidence: `src/api/demo.py:48–49` returns live for every request when `demo_mode=false` and `hosted_environment=false`. `/create` has explicit client checks (`creator.js:146,152`) and sends a live flag only when enabled; `/` uses the old unqualified API requests and saved-copy claims (see Claude audit). Hosted requests now remain guarded even with false demo mode.
- Reproduction without spend: configure a local app fixture with false demo mode and a fake service; POST without live flag/key and verify it reaches the fake live service. It is not a hosted authorization bypass under the current `VERCEL` detection.
- Recording mitigation: always use DEMO_MODE=true. Hardening opportunity: require explicit live=true in local false mode too. This is a compatibility change, not needed to run saved mode safely.

### 6. Readiness error does not prevent choosing an unverified live session

- Evidence: `creator.js:177` checks absent provider credentials only if readiness exists; `:180–182` handles fulfilled readiness but gives no warning/disable behavior when readiness fetch fails. A typed key plus a failed readiness request allows selecting live mode. `main.py:61` truthfully returns provider_verified=false even when configured.
- Offline reproduction: have readiness return 500, type an unlock key, enable live mode. The badge says live requests selected without a readiness warning. Server authorization remains the true boundary; this is a presenter-readiness gap rather than an auth bypass.
- Smallest fix: explain readiness could not be checked and require explicit acknowledgement or disable live until a successful readiness response. Never interpret configured=true as a provider probe.

## Failure recovery that is already present

`creator.js:128` disables buttons/inputs during requests; failed draft/render paths keep prior state; `:133` warns a timeout may still process and bill; SDK automatic retries are disabled (`meta.py:209–210`). Live responses labeled demo-cache are rejected (`creator.js:159`). Inline image bytes are decoded in-browser before replacing the prior preview (`:160–161`). None of these observations establish actual provider latency or successful browser rendering.

## No-spend recording configuration

Start a fresh local process from the repository with explicit environment overrides (not a reused server with cached settings):

```sh
cd /Users/nav/meta-smb-gtm
env DEMO_MODE=true META_MODEL_API_KEY= DEMO_KEY= OUTPUT_DIR=/Users/nav/meta-smb-gtm/outputs .venv/bin/uvicorn src.api.main:app --host 127.0.0.1 --port 8013
```

This recipe does not edit .env. Existing empty environment values are not overwritten by dotenv's default loading, and Settings uses empty-key defaults. Do not actually run this until the operator chooses the recording process.

Open `/create`. Expected readiness: default_mode=saved, provider_key_configured=false, live_unlock_configured=false, provider_verified=false. Leave presenter live toggle off. Saved preview, source-photo layout, caption edits, imports, feed/story downloads and campaign-pack export make no Muse calls. A shop import still reads public third-party web pages, so skip importing if the recording must also be fully network-independent. Keep preset/sample assets locally available.

Record the saved mode label visibly and call assets saved Muse outputs. A no-spend rehearsal cannot substantiate fresh generation. A real model demonstration requires separate explicit provider-call allowance and measured verification before presenting it as live.
