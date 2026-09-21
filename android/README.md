# NoteMeld Android adapter

The shared lifecycle and Relay contract is documented in
`docs/system/cloud-adapter-contract.md`.

Android-specific adapter boundary for the shared cloud sync protocol.

- Use Android Keystore to provide the key for the `CloudTokenStore` contract.
- Generate a persisted app-install identifier and derive the device id with
  `make_device_id("android", install_id)`.
- Reuse the canonical CloudClient API and LAN-first connection strategy.
- Keep Agent state and workspace ownership in the host/runtime layer; this
  directory must not implement a second Agent loop.

## Standalone Agent runtime build

The `:agent-runtime` module consumes the published standalone SDK AAR and
never loads SDK source code.  Supply the pinned artifact explicitly:

```bash
NOTEMELD_AGENT_SDK_AAR=/absolute/path/notemeld-agent-sdk-0.1.0.aar \
  ./gradlew --no-daemon :agent-runtime:lint :agent-runtime:testDebugUnitTest \
  :ui-core:lint :app:assembleDebug
```

The module verifies the AAR SHA-256 before compilation.  A missing or
different artifact fails closed; it is not replaced with a mock runtime.
