"""Test _vec_blob_to_json — sqlite-vec BLOB → JSON conversion."""

from __future__ import annotations

import json
import struct
import unittest

from scripts.inject_memory import _vec_blob_to_json


def _make_vec_blob(floats: list[float]) -> bytes:
    """Build a sqlite-vec vec0 embedding BLOB from a float list.

    Format: <4 bytes: dim as uint32 LE><dim * 4 bytes: float32 LE>
    """
    dim = len(floats)
    header = struct.pack("<I", dim)
    body = struct.pack(f"<{dim}f", *floats)
    return header + body


class VecBlobToJsonTests(unittest.TestCase):
    def test_1024_dim_roundtrip(self) -> None:
        """Roundtrip: Python list → BLOB → JSON → Python list."""
        original = [0.1 * (i % 10) - 0.5 for i in range(1024)]
        blob = _make_vec_blob(original)
        result = _vec_blob_to_json(blob)
        self.assertIsNotNone(result)
        parsed = json.loads(result)
        self.assertEqual(len(parsed), 1024)
        # Float32 precision: 1e-6 tolerance
        for a, b in zip(original, parsed):
            self.assertAlmostEqual(a, b, delta=1e-6)

    def test_single_element(self) -> None:
        blob = _make_vec_blob([3.14])
        result = _vec_blob_to_json(blob)
        parsed = json.loads(result)
        self.assertEqual(len(parsed), 1)
        self.assertAlmostEqual(parsed[0], 3.14, delta=1e-6)

    def test_none_returns_none(self) -> None:
        self.assertIsNone(_vec_blob_to_json(None))

    def test_too_short_returns_none(self) -> None:
        self.assertIsNone(_vec_blob_to_json(b"\x01\x00"))
        self.assertIsNone(_vec_blob_to_json(b"\x01\x00\x00\x00"))

    def test_dim_mismatch_returns_none(self) -> None:
        """BLOB header says 1024 dims but body is shorter."""
        # only 4 floats instead of 1024
        bad_blob = struct.pack("<I", 1024) + struct.pack("<4f", 1.0, 2.0, 3.0, 4.0)
        self.assertIsNone(_vec_blob_to_json(bad_blob))

    def test_empty_bytes_returns_none(self) -> None:
        self.assertIsNone(_vec_blob_to_json(b""))

    def test_dim_0(self) -> None:
        """0-dimension embedding — edge case, should not happen in practice."""
        blob = struct.pack("<I", 0)  # dim=0, no floats
        result = _vec_blob_to_json(blob)
        self.assertEqual(result, "[]")

    def test_mixed_sign_floats(self) -> None:
        # Realistic embedding values: in [-1, 1] range with signs
        original = [-1.0, 0.0, 1.0, -0.5, 0.5, 0.003, -0.997]
        blob = _make_vec_blob(original)
        result = _vec_blob_to_json(blob)
        parsed = json.loads(result)
        self.assertEqual(len(parsed), 7)
        for a, b in zip(original, parsed):
            self.assertAlmostEqual(a, b, delta=1e-6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
