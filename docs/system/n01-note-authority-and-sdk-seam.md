# N01 Note authority and SDK adapter seam

For the first Note Agent release, `note_documents.task_id` is the opaque SDK
`NoteId`. Existing task IDs are not rewritten and the application must not
create a second authoritative Note正文 table. `note_documents` owns the
title, Markdown content, source URL/platform and product status.

`note_results/`, conversation messages, Wiki/FTS/Chroma and UI state are
projections or compatibility outputs. Their failure cannot roll back a
successful Note commit; each remains independently rebuildable.

`backend/app/agent_host/note_contract.py` contains the only N01 product-side
DTO seam. It has no SDK import and no persistence side effect. `SdkNoteDto`
maps an existing document to the frozen SDK-facing fields, while
`NoteSdkAdapter` defines read/search/create/update/link ports for N02.
Concrete adapters must delegate operation, idempotency, version conflict,
provenance and authority decisions to the fixed SDK artifact.
