# Security and operations notes

## Built and tested
| Control | Where | Notes |
|---|---|---|
| Sign-in, roles (viewer < reviewer < admin), API tokens | `app/auth.py`, `routes_auth.py` | `AUTH_MODE=on`; tokens never outrank their owner |
| MFA (TOTP, 6 digits) + one-time recovery codes | `app/mfa.py` | verified against RFC 6238 vectors; admin can reset |
| Password policy, lockout | `routes_auth.py` | min 10 chars, 5 failures lock 15 minutes, audited |
| OpenID Connect token check | `auth.verify_oidc` | RS256/ES256 against the issuer's JWKS; roles from a claim |
| SCIM 2.0 Users | `routes_scim.py` | admin API token as bearer; create / filter / patch / deactivate; last-admin guard |
| Audit log | `audit_log` table | every change, sign-in, refusal, export; retention via `AUDIT_RETENTION_DAYS` |
| Secrets at rest | `connectors/crypto.py` | Fernet, key from `SECRET_KEY` or `data/.secret_key` |
| Share / signing links | `routes_comments.py`, `routes_signatures.py` | random tokens, only the SHA-256 is stored; expiry, revoke, level (view/comment/edit) |
| Security headers, no-store on API, request ids | `main.py` | `HSTS=1` when behind TLS; `LOG_JSON=1` for JSON logs |
| Metrics | `GET /api/ops/metrics` (admin) | Prometheus text |
| Backups | `scripts/backup.sh` | pg_dump + data folder + checksums, retention |
| CI | `.github/workflows/ci.yml` | tests, offline evals, frontend build (not yet run on GitHub) |

## Not built (be explicit with buyers)
* **Multi-tenancy.** One deployment = one customer. The plan: a `tenant_id` on every table, Postgres row-level security keyed on a per-request setting, tenant-scoped storage folders and encryption keys, tenant in tokens. About 4-6 weeks plus a security review; do it only when the second customer needs to share an install.
* **Encryption at rest** is delegated to the database volume / cloud disk; the app encrypts only connector and MFA secrets.
* **SOC 2 / ISO 27001**: no policies, evidence collection or independent audit. External pen test not done.
* Data residency, field-level encryption, IP allow-lists, SSO-enforced MFA (use the identity provider's MFA with OIDC).
* The TOTP and e-signature features are application-level: the internal signature is a click-to-sign with audit trail, not a qualified electronic signature.

## Operations
`make test` runs the suite; use a separate database and `DATA_DIR` for tests. Health: `GET /health`. Logs: set `LOG_JSON=1`. Back up with `scripts/backup.sh` on a schedule (cron / systemd timer).
