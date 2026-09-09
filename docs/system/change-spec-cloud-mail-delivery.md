# Change Spec: Cloud production invitation delivery

## Current state

Cloud already has an SMTP adapter for verification codes. Administrator invitations are persisted with a hashed token, but the create response always returns the raw token and does not send an email. That is acceptable for development smoke tests but is not a complete production invitation flow.

## Goal

When OTP development mode is disabled, send invitation links through the configured SMTP adapter and never return the raw invitation token in the HTTP response. Development mode keeps the existing token response for local tests.

## Non-goals

- No database schema change.
- No change to invitation acceptance or token hashing.
- No provider-specific mail SDK; SMTP remains the replaceable delivery boundary.

## Affected modules

- `cloud/config.py`: public invitation URL configuration.
- `cloud/mailer.py`: invitation message delivery.
- `cloud/app.py`: production response and failure handling.
- `desktop/backend/tests/test_cloud_backend_slice.py`: development and production regression tests.
- `cloud/README.md`, `docs/system/api-inventory.md`: runtime contract and deployment configuration.

## Security and failure behavior

The raw token is used only to construct the outbound link. If SMTP delivery fails, the pending invitation is revoked before returning `503`; the token is not returned. Audit records contain the invitation id and delivery result, never the token or link.

## Verification

- Development invitation still returns a token for local setup.
- Production invitation calls the mail adapter, omits the token, and stores only the hash.
- SMTP failure returns `503` and leaves no usable pending invitation.
- Cloud backend tests and Python compilation pass.
