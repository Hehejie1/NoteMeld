"""OS credential-store backed Host identity storage.

This is intentionally a small platform seam. It never falls back to a plain
file, environment variable, or device-id-derived key when the OS store is not
available.
"""
from __future__ import annotations

import base64
import binascii
import os
import platform
import subprocess
from dataclasses import dataclass

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519


class SecureIdentityUnavailable(RuntimeError):
    pass


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


@dataclass(frozen=True)
class HostIdentity:
    private_key: bytes
    public_key: bytes

    def __post_init__(self) -> None:
        if len(self.private_key) != 32 or len(self.public_key) != 32:
            raise ValueError("Ed25519 raw key lengths are invalid")
        derived = ed25519.Ed25519PrivateKey.from_private_bytes(self.private_key).public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        if derived != self.public_key:
            raise ValueError("Host identity key pair does not match")


class OsIdentityStore:
    def __init__(self, service: str = "com.notemeld.desktop.host") -> None:
        if not service or any(char in service for char in "\r\n"):
            raise ValueError("invalid secure-store service")
        self.service = service
        self.account = "host-identity"

    def load_or_create(self) -> HostIdentity:
        private = self._get("private")
        public = self._get("public")
        if private is None and public is None:
            signing = ed25519.Ed25519PrivateKey.generate()
            private_bytes = signing.private_bytes(
                serialization.Encoding.Raw,
                serialization.PrivateFormat.Raw,
                serialization.NoEncryption(),
            )
            public_bytes = signing.public_key().public_bytes(
                serialization.Encoding.Raw,
                serialization.PublicFormat.Raw,
            )
            identity = HostIdentity(private_bytes, public_bytes)
            self._set("private", _b64(private_bytes))
            try:
                self._set("public", _b64(public_bytes))
            except Exception:
                self._delete("private")
                raise
            return identity
        if private is None or public is None:
            raise SecureIdentityUnavailable("Host identity in OS secure storage is incomplete")
        try:
            return HostIdentity(_unb64(private), _unb64(public))
        except (ValueError, TypeError, binascii.Error) as exc:
            raise SecureIdentityUnavailable("Host identity in OS secure storage is invalid") from exc

    def _command(self) -> str:
        system = platform.system()
        if system == "Darwin":
            return "security"
        if system == "Windows":
            return "windows-credential"
        if system == "Linux" and _which("secret-tool"):
            return "secret-tool"
        raise SecureIdentityUnavailable("OS secure credential store is unavailable")

    def _get(self, label: str) -> str | None:
        command = self._command()
        if command == "windows-credential":
            return _windows_credential_read(f"{self.service}.{label}")
        if command == "security":
            args = [command, "find-generic-password", "-a", self.account, "-s", f"{self.service}.{label}", "-w"]
            result = _run(args)
        else:
            result = _run([command, "lookup", "service", self.service, "account", f"{self.account}.{label}"])
        if result.returncode == 44 or result.returncode == 1:
            return None
        if result.returncode != 0:
            raise SecureIdentityUnavailable("OS secure credential lookup failed")
        value = result.stdout.strip()
        return value or None

    def _set(self, label: str, value: str) -> None:
        command = self._command()
        if command == "windows-credential":
            _windows_credential_write(f"{self.service}.{label}", self.account, value)
            return
        if command == "security":
            result = _run([command, "add-generic-password", "-a", self.account, "-s", f"{self.service}.{label}", "-w", value, "-U"])
        else:
            result = _run([command, "store", "--label", f"NoteMeld {label}", "service", self.service, "account", f"{self.account}.{label}"], input_text=value)
        if result.returncode != 0:
            raise SecureIdentityUnavailable("OS secure credential write failed")

    def _delete(self, label: str) -> None:
        command = self._command()
        if command == "windows-credential":
            _windows_credential_delete(f"{self.service}.{label}")
        elif command == "security":
            _run([command, "delete-generic-password", "-a", self.account, "-s", f"{self.service}.{label}"])
        else:
            _run([command, "clear", "service", self.service, "account", f"{self.account}.{label}"])


def _windows_credential_api():
    """Load the Unicode Windows Credential Manager API without pywin32."""
    try:
        import ctypes
        from ctypes import wintypes

        class CredentialW(ctypes.Structure):
            _fields_ = [
                ("Flags", wintypes.DWORD),
                ("Type", wintypes.DWORD),
                ("TargetName", wintypes.LPWSTR),
                ("Comment", wintypes.LPWSTR),
                ("LastWritten", wintypes.FILETIME),
                ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                ("Persist", wintypes.DWORD),
                ("AttributeCount", wintypes.DWORD),
                ("Attributes", ctypes.c_void_p),
                ("TargetAlias", wintypes.LPWSTR),
                ("UserName", wintypes.LPWSTR),
            ]

        api = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
        credential_pointer = ctypes.POINTER(CredentialW)
        api.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(credential_pointer)]
        api.CredReadW.restype = wintypes.BOOL
        api.CredWriteW.argtypes = [credential_pointer, wintypes.DWORD]
        api.CredWriteW.restype = wintypes.BOOL
        api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        api.CredDeleteW.restype = wintypes.BOOL
        api.CredFree.argtypes = [ctypes.c_void_p]
        api.CredFree.restype = None
        return ctypes, CredentialW, credential_pointer, api
    except (AttributeError, ImportError, OSError) as exc:
        raise SecureIdentityUnavailable("Windows Credential Manager is unavailable") from exc


def _windows_credential_read(target: str) -> str | None:
    ctypes, _credential_type, credential_pointer, api = _windows_credential_api()
    pointer = credential_pointer()
    if not api.CredReadW(target, 1, 0, ctypes.byref(pointer)):
        error = ctypes.get_last_error()
        if error == 1168:  # ERROR_NOT_FOUND
            return None
        raise SecureIdentityUnavailable(f"Windows credential lookup failed ({error})")
    try:
        size = int(pointer.contents.CredentialBlobSize)
        blob = ctypes.string_at(pointer.contents.CredentialBlob, size) if size else b""
        try:
            return blob.decode("utf-8") or None
        except UnicodeDecodeError as exc:
            raise SecureIdentityUnavailable("Windows credential value is invalid") from exc
    finally:
        api.CredFree(pointer)


def _windows_credential_write(target: str, username: str, value: str) -> None:
    ctypes, credential_type, _credential_pointer, api = _windows_credential_api()
    blob_bytes = value.encode("utf-8")
    if not blob_bytes or len(blob_bytes) > 512:
        raise SecureIdentityUnavailable("Windows credential value has an invalid size")
    blob = (ctypes.c_ubyte * len(blob_bytes)).from_buffer_copy(blob_bytes)
    credential = credential_type()
    credential.Type = 1  # CRED_TYPE_GENERIC
    credential.TargetName = target
    credential.CredentialBlobSize = len(blob_bytes)
    credential.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(ctypes.c_ubyte))
    credential.Persist = 2  # CRED_PERSIST_LOCAL_MACHINE, scoped to the current logon
    credential.UserName = username
    if not api.CredWriteW(ctypes.byref(credential), 0):
        raise SecureIdentityUnavailable(f"Windows credential write failed ({ctypes.get_last_error()})")


def _windows_credential_delete(target: str) -> None:
    ctypes, _credential_type, _credential_pointer, api = _windows_credential_api()
    if not api.CredDeleteW(target, 1, 0):
        error = ctypes.get_last_error()
        if error != 1168:  # ERROR_NOT_FOUND
            raise SecureIdentityUnavailable(f"Windows credential delete failed ({error})")


def _which(command: str) -> str | None:
    from shutil import which

    return which(command)


def _run(args: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
        env={"PATH": os.getenv("PATH", "")},
    )
