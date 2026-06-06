import unittest

from spine.core import SpineValidationError
from spine.core.canonical_json import canonical_json_bytes, canonical_json_text


class CanonicalJsonTests(unittest.TestCase):
    def test_object_keys_sort_and_arrays_preserve_order(self) -> None:
        value = {"z": ["second", "first"], "a": {"b": True, "a": None}}

        self.assertEqual(canonical_json_text(value), '{"a":{"a":null,"b":true},"z":["second","first"]}')

    def test_string_escaping_is_canonical(self) -> None:
        value = {"s": 'quote" slash/ backslash\\ newline\n tab\t café'}

        self.assertEqual(
            canonical_json_text(value),
            '{"s":"quote\\" slash/ backslash\\\\ newline\\u000a tab\\u0009 café"}',
        )

    def test_utf8_bytes_are_not_ascii_escaped(self) -> None:
        self.assertEqual(canonical_json_bytes({"place": "café"}), b'{"place":"caf\xc3\xa9"}')

    def test_numbers_are_rejected_but_booleans_are_allowed(self) -> None:
        self.assertEqual(canonical_json_text({"ok": False}), '{"ok":false}')

        with self.assertRaisesRegex(SpineValidationError, "canonical_json_number_not_allowed"):
            canonical_json_text({"count": 1})

        with self.assertRaisesRegex(SpineValidationError, "canonical_json_number_not_allowed"):
            canonical_json_text({"ratio": 1.5})

    def test_invalid_surrogate_code_points_are_rejected(self) -> None:
        with self.assertRaisesRegex(SpineValidationError, "canonical_json_invalid_surrogate"):
            canonical_json_text({"bad": "\ud800"})

    def test_non_string_object_keys_are_rejected(self) -> None:
        with self.assertRaisesRegex(SpineValidationError, "canonical_json_non_string_key"):
            canonical_json_text({1: "one"})


if __name__ == "__main__":
    unittest.main()
