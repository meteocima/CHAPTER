#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Static land fields for the CHAPTER GRIB archive, derived from geo_em.d02.

The hourly wrfout carry only the DOMINANT land-use and soil category (IVGTYP,
ISLTYP). The fractional cover they were reduced from lives in the WPS static
file geo_em_d02, which was believed lost and was recovered from LRZ in
September 2026. That file is what makes cvl/cvh/tvl/tvh/slt/cl/dl possible:
over this domain the dominant category carries only 90.1% of a land cell on
average, and 17.9% of land cells hold both high and low vegetation above 5%, a
state the dominant category cannot express at all.

geo_em is time-invariant, so it is read ONCE into a small sidecar
(chapter_static_d02.npz) and the convert jobs read that instead of opening a
2.4 GB NetCDF per timestep. EVERY mapping decision is taken here, at extract
time, so the whole crosswalk sits in one auditable place and the sidecar meta
records the table that produced the numbers.

Verified before any of this was written (2026-09-18), against wrfout of 2019
and 2024:
  * XLAT_M/XLONG_M match the wrfout grid to 0.0 -- same domain, not a cousin;
  * LU_INDEX == IVGTYP on 97.1% of points and the ONLY difference is category
    21 (lake) -> 17 (water), i.e. sf_lake_physics=0. So geo_em's land use IS
    the run's land use, plus the lake information WRF discarded at runtime;
  * SCT_DOM == ISLTYP on 98.5% (the difference is water/ice);
  * HGT_M == HGT up to real.exe's terrain adjustment (rms 8.2 m, 98.6% of
    points within 1 m);
  * VAR_SSO is identical to the wrfout's (already used for sdor).

The geo_em is dated 2022-12-31 18Z while the archive spans 2019-2025, hence
--check-wrfout: the assumption is tested against a real wrfout and the result
is recorded in the meta. Re-run the check on the first 2025 wrfout available
before trusting these statics for 2025.

CLI:
    python static_ref.py extract <geo_em.d02.nc> <static_dir> \
        [--check-wrfout <wrfout> ...]
"""

import os
import sys
import tempfile

import numpy as np

STATIC_SCHEMA_VERSION = 2

STATIC_FILENAME = 'chapter_static_d02.npz'

# Fields the sidecar carries, in registry order. NaN means "missing" and the
# converter turns it into a GRIB bitmap.
STATIC_VARS = ['cvl', 'cvh', 'tvl', 'tvh', 'slt', 'cl', 'dl']

# Masks the sidecar carries but does NOT publish. They are here, and not in the
# converter, because they cannot be rebuilt from an hourly wrfout: WRF recodes
# the lake class to water at runtime (sf_lake_physics=0), and it flips LANDMASK
# from 0 to 1 wherever sea ice forms. Only geo_em still knows which water is
# inland and which land is permanent.
#
#   ocean_mask  1 on the sea, 0 on land AND on inland water
#   land_mask   1 on permanent land, 0 on all water -- unaffected by sea ice
#
# Both are 0/1 float32, read back with `> 0.5`.
STATIC_MASKS = ['ocean_mask', 'land_mask']

# A water cell belongs to the ocean if its connected component of water has at
# least this many cells. Not a tuned parameter: MEASURED on this geo_em, the
# water components are
#
#     844431  Atlantic + Mediterranean + Baltic + North Sea   (touches the edge)
#      49841  Black Sea + Sea of Azov                         (does NOT)
#       8583  Red Sea                                         (touches the edge)
#       1225  Vanern, the largest inland lake in the domain
#        856, 760, 402, 318, ...  the other lakes
#
# so ANY threshold between 1226 and 8583 selects exactly those three components
# and nothing else -- checked at 1226, 2000, 4000 and 8583, all giving 902855
# ocean cells. A factor of seven of slack.
#
# Why a component rule at all, rather than "water minus the cells geo_em calls
# lake", which is what issue #36 proposed: geo_em CALLS the Black Sea a lake.
# WPS's MODIS class 21 covers it, the Sea of Azov and part of the Baltic --
# together 89 per cent of the cells this domain marks as fully lake -- so using
# the lake class as the discriminator would mask `sst` off the Black Sea. The
# defect and the proposed cure share a cause.
#
# Why not "the component that touches the domain edge": the Bosporus is about
# 700 m wide and this grid is 3 km, so the Black Sea is NOT connected to the
# Mediterranean here (measured). It would be classified inland -- again exactly
# the cells the defect is about. Lake Ladoga, meanwhile, IS clipped by the
# northern boundary and would be classified ocean.
OCEAN_MIN_CELLS = 2000

# ---------------------------------------------------------------------------
# Land-use crosswalk: MODIS-IGBP 21 (MMINLU=MODIFIED_IGBP_MODIS_NOAH) -> ECMWF
# ---------------------------------------------------------------------------
# The split into high and low vegetation follows the IGBP class DEFINITIONS
# (tree cover), NOT VEGPARM.TBL's ZTOPV column: the table's row for class 8
# (Woody Savannas) is a carbon copy of the row for class 6 (Closed Shrublands),
# ZTOPV included, so ZTOPV cannot arbitrate a class it never described.
VEG_HIGH = (1, 2, 3, 4, 5, 8)          # forests (>60% tree) + woody savanna (30-60%)
VEG_LOW = (6, 7, 9, 10, 11, 12, 14, 18, 19, 20)
# 13 urban, 15 snow/ice, 16 barren, 17 water, 21 lake are neither, exactly as in
# ERA5: cvl + cvh is then < 1 and the remainder is bare/urban/water.
VEG_NEITHER = (13, 15, 16, 17, 21)

LAKE_CLASS = 21

# ECMWF code table 4.234, the one tvl/tvh are read against. Every entry below is
# a semantic identity: the ECMWF type names the same vegetation as the MODIS
# class. The two shrubland classes are deliberately absent -- see VEG_TVL_MASKED.
VEG_TYPE_4234 = {
    1: 3,    # Evergreen Needleleaf Forest -> Evergreen needleleaf trees
    2: 6,    # Evergreen Broadleaf Forest  -> Evergreen broadleaf trees
    3: 4,    # Deciduous Needleleaf Forest -> Deciduous needleleaf trees
    4: 5,    # Deciduous Broadleaf Forest  -> Deciduous broadleaf trees
    5: 18,   # Mixed Forests               -> Mixed forest/woodland
    8: 19,   # Woody Savannas              -> Interrupted forest (both 30-60% tree)
    9: 7,    # Savannas                    -> Tall grass
    10: 2,   # Grasslands                  -> Short grass
    11: 13,  # Permanent Wetlands          -> Bogs and marshes   (absent in domain)
    12: 1,   # Croplands                   -> Crops, mixed farming
    14: 1,   # Cropland/Natural Mosaic     -> Crops, mixed farming (absent in domain)
    18: 9,   # Wooded Tundra               -> Tundra
    19: 9,   # Mixed Tundra                -> Tundra
    20: 9,   # Barren Tundra               -> Tundra
}

# MODIS does not carry shrub phenology while 4.234 splits evergreen (16) from
# deciduous (17) shrubs. There is no way to choose that is not an invention, so
# tvl is written as MISSING where one of these dominates the low cover: 121653
# cells, 15.8% of the cells with cvl > 0, essentially Iberia and the North
# African margin. cvl still carries the cover there. (Decision 2026-09-18.)
VEG_TVL_MASKED = (6, 7)

# ---------------------------------------------------------------------------
# Soil type: ECMWF's own definition, not a STATSGO crosswalk
# ---------------------------------------------------------------------------
# ECMWF's 7 soil types are defined by clay/sand percentage thresholds (FAO, as
# used by HTESSEL -- Balsamo et al. 2009). geo_em carries CLAYFRAC and SANDFRAC,
# so the thresholds can be applied directly and the WRF quantity IS the ERA5
# one. Translating STATSGO category numbers instead would have been our
# invention, which is why slt was dropped on 2026-09-17.
SLT_RULE = ("ECMWF/FAO texture thresholds on geo_em CLAYFRAC/SANDFRAC (percent): "
            "clay>=60 -> 5 very fine; 35<=clay<60 -> 4 fine; clay<35 and sand<=15 "
            "-> 3 medium fine; (18<=clay<35 and sand>15) or (clay<18 and 15<sand<=65) "
            "-> 2 medium; clay<18 and sand>65 -> 1 coarse. "
            "Then SCT_DOM==13 (organic material) -> 6 organic. "
            "Masked where geo_em LANDMASK==0. Type 7 (tropical organic) never occurs.")

SOILCAT_ORGANIC = 13     # STATSGO 'ORGANIC MATERIAL' in SOILPARM.TBL section STAS

# Tolerance on the grid fingerprint, in degrees. The two files carry the same
# float32 coordinates, so the difference is 0; 1e-5 deg is ~1 m, far below the
# 3 km spacing and far above any float round-trip.
GRID_TOL_DEG = 1e-5


def _ocean_mask(lu_index, land):
    """1 on the sea, 0 on land and on inland water. See OCEAN_MIN_CELLS.

    Connected components of the water cells; a component is ocean if it is at
    least OCEAN_MIN_CELLS across. scipy is imported here and not at module
    scope so that the converter, which only ever READS the sidecar, does not
    take a dependency on it.
    """
    from scipy import ndimage

    water = ~land
    if not np.array_equal(water, np.isin(lu_index, (17, LAKE_CLASS))):
        raise ValueError(
            "geo_em's LANDMASK and LU_INDEX disagree about which cells are "
            "water; the ocean mask assumes they are the same set")
    labels, n = ndimage.label(water)
    if n == 0:
        raise ValueError("geo_em has no water at all, which cannot be this domain")
    sizes = ndimage.sum_labels(np.ones_like(labels), labels,
                               index=np.arange(1, n + 1)).astype(np.int64)
    keep = np.flatnonzero(sizes >= OCEAN_MIN_CELLS) + 1
    if keep.size == 0:
        raise ValueError(
            f"no water component reaches {OCEAN_MIN_CELLS} cells "
            f"(largest is {sizes.max()}), so this is not the CHAPTER domain")
    ocean = np.isin(labels, keep)
    # The threshold must not sit near a component boundary, or a different
    # geo_em would silently reclassify a sea. Report the margin it actually had.
    below = sizes[sizes < OCEAN_MIN_CELLS]
    print(f"  ocean mask: {keep.size} water components of "
          f"{sizes[keep - 1].min()} cells or more kept ({int(ocean.sum())} cells); "
          f"largest component left inland is {int(below.max()) if below.size else 0}")
    return ocean


def static_path(static_dir):
    """Path of the sidecar inside static_dir."""
    return os.path.join(static_dir, STATIC_FILENAME)


def write_static(path, fields, meta):
    """Atomically write the sidecar (unique tmp in the same dir + os.replace),
    so concurrent writers and readers never see a partial file."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    arrays = {f"var_{k}": np.asarray(v, dtype=np.float32) for k, v in fields.items()}
    arrays.update({f"meta_{k}": np.array(str(v)) for k, v in meta.items()})
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + '.', suffix='.tmp',
                               dir=os.path.dirname(os.path.abspath(path)))
    try:
        os.chmod(tmp, 0o644)  # mkstemp creates 0600
        with os.fdopen(fd, 'wb') as fh:
            np.savez_compressed(fh, **arrays)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def load_static(static_dir):
    """Return (fields, meta) from the sidecar in static_dir.

    Raises rather than returning a default: a convert that silently dropped the
    static block would produce a file short of the expected message inventory,
    which is exactly what the sanity check exists to catch -- but only after the
    fact, and only if someone runs it.
    """
    path = static_path(static_dir)
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"static sidecar not found: {path}\n"
            f"  The static land fields ({', '.join(STATIC_VARS)}) come from geo_em.d02.\n"
            f"  Create it with: python static_ref.py extract <geo_em.d02.nc> {static_dir}")
    with np.load(path) as z:
        fields = {k[4:]: z[k] for k in z.files if k.startswith('var_')}
        meta = {k[5:]: str(z[k]) for k in z.files if k.startswith('meta_')}
    missing = [v for v in STATIC_VARS + STATIC_MASKS if v not in fields]
    if missing:
        raise KeyError(f"static sidecar {path} lacks {missing} "
                       f"(schema version {meta.get('static_schema_version')}); re-extract it")
    return fields, meta


def assert_grid(meta, grid, source=''):
    """Fail loudly if the sidecar was built on a different grid than this wrfout.

    The single guard that stops a geo_em from another domain (or another
    resolution) silently poisoning twenty thousand files: every static field
    would still encode, on the right number of points, with the wrong geography.
    """
    checks = [('ni', int(meta['ni']), int(grid['ni']), 0),
              ('nj', int(meta['nj']), int(grid['nj']), 0),
              ('dx', float(meta['dx']), float(grid['dx']), 1e-6),
              ('dy', float(meta['dy']), float(grid['dy']), 1e-6),
              ('truelat1', float(meta['truelat1']), float(grid['truelat1']), 1e-6)]
    for key in ('lat0', 'lon0', 'lat1', 'lon1'):
        checks.append((key, float(meta[key]), float(grid[key]), GRID_TOL_DEG))
    bad = [f"{k}: sidecar {a!r} vs wrfout {b!r}" for k, a, b, tol in checks
           if abs(a - b) > tol]
    if bad:
        raise ValueError(
            "static sidecar was built on a different grid than this wrfout"
            + (f" ({source})" if source else "") + ":\n  " + "\n  ".join(bad))


# ---------------------------------------------------------------------------
# derivation
# ---------------------------------------------------------------------------

def _dominant(landusef, classes):
    """(cover, dominant class number) over a subset of the 21 MODIS classes."""
    idx = [c - 1 for c in classes]
    sub = landusef[idx]
    cover = sub.sum(axis=0)
    dom = np.asarray(classes)[sub.argmax(axis=0)]
    return cover, dom


def _soil_type(clay_pct, sand_pct, sct_dom, land):
    """ECMWF's 7-class soil type from clay/sand percentages (see SLT_RULE)."""
    slt = np.select(
        [clay_pct >= 60,
         (clay_pct >= 35) & (clay_pct < 60),
         (clay_pct < 35) & (sand_pct <= 15),
         ((clay_pct >= 18) & (clay_pct < 35) & (sand_pct > 15))
         | ((clay_pct < 18) & (sand_pct > 15) & (sand_pct <= 65)),
         (clay_pct < 18) & (sand_pct > 65)],
        [5, 4, 3, 2, 1],
        default=0).astype(np.float32)
    slt[sct_dom == SOILCAT_ORGANIC] = 6
    slt[~land] = np.nan
    unclassified = int(((slt == 0) & land).sum())
    if unclassified:
        raise ValueError(f"{unclassified} land points fall outside the FAO texture "
                         f"thresholds; the rule is meant to be exhaustive")
    return slt


def derive_from_geo_em(path):
    """Read geo_em.d02 and return (fields, meta): every mapping decision is here."""
    from netCDF4 import Dataset
    with Dataset(path) as ds:
        if getattr(ds, 'MMINLU', None) != 'MODIFIED_IGBP_MODIS_NOAH':
            raise ValueError(f"{path}: MMINLU is {getattr(ds, 'MMINLU', None)!r}, the "
                             f"crosswalk in this module is for MODIFIED_IGBP_MODIS_NOAH")
        if int(ds.NUM_LAND_CAT) != 21:
            raise ValueError(f"{path}: NUM_LAND_CAT is {ds.NUM_LAND_CAT}, expected 21")

        def get(name):
            return np.ma.filled(ds.variables[name][0], np.nan).astype(np.float64)

        landusef = get('LANDUSEF')
        land = get('LANDMASK') > 0.5
        lat, lon = get('XLAT_M'), get('XLONG_M')

        total = landusef.sum(axis=0)
        if not np.allclose(total, 1.0, atol=1e-5):
            raise ValueError(f"LANDUSEF does not sum to 1 (range {total.min()}..{total.max()})")

        cvl, dom_low = _dominant(landusef, VEG_LOW)
        cvh, dom_high = _dominant(landusef, VEG_HIGH)

        # tvl/tvh: the 4.234 code of the dominant low/high class, 0 where that
        # cover is absent (ERA5's own convention over water and bare ground).
        lut = np.full(22, np.nan)
        for modis, ecmwf in VEG_TYPE_4234.items():
            lut[modis] = ecmwf
        tvl, tvh = lut[dom_low], lut[dom_high]
        tvl[cvl <= 0] = 0.0
        tvh[cvh <= 0] = 0.0
        shrub = np.isin(dom_low, VEG_TVL_MASKED) & (cvl > 0)
        tvl[shrub] = np.nan
        if np.isnan(tvh).any():
            raise ValueError("tvh has no mapping for some dominant high class: "
                             "every class in VEG_HIGH must be in VEG_TYPE_4234")
        if not np.array_equal(np.isnan(tvl), shrub):
            raise ValueError("tvl is missing somewhere other than the shrubland cells: "
                             "every class in VEG_LOW except VEG_TVL_MASKED must be in "
                             "VEG_TYPE_4234")

        # Rounded to 1e-4 percentage points before the thresholds are applied.
        # geo_em stores the fractions as float32, and the value meant to be
        # exactly 0.35 reads back as 34.999999403953552 percent, which would
        # drop 3922 cells from 'fine' to 'medium' on a representation artefact
        # alone. The data's own spacing is ~4e-4 percentage points (239078
        # distinct clay values), so the rounding is finer than any real signal.
        slt = _soil_type(np.round(get('CLAYFRAC') * 100.0, 4),
                         np.round(get('SANDFRAC') * 100.0, 4),
                         np.asarray(get('SCT_DOM'), dtype=int), land)

        # The two masks the hourly output can no longer express. See
        # STATIC_MASKS and OCEAN_MIN_CELLS for why they have to live here.
        lu_index = np.asarray(get('LU_INDEX'), dtype=int)
        ocean = _ocean_mask(lu_index, land)

        # cl: the MODIS inland-water fraction. It is NOT redundant with lsm --
        # 19309 cells with LANDMASK==1 carry a sub-grid lake, and WRF itself
        # threw the class away at runtime (sf_lake_physics=0 recodes 21 -> 17).
        #
        # Zero on the ocean, which is where WPS's lake class is simply wrong:
        # it calls the Black Sea a lake at cl = 0.993 against ERA5's 0.0001.
        # ZERO and not missing, because ERA5's cl IS defined over the sea and
        # is ~0 there -- the rule is "masked where the ERA5 parameter is not
        # defined", and this one is (issue #36).
        cl = landusef[LAKE_CLASS - 1].copy()
        cl[ocean] = 0.0

        # dl: GLDB lake depth, masked off-lake -- and now off the sea with it,
        # since cl is zero there. The mask is not cosmetic: LAKE_DEPTH is
        # exactly 10.0 m (the WPS default fill) on 99.56% of the domain, and on
        # the Black Sea it read 10.0 m against a true 2209.8 m.
        dl = get('LAKE_DEPTH')
        dl[cl <= 0] = np.nan

        fields = {'cvl': cvl, 'cvh': cvh, 'tvl': tvl, 'tvh': tvh,
                  'slt': slt, 'cl': cl, 'dl': dl,
                  'ocean_mask': ocean.astype(np.float32),
                  'land_mask': land.astype(np.float32)}
        meta = {
            'static_schema_version': STATIC_SCHEMA_VERSION,
            'source_path': os.path.abspath(path),
            'source_mtime': os.path.getmtime(path),
            'TITLE': getattr(ds, 'TITLE', ''),
            'MMINLU': ds.MMINLU,
            'NUM_LAND_CAT': int(ds.NUM_LAND_CAT),
            'ni': lat.shape[1], 'nj': lat.shape[0],
            'dx': float(ds.DX), 'dy': float(ds.DY),
            'truelat1': float(ds.TRUELAT1), 'map_proj': int(ds.MAP_PROJ),
            'lat0': float(lat[0, 0]), 'lon0': float(lon[0, 0]),
            'lat1': float(lat[-1, -1]), 'lon1': float(lon[-1, -1]),
            'veg_high': VEG_HIGH, 'veg_low': VEG_LOW, 'veg_neither': VEG_NEITHER,
            'veg_type_4234': VEG_TYPE_4234, 'veg_tvl_masked': VEG_TVL_MASKED,
            'slt_rule': SLT_RULE,
            'land_points': int(land.sum()),
            'tvl_masked_points': int(shrub.sum()),
            'dl_present_points': int(np.isfinite(dl).sum()),
            'cl_land_points': int(((cl > 0) & land).sum()),
        }
    return fields, meta


def check_against_wrfout(geo_em_path, wrfout_path):
    """Test the assumption that this geo_em is the one the run used.

    Returns a dict of agreement statistics. Raises if the grids differ at all:
    a geo_em from another domain must never reach a sidecar.
    """
    from netCDF4 import Dataset
    with Dataset(geo_em_path) as g, Dataset(wrfout_path) as w:
        def gv(ds, n):
            return np.ma.filled(ds.variables[n][0], np.nan).astype(np.float64)

        dlat = np.abs(gv(g, 'XLAT_M') - gv(w, 'XLAT')).max()
        dlon = np.abs(gv(g, 'XLONG_M') - gv(w, 'XLONG')).max()
        if dlat > GRID_TOL_DEG or dlon > GRID_TOL_DEG:
            raise ValueError(f"{geo_em_path} is not the grid of {wrfout_path}: "
                             f"max|dlat|={dlat}, max|dlon|={dlon}")

        lu, ivg = gv(g, 'LU_INDEX'), gv(w, 'IVGTYP')
        # WRF recodes lake -> water at runtime (sf_lake_physics=0), so the lake
        # cells are the one difference we expect and allow.
        not_lake = lu != LAKE_CLASS
        lake_to_water = int(((lu == LAKE_CLASS) & (ivg == 17)).sum())
        lu_agree = float((lu[not_lake] == ivg[not_lake]).mean())

        sct, islt = gv(g, 'SCT_DOM'), gv(w, 'ISLTYP')
        hgt_rms = float(np.sqrt(((gv(g, 'HGT_M') - gv(w, 'HGT')) ** 2).mean()))
        return {
            'wrfout': os.path.basename(wrfout_path),
            'valid': w.variables['Times'][0].tobytes().decode(),
            'max_dlat': float(dlat), 'max_dlon': float(dlon),
            'lu_index_agreement_excl_lake': round(lu_agree, 6),
            'lake_cells_recoded_to_water': lake_to_water,
            'sct_dom_agreement': round(float((sct == islt).mean()), 6),
            'hgt_rms_m': round(hgt_rms, 3),
        }


def _cli(argv):
    if len(argv) < 3 or argv[0] != 'extract':
        print(__doc__)
        return 2
    geo_em, static_dir = argv[1], argv[2]
    rest = argv[3:]
    checks = []
    while rest:
        if rest[0] != '--check-wrfout' or len(rest) < 2:
            print(f"unexpected argument {rest[0]!r}", file=sys.stderr)
            return 2
        checks.append(rest[1])
        rest = rest[2:]

    fields, meta = derive_from_geo_em(geo_em)
    for i, wrfout in enumerate(checks):
        result = check_against_wrfout(geo_em, wrfout)
        meta[f'check_{i}'] = result
        print(f"check {result['valid']}: LU_INDEX agreement (excluding lake) "
              f"{result['lu_index_agreement_excl_lake']:.4f}, "
              f"{result['lake_cells_recoded_to_water']} lake cells recoded to water, "
              f"SCT_DOM {result['sct_dom_agreement']:.4f}, HGT rms {result['hgt_rms_m']} m")
    if not checks:
        print("WARNING: no --check-wrfout given; the assumption that this geo_em is "
              "the one the run used has not been tested", file=sys.stderr)

    path = static_path(static_dir)
    write_static(path, fields, meta)
    print(f"written: {path} ({os.path.getsize(path) / 1e6:.1f} MB)")
    for k in STATIC_VARS:
        a = np.asarray(fields[k], dtype=float)
        finite = a[np.isfinite(a)]
        print(f"  {k:4s} {finite.min():.4g}..{finite.max():.4g}  "
              f"present {finite.size} / {a.size}")
    for k in STATIC_MASKS:
        a = np.asarray(fields[k], dtype=float)
        print(f"  {k:11s} {int((a > 0.5).sum())} of {a.size} cells set")
    return 0


if __name__ == '__main__':
    sys.exit(_cli(sys.argv[1:]))
