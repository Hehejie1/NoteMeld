"""The only SDK release identity accepted by the NoteMeld host."""

from __future__ import annotations

SDK_SOURCE_COMMIT = "0766e80973a4021f200c8f9f0763aca2f743734d"
SDK_VERSION = "0.1.0"
SCHEMA_VERSION = "1"
ABI_VERSION = 1
NOTE_WIRE_VERSION = "note-agent-v1"
FEATURE = "default"
TEST_RUN_ID = "t12-local"

# These are the S08 handoff identity pins plus the desktop bundle consumed by
# NoteMeld. Runtime/platform waivers do not waive identity verification.
ARTIFACT_MANIFEST_SHA256 = {
    "x86_64-apple-darwin": "45b28fa761c218acc2bde1817cf07cc6025208cb55999ed24b89cb4886c6eb3c",
    "aarch64-apple-darwin": "82da881553b5cb269a923c032bcdf94f171419f7926d342ea5f06929e588bd3e",
    "aarch64-apple-ios": "e381e742a8c7916dc7e78756b69b8e5270f9f140d70e62605da9f6759e8abadf",
    "x86_64-apple-ios": "e8352e225a3ecb8add97d463e97f3547ac42a3b1376a14a3638f4a054aea8c84",
    "aarch64-linux-android": "aeb6065624c9f0935688aab3d49a2d0c4797ea349f09cb06472f3e7dd87681fe",
    "armv7-linux-androideabi": "8ee4be2d66d34e9cc338a3f5fe36f34f7c63eee5ad72e64495f6198148126e4d",
    "i686-linux-android": "f6ca041d41d884b82a1cbef33838839990973f5f086e9422c0f10ba8a8f57fa5",
    "x86_64-linux-android": "267dd61b309fbb857d83a0df9bfe1730e790138dba7a72c47c6aa94c4212d30c",
    "aarch64-unknown-linux-ohos": "fee043818b0182975c941cffd08a4cb70e9e6e6f6123b391852ee31b0118997d",
}

NATIVE_LIBRARY_SHA256 = {
    "x86_64-apple-darwin": "8ebe0a83d8ec3a191e5897b7f8ef4016f362dcbfdc4543ae05c28892f1784c9c",
    "aarch64-apple-darwin": "6be8c59d44668361ee4f1cfcc82efba19233e8707c524eda1c93d677f35aecfd",
}

# PyInstaller rewrites the install name of bundled Mach-O libraries from the
# build-tree path to @rpath while assembling a frozen sidecar.  The frozen
# sidecar must therefore verify the deterministic post-packaging digest, while
# standalone SDK consumers continue to verify NATIVE_LIBRARY_SHA256 above.
PACKAGED_NATIVE_LIBRARY_SHA256 = {
    "x86_64-apple-darwin": "57d1d1bdf7732b9137950a4e14d5032cd96d56e27b37f19a61eae66b5ad4cd5c",
}

PYTHON_WHEEL_SHA256 = {
    "x86_64-apple-darwin": "912d7df566dbacd239a32b5afd06c1daf48d64a61260aab9ae718754416407ed",
    "aarch64-apple-darwin": "f2d2f1bbc5cfd125c449bc8786b1e79e690f6e90c067ab64326675926d4c280d",
}

SUPPORTED_CONFORMANCE = {
    "python-ctypes": "verified",
    "swift-ios-device": "verified",
    "swift-ios-simulator": "verified",
    "kotlin-android": "verified",
    "harmony-har-hap": "waived/skipped",
}
