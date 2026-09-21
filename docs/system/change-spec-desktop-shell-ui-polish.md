# Change Spec: Desktop Shell, Home, and Settings UI Polish

## Status

- Owner: Codex
- Scope: NoteMeld desktop frontend shell only
- Target platforms: local cloud, macOS desktop, Jetson Linux desktop, USB Android verification
- Explicitly out of scope: iOS and HarmonyOS

## Current state

- The desktop shell has the required routes and real conversation loading, but the visual hierarchy is inherited from an earlier static prototype.
- The `/new` route is a technically functional empty state, but its presentation does not clearly establish the primary job: start a real local Agent task.
- The sidebar mixes brand, utility buttons, primary navigation, sessions, and runtime status without enough grouping or emphasis.
- Settings has a route-aware navigation layout, but the overview repeats broad cards and sends unrelated categories to the same destination.
- Brand assets were referenced through absolute public URLs in React while the production Tauri build used a relative frontend base path; the UI now imports the bundled SVG asset and the Vite build uses root-relative `/assets` paths.

## Goal

Make the desktop shell feel like a deliberate local Agent workbench while preserving existing routes, stores, services, and backend contracts:

1. The packaged app visibly renders its brand mark using a bundled frontend asset.
2. `/new` presents one clear next action, real input, useful capability shortcuts, and truthful local runtime status.
3. The sidebar has a stable hierarchy: brand, primary navigation, sessions, and connection/actions.
4. Settings presents stable categories and real destinations with a calm overview; no fake controls or duplicated design system.
5. The result works in wide and narrow desktop windows, light and dark themes, and remains keyboard/focus accessible.

## Non-goals

- No backend API, database schema, authentication, Agent protocol, or data migration changes.
- No new component library or parallel design-token system.
- No changes to iOS or HarmonyOS code.
- No removal of existing application, plugin, cloud, remote-device, or Android functionality.

## Design decisions

- Reuse existing semantic tokens, Tailwind primitives, Lucide icons, and current route/service contracts.
- Use one blue accent, neutral surfaces, border-first panels, and restrained radii/shadows.
- Use imported/bundled assets for runtime UI; retain Tauri bundle icon configuration for the native app icon.
- Keep all user-visible runtime claims derived from `backendReady` or existing stores; do not invent connected devices or workspace data.

## Affected files

- `desktop/frontend/src/layouts/AppLayout.tsx`
- `desktop/frontend/src/layouts/SettingLayout.tsx`
- `desktop/frontend/src/pages/SettingPage/Menu.tsx`
- `desktop/frontend/src/pages/SettingPage/SettingsHome.tsx`
- `desktop/frontend/src/pages/HomePage/Home.tsx`
- `desktop/frontend/src/pages/AboutPage.tsx`
- `desktop/frontend/src/pages/LandingPage/index.tsx`
- `desktop/frontend/src/App.css` and/or existing desktop surface styles
- Relevant frontend contract tests and documentation contracts

## Verification

- Frontend contract tests and production build.
- Local cloud readiness/smoke check.
- macOS app build and app/resource/icon inspection; DMG gate when the packaging prerequisites are available.
- Jetson ARM64 desktop build in an isolated remote build directory.
- USB Android build/install/launch/screenshot smoke check.
- Manual screenshots for `/new`, `/settings`, and at least one existing session in light/dark themes where the runtime permits.

Verification note: the same `/new` UI renders correctly in the local browser build and has been captured at `/tmp/notemeld-browser-new-20260911.png`. The packaged macOS window was also captured, but macOS 26.6.1 with the locked `tao 0.35.3` runtime produces a known Tauri blank-window failure before the WebView content is painted; this is an upstream runtime blocker, not a frontend rendering result.

## Risks and rollback

- CSS selector contracts and existing route semantics are relied on by tests; keep existing class names where practical.
- Asset import changes may require contract updates because the current tests assert the old public-path implementation.
- Rollback is a revert of this spec's frontend-only commit; no database or remote service migration is introduced.

## Open questions

- The macOS 26 packaged-window gate requires a Tauri/tao release that contains the upstream `did_finish_launching` fix, or a supported host downgrade. The current build artifact and UI remain valid, but this host cannot certify the native WebView render until that runtime issue is resolved.
