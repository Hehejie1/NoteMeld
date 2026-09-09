# Change Spec: Implement new-product surfaces in NoteMeld

## Scope

Implement the approved `docs/new-product` desktop, cloud, and mobile information architecture in the formal NoteMeld application. The work keeps existing Agent v1, CloudClient, application, settings, and storage services as the source of truth and adds only presentation routes, shared interaction states, and platform-facing UI logic.

## Acceptance

- Desktop D01, D03, D06, and D09 remain reachable through formal routes and use the shared workspace shell.
- Cloud C01–C06 share authenticated navigation; session, user, device, model, workspace, approval, and audit actions use existing cloud interfaces.
- Mobile M01–M06 use a bounded iPhone shell; session actions call Agent v1 and settings actions provide persisted or explicitly local prototype state.
- Every new surface has unit/contract coverage; device and end-to-end testing are intentionally out of scope.

## Non-goals

No database/schema/ABI change, no secret persistence, no generated artifact changes, and no real-device test run.
