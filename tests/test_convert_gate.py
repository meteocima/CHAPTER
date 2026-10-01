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


def run(gate_src, *, gated=1, cap=4, queue=0, fail=False, attempts=10, drain=0):
    """Ask the gate for `attempts` admissions.

    Each admission adds one job to the simulated queue; `drain` jobs leave it after
    every attempt. Returns (admitted, squeue_calls).
    """
    script = f"""
set -u
GATED={gated}
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
for i in $(seq 1 {attempts}); do
    if gate_admit; then
        admitted=$((admitted + 1))
        QUEUE=$((QUEUE + 1))
    fi
    QUEUE=$(( QUEUE - {drain} < 0 ? 0 : QUEUE - {drain} ))
done
echo "RESULT ${{admitted}}"
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
