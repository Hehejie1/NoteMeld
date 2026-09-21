# Android M01–M10 new-product alignment

## Change

Bring the Android mobile surface into parity with the `/docs/new-product` M01–M10 information architecture and visual language. M03 is a navigation hub; model and remote configuration live in M07/M08, and task artifacts live in M09/M10.

## Scope

- Add typed Android routes and reducer actions for M07 model settings, M08 remote settings, M09 artifact list, and M10 file preview.
- Keep model, Cloud sync, remote device, and artifact state sourced from existing host/runtime adapters. Empty states must be explicit and must not fabricate a connected device or generated file.
- Use the existing `:ui-core` tokens/primitives and Lucide-style outline resources; no second component system.
- Make M03 grouped settings match the new-product hierarchy and keep its header as back / 设置 / no right action.

## M01–M06 page brief

- User job: start or resume an Agent task, inspect its real execution state, and manage the local mobile workspace without losing the current location or sync context.
- Primary action: M01/M02 send a prompt; M03 routes to one focused setting; M04 adds a memory; M05 confirms readable type; M06 clears a selected recoverable storage category.
- Must-see information: active Agent location and terminal state, real task/session content, memory contents, current font mode/size, and measured local storage usage.
- Required states: empty, loading/sending, offline-readonly, recoverable error, permission/approval, and completed. UI must not invent a model, remote device, memory, artifact, size, or successful sync.
- Responsive and accessibility rules: one-column phone layout, 44 dp minimum targets, semantic locators from `tests/visual/locator-contract.json`, system back support, rotation survival, TalkBack labels, and no clipped controls at large font scale.

## Component map

- Shared shell: `NoteMeldTheme`, `Header`, `NoteMeldTokens`, `NoteMeldToast`, `NoteMeldBottomSheet`.
- M01: `HomeScreen`, `HomeQuickAction`, `HomeComposer`; collapsed composer expands in place to tools/permission/model controls.
- M02: `SessionScreen`, message bubbles, runtime status, shared composer controls; work location is selected in the drawer, not duplicated as a page tab bar.
- M03: `SettingsScreenWithTheme`, `SettingGroup`, `SettingRow`, `NoteMeldSegmentedControl`.
- M04: memory summary card, memory content card/list, memory composer card; empty data uses `NoteMeldEmptyState`.
- M05: type preview card and controls card with follow-system switch and semantic slider.
- M06: measured usage summary and grouped storage rows with a confirmation dialog for destructive clears.

## Protocol and safety

Cloud configuration continues through the existing revision-aware adapter. Remote pages show actual device state only; pairing credentials remain outside UI state. Artifact preview reads typed local artifact content and offers download only when the host marks it downloadable.

## Verification

Run `:app:assembleDebug :app:testDebugUnitTest :app:lintDebug`, install the debug APK on the connected Android device, and capture M01–M10 screenshots. Record real-device and unavailable-backend limitations in the acceptance matrix.
