import unittest
from pathlib import Path

from llm_shield.anonymizer import restore, scrub
from llm_shield.config import Pattern, ShieldConfig


def make_config(terms=("Antonio", "Antonio Maria", "ID42"), patterns=()):
    return ShieldConfig(
        root=Path("."),
        terms=terms,
        patterns=tuple(Pattern(name="test", regex=pattern) for pattern in patterns),
        placeholder_prefix="REDACTED_",
        cache_dir=Path(".llm-shield"),
    )


class AnonymizerTests(unittest.TestCase):
    def test_scrub_restore_repeated_terms_and_longest_match(self):
        original = "Antonio Maria met Antonio; ID42 and Antonio."
        result = scrub(original, make_config())

        self.assertEqual(result.text, "REDACTED_0 met REDACTED_1; REDACTED_2 and REDACTED_1.")
        self.assertEqual(restore(result.text, result.mapping), original)

    def test_regex_matches_are_restored_and_repeated_values_share_tokens(self):
        original = "Key sk_live_0123456789abcdef01234567 was repeated: sk_live_0123456789abcdef01234567"
        result = scrub(original, make_config(terms=(), patterns=(r"sk_live_[0-9a-zA-Z]{24}",)))

        self.assertEqual(result.text, "Key REDACTED_0 was repeated: REDACTED_0")
        self.assertEqual(restore(f"returned {result.text}", result.mapping), f"returned {original}")

    def test_scrub_avoids_tokens_already_present_in_input(self):
        result = scrub("REDACTED_0 and Antonio", make_config(terms=("Antonio",)))

        self.assertEqual(result.text, "REDACTED_0 and REDACTED_1")
        self.assertEqual(restore(result.text, result.mapping), "REDACTED_0 and Antonio")
