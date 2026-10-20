# docs

Start with the main [README](../README.md). Every number quoted here comes from a file in [evidence/](evidence/) and
can be regenerated with the tools in `backend/research/` and `backend/scripts/`.

| Document | What it covers |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Components, data flow, request lifecycle |
| [MODEL_CARD.md](MODEL_CARD.md) | Every model, its training data and its held-out accuracy |
| [RESULTS_WITH_CI.md](RESULTS_WITH_CI.md) | Every metric with sample size and 95 % CI (generated, do not edit) |
| [ANALYSES.md](ANALYSES.md) | Where the model fails, accuracy vs referral rate, a case gallery |
| [LIMITATIONS.md](LIMITATIONS.md) | Every known weakness, what was fixed, what is measured, what is still open |
| [PROGRESSION.md](PROGRESSION.md) | How change between visits is detected, bench results and limits |
| [VERIFICATION_REPORT.md](VERIFICATION_REPORT.md) | Independent accuracy audit, with re-run commands |
| [DATASETS.md](DATASETS.md) · [DATA_SPLITS.md](DATA_SPLITS.md) | Datasets, licences, and train / test leakage checks |
| [TRAINING_INVENTORY.md](TRAINING_INVENTORY.md) | Every model that was trained, and which one is in use and why |
| [SECURITY.md](SECURITY.md) · [OWASP_TOP10.md](OWASP_TOP10.md) | Security controls, threat model, key rotation; review against each OWASP Top 10 category |
| [API.md](API.md) · [openapi.json](openapi.json) | Every endpoint, its permission and payloads (generated) |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Live mode on your own machine; the full online server is in [deploy/server](../deploy/server/README.md) |
| [INSTRUCTIONS_FOR_USE.md](INSTRUCTIONS_FOR_USE.md) | How clinicians should read every result, and its limits |
| [TRACEABILITY.md](TRACEABILITY.md) | Each synopsis objective (O1–O7) → code → API → page → test |
| [evidence/](evidence/) | Raw outputs of every evaluation quoted in these documents |
| [reference/screenshots/](reference/screenshots/) | Screenshots used by the main README |
