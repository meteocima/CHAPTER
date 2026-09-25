# The audit harness, and what it can and cannot see

Every family ticket calls `tools/audit/harness.py`; none reimplements it. This
file is the method it implements and, more importantly, the list of things it
**cannot** detect — a harness whose limits live only in an issue comment will be
trusted past them.

```
source tools/eccodes_env.sh
uv run python tools/audit/harness.py compare --family 2 --timestep 2024-07-15T12 --out rows.jsonl
uv run python tools/audit/harness.py compare --variable 2t --all-timesteps --out rows.jsonl
uv run python tools/audit/harness.py report --rows rows.jsonl
```

## Three legs, and they are not equally strong

The ticket's title asks how 3 km is compared against 31 km, and the honest first
answer is that **most of the audit does not need to cross that gap at all**. The
eight family tickets each ask four things — value, unit, ERA5, mask — and only
the third has a resolution problem.

| leg | what it compares | grid gap | what it catches |
|---|---|---|---|
| **A** | the GRIB against itself and against the eccodes parameter definition | none | an impossible range, a wrong sign, a missing or unexpected bitmap |
| **B** | the GRIB against the wrfout it was made from | **none — same grid, same instant** | a factor, a sign, a unit conversion, a wrong source variable, **to machine precision** |
| **C** | the GRIB against ERA5 | 59 WRF cells per ERA5 cell | only whether it is the right *quantity* — a definition error |
| **D** | the GRIB against **other messages of the same file** | none | an identity inside the published archive: a factor, a sign, a swapped level |

Leg B is the strong one. The defect the GRIB1 archive actually carried — `2d`
written in degC under a paramId defined in K — is caught there exactly, not
statistically. Leg C exists for a different failure: publishing a mixing ratio
under a specific-content paramId, or a most-unstable parcel under a
surface-parcel name. **Leg C cannot see a 5 per cent bias and must never be
asked to.**

## Leg D: identities inside the published archive

Added for the ten variables ERA5 does not carry. For three of them it is the
**only exact evidence that can exist**: leg C is impossible by definition and leg
B is unavailable because the converter derives them itself.

Leg D recomputes a variable from other *published* messages of the same file — no
wrfout, no ERA5. Two consequences: it is repeatable on **every file of the
archive for ever**, not only on the sample, and it checks the internal
consistency of what a user actually reads, which neither B nor C can see.

Three strengths, and the report keeps them apart, because conflating them is how
a tolerance gets invented:

Measured over the **whole sample**, 34 timesteps:

| kind | variable | formula | measured |
|---|---|---|---|
| **exact** | `vwsh` | `sqrt((100u-10u)² + (100v-10v)²) / 90` — the converter's own formula, restated | **exact at all 34**, worst relative 5.39e-07. A disagreement would be asserted as a defect |
| **approximate** | `wz` | `w_z = -ω / (ρg)`, `ρ = p / (R_d T)`, against the published `w` and `t` | 442 rows (34 × 13 levels), typical median **8.9e-05 m/s** |
| **approximate** | `2r` | the reconstruction from the published `2t` and `2d`, both over liquid water: `esat_water(2d)/esat_water(2t)` | median **0.39 %RH**, max **2.48** — see below |
| **bracket** | `200u` `200v` | speed should not fall from 100 m to 200 m; the two vectors should be near-parallel | 81.8 per cent non-falling; **87.5 to 99.0 per cent within 20°** depending on the timestep |

### What leg D can and cannot see, from the `2r` episode

This row now reconstructs `2r` from the published `2t` and `2d`, **both over
liquid water** — `ifs_humidity.py`, Buck constants from IFS Cy41r2
Part IV Eq. 7.5. It reports **median 0.39 %RH, maximum 2.48** over the sample,
and the residual is essentially the clip of
[#40](https://github.com/meteocima/CHAPTER/issues/40) plus the dewpoint round
trip. After #40 it should fall to the round trip alone, `2d` against `Q2` at
3.6e-4 to 1.1e-2 relative in vapour pressure.

It is worth recording what this check could and could not do, because both halves
generalise.

**It could not see the clip**, and reported a comfortable 0.40 %RH median while
the field was truncated. At 2 m the clip removes at most about 2 %RH, which is
inside the scatter a physical approximation legitimately has. *An `approximate`
leg D cannot detect a defect smaller than its own tolerance* — that is what
`approximate` means, and it is why the row is reported rather than asserted.

**A check written against the same definition as the field cannot fail at all.**
That is the stronger failure, and it is what happened to `r` on pressure levels:
leg D would have compared a humidity over liquid water against a Magnus ratio
over liquid water and agreed, while the parameter is defined over the mixed phase
and the field was wrong by a factor of up to 1.8. Leg D is only as independent as
the definition it is written against, and that definition has to come from the
authority, not from the library that produced the field.

Related, and it cost this repo a wrong resolution in
[#33](https://github.com/meteocima/CHAPTER/issues/33): **a clip cannot be seen in
the packed maxima.** A value pinned at exactly 100 comes back from 24-bit CCSDS
packing scattered by a few 1e-6, indistinguishable from float noise on a ratio
reaching 1. Only recomputing from the source field tells them apart.

`wz`'s *worst* relative difference reaches 0.41, and that is not a finding: the
relative error blows up wherever `w` passes through zero, which on a
convection-permitting field it does constantly. The median absolute difference —
**9e-05 m/s against a field reaching 28 m/s** — is the number that means
something, which is why the row carries both.

Only `exact` is asserted. An `approximate` leg D is a physical relation that holds
to a tolerance — a thermodynamic approximation, a different saturation formula —
so the scatter **is** the physics and is reported, never failed. The `bracket` is
weaker still and says so in the row: it catches a swapped level or a flipped
sign, and cannot catch an error in the interpolation height.

**Sibling levels come from the registry, never written by hand.** The first
version hard-coded level 0 and every lookup but `wz`'s missed, because `2t` sits
on `heightAboveGround` level 2 and `10u` on level 10. Same class of mistake as
assuming a shortName is an identity — and the harness said "sibling absent"
rather than comparing against nothing, which is why it was caught.

## Leg B does not import the converter's tables

The defect leg B exists to catch is a wrong unit factor, and
`convert_to_pressure_levels.UNIT_SCALE` is precisely where such a factor would
live. A harness that read that table would apply the same wrong number to the
source field and report perfect agreement.

So the expected conversion is derived here, independently, from **metadata on
both sides**: the wrfout variable's own `units` attribute, and the unit eccodes
says the paramId is defined in. Neither was written by us. The converter's table
is then read only to be *disagreed with*: where its factor differs from the one
the metadata implies, the row says so.

An unknown unit pair is **reported, never guessed at as 1.0**. A silent 1.0 is
the degC-under-K defect reappearing in the instrument meant to find it.

Three kinds of leg B, and the classification is itself a deliverable:

- **direct** — the registry key *is* a wrfout variable, or one of the seven
  static sidecar fields. Read it, convert it, compare point for point.
  Accumulated variables are read at this hour **and at 00Z and subtracted here**,
  independently of the accumulation sidecar, which is therefore also under test.
- **identity** — the quantity is a short combination whose definition is not a
  choice of ours. Net radiation is downward minus upward whoever writes it, and
  total runoff is surface plus sub-surface, so restating them here is a second
  opinion rather than a copy. Ten variables: the eight net-radiation fields,
  `ro` and `tirf`.
- **none** — the derivation **is** the converter's own algorithm: vertical
  interpolation to pressure levels, the `skt` inversion, CAPE. Recomputing those
  independently means writing a second converter. Leg B is unavailable and the
  verdict rests on legs A and C plus reading the code. This is a limit of the
  harness, stated rather than hidden.

**The column integrals were in that last list and did not belong there.**
[Audit family 3](https://github.com/meteocima/CHAPTER/issues/21) found leg B for
all six of `tcw`, `tcwv`, `tclw`, `tciw`, `tcrw`, `tcsw`. WRF integrates on a
**dry-mass** vertical coordinate, so the column water of a species is not an
integral to be approximated but the weighted sum
`sum_k X_k (MU+MUB) |DNW_k| / g`, whose weights the model itself wrote out —
three wrfout fields (`MU`, `MUB`, `DNW`) the converter never opens. A second
opinion, not a copy, and an exact one: it showed the converter's pressure
quadrature to be 3 to 8 per cent off
([#46](https://github.com/meteocima/CHAPTER/issues/46)), which legs A and C
could not have called a defect. The lesson generalises — **a field that is a
vertical sum has a leg B whatever the harness says** — and the rows still read
`none` only because the measurement lives in `tools/audit/f3_columns.py`,
deliberately outside a harness that is under the audit it serves.

## Upscaling: WRF to ERA5, never the other way

Averaging discards information WRF has, and what survives is what ERA5 should
hold. Interpolating ERA5 up to 3 km invents structure and then compares it
against the real thing.

The upscale is **exact index bucketing, not interpolation**. The WRF grid is
Mercator, so longitude spacing is constant (0.037944 degrees, measured) and rows
sit at fixed latitudes; ERA5's is regular lat/lon. The mapping is therefore
separable — every WRF row falls in one ERA5 latitude band and every column in
one longitude band — and each WRF cell lies wholly inside one ERA5 cell. No
weights are computed and nothing is interpolated.

Cells are weighted by **cos²(latitude)**: with `dlon` constant, a Mercator
cell's physical area goes as cos², and that was checked rather than assumed —
the ratio of row spacings between the south and north edges of this grid is
1.8338 against cos(23.4719°)/cos(60.0006°) = 1.8345, agreeing to 0.04 per cent.

Between 43 WRF cells per ERA5 cell at 60 N and 78 at 25 N, 59 on average.

**Categorical fields are not averaged.** Halfway between evergreen broadleaf and
short grass is not a vegetation type, so `tvl`, `tvh` and `slt` are upscaled by
**majority** and leg C reports the fraction of ERA5 cells whose dominant class
agrees, plus each side's class histogram.

**Masked fields average only their valid points**, or the coastline manufactures
a bias out of nothing.

## What is asserted and what is only reported

The harness fails a variable **only on what cannot be a resolution difference**:

1. a value outside the physically possible range for the declared unit;
2. a sign the quantity cannot have (`ttr` positive, `tp` negative);
3. a mask that disagrees with the land-sea mask, including a field defined over
   water that carries no bitmap;
4. a bitmap where none belongs.

Everything else — a 5 per cent bias, a smoother field, a lower maximum, a
correlation of 0.8 — is a number printed for a person to read.

**A masked field is not a failed field.** Every row carries `notes` beside
`failures`, and a field that is entirely missing where its masking is legitimate
is a note: `fal` at 00Z, when there is no downward shortwave and an albedo does
not exist; `tsn` where there is no snow anywhere in the domain. A family ticket
needs to see those — `tsn` is entirely missing at 7 of the 34 timesteps, which is
information about snow cover — but reporting them as defects buries the real one.
The first full-sample run raised 329 failures on eleven variables and **328 of
them were the harness's own**, from soil fields bitmapped over water and an
albedo missing at night. One was real.

**There is deliberately no per-variable tolerance table.** Those numbers would be
invented here, and an invented tolerance converts "I do not know" into "pass",
which is the failure this whole audit exists to undo.

## What it cannot detect

Stated plainly, because a family ticket that does not know this will over-read a
clean row:

- **A bias smaller than the resolution difference.** Leg C's spread between a
  3 km field and its 31 km average is of the order of a few per cent for smooth
  fields and far more for anything convective. A genuine 5 per cent error in a
  precipitation field is invisible.
- **Anything at all, on leg C, for the ten variables ERA5 does not carry.** Leg D
  covers five of them and leg B another three; `mucape` and `mucin` have none of
  the four and are **unverifiable** in the sense `CONTEXT.md` defines.
- **A systematic error shared by the wrfout and the GRIB.** Leg B compares the
  encoding, not the model. If WRF itself writes a wrong field, leg B says
  "exact".
- **An error inside the converter's own algorithms**, for the same reason leg B
  `none` exists: vertical interpolation, `skt` and CAPE have no independent
  source to be read back from. (Column integrals were listed here too and turned
  out to have one — see above.)
- **A time-of-day or seasonal defect from one timestep.** The harness measures
  what it is given; the sample's three axes exist so a family ticket asks for
  all 34.

## Below ground and the model lid

Below-ground pressure levels — 1000 hPa over the Alps, 925 over any high
terrain — are **kept and flagged, never silently dropped**. Whatever the
vertical interpolation does there is a value a user will read, so it is under
audit rather than an inconvenience to the statistics: every pressure-level row
carries an `above_ground` region alongside `all`, `land` and `sea`, and the two
can be read against each other.

50 hPa is the model lid with no damping (settled by the configuration ticket),
so disagreement there is expected and is not by itself a finding.

## The whole sample is already measured

`$WORK/CHAPTER/audit_rows/rows_<timestep>.jsonl`, one file per timestep,
**34 files and 8364 rows, all 246 messages at all 34 timesteps**, produced in a
single array so that every family reads numbers from the same pass. A family
ticket does not need to run the harness before reading: point `report` at the
rows.

Across the whole sample there are **34 leg A failures and they are all the same
one** — `ci` carrying no bitmap, at every timestep, which is
[issue #34](https://github.com/meteocima/CHAPTER/issues/34).

## Regions

Every row carries statistics over **all**, **land** and **sea** separately. A
land-only defect disappears in a domain mean when two thirds of the box is sea,
and the split is itself the cheapest mask test there is. Land and sea are taken
from each side's own mask: ours from the `lsm` message of the same file, ERA5's
from its own `lsm`, both at 0.5.

## Output

One JSONL row per (variable, level, timestep), each holding the three legs and
the per-region statistics; `report` turns a set of rows into the Markdown table
the family docs need. Rows rather than prose, so that eight family tickets do
not write eight table generators and the numbers stay comparable across
families, and so a later ticket can re-read a measurement without recomputing it.

`z` is addressed as **`z_sfc`** or **`z_pl`**, never as `z`: two registry rows
share that shortName — surface orography and pressure-level geopotential — and
a shortName is therefore not an identity.

## Completeness, and why `compare` says how many rows it expected

`compare` ends by printing `N of M expected rows` and **exits non-zero if the two
differ**. That is not decoration. This repo has now been bitten three times by a
run that stopped early and looked finished:

- the staging fetch declared `fetch phase done` after 3 of 21 files;
- the ERA5 retrieval had to be checked against the tree rather than against its
  own "all requests satisfied";
- and this command's first pressure-level run was cut off at **154 of 169 rows**
  by a shell `timeout`, after which the `report` chained behind it read the
  truncated file and exited 0 — so the whole thing looked successful and the two
  missing variables were only found by counting.

A measuring instrument that can stop early without saying so is worse than no
instrument, because its silence is indistinguishable from a clean result. Never
chain `compare` and `report` with `;` and read only the last exit code.

## Cost, and the two things that made it affordable

The GRIB is read in **one streaming pass** per timestep, each message released as
soon as its row is written. The first version collected every wanted message
first, which for a pressure-level family is 169 fields of 2.2 million points —
3 GB held for no reason.

The ERA5 file is read **once per timestep and cached**, not re-walked per row. A
pressure-level family otherwise asks 169 separate times for messages that all
live in the same 21 MB file, and the re-walking cost more than the comparison
did.
