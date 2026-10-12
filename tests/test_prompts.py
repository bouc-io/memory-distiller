"""
Prompt registry tests.

The one that matters is TestDriftGate: it compares the loaded registry against the
committed prompts/promptset.lock.json. The Node services get this from their committed
generated.ts; this service loads markdown at runtime, so without the lock there is nothing
to compare against and a prompt edit could ship without a version bump unnoticed, which
would make the promptset hash recorded on eval rows describe text that is not what ran.

The byte-for-byte comparison against the pre-extraction constants in prompts.py was a
one-time migration check. It passed at extraction time and was then deleted, since its
subject no longer exists in HEAD and pinning it to a commit would break under GitLab CI's
shallow clone.
"""

import hashlib
import pathlib
import re
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))  # noqa: E402

import prompts as registry  # noqa: E402

EXPECTED_IDS = {
    "system_preamble",
    "segmentation",
    "worthiness",
    "synthesis",
    "scoring",
    "combined_eval",
}


class TestRegistry:
    def test_loads_all_six_units(self):
        assert set(registry.PROMPTS) == EXPECTED_IDS

    def test_promptset_version_and_hash_are_wellformed(self):
        # Deliberately not pinned to a literal version: bumping promptset.json is the
        # correct response to a prompt change and must not fail the suite.
        assert re.fullmatch(r"\d+\.\d+\.\d+", registry.PROMPTSET_VERSION), (
            registry.PROMPTSET_VERSION
        )
        assert re.fullmatch(r"[0-9a-f]{64}", registry.PROMPTSET_HASH)

    def test_no_trailing_newline_in_templates(self):
        # The original constants had none; a stray one would change every system message.
        for pid, entry in registry.PROMPTS.items():
            assert not entry["template"].endswith("\n"), pid

    def test_get_prompt_rejects_unknown_id(self):
        with pytest.raises(KeyError):
            registry.get_prompt("nope")

    def test_list_prompts_is_sorted_and_complete(self):
        listed = registry.list_prompts()
        assert len(listed) == 6
        assert [p["id"] for p in listed] == sorted(EXPECTED_IDS)


class TestDriftGate:
    """The committed lock must describe the prompts actually on disk."""

    REGENERATE = "python prompts.py --write-lock"

    def test_lock_matches_loaded_prompts(self):
        lock = registry.read_lock()
        assert lock is not None, f"missing lock. Run: {self.REGENERATE}"
        assert lock == registry.build_lock(), (
            "Prompt drift: prompts/*.md no longer match the committed lock. If the change "
            f"was intentional, bump the affected version(s) and run: {self.REGENERATE}"
        )

    def test_lock_covers_every_unit(self):
        lock = registry.read_lock()
        assert set(lock["prompts"]) == EXPECTED_IDS

    def test_set_hash_changes_when_a_template_changes(self):
        """
        Guards the gate itself: the set hash must actually depend on template content, so a
        silently edited prompt cannot keep the same promptset hash.
        """
        baseline = registry.build_lock()["promptset_hash"]
        original = registry.PROMPTS["scoring"]["template"]
        try:
            registry.PROMPTS["scoring"]["template"] = original + " (mutated)"
            registry.PROMPTS["scoring"]["hash"] = hashlib.sha256(
                registry.PROMPTS["scoring"]["template"].encode("utf-8")
            ).hexdigest()
            assert registry.build_lock()["promptset_hash"] != baseline
        finally:
            registry.PROMPTS["scoring"]["template"] = original
            registry.PROMPTS["scoring"]["hash"] = hashlib.sha256(
                original.encode("utf-8")
            ).hexdigest()
        assert registry.build_lock()["promptset_hash"] == baseline
