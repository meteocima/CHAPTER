"""The convert queue gate (issue #65).

`fetch_step.sh` used to drain the convert queue to zero between batches, so every
batch cost as much as its slowest job. It now admits whenever fewer than
MAX_QUEUED_CONVERTS are queued. Two properties have to hold and neither is
obvious from reading the shell:

  * it never admits past the cap, even though it avoids calling squeue every time;
  * when squeue fails it waits instead of guessing, which is what the old gate did
    and what keeps a slurm outage from flooding the queue.

The gate is extracted from the driver between its markers and run against a stub
`queued_converts`, so this tests the shipped code rather than a copy -- the same
reason `test_ledger.py` reads the driver for its tokens.
"""
import pathlib
import re
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
DRIVER = ROOT / "hpc" / "fetch_step.sh"
BEGIN = "# --- convert gate (extracted by tests/test_convert_gate.py; keep the markers) ---"
END = "# --- end convert gate ---"


@pytest.fixture(scope="module")
def gate_src():
    text = DRIVER.read_text()
    assert BEGIN in text and END in text, (
        "the convert gate markers are gone from hpc/fetch_step.sh; this test extracts "
        "the gate by them, so moving the code means moving the markers with it")
    return text.split(BEGIN, 1)[1].split(END, 1)[0]


def run(gate_src, *, gated=1, cap=4, queue=0, fail=False, attempts=10, drain=0,
        parallel=1, lag=0, budget=100000, stopped=0, body=None):
    """Ask the gate for `attempts` admissions.

    Each admission adds one job to the simulated queue; `drain` jobs leave it after
    every attempt. With `lag` > 0 an admitted job stays INVISIBLE to squeue for that
    many further attempts, which is what a backgrounded process_one does while its
    sftp runs: the slot is taken but no sbatch has happened yet.

    Returns (admitted, squeue_calls).
    """
    script = f"""
set -euo pipefail
GATED={gated}
FETCH_PARALLEL={parallel}
DRIVER_START=$(date +%s)
DRIVER_MAX_SECONDS={budget}
LAG={lag}
sleep() {{ :; }}
STOPPED={stopped}
stop_requested() {{ [ "$STOPPED" = "1" ]; }}
MAX_QUEUED_CONVERTS={cap}
QUEUE={queue}
QFAIL={1 if fail else 0}
CALLS=0
STOP_FLAG=/nonexistent
stop_requested() {{ return 1; }}
queued_converts() {{
    echo bump >> "$CALLFILE"
    [ "$QFAIL" = "1" ] && return 1
    echo "$QUEUE"
}}
{gate_src}
admitted=0
committed=0
declare -a INFLIGHT=()
for i in $(seq 1 {attempts}); do
    # Back-pressure of the real loop: it waits once FETCH_PARALLEL dispatches are
    # running, so that many is the most that can ever be in flight. Without this the
    # harness models a driver that fires without bound, and hardens the gate against
    # a case it cannot produce.
    while [ "${{#INFLIGHT[@]}}" -ge "$FETCH_PARALLEL" ]; do
        QUEUE=$((QUEUE + 1))
        INFLIGHT=(${{INFLIGHT[@]:1}})
    done
    if gate_admit; then
        admitted=$((admitted + 1))
        committed=$((committed + 1))
        INFLIGHT+=("$((i + LAG))")
    fi
    # i lavori ammessi diventano visibili a squeue solo dopo LAG tentativi
    newq=0; rest=()
    for due in ${{INFLIGHT[@]+"${{INFLIGHT[@]}}"}}; do
        if [ "$due" -le "$i" ]; then newq=$((newq + 1)); else rest+=("$due"); fi
    done
    INFLIGHT=(${{rest[@]+"${{rest[@]}}"}})
    QUEUE=$((QUEUE + newq))
    QUEUE=$(( QUEUE - {drain} < 0 ? 0 : QUEUE - {drain} ))
done
echo "RESULT ${{admitted}} COMMITTED ${{committed}}"
"""
    import tempfile, os
    with tempfile.TemporaryDirectory() as d:
        callfile = os.path.join(d, "calls")
        open(callfile, "w").close()
        p = subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                           env={**os.environ, "CALLFILE": callfile})
        assert p.returncode == 0, p.stderr
        admitted = int(re.search(r"RESULT (\d+)", p.stdout).group(1))
        calls = sum(1 for _ in open(callfile))
    return admitted, calls


def run_raw(gate_src, *, snippet, gated=1, cap=4, queue=0, fail=False, parallel=1,
            budget=100000, stopped=0):
    """Run an arbitrary snippet against the gate and return its stdout."""
    import os, subprocess, tempfile
    script = f"""
set -euo pipefail
GATED={gated}
MAX_QUEUED_CONVERTS={cap}
FETCH_PARALLEL={parallel}
DRIVER_START=$(date +%s)
DRIVER_MAX_SECONDS={budget}
QUEUE={queue}
QFAIL={1 if fail else 0}
STOP_FLAG=/nonexistent
STOPPED={stopped}
sleep() {{ :; }}
stop_requested() {{ [ "$STOPPED" = "1" ]; }}
queued_converts() {{
    echo bump >> "$CALLFILE"
    [ "$QFAIL" = "1" ] && return 1
    echo "$QUEUE"
}}
{gate_src}
{snippet}
"""
    with tempfile.TemporaryDirectory() as d:
        callfile = os.path.join(d, "calls")
        open(callfile, "w").close()
        p = subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                           timeout=60, env={**os.environ, "CALLFILE": callfile})
        return p.stdout + p.stderr


def test_gate_off_admits_everything_without_asking_slurm(gate_src):
    admitted, calls = run(gate_src, gated=0, attempts=25)
    assert admitted == 25
    assert calls == 0


def test_never_admits_past_the_cap(gate_src):
    """Jobs never leave the queue, so admissions must stop at the cap."""
    admitted, _ = run(gate_src, cap=4, attempts=20, drain=0)
    assert admitted == 4


def test_the_cap_is_honoured_for_several_sizes(gate_src):
    for cap in (1, 2, 8, 48, 96):
        admitted, _ = run(gate_src, cap=cap, attempts=cap + 15, drain=0)
        assert admitted == cap, f"cap {cap} admitted {admitted}"


def test_a_full_queue_admits_nothing(gate_src):
    admitted, calls = run(gate_src, cap=4, queue=4, attempts=6, drain=0)
    assert admitted == 0
    assert calls > 0, "it must actually ask slurm before refusing"


def test_room_freed_is_room_used(gate_src):
    """One job leaves per attempt: the gate keeps admitting instead of stalling."""
    admitted, _ = run(gate_src, cap=4, attempts=20, drain=1)
    assert admitted == 20


def test_squeue_failure_waits_instead_of_guessing(gate_src):
    """A slurm outage must not look like an empty queue."""
    admitted, calls = run(gate_src, cap=4, queue=4, fail=True, attempts=8)
    assert admitted == 0
    assert calls == 8, "every refusal under failure should have tried squeue"


def test_it_does_not_call_squeue_once_per_admission(gate_src):
    """The cached estimate is the point: one squeue per batch of N, not per timestep."""
    admitted, calls = run(gate_src, cap=48, attempts=48, drain=0)
    assert admitted == 48
    assert calls <= 2, f"{calls} squeue calls for 48 admissions"


# --- found by review of 0f674cf ----------------------------------------------

def test_the_cap_holds_even_when_submission_lags_behind_admission(gate_src):
    """With FETCH_PARALLEL > 1 the sbatch happens inside a backgrounded
    process_one, minutes after the slot was taken. A refresh that trusts squeue
    alone forgets those, and the cap is exceeded by up to FETCH_PARALLEL."""
    admitted, _ = run(gate_src, cap=4, attempts=30, drain=0, parallel=3, lag=3)
    assert admitted <= 4, f"committed {admitted} converts against a cap of 4"


def test_the_cap_holds_at_campaign_settings(gate_src):
    # parallel=6 since 2026-10-06 (#69): the campaign's download chains run at the
    # measured knee, and the gate's reserve is derived from exactly this number.
    admitted, _ = run(gate_src, cap=48, attempts=200, drain=0, parallel=6, lag=6)
    assert admitted <= 48, f"committed {admitted} against a cap of 48"


def test_gate_wait_gives_up_when_the_driver_time_budget_is_spent(gate_src):
    """The old gate slept and re-entered the main loop, where the budget check
    respawns the driver. gate_wait loops on its own, so without a budget check a
    full queue parks a login-node process indefinitely and it writes no ledger
    entry while parked."""
    out = run_raw(gate_src, cap=4, queue=4, budget=0, snippet='''
set +e; gate_wait; rc=$?; set -e; echo "WAIT_RC $rc"
''')
    assert "WAIT_RC 0" not in out, "gate_wait must not succeed on a full queue"
    assert "WAIT_RC 1" not in out, (
        "a spent budget must be distinguishable from a stop request, so the caller "
        "can respawn instead of exiting")


def test_gate_wait_reports_a_stop_request_distinctly(gate_src):
    out = run_raw(gate_src, cap=4, queue=4, budget=100000, stopped=1, snippet='''
set +e; gate_wait; rc=$?; set -e; echo "WAIT_RC $rc"
''')
    assert "WAIT_RC 1" in out


def test_gate_wait_returns_success_when_there_is_room(gate_src):
    out = run_raw(gate_src, cap=4, queue=0, snippet='''
set +e; gate_wait; rc=$?; set -e; echo "WAIT_RC $rc"
''')
    assert "WAIT_RC 0" in out
