"""A phase that produced nothing must not look finished (issue #68).

The sequence scripts logged `0 done, 72 pending` and then `DONE | all phases
processed`, and marched on to spend another 10 TB of relay. The count was right
there and nothing acted on it.

The seam is the report itself: `do_report` returns what it counted, and the CLI
exits non-zero in report mode when anything is still pending, so the shell reads
an exit status instead of re-deriving a number we already computed.
"""
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "hpc"))

import submit_step_pipeline as ssp  # noqa: E402

TEMPLATE = "g-{year}-{date_compact}{hour:02d}.grib"


def make_gribs(grib_dir, hours):
    """Create the artefacts for `hours`, as (YYYY-MM-DD, HH) pairs."""
    for day, hh in hours:
        y, m, _ = day.split("-")
        d = grib_dir / y / m
        d.mkdir(parents=True, exist_ok=True)
        (d / f"g-{y}-{day.replace('-', '')}{hh}.grib").write_text("x")


def report(tmp_path, produced_hours, status_lines="", start="2019-09-07T00",
           end="2019-09-07T03"):
    grib_dir = tmp_path / "grib"
    grib_dir.mkdir(exist_ok=True)
    make_gribs(grib_dir, produced_hours)
    log = tmp_path / "status.log"
    log.write_text(status_lines)
    return ssp.do_report(start, end, "backward", str(grib_dir), TEMPLATE, str(log))


def test_a_window_with_nothing_produced_reports_every_hour_pending(tmp_path):
    done, pending, recall = report(tmp_path, [])
    assert (done, pending, recall) == (0, 4, 0)


def test_a_fully_produced_window_reports_nothing_pending(tmp_path):
    hours = [("2019-09-07", h) for h in ("00", "01", "02", "03")]
    done, pending, recall = report(tmp_path, hours)
    assert (done, pending, recall) == (4, 0, 0)


def test_a_partly_produced_window_counts_both(tmp_path):
    done, pending, recall = report(tmp_path, [("2019-09-07", "00"), ("2019-09-07", "02")])
    done_, pending_, recall_ = done, pending, recall
    assert (done_, pending_, recall_) == (2, 2, 0)


def test_a_logged_problem_is_counted_as_recall_not_as_pending(tmp_path):
    """An hour the source could not supply is a different thing from an hour
    nobody attempted, and the sequence should be able to tell them apart."""
    lines = ("2026-10-02T10:00:00Z | 2019-09-07T01 | MISSING_ON_LRZ | not found\n")
    done, pending, recall = report(tmp_path, [("2019-09-07", "00")], status_lines=lines)
    assert done == 1
    assert recall == 1
    assert pending == 2


# --- the seam the shell actually uses: the process exit status ----------------
# These shell out, which is slow, and they are worth it: the sequence scripts
# branch on the exit code of this exact command line, and nothing else here
# proves that contract.

import json  # noqa: E402
import os  # noqa: E402
import subprocess  # noqa: E402

UV = os.path.expanduser("~/.local/bin/uv")


def production_template():
    """The real naming template. Read from the config rather than copied, so the
    test cannot keep passing against a template the pipeline no longer uses."""
    import re
    text = (ROOT / "conf" / "pipeline.yaml").read_text()
    m = re.search(r'^\s*name_template:\s*"([^"]+)"', text, re.M)
    assert m, "name_template not found in conf/pipeline.yaml"
    return m.group(1)


def run_cli(tmp_path, produced_hours):
    """Hydra's override grammar rejects the braces in a template, so these use
    the production one and name the artefacts through the pipeline's own
    grib_name()."""
    from datetime import datetime
    tpl = production_template()
    grib_dir = tmp_path / "grib"
    for day, hh in produced_hours:
        dt = datetime.strptime(f"{day}T{hh}", "%Y-%m-%dT%H")
        d = grib_dir / f"{dt.year:04d}" / f"{dt.month:02d}"
        d.mkdir(parents=True, exist_ok=True)
        (d / ssp.grib_name(tpl, dt)).write_text("x")
    grib_dir.mkdir(exist_ok=True)
    log = tmp_path / "status.log"
    log.write_text("")
    cmd = [UV, "run", "python", "hpc/submit_step_pipeline.py", "report=true",
           "window.start_date=2019-09-07", "window.start_hour=0",
           "window.end_date=2019-09-07", "window.end_hour=3",
           f"paths.grib_dir={grib_dir}", f"paths.status_log={log}"]
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=300)


@pytest.mark.slow
def test_report_exits_nonzero_when_hours_are_still_pending(tmp_path):
    p = run_cli(tmp_path, [])
    assert "0 done, 4 pending" in p.stdout
    assert p.returncode != 0, "a phase that produced nothing must not exit 0"


@pytest.mark.slow
def test_report_exits_zero_when_the_window_is_complete(tmp_path):
    p = run_cli(tmp_path, [("2019-09-07", h) for h in ("00", "01", "02", "03")])
    assert "4 done, 0 pending" in p.stdout
    assert p.returncode == 0
