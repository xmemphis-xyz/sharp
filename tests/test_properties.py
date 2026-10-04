"""Regression tests using the pinned Sharp API dependency."""
import importlib.util
import unittest
from pathlib import Path

from aiosharp_cocoro_air import SharpApiError, decode_echonet_property
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
        with self.assertRaises(SharpApiError):
            api.sanitize_properties("invalid")

    def test_real_decoder_survives_empty_fields(self):
        clean = api.sanitize_properties("00000000000000008000840200098800a000c000")
        self.assertEqual(decode_echonet_property(clean), {"power_watts": 9})


if __name__ == "__main__":
    unittest.main()
