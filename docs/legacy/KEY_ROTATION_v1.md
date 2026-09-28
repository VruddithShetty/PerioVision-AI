# PerioVision AI Key Rotation Policy & Procedure

This document outlines the manual procedure for rotating critical cryptographic keys used in PerioVision AI, specifically the `FIELD_ENCRYPTION_KEY` and the Model Signing Keys (RSA-4096).

## 1. Field Encryption Key Rotation (`FIELD_ENCRYPTION_KEY`)

The `FIELD_ENCRYPTION_KEY` is a 256-bit AES key used for encrypting patient records (AES-256-GCM) and generating Blind Indexes (HMAC-SHA256) for searching.

### When to Rotate:
- Annually (compliance requirement).
- Immediately upon suspicion of key compromise.
- When an administrator with production key access leaves the organization.

### Rotation Procedure:
1. **Generate New Key:** Generate a new secure 256-bit key hex string.
   ```python
   import secrets
   new_key = secrets.token_hex(32)
   ```
2. **Update Secrets Manager:** Add the new key to AWS Secrets Manager as the active `FIELD_ENCRYPTION_KEY`. Ensure the old key is temporarily retained for the migration phase.
3. **Run Migration Script:** Stop all write access to the database. Run the migration script that decrypts data using the old key and re-encrypts it using the new key.
   ```bash
   python scripts/migrate_encryption.py
   ```
4. **Verify System Functionality:** Run regression tests and manually verify that a doctor can search and retrieve a patient record successfully.
5. **Revoke Old Key:** Once all data is migrated and verified, permanently delete the old key from AWS Secrets Manager.

## 2. Model Signing Key Rotation

Model signing keys are RSA-4096 key pairs used to verify the integrity and provenance of AI models (e.g., YOLO Landmark Detector).

### When to Rotate:
- Bi-annually (every two years).
- Immediately upon suspicion of private key compromise.

### Rotation Procedure:
1. **Generate New Keypair:**
   ```bash
   openssl genrsa -out keys/model_signing_new.pem 4096
   openssl rsa -in keys/model_signing_new.pem -pubout -out keys/model_signing_new.pub
   ```
2. **Sign Existing Models:** Use the new private key to sign the production models and generate new `.sig` files.
3. **Deploy Public Key:** Replace `keys/model_signing.pub` on the application servers with the new public key.
4. **Update Private Key Storage:** Store the new private key securely offline (e.g., in a hardware vault or highly restricted Secrets Manager tier). Do NOT deploy the private key to the application servers.
5. **Revoke Old Key:** Destroy the old private key and delete the old public key from all servers.
