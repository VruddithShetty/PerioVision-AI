# Full production deployment on one server

The complete PerioVision AI system online: live mode (real accounts with MFA, MongoDB, encrypted storage, signed
models and reports), HTTPS on your own address, automatic restarts, nightly backups. One server runs everything:

```
browser ──HTTPS──> web (Caddy: website + certificate) ──/api──> backend (Flask, AI models) ──> MongoDB
```

Nothing here costs money on Oracle Cloud's **Always Free** tier. Any other Ubuntu server with at least 4 GB RAM
(DigitalOcean, Hetzner, AWS Lightsail ...) works the same way.

> **Patient data.** Live mode is built to protect real data (encryption, MFA, audit log), but storing real patients
> online needs their consent and compliance with data-protection law (India: DPDP Act 2023), and PerioVision is not a
> certified medical device. For a thesis or demonstration, use test or de-identified data.

## 1. Create the server (Oracle Cloud, free)

1. Sign up at **cloud.oracle.com** (Free Tier). Oracle verifies identity with a card; Always Free resources are not charged.
2. **Compute → Instances → Create instance**:
   - Image: **Canonical Ubuntu 24.04** (or 22.04)
   - Shape: **Ampere A1 (VM.Standard.A1.Flex)**, **4 OCPU, 24 GB memory** (all within Always Free)
   - Boot volume: 100 GB
   - Add your SSH public key (or let Oracle generate one and download it)
3. Open the web ports: instance → **Subnet → Security list → Add ingress rules**: source `0.0.0.0/0`, TCP, destination
   ports **80** and **443**.
4. Note the instance's **public IP address**.

(If the ARM shape is "out of capacity" in your region, try again later or another availability domain.)

## 2. A free web address

1. Go to **duckdns.org**, sign in, create a subdomain, e.g. `periovision-yourname`.
2. Set its IP to the server's public IP → your address is `periovision-yourname.duckdns.org`.

## 3. Install (one command)

Connect to the server (`ssh ubuntu@<public IP>`), then:

```bash
git clone https://github.com/VruddithShetty/PerioVision-AI.git
cd PerioVision-AI/deploy/server
bash setup.sh periovision-yourname.duckdns.org
```

It takes 20-30 minutes the first time (it builds the AI image). At the end it asks for the **first admin account**:
name, email and a password (12+ characters, upper and lower case, a digit). Then open
`https://periovision-yourname.duckdns.org`.

## 4. After installing

1. Sign in as the admin and **enrol MFA** (Security center): admins and dentists must use it in live mode.
2. **Admin → Users**: create accounts for the dentists and technicians.
3. **Copy the secrets off the server once** (they never leave it otherwise):
   `scp -r ubuntu@<IP>:PerioVision-AI/backups ./periovision-backups`. Keep the `secrets-*.tgz` file private:
   with it the encrypted data can be read, without it the data is lost forever.

## Everyday operation

| Task | Command (in `PerioVision-AI/deploy/server`) |
|---|---|
| Status | `docker compose --env-file ../../.env.production ps` |
| Logs | `docker compose --env-file ../../.env.production logs -f backend` |
| Restart | `docker compose --env-file ../../.env.production restart` |
| Backup now | `bash backup.sh` (also runs every night at 02:30; 14 days kept in `PerioVision-AI/backups`) |
| Update to the latest code / models | `bash update.sh` (backs up, pulls, rebuilds, re-signs models, restarts) |
| Another admin | `docker compose --env-file ../../.env.production exec backend python scripts/create_admin.py` |

**Restore** (new server): run `setup.sh` once, stop the stack, unpack `secrets-*.tgz` and `files-*.tgz` into the repo,
restore the database with `mongorestore --archive --gzip` from `db-*.archive.gz` inside the mongodb container, start again.

## What is where

| Item | Location | Notes |
|---|---|---|
| Secrets (JWT, AES key ring, audit key, signing password, DB password) | `.env.production` | created on the server by `setup.sh`, mode 600 |
| Signing keys | `backend/keys-production/` | private key password-protected |
| Signed models | `backend/weights-production/` | re-signed by `update.sh` |
| Encrypted radiographs, overlays, reports | `backend/storage-production/` | AES-256-GCM |
| Audit Merkle anchors, logs | `backend/logs-production/` | |
| Database | Docker volume `periovision_mongodb_data` | not reachable from the internet |
| HTTPS certificates | Docker volume `periovision_caddy_data` | renewed automatically |
