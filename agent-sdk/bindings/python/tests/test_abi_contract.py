import ctypes
import json
import unittest
from pathlib import Path

from notemeld_agent_sdk.runtime import ABI_SIGNATURES, _CALLBACK, _RELEASE_CALLBACK


class AbiContractTest(unittest.TestCase):
    def test_all_manifest_functions_have_exact_ctypes_signatures(self) -> None:
        root = Path(__file__).resolve().parents[3]
        manifest = json.loads((root / "bindings" / "abi-v1.json").read_text())
        returns = {
            "void": None, "int32_t": ctypes.c_int32, "uint64_t": ctypes.c_uint64,
            "const char *": ctypes.c_char_p, "char *": ctypes.c_void_p,
            "AgentRuntimeHandle *": ctypes.c_void_p,
        }
        params = {
            "int32_t": ctypes.c_int32, "uint64_t": ctypes.c_uint64,
            "const char *": ctypes.c_char_p, "char *": ctypes.c_void_p,
            "void *": ctypes.c_void_p, "AgentRuntimeHandle *": ctypes.c_void_p,
            "NotemeldAgentEventCallback": _CALLBACK,
            "NotemeldAgentDriverCallback": _CALLBACK,
            "NotemeldAgentContextReleaseCallback": _RELEASE_CALLBACK,
        }
        expected = {
            item["name"]: (
                returns[item["return"]],
                tuple(params[param["type"]] for param in item["params"]),
            )
            for item in manifest["functions"]
        }
        self.assertEqual(ABI_SIGNATURES, expected)
        self.assertEqual(ABI_SIGNATURES["notemeld_agent_runtime_set_callbacks"], (
            ctypes.c_int32,
            (ctypes.c_void_p, _CALLBACK, ctypes.c_void_p, _CALLBACK,
             ctypes.c_void_p, _RELEASE_CALLBACK, ctypes.c_void_p),
        ))
        self.assertEqual(ABI_SIGNATURES["notemeld_agent_string_free"], (None, (ctypes.c_void_p,)))
        self.assertEqual(ABI_SIGNATURES["notemeld_agent_runtime_free"], (None, (ctypes.c_void_p,)))


if __name__ == "__main__":
    unittest.main()
