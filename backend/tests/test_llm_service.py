"""Tests for llm_service — JSON parsing, prompt handling, sanitisation."""

import pytest

from app.services.llm_service import (
    VALID_CATEGORIES,
    _parse_response,
    _sanitize_json_response,
)


class TestSanitizeJsonResponse:
    def test_plain_json(self):
        assert _sanitize_json_response('{"key": "value"}') == '{"key": "value"}'

    def test_strips_markdown_fencing(self):
        raw = '```json\n{"key": "value"}\n```'
        assert _sanitize_json_response(raw) == '{"key": "value"}'

    def test_strips_plain_fencing(self):
        raw = '```\n{"key": "value"}\n```'
        assert _sanitize_json_response(raw) == '{"key": "value"}'

    def test_strips_whitespace(self):
        raw = '  \n  {"key": "value"}  \n  '
        assert _sanitize_json_response(raw) == '{"key": "value"}'


class TestParseResponse:
    def test_valid_response(self):
        raw = '''{
            "description": "A test screenshot",
            "tags": ["test", "unit"],
            "category": "code",
            "contains_text": true,
            "extracted_text": "hello world",
            "language": "en"
        }'''
        result = _parse_response(raw)
        assert result["description"] == "A test screenshot"
        assert result["tags"] == ["test", "unit"]
        assert result["category"] == "code"
        assert result["contains_text"] is True

    def test_invalid_category_defaults_to_other(self):
        raw = '''{
            "description": "test",
            "tags": ["a"],
            "category": "INVALID_CATEGORY",
            "contains_text": false
        }'''
        result = _parse_response(raw)
        assert result["category"] == "other"

    def test_tags_truncated_to_six(self):
        raw = '''{
            "description": "test",
            "tags": ["a", "b", "c", "d", "e", "f", "g", "h"],
            "category": "photo",
            "contains_text": false
        }'''
        result = _parse_response(raw)
        assert len(result["tags"]) == 6

    def test_tags_normalised_to_lowercase(self):
        raw = '''{
            "description": "test",
            "tags": ["UPPER", "Mixed"],
            "category": "document",
            "contains_text": false
        }'''
        result = _parse_response(raw)
        assert result["tags"] == ["upper", "mixed"]

    def test_missing_required_fields(self):
        raw = '{"description": "test"}'
        with pytest.raises(ValueError, match="missing fields"):
            _parse_response(raw)

    def test_invalid_json(self):
        with pytest.raises(ValueError, match="invalid JSON"):
            _parse_response("this is not json")

    def test_with_markdown_fencing(self):
        raw = '```json\n{"description":"test","tags":["a"],"category":"photo","contains_text":false}\n```'
        result = _parse_response(raw)
        assert result["category"] == "photo"


class TestValidCategories:
    def test_expected_categories(self):
        expected = {"document", "social", "receipt", "code", "map", "photo", "meme", "other"}
        assert VALID_CATEGORIES == expected
