"""Regression tests for empty Sharp cloud properties (stdlib only)."""
import importlib.util
import sys
import types
import unittest
from pathlib import Path

stub = types.ModuleType("aiosharp_cocoro_air")
stub.SharpCOCOROAir = type("SharpCOCOROAir", (), {})
stub.SharpApiError = type("SharpApiError", (Exception,), {})
sys.modules["aiosharp_cocoro_air"] = stub
spec = importlib.util.spec_from_file_location(
    "sharp_api", Path(__file__).parents[1] / "custom_components/sharp_life_air/api.py"
)
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


class TestProperties(unittest.TestCase):
    def test_empty_power_with_valid_readings(self):
        value = "00000000000000008000840200098800a000c000"
        self.assertEqual(api.sanitize_properties(value), "000000000000000084020009")

    def test_valid_power_preserved(self):
        value = "000000000000000080013084020009"
        self.assertEqual(api.sanitize_properties(value), value)

    def test_missing_values(self):
        for value in (None, "", "00"):
            self.assertEqual(api.sanitize_properties(value), "")

    def test_truncated_property_preserves_previous(self):
        self.assertEqual(
            api.sanitize_properties("0000000000000000800130840200"),
            "0000000000000000800130",
        )

    def test_invalid_hex(self):
        with self.assertRaises(stub.SharpApiError):
            api.sanitize_properties("invalid")


if __name__ == "__main__":
    unittest.main()
