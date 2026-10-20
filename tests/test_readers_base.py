"""Tests for the Reader protocol and all_readers discovery."""
from __future__ import annotations
import tempfile
from pathlib import Path
from moatleak.readers import all_readers


def test_all_readers_returns_three():
    """all_readers() returns exactly 3 Reader objects."""
    readers = all_readers()
    assert len(readers) == 3, f"Expected 3 readers, got {len(readers)}"


def test_all_readers_names():
    """Each reader has the correct name attribute."""
    readers = all_readers()
    names = {r.name for r in readers}
    expected = {"hermes_log", "hermes_db", "claude_code"}
    assert names == expected, f"Expected names {expected}, got {names}"


def test_all_readers_have_callables():
    """Each reader has callable detect, iter_rows, iter_content."""
    readers = all_readers()
    for reader in readers:
        assert callable(reader.detect), f"{reader.name}: detect is not callable"
        assert callable(reader.iter_rows), f"{reader.name}: iter_rows is not callable"
        assert callable(reader.iter_content), f"{reader.name}: iter_content is not callable"


def test_detect_returns_false_on_empty_home(tmp_path):
    """Every reader's detect() returns False when home dir is empty."""
    readers = all_readers()
    for reader in readers:
        result = reader.detect(tmp_path)
        assert result is False, f"{reader.name}: detect() should return False for empty dir, got {result}"


def test_iter_content_yields_nothing_on_empty_home(tmp_path):
    """Every reader's iter_content() yields nothing when home dir is empty."""
    readers = all_readers()
    for reader in readers:
        content_list = list(reader.iter_content(tmp_path))
        assert len(content_list) == 0, f"{reader.name}: iter_content() should yield nothing for empty dir, got {len(content_list)} items"
