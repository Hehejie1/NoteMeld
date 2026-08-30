# NoteMeld Android adapter

Android-specific adapter boundary for the shared cloud sync protocol.

- Use Android Keystore to provide the key for the `CloudTokenStore` contract.
- Generate a persisted app-install identifier and derive the device id with
  `make_device_id("android", install_id)`.
- Reuse the canonical CloudClient API and LAN-first connection strategy.
- Keep Agent state and workspace ownership in the host/runtime layer; this
  directory must not implement a second Agent loop.
