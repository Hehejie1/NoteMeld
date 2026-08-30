# Change Spec: Cloud PC/Web vertical slice

## Current state

The cloud FastAPI control plane and a set of React cloud components already
exist, but `/cloud` is a dense functional prototype. Session events are shown
as raw event names, the page has no clear desktop/mobile information hierarchy,
and session polling does not recover from cursor gaps or reset state cleanly
when switching sessions.

## Goal

Provide a production-quality first UI slice for the cloud workflow: sign in,
create/select/archive sessions, inspect event history, send commands, review
approvals, browse a read-only workspace, and inspect connected devices. The
same components must remain usable at mobile widths.

## Explicit non-goals

- Native Android, iOS, or Harmony UI.
- Replacing the Agent runtime or cloud API.
- Adding a second transport implementation in the UI.
- Persisting cloud tokens in localStorage.

## Implementation

- Keep `CloudClient` as the only transport authority.
- Improve the session hook/controller lifecycle and cursor-gap recovery.
- Add semantic status badges, empty/loading/error states, and responsive
  navigation to the cloud page.
- Render structured event payloads with bounded previews and accessible labels.
- Keep workspace browsing read-only in this slice.

## Verification

- TypeScript contract check and frontend build.
- Existing cloud client/session contract tests.
- Add focused contract assertions for session state reset and page landmarks.

## Risks and rollback

The change is isolated to the cloud page, cloud session hook/controller, and
frontend contract tests. Reverting the commit restores the existing cloud
prototype without changing cloud APIs or persisted data.
