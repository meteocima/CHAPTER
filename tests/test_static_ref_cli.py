"""The --check-wrfout parser (issue #62).

`static_ref.py`'s docstring showed `[--check-wrfout <wrfout> ...]` while the
parser consumed exactly one path per flag and rejected the rest with exit 2.
That cost two SLURM jobs. The parser now accepts both spellings, and this file
is what keeps the two from drifting apart again -- pure string logic, the same
reason `test_ledger.py` exists.

Imported by path so the test does not depend on netCDF4 being importable:
`static_ref` is at the repository root and pulls the whole conversion stack in
at module level.
"""
import importlib.util
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def parse():
    spec = importlib.util.spec_from_file_location("static_ref", ROOT / "static_ref.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["static_ref"] = mod
    spec.loader.exec_module(mod)
    return mod._parse_check_args


def test_no_checks_is_not_an_error(parse):
    assert parse([]) == ([], None)


def test_one_path(parse):
    assert parse(["--check-wrfout", "/a/w1"]) == (["/a/w1"], None)


def test_the_form_the_docstring_shows(parse):
    """Several paths after one flag -- this is what used to exit 2."""
    assert parse(["--check-wrfout", "/a/w1", "/a/w2", "/a/w3"]) == (
        ["/a/w1", "/a/w2", "/a/w3"], None)


def test_the_form_the_parser_used_to_demand(parse):
    assert parse(["--check-wrfout", "/a/w1", "--check-wrfout", "/a/w2"]) == (
        ["/a/w1", "/a/w2"], None)


def test_the_two_forms_agree(parse):
    """The point of the fix: both spellings name the same set of files."""
    listed, _ = parse(["--check-wrfout", "/a/w1", "/a/w2", "/a/w3"])
    repeated, _ = parse(["--check-wrfout", "/a/w1",
                         "--check-wrfout", "/a/w2",
                         "--check-wrfout", "/a/w3"])
    assert listed == repeated


def test_mixed_forms(parse):
    assert parse(["--check-wrfout", "/a/w1", "/a/w2",
                  "--check-wrfout", "/a/w3"]) == (["/a/w1", "/a/w2", "/a/w3"], None)


def test_a_bare_path_first_is_rejected(parse):
    paths, err = parse(["/a/w1"])
    assert paths == []
    assert "--check-wrfout" in err


def test_an_empty_flag_is_rejected(parse):
    """A trailing flag with nothing after it must not pass silently."""
    paths, err = parse(["--check-wrfout"])
    assert paths == []
    assert "at least one" in err


def test_an_empty_flag_before_another_is_rejected(parse):
    paths, err = parse(["--check-wrfout", "--check-wrfout", "/a/w1"])
    assert paths == []
    assert "at least one" in err


def test_an_unknown_flag_is_rejected(parse):
    paths, err = parse(["--check-wrfout", "/a/w1", "--verbose"])
    assert paths == []
    assert "--verbose" in err
