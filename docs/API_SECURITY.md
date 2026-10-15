# PerioVision AI: API Security

53 routes. 9 deliberately public. **0 unclassified** — and that is a structural property,
not the result of a review.

---

## 1. Deny by default

`enforce_deny_by_default` runs before every request. A route that carries neither
`@secured("permission")` nor `@public` is refused with 403 and the refusal is audited. A
forgotten decorator therefore fails closed rather than exposing a handler.

```python
@bp.get("/api/patients/<int:patient_id>")
@secured("patient:read")          # policy, checked before the handler runs
def get_patient(patient_id):
    patient, err = load_patient_or_404(patient_id)   # object-level scope
    if err:
        return err
```

Two separate checks. `@secured` answers "may this role do this kind of thing";
`load_patient_or_404` answers "may this user touch this record". Neither substitutes for the
other.

## 2. The 9 public routes

| Route | Why public |
|---|---|
| `GET /`, `GET /health`, `GET /api/health` | Liveness, no data |
| `GET /api/docs` | OpenAPI specification |
| `POST /api/auth/login` | Pre-authentication by definition |
| `POST /api/auth/mfa` | Second factor, holds a short-lived MFA token |
| `POST /api/auth/refresh` | Authenticates via the httpOnly cookie |
| `POST /api/reports/verify`, `GET /api/reports/verify/<id>` | Verification must work without an account, or it proves nothing |

Report verification is deliberately open: a signature anyone can check is worth more than
one only the issuer can.

## 3. Request validation

Every body is a Pydantic model with `extra="forbid"`. This single setting closes two classes
at once:

- **NoSQL injection** — `{"email": {"$ne": null}}` fails validation because `email` is typed
  `str`. The operator never reaches MongoDB.
- **Mass assignment** — `doctor_id`, `care_team`, `pseudo_id` appear in no input schema, so
  ownership cannot be assigned by the caller. Ownership is set server-side from the session.

Additionally: `MAX_CONTENT_LENGTH` caps request size before the body is read; `<int:...>`
converters reject non-numeric identifiers at routing; patient names reject `<` and `>`.

## 4. Responses and errors

Errors are generic and uniform. No stack traces, no internal paths, no database messages;
`FLASK_DEBUG` is never enabled in the container. Every response carries the same envelope,
so an error cannot be distinguished by shape.

**404 instead of 403** for out-of-scope records, with an identical message to a genuine miss.

## 5. Headers and transport

```
Content-Security-Policy: default-src 'none'; frame-ancestors 'none'; base-uri 'none'
X-Content-Type-Options: nosniff          X-Frame-Options: DENY
Referrer-Policy: no-referrer             Cross-Origin-Opener-Policy: same-origin
Permissions-Policy: camera=(), microphone=(), geolocation=()
Cache-Control: no-store                  (on /api/*)
Strict-Transport-Security                (when the request is HTTPS)
```

The CSP is `default-src 'none'` because the API returns only JSON, images and PDFs — nothing
it serves should ever execute or be framed. The `Server` header is removed. CORS is an
allow-list from `CORS_ORIGINS`, never a wildcard.

## 6. Rate limiting

120/min globally; 5/min on login and MFA; 10/min on analysis; 20/min on upload.

`TRUSTED_PROXY_COUNT` enables ProxyFix so limits key on the real client. Without it, every
client behind a proxy shares one bucket — and audit records log the proxy. It is **off by
default**, because trusting `X-Forwarded-For` with no proxy present would let any client
forge its own source IP.

## 7. CSRF

Not implemented, deliberately. The API authenticates with a Bearer token in the
`Authorization` header, which browsers never attach automatically. The only cookie is the
refresh token: `httpOnly`, `SameSite=Strict`, scoped to `/api/auth`, and rotated on every
use with reuse detection. Adding CSRF tokens would protect nothing that is not already
protected.

## 8. Attacks tested, not asserted

| Attack | Result | Where |
|---|---|---|
| `{"$ne": null}` login bypass | Rejected at validation | Lab: nosql-injection |
| Writing `doctor_id` via the patient API | Rejected | `test_authorization` |
| Reading another clinician's patient | 404, identical to absent | Lab: idor |
| Role without permission | 403 | Lab: privilege-escalation |
| Forged, expired, `alg:none` tokens | Rejected | Lab: jwt-replay |
| Token from another device | Session revoked | Lab: session-theft |
| Refresh token replay | Whole session revoked | `test_api` |
| Traversal in an image layer | Not in the allow-list | Lab: path-traversal |
| Executable, PDF, SVG as a radiograph | Blocked on magic bytes | Lab: disguised-upload |
| Unsupported HTTP method | Never reaches the handler | `test_authorization` |

## 9. Limitations

- **Rate-limit storage is in-memory** unless `REDIS_URL` is set. With more than one waitress
  worker each has its own counters, so effective limits are higher than configured.
- **No response-schema validation.** Inputs are strict; outputs are hand-built.
- **No pagination limits on every list route.** Patient and analysis lists are scoped by
  authorization but not all are page-capped.
- **Authorization failures are detected, not throttled.** A burst raises an alert; nothing
  blocks the account.
