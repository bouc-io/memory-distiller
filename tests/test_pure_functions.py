"""Unit tests for the memory-distiller pure helper functions.

Run from the memory-distiller directory:
    python -m pytest
"""
import os
import sys

# Make the package root importable when pytest is invoked from the repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import map_importance, map_category  # noqa: E402
from llm_client import _robust_json_parse  # noqa: E402


class TestMapImportance:
    def test_critical_threshold(self):
        assert map_importance(0.9) == "critical"
        assert map_importance(0.95) == "critical"

    def test_high_threshold(self):
        assert map_importance(0.7) == "high"
        assert map_importance(0.89) == "high"

    def test_medium_threshold(self):
        assert map_importance(0.4) == "medium"
        assert map_importance(0.69) == "medium"

    def test_low_threshold(self):
        assert map_importance(0.0) == "low"
        assert map_importance(0.39) == "low"


class TestMapCategory:
    def test_known_distiller_types(self):
        assert map_category("semantic") == "fact"
        assert map_category("episodic") == "context"
        assert map_category("procedural") == "instruction"
        assert map_category("personal") == "persona"
        assert map_category("preference") == "preference"

    def test_unknown_type_defaults_to_fact(self):
        assert map_category("nonsense") == "fact"


class TestRobustJsonParse:
    def test_plain_json_object(self):
        assert _robust_json_parse('{"a": 1}') == {"a": 1}

    def test_strips_markdown_fences(self):
        assert _robust_json_parse('```json\n{"a": 1}\n```') == {"a": 1}

    def test_extracts_object_from_surrounding_prose(self):
        assert _robust_json_parse('Here you go: {"a": 1} hope that helps') == {"a": 1}

    def test_extracts_array(self):
        assert _robust_json_parse('prefix [1, 2, 3] suffix') == [1, 2, 3]

    def test_unparseable_returns_raw_string(self):
        assert _robust_json_parse("not json at all") == "not json at all"
