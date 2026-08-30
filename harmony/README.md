# NoteMeld Harmony adapter

Harmony-specific adapter boundary for the shared cloud sync protocol.

- Use Harmony secure storage for the TokenStore encryption key.
- Generate a persisted app-install identifier and derive the device id with
  `make_device_id("harmony", install_id)`.
- Reuse CloudClient and the canonical relay/session schemas; do not duplicate
  Agent runtime or queue semantics in the UI adapter.
