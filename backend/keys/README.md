# backend/keys

The RSA key pair used to sign model weights and reports. `model_signing.pub` (public) may be committed; `model_signing.pem` (private) is gitignored and is protected by `MODEL_SIGNING_PASSWORD` from `.env`. Never share the `.pem` file.
