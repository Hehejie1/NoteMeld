# Change Spec: Mobile artifact list and preview prototype

## Scope and page brief

M02's “全部产物” opens M09, a task-scoped artifact list. Selecting a file opens M10, a read-only preview. The primary job is to find and inspect a task result; the secondary job is to return to the conversation. The hierarchy is task name → file identity/type → file content. The existing mobile header, list-card, Lucide icon, color, spacing and focus primitives are reused; no new global component is introduced.

## Data and authority

M09/M10 are static design prototypes with a clearly labelled sample dataset, not a live conversation or filesystem browser. Production data must come from an authorized conversation-artifact listing and a per-artifact read/download endpoint; never accept arbitrary paths or a URL from page input. File identity is a scoped opaque ID, with task ID, filename, MIME, size, source, read permission and optional download permission. Local storage only remembers the selected sample artifact ID across prototype frames.

## Interaction and states

M02 menu → M09 list → M10 preview → M09 list → M02. M09 supports populated, empty and error states; M10 supports loading, supported text/HTML/image/PDF/media, missing and unsupported formats. HTML is sandboxed with scripts and network resources disabled. Markdown renders escaped, limited block formatting; source view is available. Text and code are escaped. Binary formats the browser cannot render show an explicit unsupported message and a download action only when an authorized source exists. A web prototype cannot truthfully promise native rendering for every file type.

## Acceptance

- Collapsed M02 send-arrow SVG matches expanded arrow SVG size.
- “全部产物” opens a task-titled file list, not a scroll-to-top action.
- Rows show file type icon and filename; selecting a row opens its own preview.
- Return buttons preserve the task/list flow, including iframe navigation.
- Fixture/sample status is documented in the design contract and registry; no sample result is presented as a live backend artifact.
- Keyboard focus, narrow viewport, light/dark themes and unsupported-file fallback remain usable.

## 2026-09-17 layout refinement

The list page now reserves the top bar for task title and file count, followed immediately by file rows. Remove the duplicated current-task eyebrow, “全部产物” heading, “文件” section heading, explanatory copy, and bottom prototype notice. The preview page top bar uses the selected filename as its centered title and places the Preview/Source switch on the right. Remove the redundant file identity block and bottom notice; put a small current-view label at the top of the preview surface and Download on its right. Keep fixture status in this design contract and feature registry, not as repeated page chrome. No data source, API, or authority changes are part of this refinement.
