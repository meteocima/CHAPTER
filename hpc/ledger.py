"""The vocabulary of the step-pipeline ledger.

`fetch_step.sh` appends one line per outcome to the status ledger. This module
holds what those tokens mean and turns a ledger into the three things a report
needs: the per-timestep problems, the per-chain events, and whatever it could
not recognise.
"""

import collections

PROBLEM = 'problem'
CLEAR = 'clear'
CHAIN = 'chain'

# What the driver can say about a timestep or about itself. A token absent from
# this mapping is unknown BY CONSTRUCTION, and unknown is reported rather than
# dropped -- the two-set version of this table had no way to say "neither", which
# is how RESPAWN_FAILED, DATAMOVER_UNREACHABLE and REF_OK went unseen (issue #1).
TOKEN_KINDS = {
    # the timestep is fine, and this clears any problem logged against it
    'FETCH_OK': CLEAR,
    'CONVERT_SUBMITTED': CLEAR,
    'SKIP_GRIB_EXISTS': CLEAR,
    'SKIP_RAW_EXISTS': CLEAR,
    'REF_OK': CLEAR,

    # the timestep needs attention: usually a re-run, a recall on LRZ only if it
    # persists across re-runs
    'MISSING_ON_LRZ': PROBLEM,
    'FETCH_TIMEOUT': PROBLEM,
    'UNREADABLE': PROBLEM,
    'FETCH_ERROR': PROBLEM,
    'SKIP_OFFLINE': PROBLEM,
    'REF_UNAVAILABLE': PROBLEM,

    # about the chain itself, keyed DRIVER@<host> and not about any timestep
    'RESPAWN_FAILED': CHAIN,
    'DATAMOVER_UNREACHABLE': CHAIN,

    # historical: no current driver writes these, but they sit in live ledgers.
    # TAPE_TIMEOUT and UNREADABLE_TAPE were renamed (cae74a3, c67b7f9);
    # CONVERT_RESUBMITTED never existed in a committed driver at all, so the
    # share2024 chain ran a locally edited one -- which the snapshot mechanism
    # allows and this table has to survive
    'TAPE_TIMEOUT': PROBLEM,
    'UNREADABLE_TAPE': PROBLEM,
    'CONVERT_RESUBMITTED': CLEAR,
}

# Of the above, the ones no current driver writes. Named so that the drift test
# can tell "the driver gained a token" from "the driver lost one".
HISTORICAL = frozenset({'TAPE_TIMEOUT', 'UNREADABLE_TAPE', 'CONVERT_RESUBMITTED'})

Summary = collections.namedtuple('Summary', 'problems chain_events unknown')


def classify(lines):
    """Turn ledger lines into a Summary. Pure: no file access, no printing."""
    problems = {}
    chain_events = []
    unknown = collections.Counter()
    for raw in lines:
        parts = [p.strip() for p in raw.split('|')]
        if len(parts) < 3:
            continue        # a line half-written when the driver was killed
        key, token = parts[1], parts[2]
        detail = parts[3] if len(parts) > 3 else ''
        kind = TOKEN_KINDS.get(token)
        if kind == PROBLEM:
            problems[key] = (token, detail)
        elif kind == CLEAR:
            problems.pop(key, None)
        elif kind == CHAIN:
            # Not last-wins: a driver that failed to respawn failed, and a later
            # chain succeeding does not unmake it.
            chain_events.append((key, token, detail))
        else:
            # Never drop it: a token this module has not been taught is exactly
            # how a report comes to understate what went wrong.
            unknown[token] += 1
    return Summary(problems=problems, chain_events=chain_events,
                   unknown=dict(unknown))
