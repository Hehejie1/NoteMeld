# Change Spec: Cloud Web Entry and API Integration

## Current state

`cloud/` provides the standalone FastAPI control plane. The Cloud page designs
are static HTML under `docs/new-product/pages/cloud/` and their interactions
were previously intended for the prototype host; direct browser navigation and
authentication were not connected to the Cloud API.

## Goal

Serve the Cloud web pages from the Cloud service and connect the login, session
creation, and Cloud Agent command submission flows to the existing authenticated
API. Keep the same page assets and preserve the prototype iframe navigation
bridge.

## Explicitly out of scope

This change does not start or move the desktop frontend/backend, alter the
Cloud API data model, or replace the existing API authentication and approval
semantics. Member, device, workspace, and model screens remain compatible with
their existing API contracts; their deeper API wiring is a follow-up slice.

## Implementation and verification

- Mount `docs/new-product` as `/cloud` and redirect `/` to the Cloud login page.
- Use the real login token for protected page requests.
- Use the existing session and command endpoints for Cloud Agent actions.
- Verify with Cloud web entry tests, Cloud backend tests, JavaScript syntax
  checks, and a live `/` plus `/ready` smoke test.

## Risk and rollback

The static mount is conditional on the page directory existing, so API-only
deployments remain importable. Removing the mount and the standalone web API
adapter restores the previous API-only behavior without changing database
contents.
