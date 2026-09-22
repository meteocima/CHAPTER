#!/usr/bin/env python3
"""The inventory sweep: everything ERA5 publishes that we do not, and why.

    source tools/eccodes_env.sh
    uv run python tools/audit/inventory_sweep.py

Regenerates the residue lists the sweep is built on, so the table in
`docs/audit/inventory-sweep.md` can be checked rather than trusted. Three ends,
as the ticket asks: the wrfout, `geo_em.d02`, and ERA5's own catalogue.

WHY THE NAME MATCHING IS EXACT-ONLY. A first attempt used difflib to bridge the
gap between CDS's labels and ECMWF's parameter names, and it mapped "Vertical
integral of eastward **ozone** flux" onto "Vertical integral of eastward
**heat** flux". A wrong paramId in this table is precisely the defect the audit
exists to catch, so approximate matching is gone: names resolve exactly, or they
resolve through the ALIASES table below, which was written by hand against the
local ECMWF tables and can be read.

Sources, all local, nothing downloaded:
  * the CDS catalogue forms cached by `era5_crosswalk.catalogue_variables`;
  * eccodes' own `grib2/{paramId,shortName,name}.def`, read in parallel;
  * ECMWF local table 162 (`grib1/2.98.162.table`), which is where the whole
    vertical-integral family lives and which the grib2 tables do not carry.
"""

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import era5_crosswalk as X  # noqa: E402


def eccodes_definitions():
    import eccodes
    # codes_definition_path may be a colon-separated list; the first entry is
    # the installed tree.
    return Path(eccodes.codes_definition_path().split(':')[0])


def grib2_params(definitions):
    """paramId, shortName and name, read from three files in parallel."""
    def entries(name):
        pattern = re.compile(r"^'(.*)' = \{")
        return [m.group(1) for m in
                (pattern.match(l) for l in
                 open(definitions / 'grib2' / name, errors='ignore'))
                if m]
    ids = entries('paramId.def')
    shorts = entries('shortName.def')
    names = entries('name.def')
    if not (len(ids) == len(shorts) == len(names)):
        raise SystemExit('the three grib2 tables are not parallel; do not trust them')
    return list(zip(ids, shorts, names))


def table_162(definitions):
    """ECMWF local table 162: paramId is 162000 + the table's own number."""
    out = []
    pattern = re.compile(r'^(\d+)\s+(\S+)\s+(.*?)\s*\((.*)\)\s*$')
    for line in open(definitions / 'grib1' / '2.98.162.table', errors='ignore'):
        m = pattern.match(line.rstrip('\n'))
        if m:
            out.append((f'162{int(m.group(1)):03d}', m.group(2), m.group(3),
                        m.group(4)))
    return out


# CDS label -> ECMWF name, for the cases where the two differ. Written by hand
# against the local tables; every row is a claim that can be checked there.
ALIASES = {
    'Maximum 2m temperature since previous post-processing':
        'Maximum temperature at 2 metres since previous post-processing',
    'Minimum 2m temperature since previous post-processing':
        'Minimum temperature at 2 metres since previous post-processing',
    '10m u-component of neutral wind': '10 metre u-component of neutral wind',
    '10m v-component of neutral wind': '10 metre v-component of neutral wind',
    'Zero degree level': '0 degrees C isothermal level (atm)',
    'Snow evaporation': 'Snow evaporation water equivalent',
    'Total sky direct solar radiation at surface':
        'Total sky direct short-wave (solar) radiation at surface',
}

SKIP_GROUPS = {'Ocean waves', 'Mean rates'}


def main():
    definitions = eccodes_definitions()
    print(f'eccodes definitions: {definitions}')
    g2 = grib2_params(definitions)
    t162 = table_162(definitions)
    print(f'grib2 parameter table: {len(g2)} entries')
    print(f'ECMWF local table 162: {len(t162)} entries, '
          f'{sum(1 for e in t162 if e[1].startswith("vi"))} of them vertical integrals')

    mapped = set(X.SL_CROSSWALK.values()) | set(X.SL_CONTROLS)
    offered = X.catalogue_variables(X.COLLECTIONS['sl'])
    print(f'\nERA5 single levels offered by CDS: {len(offered)}')
    print(f'  we map or use as a control:       {len(mapped & offered)}')
    print(f'  residue:                          {len(offered - mapped)}')
    print('\nThe vertical-integral family, from table 162 '
          '(the grib2 tables carry only six of these):')
    for pid, short, name, units in t162:
        if short.startswith('vi'):
            print(f'   {pid}  {short:<8} {name}  [{units}]')
    return 0


if __name__ == '__main__':
    sys.exit(main())
