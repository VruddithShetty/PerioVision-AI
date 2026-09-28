# PerioVision AI — Cybersecurity Architecture (HIPAA Hardened)

This system implements a state-of-the-art security layer for clinical dental AI, following HIPAA compliance guidelines and zero-trust principles.

## 🛡️ Security Pillars

### 1. PHI Protection (CS-1)
*   **CSFLE (Client-Side Field Level Encryption)**: Sensitive patient data (Contact, Notes) is encrypted before hitting the database using **AES-256-GCM**.
*   **Searchable Encryption**: Deterministic encryption allows for secure field searching without decrypting the entire database.

### 2. X-Ray Provenance (CS-2)
*   **Fragile LSB Watermarking**: HMAC-SHA256 signatures are embedded into image pixels to detect tampering.
*   **Perceptual Hashing (pHash)**: Structural integrity verification to detect resizing or compression manipulation.
*   **Merkle Audit Chain**: All clinical actions are linked in a cryptographically verifiable hash chain.

### 3. AI Model Security (CS-3)
*   **Model Signing**: YOLO and Risk models are signed with **RSA-4096** to prevent model substitution attacks.
*   **Adversarial Defense**: FFT-based frequency analysis detects PGD/FGSM perturbations.
*   **Defensive Denoising**: Automated TV-denoising to strip adversarial noise from inputs.

### 4. Zero-Trust Access (CS-4)
*   **Device Fingerprinting**: Tracking unique browser fingerprints to prevent session hijacking.
*   **RBAC Query Filtering**: Database-level filtering ensures doctors only access their authorized patients.
*   **Token Rotation**: One-time use refresh tokens with automatic revocation on reuse detection.

### 5. Threat Intelligence (CS-5)
*   **Digital Honeypots**: Traps for detecting internal bad actors or database exploration.
*   **Automated Incident Response**: Playbooks for auto-locking accounts upon critical breach detection.
*   **Real-time Risk Scoring**: Dynamic assessment of user behavior.

### 6. Governance & Compliance (CS-6)
*   **Signed Governance Reports**: Automated PDF generation of audit trails signed with RSA-4096.
*   **Production Readiness**: Automated preflight checks for security configurations.

---
**Status**: 🟢 PRODUCTION HARDENED
**Compliance**: HIPAA Ready
