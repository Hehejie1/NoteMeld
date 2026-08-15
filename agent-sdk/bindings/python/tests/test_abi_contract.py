import ctypes
import json
import unittest
from pathlib import Path

from notemeld_agent_sdk.runtime import ABI_SIGNATURES, _CALLBACK, _RELEASE_CALLBACK


class AbiContractTest(unittest.TestCase):
    def setUp(self) -> None:
        root = Path(__file__).resolve().parents[3]
        self.manifest = json.loads((root / "bindings" / "abi-v1.json").read_text())

    def test_callback_types_are_derived_independently_from_the_manifest(self) -> None:
        callback_types = {
            "void": None,
            "int32_t": ctypes.c_int32,
            "void *": ctypes.c_void_p,
            "const char *": ctypes.c_char_p,
        }
        expected = {
            callback["name"]: (
                callback_types[callback["return"]],
                tuple(callback_types[param["type"]] for param in callback["params"]),
            )
            for callback in self.manifest["callbacks"]
        }
        self.assertEqual(
            (_CALLBACK._restype_, tuple(_CALLBACK._argtypes_)),
            expected["NotemeldAgentEventCallback"],
        )
        self.assertEqual(
            (_CALLBACK._restype_, tuple(_CALLBACK._argtypes_)),
            expected["NotemeldAgentDriverCallback"],
        )
        self.assertEqual(
            (_RELEASE_CALLBACK._restype_, tuple(_RELEASE_CALLBACK._argtypes_)),
            expected["NotemeldAgentContextReleaseCallback"],
        )

    def test_all_manifest_functions_have_exact_ctypes_signatures(self) -> None:
        returns = {
            "void": None, "int32_t": ctypes.c_int32, "uint64_t": ctypes.c_uint64,
            "const char *": ctypes.c_char_p, "char *": ctypes.c_void_p,
            "AgentRuntimeHandle *": ctypes.c_void_p,
        }
        primitive_params = {
            "int32_t": ctypes.c_int32, "uint64_t": ctypes.c_uint64,
            "const char *": ctypes.c_char_p, "char *": ctypes.c_void_p,
            "void *": ctypes.c_void_p, "AgentRuntimeHandle *": ctypes.c_void_p,
        }

        callback_descriptors = {
            callback["name"]: (
                "callback",
                returns[callback["return"]],
                tuple(primitive_params[param["type"]] for param in callback["params"]),
            )
            for callback in self.manifest["callbacks"]
        }

        def descriptor(value):
            if isinstance(value, type) and issubclass(value, ctypes._CFuncPtr):
                return ("callback", value._restype_, tuple(value._argtypes_))
            return value

        expected = {
            item["name"]: (
                returns[item["return"]],
                tuple(
                    callback_descriptors.get(param["type"], primitive_params.get(param["type"]))
                    for param in item["params"]
                ),
            )
            for item in self.manifest["functions"]
        }
        actual = {
            name: (restype, tuple(descriptor(param) for param in params))
            for name, (restype, params) in ABI_SIGNATURES.items()
        }
        self.assertEqual(actual, expected)
        self.assertEqual(ABI_SIGNATURES["notemeld_agent_string_free"], (None, (ctypes.c_void_p,)))
        self.assertEqual(ABI_SIGNATURES["notemeld_agent_runtime_free"], (None, (ctypes.c_void_p,)))


if __name__ == "__main__":
    unittest.main()
