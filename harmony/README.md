# NoteMeld Harmony adapter

The shared lifecycle and Relay contract is documented in
`docs/system/cloud-adapter-contract.md`.

Harmony-specific adapter boundary for the shared cloud sync protocol.

The application entry is the real `EntryAbility`, which hosts the
`pages/MobileSurface` ArkUI page. Build the HAP with the OpenHarmony Hvigor
wrapper; the unsigned output must be signed with the deployment profile before
installing with `hdc`.

- Use Harmony secure storage for the TokenStore encryption key and encrypt the persisted Ed25519 identity spec with that HUKS-backed store.
- Cloud registration includes the stable Harmony Ed25519 public key; the private key never leaves the device.
- Generate a persisted app-install identifier and derive the device id with
  `make_device_id("harmony", install_id)`.
- Reuse CloudClient and the canonical relay/session schemas; do not duplicate
  Agent runtime or queue semantics in the UI adapter.
- Harmony remote execution is fail-closed until its native LAN/Relay E2EE
  WebSocket frame transport is implemented; it must never silently execute through Cloud-native.
