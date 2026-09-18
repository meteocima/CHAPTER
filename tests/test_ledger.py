"""The ledger vocabulary: which tokens mean trouble for a timestep, which clear
it, which are about the chain itself, and which the reporter does not know."""

import os
import re

import pytest

from hpc import ledger


def line(timestep, token, detail=""):
    return f"2026-09-18T10:00:00Z | {timestep} | {token} | {detail}"


def test_a_problem_token_is_reported_against_its_timestep():
    result = ledger.classify([line("2025-06-30T20", "MISSING_ON_LRZ", 'File "..." not found.')])

    assert result.problems == {"2025-06-30T20": ("MISSING_ON_LRZ", 'File "..." not found.')}


def test_a_later_clear_token_clears_an_earlier_problem():
    result = ledger.classify([
        line("2025-06-30T20", "FETCH_TIMEOUT", "sftp exceeded 600s"),
        line("2025-06-30T20", "FETCH_OK", "size=9139353544B"),
    ])

    assert result.problems == {}


def test_an_earlier_clear_token_does_not_excuse_a_later_problem():
    result = ledger.classify([
        line("2025-06-30T20", "FETCH_OK", "size=9139353544B"),
        line("2025-06-30T20", "FETCH_TIMEOUT", "sftp exceeded 600s"),
    ])

    assert result.problems == {"2025-06-30T20": ("FETCH_TIMEOUT", "sftp exceeded 600s")}


def test_a_chain_event_is_kept_apart_from_the_timestep_table():
    result = ledger.classify([
        line("DRIVER@login02", "RESPAWN_FAILED", "driver script unparsable"),
    ])

    assert result.problems == {}
    assert result.chain_events == [
        ("DRIVER@login02", "RESPAWN_FAILED", "driver script unparsable"),
    ]


def test_a_chain_event_is_never_cleared_and_keeps_ledger_order():
    result = ledger.classify([
        line("DRIVER@login08", "DATAMOVER_UNREACHABLE", "run from a regular login node"),
        line("DRIVER@login02", "RESPAWN_FAILED", "driver script unparsable"),
        line("DRIVER@login02", "FETCH_OK", "size=9139353544B"),
    ])

    assert result.chain_events == [
        ("DRIVER@login08", "DATAMOVER_UNREACHABLE", "run from a regular login node"),
        ("DRIVER@login02", "RESPAWN_FAILED", "driver script unparsable"),
    ]


def test_an_unrecognised_token_is_counted_and_named():
    result = ledger.classify([
        line("2025-06-30T22", "FETCH_DEFERRED", "job=12345"),
        line("2025-06-30T21", "FETCH_DEFERRED", "job=12346"),
        line("2025-06-30T20", "SOMETHING_NEW", ""),
    ])

    assert result.unknown == {"FETCH_DEFERRED": 2, "SOMETHING_NEW": 1}


def test_an_unrecognised_token_neither_raises_nor_clears_a_problem():
    result = ledger.classify([
        line("2025-06-30T20", "FETCH_TIMEOUT", "sftp exceeded 600s"),
        line("2025-06-30T20", "SOMETHING_NEW", ""),
    ])

    assert result.problems == {"2025-06-30T20": ("FETCH_TIMEOUT", "sftp exceeded 600s")}
    assert result.chain_events == []
    assert result.unknown == {"SOMETHING_NEW": 1}


def test_a_truncated_line_is_skipped_rather_than_costing_the_whole_report():
    result = ledger.classify([
        line("2025-06-30T20", "FETCH_TIMEOUT", "sftp exceeded 600s"),
        "2026-09-18T10:00:00Z | 2025-06-30T1",          # crash mid-write
        "",
        line("2025-06-30T19", "MISSING_ON_LRZ", ""),
    ])

    assert set(result.problems) == {"2025-06-30T20", "2025-06-30T19"}
    assert result.unknown == {}


def test_a_token_with_no_detail_field_is_still_classified():
    result = ledger.classify(["2026-09-18T10:00:00Z | 2025-06-30T20 | MISSING_ON_LRZ"])

    assert result.problems == {"2025-06-30T20": ("MISSING_ON_LRZ", "")}


def test_an_empty_ledger_yields_nothing():
    result = ledger.classify([])

    assert result.problems == {}
    assert result.chain_events == []
    assert result.unknown == {}


# The classification settled in the spec of issue #1. Kept as a literal so that
# changing a token's meaning has to be a deliberate edit here, not a side effect.
EXPECTED_KINDS = {
    'FETCH_OK': ledger.CLEAR,
    'CONVERT_SUBMITTED': ledger.CLEAR,
    'SKIP_GRIB_EXISTS': ledger.CLEAR,
    'SKIP_RAW_EXISTS': ledger.CLEAR,
    'REF_OK': ledger.CLEAR,
    'MISSING_ON_LRZ': ledger.PROBLEM,
    'FETCH_TIMEOUT': ledger.PROBLEM,
    'UNREADABLE': ledger.PROBLEM,
    'FETCH_ERROR': ledger.PROBLEM,
    'SKIP_OFFLINE': ledger.PROBLEM,
    'REF_UNAVAILABLE': ledger.PROBLEM,
    'RESPAWN_FAILED': ledger.CHAIN,
    'DATAMOVER_UNREACHABLE': ledger.CHAIN,
    # Historical: written by drivers that no longer exist, still in live ledgers.
    'TAPE_TIMEOUT': ledger.PROBLEM,
    'UNREADABLE_TAPE': ledger.PROBLEM,
    'CONVERT_RESUBMITTED': ledger.CLEAR,
}


def observed_kind(token):
    """The kind a token has as far as anyone reading a report can tell."""
    key = "DRIVER@login02" if token in CHAIN_KEYED else "2025-06-30T20"
    # A problem is pre-loaded so that a clear token has something to clear: that
    # is the only way "clear" is observable from outside.
    result = ledger.classify([
        line(key, "MISSING_ON_LRZ", "pre-existing"),
        line(key, token, "detail"),
    ])
    if result.unknown:
        return "unknown"
    if result.chain_events:
        return ledger.CHAIN
    return ledger.PROBLEM if key in result.problems else ledger.CLEAR


CHAIN_KEYED = {t for t, kind in EXPECTED_KINDS.items() if kind == ledger.CHAIN}


@pytest.mark.parametrize("token,kind", sorted(EXPECTED_KINDS.items()))
def test_every_token_lands_in_its_kind(token, kind):
    assert observed_kind(token) == kind


# --- drift ------------------------------------------------------------------
# The driver is bash and this module is Python, so the token table cannot be
# shared with the code that writes it. This test is the bridge: it reads the
# tokens back out of the driver and insists the two agree. It is coupled to the
# shape of a shell string literal on purpose -- that coupling is what makes
# "someone added a token and forgot the reporter" a failure instead of a silence.

DRIVER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "hpc", "fetch_step.sh")


TOKEN_LITERAL = r'"([A-Z][A-Z0-9_]{2,})"'


def tokens_written_by_the_driver():
    """Every ledger token fetch_step.sh can write, read back out of the script.

    Two shapes, because the driver has two: the token is usually a literal
    argument of log_status, but already_done() prints the skip tag for its caller
    to pass on, so `echo "SKIP_..."` is a writer too.
    """
    found = set()
    with open(DRIVER) as fh:
        for ln in fh:
            if "log_status" in ln:
                found |= set(re.findall(TOKEN_LITERAL, ln))
            printed = re.search(r"\becho\s+" + TOKEN_LITERAL, ln)
            if printed:
                found.add(printed.group(1))
    return found


def test_the_driver_tokens_can_still_be_read_out_of_the_driver():
    """Guards the three tests below: a subset assertion passes trivially against
    an empty set, so a regex that quietly stops matching would look like health."""
    assert len(tokens_written_by_the_driver()) == 13


def test_the_driver_writes_no_token_this_module_has_not_been_taught():
    assert tokens_written_by_the_driver() - set(ledger.TOKEN_KINDS) == set()


def test_this_module_claims_no_current_token_the_driver_never_writes():
    claimed = set(ledger.TOKEN_KINDS) - set(ledger.HISTORICAL)

    assert claimed - tokens_written_by_the_driver() == set()


def test_the_historical_tokens_are_not_written_by_the_driver_any_more():
    assert set(ledger.HISTORICAL) & tokens_written_by_the_driver() == set()
