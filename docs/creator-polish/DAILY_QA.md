# Daily studio offline QA — November 4, 2026

Scope: only `tests/today_studio_contract.cjs`, `tests/test_today_studio.py` and this report. No runtime files or existing tests edited. No network, provider calls, secrets, deployment or git mutations.

## Verified

`pytest tests/test_today_studio.py`: **2 passed**. Ruff lint/format and the Node syntax check pass.

- `/today` and its CSS/JS serve; a starter content plan returns three posts without any outbound `httpx` request.
- Page initialization requests only a starter plan, even when readiness reports a local live-default server.
- Export is blocked until review. A reviewed image export uses current edited words, and the caption copies correctly.
- Instagram/Facebook/X/TikTok switching sets the intended channel; X selects text and TikTok selects video.
- Manual opening/caption edits survive a channel roundtrip and a format roundtrip. Changing a format clears review.
- A live plan requires explicit opt-in. Its mock request carries both `use_muse=true` and `?live=true`; the unlock token is absent from local storage.
- A mocked failed live request preserves the edited caption.
- Importing another item clears the artist image, offers and entered performance. A missing imported image blocks media export rather than showing unrelated artwork.
- Cancelling a partial destination edit restores the prior destination/link and caption.
- Restoring a saved custom item with no photo keeps that item's identity and its missing-photo state.

## Findings relayed and resolved by Codex

The first static pass found that setup mutated canonical destination/item state before Apply, so closing setup could leave mismatched link/price identity. Codex added a setup backup and close/escape rollback; the added regression passes. The initial restore path also rejected custom items with an empty original photo and fell back to the artist example; Codex fixed that and the restoration regression passes.

## Limits

These are mocked DOM/HTTP contracts. They do not prove canvas fidelity, actual downloads, browser clipboard permissions, mobile appearance, six-second clip encoding, live Muse quality, publishing, attributed sales, or a five-minute completion time. Those need the parent's browser rehearsal and actual user timing. No current blocker found in the tested state transitions.
