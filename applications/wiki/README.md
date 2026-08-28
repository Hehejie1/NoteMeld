# Wiki application

This is the built-in `notemeld.application.v1` package boundary for Wiki.
The host-owned React bundle lives in `frontend/src/apps/wiki/` and is loaded
only after the user opens the application. `ui/index.html` is the package
entry required by the package protocol and is included in desktop resources.

Wiki is intentionally UI-only: graph and article data are supplied by the
host's `wiki.read` capability adapter, which remains the authority for the
existing Wiki store and Note-derived data. Applications that declare their
own backend use the Host's platform-selected `process-jsonl` or
`managed-worker` runtime instead.
