# Key Rotation

## Field/file encryption keys (AES-256-GCM)

Every ciphertext records the ID of the key that produced it (`enc:v1:<kid>:...` for fields, a `PVE1` header for files), so keys can be rotated without downtime.

1. Generate a new key: `python -c "import secrets; print(secrets.token_hex(32))"`
2. In `.env`, add it to the ring and make it active, keeping the old key:
   ```
   FIELD_ENCRYPTION_KEYS=k3:<new key>,k2:<current key>,k1:<older key>
   FIELD_ENCRYPTION_ACTIVE_KID=k3
   ```
3. Restart the backend. New data is now encrypted with `k3`, and old data still decrypts.
4. Re-encrypt existing data: `cd backend && python scripts/rotate_keys.py`
5. Once it reports nothing left on old keys, remove them from the ring.

Note: blind indexes (exact-match search) and pseudonyms are derived from the active key. After a rotation, re-save patients (or re-run a migration) before relying on search for old records.

## Model/report signing key (RSA-PSS)

1. Keep the old public key (`backend/keys/model_signing.pub`) somewhere safe if old reports must stay verifiable.
2. Move the old key pair aside, then run `python scripts/sign_model.py --init-keys` with a new `MODEL_SIGNING_PASSWORD`.
3. Re-sign the weights: `python scripts/sign_model.py`
4. Reports keep their stored `key_fingerprint`, so you can tell which key signed each one.

## Other secrets

`JWT_SECRET_KEY`: changing it logs everyone out. `AUDIT_ANCHOR_KEY`: changing it makes older anchors fail verification, so publish a fresh anchor right after rotating and archive the old anchor file first.
