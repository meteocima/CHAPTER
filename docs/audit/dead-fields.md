# The dead-field census

Every one of the 200 variables in every one of the 34 wrfout of the audit
sample, tested for the thing `CONTEXT.md` actually defines:

> **Dead field**: a field that is identically zero on every sampled timestep. A
> dead field is not published, whatever the physical reason for its being zero.

Two words in that sentence shaped the measurement. *Identically* means exactly
zero, `max(abs(x)) == 0`, with no tolerance — a field of 1e-30 is alive and badly
scaled, which is a different finding. *Every sampled timestep* means the census
cannot be run on a summer afternoon and generalised, which is how the list in
`CLAUDE.md` was built.

Tool: `tools/audit/dead_fields.py`, submitted by `tools/audit/submit_census.sh`.
Raw per-timestep JSON in `$WORK/CHAPTER/audit_census/`.

## The verdict

**34 of 34 timesteps. 146 alive, 37 dead, 16 seasonally zero.**

**Every one of the sixteen fields `CLAUDE.md` calls dead is confirmed dead** on
the full seasonal sample. Not one of them turned out to be seasonally zero, and
not one turned out to be alive. The list was right.

That includes **`ACSNOW`**, which was the named risk: a snow accumulator is
exactly the field a summer-only sample cannot judge, and with January, February,
November and December in the sample it is still exactly zero everywhere.

## What the seasonal axis was for

Sixteen fields are zero at some timesteps and not others. Kept strictly apart
from the dead, because on a narrower sample most of them would have joined it.

| field | zero at | what it is |
|---|---|---|
| `SWDNB` `SWDNBC` `SWDNT` `SWDNTC` `SWDOWN` `SWDOWNC` `SWUPB` `SWUPBC` `SWUPT` `SWUPTC` | 15 of 34 | shortwave, dark at 00Z |
| `SEAICE` `XICEM` | 20 of 34 | no ice May to November |
| `HAIL_MAXK1` | 8 of 34 | |
| `GRAUPELNC` | 6 of 34 | zero through all of 2024-07-15 and 2024-08-15 |
| `SNOW` `SNOWH` | **1** of 34 | snow-free only at 2024-08-15T00 |

**A census run on a July midday would have called ten radiation fields alive and
learned nothing; one run at 00Z would have called them dead.** The sample has
both, which is why the answer is neither.

The shortwave set earns a closer look, because it is the census proving it is
sensitive rather than merely arithmetical. Those ten fields are zero at **15 of
the 17** 00Z timesteps. The exception is **2024-06-15T00** — six days before the
solstice, when the domain's north-eastern corner near 60 N, 42 E is already in
daylight at 00 UTC. A month later, at 2024-07-15T00, it is dark again and the
fields are zero. Nothing in the tool knows about solstices; it found the
terminator by arithmetic.

`SNOW` and `SNOWH` are the mirror image: alive at 33 of 34 timesteps and zero at
exactly one, the 00Z of 15 August. A field can be **almost** seasonally zero, and
a sample of one August timestep would have put them in the wrong column.

## The twenty-one dead fields not on the list

The census was told to look at everything, so it found more than the sixteen. All
twenty-one are WRF scaffolding, and **none is a physical field anyone would
publish**:

- idealised-run forcing, never used by a real case: `HFX_FORCE`, `LH_FORCE`,
  `TSK_FORCE`, and their `_TEND` partners, `THIS_IS_AN_IDEAL_RUN`;
- stochastic-perturbation seeds, all schemes off: `ISEEDARR_RAND_PERTURB`,
  `ISEEDARR_SKEBS`, `ISEEDARR_SPPT`, `ISEEDARRAY_SPP_CONV`,
  `ISEEDARRAY_SPP_LSM`, `ISEEDARRAY_SPP_PBL`;
- nesting and setup bookkeeping: `NEST_POS`, `SAVE_TOPO_FROM_REAL`;
- stratospheric-profile constants unused in this configuration: `P_STRAT` and
  `ZETATOP` (while `TLP_STRAT`, from the same block, is alive);
- `PC`, `PCB`, `RESM`;
- **`SINALPHA`**, which is zero *by construction*: on a Mercator grid the map
  rotation angle is zero everywhere, and `COSALPHA` is correspondingly alive at
  1. A field being dead for a geometric reason is still dead, and this is the
  cleanest illustration of why `CONTEXT.md` refuses to make the reason part of
  the definition.

**So the census adds nothing publishable to the dead list. It confirms it.**
No family ticket's variable set changes, and no ticket of the map is invalidated.

## Crossed with the configuration

The ticket asks that a dead field be checked against whether its scheme was even
running. Against `docs/audit/run-configuration.md`:

| field | why it is zero | settled? |
|---|---|---|
| `RAINC` `RAINSH` `PREC_ACC_C` | `cu_physics = 6, 0, 0` — d02 has **no** cumulus scheme | settled |
| `SST_INPUT` | `SST_UPDATE = 0` | settled |
| `SSTSK` | `SST_SKIN = 0` | settled |
| `SWNORM` | `SLOPE_RAD = 0`, `TOPO_SHADING = 0` | settled |
| `NOAHRES` | `sf_surface_physics = 3` is RUC; this is a Noah diagnostic | settled |
| `HAILNC` | `mp_physics = 6` is WSM6, which has graupel but **no hail category** — and `GRAUPELNC` is indeed alive | settled |
| `LWDNT` `LWDNTC` `ACLWDNT` `ACLWDNTC` | downward longwave at the top of the atmosphere has no source | settled by physics; the converter already relies on it, writing `ttr` as minus `ACLWUPT` |
| `ACHFX` `ACLHF` `ACGRDFLX` | accumulators of `HFX`, `LH`, `GRDFLX`, which the modified Registry never wrote (issue #31) | settled, by a different ticket |
| **`ACSNOW`** | the surface scheme is **running**, so this is the one that is not settled by a switch. The likely reason is the same as `NOAHRES`: `ACSNOW` is filled by the Noah driver and we run RUC, which leaves it at zero while the microphysics `SNOWNC` is alive. **Inferred from the pairing, not measured** | **open, low stakes** |

Only `ACSNOW` is dead with its scheme enabled. It changes nothing — it was
already excluded, and `SNOWNC` carries the snowfall — but it is the one line of
this census that rests on an inference rather than a switch.

## What was not needed

The GRIB1 archive was available as a control for 2024-10..12 and 2025-01..06. It
was not consulted: the seasonal sample answered the question on its own, and a
different encoder with known defects is corroboration at best. Nothing here rests
on it.
