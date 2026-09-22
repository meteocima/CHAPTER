#!/usr/bin/env python3
"""Relative humidity exactly as the IFS defines it, for `r` and `2r`.

EVERY CONSTANT HERE IS QUOTED, NOT RECALLED. The source is

    IFS Documentation - Cy41r2, Part IV: Physical Processes,
    Chapter 7 "Clouds and large-scale precipitation"
    https://www.ecmwf.int/sites/default/files/elibrary/2016/16648-part-iv-physical-processes.pdf

and Cy41r2 is the cycle ERA5 was produced with, so it is the cycle whose
definition our paramId 157 has to match -- not the current one.

Page 112, above Eq. (7.89), states the definition in words:

    "currently defined as relative humidity with respect to water for
     temperatures warmer than 0 C, with respect to ice for temperatures
     colder than -23 C, and a mix of the two in the 0 C to -23 C
     temperature range."

Eq. (7.89), the humidity itself:

    e / esat(T) = p q (1/eps) / ( esat(T) (1 + q (1/eps - 1)) )

    with eps = Rdry/Rvap = 0.621981  ("the ratio of the molar masses of water
    and dry air (= Rdry/Rvap = 0.621981 in the IFS)")

Eq. (7.90), the saturation it is divided by:

    esat(T) = alpha esat_w(T) + (1 - alpha) esat_i(T)

Eq. (7.5), page 95, Tetens, with T0 = 273.16 K:

    esat(T) = a1 exp( a3 (T - T0) / (T - a4) )

    over water, Buck (1981):                a1 = 611.21 Pa, a3 = 17.502, a4 =  32.19 K
    over ice, Alduchov and Eskridge (1996): a1 = 611.21 Pa, a3 = 22.587, a4 =  -0.7 K

Eq. (7.6), page 95, the mixed-phase function -- the fraction of LIQUID, and it
is QUADRATIC, not linear:

    alpha = 0                               T <= Tice
    alpha = ((T - Tice)/(T0 - Tice))**2     Tice < T < T0
    alpha = 1                               T >= T0

    with Tice = 250.16 K and T0 = 273.16 K.

NOTHING IN THE DEFINITION CLIPS THE RESULT. Supersaturation with respect to the
mixed phase is a state the atmosphere and the model are both allowed to be in,
and ERA5 publishes it: 127.7 per cent at 400 hPa on our own sample dates.

What this replaces. `wrf.getvar('rh')` and `getvar('rh2')` call
`fortran/wrf_user.f90:722`, which saturates over LIQUID WATER at every
temperature (Magnus, 6.112 / 17.67 / 29.65) and then applies
`MAX(MIN(qv/qvs, 1), 0)`. Over ice that is a different quantity by up to a
factor 1.8, and the MIN destroys supersaturation irreversibly.
"""

import numpy as np

# --- Eq. (7.5), page 95 ------------------------------------------------------
T0 = 273.16                    # K
A1 = 611.21                    # Pa, both phases
A3_WATER, A4_WATER = 17.502, 32.19        # Buck (1981)
A3_ICE, A4_ICE = 22.587, -0.7             # Alduchov and Eskridge (1996), AERKi

# --- Eq. (7.6), page 95 ------------------------------------------------------
T_ICE = 250.16                 # K

# --- Eq. (7.89), page 112 ----------------------------------------------------
EPSILON = 0.621981             # Rdry/Rvap, the IFS value

# The kernel this replaces, for the comparison in the audit only.
MAGNUS_EZERO, MAGNUS_A, MAGNUS_B = 6.112, 17.67, 29.65      # hPa, wrf_user.f90


def esat_water(t):
    """Saturation vapour pressure over liquid water, Pa. Eq. (7.5), Buck."""
    return A1 * np.exp(A3_WATER * (t - T0) / (t - A4_WATER))


def esat_ice(t):
    """Saturation vapour pressure over ice, Pa. Eq. (7.5), AERKi."""
    return A1 * np.exp(A3_ICE * (t - T0) / (t - A4_ICE))


def alpha_liquid(t):
    """The mixed-phase function: the fraction of LIQUID. Eq. (7.6). Quadratic."""
    a = (np.asarray(t, dtype=float) - T_ICE) / (T0 - T_ICE)
    return np.clip(a, 0.0, 1.0) ** 2


def esat_mixed(t):
    """Saturation over the mixed phase, Pa. Eq. (7.90)."""
    a = alpha_liquid(t)
    return a * esat_water(t) + (1.0 - a) * esat_ice(t)


def vapour_pressure(q, p):
    """Vapour pressure from SPECIFIC humidity and pressure, Pa. Eq. (7.89).

    q is per kg of moist air, p in Pa. This is the ECMWF form, with the IFS
    epsilon; it is not the mixing-ratio shortcut.
    """
    return p * q / (EPSILON * (1.0 + q * (1.0 / EPSILON - 1.0)))


def relative_humidity(q, p, t):
    """Relative humidity in per cent, the IFS definition. NOT CLIPPED."""
    return 100.0 * vapour_pressure(q, p) / esat_mixed(t)


def relative_humidity_over_water(q, p, t):
    """The same, but saturating over liquid water at every temperature.

    Not a quantity we publish -- it is here so the audit can separate the two
    changes, the saturation PHASE and the saturation FORMULA.
    """
    return 100.0 * vapour_pressure(q, p) / esat_water(t)


def esat_magnus_water(t):
    """What `fortran/wrf_user.f90:722` uses, Pa. For comparison only."""
    return 100.0 * MAGNUS_EZERO * np.exp(MAGNUS_A * (t - 273.15) / (t - MAGNUS_B))


def mixing_ratio_to_specific(mr):
    return mr / (1.0 + mr)


def self_check(verbose=True):
    """The identities the definition must satisfy, checked rather than assumed."""
    out = {}
    t_warm = np.array([273.16, 280.0, 300.0, 320.0])
    t_cold = np.array([150.0, 200.0, 240.0, 250.16])
    t_mid = np.linspace(250.16, 273.16, 2001)

    out['warm_equals_water'] = float(np.max(np.abs(
        esat_mixed(t_warm) - esat_water(t_warm))))
    out['cold_equals_ice'] = float(np.max(np.abs(
        esat_mixed(t_cold) - esat_ice(t_cold))))
    out['alpha_at_Tice'] = float(alpha_liquid(T_ICE))
    out['alpha_at_T0'] = float(alpha_liquid(T0))
    out['alpha_is_quadratic_at_midpoint'] = float(alpha_liquid(0.5 * (T_ICE + T0)))
    # continuity: the mixed curve must not jump at either threshold
    eps = 1e-6
    out['jump_at_Tice'] = float(abs(esat_mixed(T_ICE + eps) - esat_ice(T_ICE)))
    out['jump_at_T0'] = float(abs(esat_mixed(T0 - eps) - esat_water(T0)))
    # monotone in T, as a saturation curve must be
    out['mixed_is_monotone'] = bool(np.all(np.diff(esat_mixed(
        np.linspace(200.0, 320.0, 12001))) > 0))
    # the mixed curve lies between the two pure ones in the transition band
    em, ew, ei = esat_mixed(t_mid), esat_water(t_mid), esat_ice(t_mid)
    out['mixed_between_ice_and_water'] = bool(
        np.all(em >= ei - 1e-9) and np.all(em <= ew + 1e-9))
    # round trip: RH of saturated air must be 100 in every phase regime
    for name, t in (('warm', 290.0), ('band', 262.0), ('cold', 230.0)):
        p = 70000.0
        e = esat_mixed(t)
        q = EPSILON * e / (p - (1.0 - EPSILON) * e)
        out[f'saturated_air_reads_100_{name}'] = float(
            relative_humidity(q, p, t) - 100.0)
    # how far the IFS water curve is from the Magnus one the kernel uses
    t = np.linspace(230.0, 310.0, 801)
    out['ifs_water_vs_magnus_max_rel'] = float(np.max(np.abs(
        esat_water(t) / esat_magnus_water(t) - 1.0)))
    out['ifs_water_vs_magnus_rel_at_273'] = float(
        esat_water(273.15) / esat_magnus_water(273.15) - 1.0)
    # epsilon: 0.621981 against the 0.622 the kernel uses
    out['epsilon_relative_difference_vs_0_622'] = float(0.622 / EPSILON - 1.0)
    if verbose:
        for k, v in out.items():
            print(f'{k:42s} {v}')
    return out


if __name__ == '__main__':
    self_check()
