# NoteMeld iOS adapter

The shared lifecycle and Relay contract is documented in
`docs/system/cloud-adapter-contract.md`.

iOS-specific adapter boundary for the shared cloud sync protocol.

- Store the TokenStore encryption key in Keychain with device-only access.
- Generate a persisted app-install identifier and derive the device id with
  `make_device_id("ios", install_id)`.
- Reuse CloudClient, encrypted relay framing and LAN-first connection strategy.
- Dangerous operations remain approval-gated by the host device.
