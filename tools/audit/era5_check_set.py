#!/usr/bin/env python3
"""Is the ERA5 comparison set complete, and does it hold what was asked for?

    source tools/eccodes_env.sh
    uv run python tools/audit/era5_check_set.py

The fetch reports what the server sent; this reports what is on disk. They are
not the same claim, and the audit's rule is that the second one is the one that
counts. Checks, per sample date: the single-level file holds every crosswalked
parameter and every control at all 24 hours, the pressure-level file holds every
crosswalked parameter on all 13 levels at exactly the sample hours, and nothing
arrived on a grid other than the one requested.

Exits non-zero on any gap, so it can gate a resolution rather than decorate one.
"""

import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import era5_crosswalk as X          # noqa: E402
from era5_inventory import messages  # noqa: E402
from fetch_era5 import (OUT, PRESSURE_LEVELS, sample_timesteps,  # noqa: E402
                        target)


def main():
    steps = sample_timesteps()
    want_sl = set(X.SL_CROSSWALK) | {'i10fg', 'cape', 'cin', 'cp', 'csf',
                                     'lsp', 'lsf', 'asn', 'lai_lv', 'lai_hv',
                                     'smlt'}
    want_pl = set(X.PL_CROSSWALK)
    problems = []
    totals = collections.Counter()

    for date, hours in steps:
        for kind, want, levels, n_times in (
            ('sl', want_sl, {0, 7, 28, 100}, 24),
            ('pl', want_pl, set(PRESSURE_LEVELS), len(hours)),
        ):
            path = target(kind, date)
            if not path.exists():
                problems.append(f'{path.name}: missing')
                continue
            seen = collections.defaultdict(lambda: {'times': set(), 'levels': set()})
            grids = set()
            n = 0
            for m in messages(path):
                n += 1
                rec = seen[m['shortName']]
                rec['times'].add((m['validityDate'], m['validityTime']))
                rec['levels'].add(m['level'])
                grids.add((m['gridType'], m['Ni'], m['Nj']))
            totals[kind] += n
            totals[f'{kind}_bytes'] += path.stat().st_size

            missing = want - set(seen)
            if missing:
                problems.append(f'{path.name}: missing {sorted(missing)}')
            if grids != {('regular_ll', 252, 149)}:
                problems.append(f'{path.name}: unexpected grid {sorted(grids)}')
            for short in sorted(want & set(seen)):
                rec = seen[short]
                if len(rec['times']) != n_times:
                    problems.append(f'{path.name}: {short} has {len(rec["times"])} '
                                    f'times, expected {n_times}')
                if kind == 'pl' and rec['levels'] != levels:
                    problems.append(f'{path.name}: {short} has levels '
                                    f'{sorted(rec["levels"])}')
            if kind == 'pl':
                expected_hours = {int(h) * 100 for h in hours}
                got = {t for rec in seen.values() for _, t in rec['times']}
                if got != expected_hours:
                    problems.append(f'{path.name}: hours {sorted(got)}, '
                                    f'expected {sorted(expected_hours)}')
            print(f'  {path.name}: {n} messages, {len(seen)} parameters', flush=True)

    print()
    print(f'single level:   {totals["sl"]} messages, '
          f'{totals["sl_bytes"] / 2**30:.1f} GiB')
    print(f'pressure level: {totals["pl"]} messages, '
          f'{totals["pl_bytes"] / 2**30:.1f} GiB')
    print(f'total:          {totals["sl"] + totals["pl"]} messages, '
          f'{(totals["sl_bytes"] + totals["pl_bytes"]) / 2**30:.1f} GiB in '
          f'{2 * len(steps)} files')
    if problems:
        print(f'\n{len(problems)} problem(s):')
        for line in problems:
            print('  ' + line)
        return 1
    print('\ncomplete: every sample date, every parameter, every hour.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
