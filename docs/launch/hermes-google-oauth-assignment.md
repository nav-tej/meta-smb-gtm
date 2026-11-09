# Assignment for Hermes: Provision Google OAuth Credentials & Verify Google Sign-In

Assigned November 9, 2026 by Antigravity on Nav's instruction.
Read `AGENTS.md` and `docs/launch/STATUS.md` first. **Never print or log `GOOGLE_CLIENT_SECRET` or any other secret key in chat, terminal output, or markdown reports.**

## Context
Google OAuth sign-in and account creation are already implemented and deployed to production (`https://meta-smb-gtm.vercel.app`, commit `5f4a082`):
- Frontend: **Continue with Google** button in `src/api/static/account.js` (`.ma-google`).
- Backend: `POST /api/v1/account/oauth`, `GET /api/v1/account/oauth/google`, and `GET /api/v1/account/oauth/google/callback` (`src/api/accounts.py`, `src/services/accounts.py`).
- Provisioning helper: `scripts/google_oauth_setup.py`.

Because `gcloud` CLI is not logged in on this machine, use your authenticated browser session to create (or retrieve) the Google OAuth 2.0 Web Client in Google Cloud Console, then run `scripts/google_oauth_setup.py` to push the credentials to Vercel and deploy.

---

## Step 1: Create or Fetch OAuth 2.0 Web Client in Google Cloud Console
1. Open [Google Cloud Console — Credentials](https://console.cloud.google.com/apis/credentials) in the authenticated browser.
2. Select Nav's project (or `nplusalpha` / `muse-growth-studio` project).
3. If the **OAuth consent screen** is not yet configured for this project:
   - User Type: **External**
   - App name: `Muse Growth Studio`
   - User support email: `help@nplusalpha.com`
   - Authorized domains: `vercel.app`, `nplusalpha.com`
   - Privacy policy link: `https://meta-smb-gtm.vercel.app/privacy`
   - Terms of service link: `https://meta-smb-gtm.vercel.app/terms`
   - Developer contact email: `help@nplusalpha.com`
   - Publish status: click **Publish App** (so non-test Google accounts can sign in).
4. In **Credentials**, click **+ Create Credentials → OAuth client ID** (or open an existing Web application client):
   - Application type: **Web application**
   - Name: `Muse Growth Studio Web`
   - **Authorized JavaScript origins:**
     - `https://meta-smb-gtm.vercel.app`
   - **Authorized redirect URIs** (add both):
     - `https://meta-smb-gtm.vercel.app/api/v1/account/oauth/google/callback`
     - `https://iwatwkiogizfmetiwlqf.supabase.co/auth/v1/callback`
5. Click **Create**, then click **Download JSON** (which downloads `client_secret_*.json` to `~/Downloads/`).

---

## Step 2: Push Credentials to `.env` and Vercel (Without Printing Secrets)
Run the helper script from `/Users/nav/meta-smb-gtm`:

```bash
cd /Users/nav/meta-smb-gtm
.venv/bin/python scripts/google_oauth_setup.py --from-json ~/Downloads/client_secret_*.json --push-vercel
```

*(If you copied the Client ID and Client Secret directly instead of downloading JSON, write `GOOGLE_CLIENT_ID=...` and `GOOGLE_CLIENT_SECRET=...` to `/Users/nav/meta-smb-gtm/.env` without echoing the secret to stdout, then run `.venv/bin/python scripts/google_oauth_setup.py --push-vercel`.)*

---

## Step 3: Redeploy Production & Verify
1. Deploy from a clean git worktree so untracked `.mp4` files are excluded:
   ```bash
   cd /Users/nav/meta-smb-gtm
   WT=$(mktemp -d /tmp/muse-prod-deploy-XXXXXX)
   git worktree add --detach "$WT" HEAD
   cp -R .vercel "$WT/.vercel"
   (cd "$WT" && vercel deploy --prod --yes)
   git worktree remove --force "$WT"
   ```
2. Verify the OAuth endpoint returns a live `https://accounts.google.com/o/oauth2/v2/auth?...` URL:
   ```bash
   curl -sS -X POST "https://meta-smb-gtm.vercel.app/api/v1/account/oauth" \
     -H "Content-Type: application/json" \
     -H "Origin: https://meta-smb-gtm.vercel.app" \
     -d '{"provider":"google","next":"/account"}'
   ```
   Expect: `{"provider":"google","url":"https://accounts.google.com/o/oauth2/v2/auth?..."}`.
3. In the browser, open `https://meta-smb-gtm.vercel.app`, click **Sign in** → **Continue with Google**, complete Google sign-in, and confirm you return signed in with `3 of 3 runs left`.
4. Record your checkpoint in `docs/launch/STATUS.md` (never include the client secret).
