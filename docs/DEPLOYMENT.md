# Deployment (live mode)

The demo setup (`.env`, in-memory database, demo accounts) stays untouched for presentations. Live use has its own settings file, keys, weights and data folders, all gitignored:

| File / folder | Contents |
|---|---|
| `.env.production` | Fresh JWT secret, AES-256-GCM key ring, audit-anchor key, model-signing password, MongoDB password. **Back it up; never share it.** |
| `backend/keys-production/` | New RSA-PSS signing key pair (different from the demo key) |
| `backend/weights-production/` | Copy of the trained weights, signed with the production key |
| `backend/storage-production/`, `logs-production/` | Encrypted files and Merkle audit anchors |

Losing `.env.production` or `keys-production` means encrypted data can no longer be read, so back up both together.

## Steps (Windows, from the repository root)

1. **Secrets and keys** (done once per server): `.\run.ps1 make-prod-env`. It refuses to overwrite an existing `.env.production`.
2. **Database:** open Docker Desktop, then `.\run.ps1 mongo`. This starts MongoDB 7 with the generated password, listening on this machine only. Alternatively, use MongoDB Atlas: put its `mongodb+srv://…` URI in `MONGO_URI` (TLS is enforced automatically for non-local hosts).
3. **Real admin account:** `.\run.ps1 create-admin`. You type the password; it is never stored in a file. After signing in, turn on MFA under Security centre → MFA. There are no demo accounts in live mode.
4. **Backend:** `.\run.ps1 prod` starts the production WSGI server (waitress) on `127.0.0.1:5000` in live mode.
5. **Frontend:** `.\run.ps1 frontend-prod` builds the web app and serves it on `http://localhost:4173`, with `/api` proxied to the backend.
6. **After new training:** `.\run.ps1 install-models -From <folder>` (demo weights), then `.\run.ps1 resign-prod` to copy and sign them for production.

## Docker (server)

`docker compose --env-file .env.production up -d --build` runs MongoDB and the backend (waitress). It mounts the production keys and weights read-only.

## Still to do for public access (deployment step 4)

- Choose a host and domain, and put an HTTPS reverse proxy (Caddy or nginx) in front. It serves `frontend/dist` and proxies `/api` to the backend.
- Set `PUBLIC_BASE_URL`, `CORS_ORIGINS` and `PUBLIC_VERIFY_URL` in `.env.production` to that domain.
- Schedule MongoDB backups (`mongodump`) and back up `backend/storage-production`.
