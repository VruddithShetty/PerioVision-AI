# deploy

Public demo: web app on **Vercel**, backend on a free **Hugging Face Docker Space** (Vercel cannot run the backend:
PyTorch and the models are far over its 250 MB function limit). The browser only ever talks to the Vercel address;
Vercel forwards `/api/*` to the Space, so the login cookie and the security headers work unchanged.

1. huggingface.co → New Space → SDK **Docker** (blank), hardware **CPU basic (free)**. In its Settings → Secrets add
   `DEMO_EMAIL` and `DEMO_PASSWORD` (14+ characters, upper, lower and a digit).
2. huggingface.co → Settings → Access Tokens → create a **write** token.
3. `.\deploy\make_hf_space.ps1 -Space <hf-username>/<space-name>` (give the token as the git password).
   Wait for the Space to show "Running", then open `https://<hf-username>-<space-name>.hf.space/health`.
4. `.\deploy\deploy_vercel.ps1 -BackendUrl https://<hf-username>-<space-name>.hf.space` (log in to Vercel when asked).

Demo mode keeps data in memory: a Space restart (or ~48 h of inactivity on the free tier) clears uploaded analyses.
For real patient data use the production setup in `docs/DEPLOYMENT.md` instead.
