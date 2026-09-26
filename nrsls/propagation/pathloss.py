"""Basic pathloss and shadow-fading statistics, TR 38.901 Table 7.4.1-1.

Distances in metres, carrier frequency ``fc_hz`` in Hz (the formulas use GHz,
the breakpoint distances Hz).  Every NLOS formula is max(PL_LOS, PL'_NLOS).
For O2I UTs the basic pathloss uses the full 3-D distance and the LOS state
of the outdoor part of the link (clause 7.4.3); the building penetration
loss is added separately (:mod:`nrsls.propagation.o2i`).

Shadow fading (Table 7.4.1-1 for LOS/NLOS, Table 7.5-6 for O2I):

    ======  ========================  ======  =====
    family  LOS                        NLOS    O2I
    ======  ========================  ======  =====
    UMa     4                          6       7
    UMi     4                          7.82    7
    RMa     4 (d2D <= d_BP) / 6        8       8
    InH     3                          8.03    --
    ======  ========================  ======  =====
"""

from __future__ import annotations

import numpy as np

from ..config.scenario import SPEED_OF_LIGHT

LOS, NLOS, O2I = 0, 1, 2      # link condition codes used across the package

_SF_STD_DB = {
    "uma": (4.0, 6.0, 7.0),
    "umi": (4.0, 7.82, 7.0),
    "rma": (None, 8.0, 8.0),   # LOS: 4 / 6 dB below / above the breakpoint
    "inh": (3.0, 8.03, None),
}


def _log10(x):
    return np.log10(np.maximum(x, 1e-12))


# --- UMa ---------------------------------------------------------------------

def sample_uma_h_e(d2d, h_ut, rng):
    """Effective environment height h_E for the UMa breakpoint (note 1).

    h_E = 1 m with probability 1 / (1 + C(d2D, h_UT)), otherwise drawn from
    the discrete uniform set {12, 15, ..., h_UT - 1.5} m.
    """
    d2d, h_ut = np.broadcast_arrays(np.asarray(d2d, float),
                                    np.asarray(h_ut, float))
    g = np.where(d2d <= 18.0, 0.0,
                 1.25 * (d2d / 100.0) ** 3 * np.exp(-d2d / 150.0))
    c = np.where(h_ut < 13.0, 0.0,
                 ((np.maximum(h_ut, 13.0) - 13.0) / 10.0) ** 1.5 * g)
    one = rng.random(d2d.shape) < 1.0 / (1.0 + c)
    n_vals = np.maximum(np.floor((h_ut - 1.5 - 12.0) / 3.0) + 1.0, 1.0)
    pick = 12.0 + 3.0 * np.floor(rng.random(d2d.shape) * n_vals)
    return np.where(one, 1.0, pick)


def uma_los(d2d, d3d, h_bs, h_ut, fc_hz, h_e=1.0):
    fc = fc_hz / 1e9
    d_bp = 4.0 * (h_bs - h_e) * (h_ut - h_e) * fc_hz / SPEED_OF_LIGHT
    pl1 = 28.0 + 22.0 * _log10(d3d) + 20.0 * np.log10(fc)
    pl2 = (28.0 + 40.0 * _log10(d3d) + 20.0 * np.log10(fc)
           - 9.0 * _log10(d_bp ** 2 + (h_bs - h_ut) ** 2))
    return np.where(d2d <= d_bp, pl1, pl2)


def uma_nlos(d2d, d3d, h_bs, h_ut, fc_hz, h_e=1.0):
    fc = fc_hz / 1e9
    pl_n = (13.54 + 39.08 * _log10(d3d) + 20.0 * np.log10(fc)
            - 0.6 * (h_ut - 1.5))
    return np.maximum(uma_los(d2d, d3d, h_bs, h_ut, fc_hz, h_e), pl_n)


# --- UMi-Street Canyon -------------------------------------------------------

def umi_los(d2d, d3d, h_bs, h_ut, fc_hz):
    fc = fc_hz / 1e9
    d_bp = 4.0 * (h_bs - 1.0) * (h_ut - 1.0) * fc_hz / SPEED_OF_LIGHT
    pl1 = 32.4 + 21.0 * _log10(d3d) + 20.0 * np.log10(fc)
    pl2 = (32.4 + 40.0 * _log10(d3d) + 20.0 * np.log10(fc)
           - 9.5 * _log10(d_bp ** 2 + (h_bs - h_ut) ** 2))
    return np.where(d2d <= d_bp, pl1, pl2)


def umi_nlos(d2d, d3d, h_bs, h_ut, fc_hz):
    fc = fc_hz / 1e9
    pl_n = (35.3 * _log10(d3d) + 22.4 + 21.3 * np.log10(fc)
            - 0.3 * (h_ut - 1.5))
    return np.maximum(umi_los(d2d, d3d, h_bs, h_ut, fc_hz), pl_n)


# --- RMa ---------------------------------------------------------------------

def rma_breakpoint(h_bs, h_ut, fc_hz):
    return 2.0 * np.pi * h_bs * h_ut * fc_hz / SPEED_OF_LIGHT


def _rma_pl1(d3d, fc, h):
    return (20.0 * _log10(40.0 * np.pi * d3d * fc / 3.0)
            + min(0.03 * h ** 1.72, 10.0) * _log10(d3d)
            - min(0.044 * h ** 1.72, 14.77)
            + 0.002 * np.log10(h) * d3d)


def rma_los(d2d, d3d, h_bs, h_ut, fc_hz, h=5.0):
    fc = fc_hz / 1e9
    d_bp = rma_breakpoint(h_bs, h_ut, fc_hz)
    pl2 = _rma_pl1(d_bp, fc, h) + 40.0 * _log10(d3d / d_bp)
    return np.where(d2d <= d_bp, _rma_pl1(d3d, fc, h), pl2)


def rma_nlos(d2d, d3d, h_bs, h_ut, fc_hz, h=5.0, w=20.0):
    fc = fc_hz / 1e9
    pl_n = (161.04 - 7.1 * np.log10(w) + 7.5 * np.log10(h)
            - (24.37 - 3.7 * (h / h_bs) ** 2) * np.log10(h_bs)
            + (43.42 - 3.1 * np.log10(h_bs)) * (_log10(d3d) - 3.0)
            + 20.0 * np.log10(fc)
            - (3.2 * np.log10(11.75 * h_ut) ** 2 - 4.97))
    return np.maximum(rma_los(d2d, d3d, h_bs, h_ut, fc_hz, h), pl_n)


# --- InH-Office --------------------------------------------------------------

def inh_los(d3d, fc_hz):
    return 32.4 + 17.3 * _log10(d3d) + 20.0 * np.log10(fc_hz / 1e9)


def inh_nlos(d3d, fc_hz):
    pl_n = 38.3 * _log10(d3d) + 17.30 + 24.9 * np.log10(fc_hz / 1e9)
    return np.maximum(inh_los(d3d, fc_hz), pl_n)


# --- dispatch ----------------------------------------------------------------

def basic_pathloss_db(family: str, los, d2d, d3d, h_bs, h_ut, fc_hz, *,
                      h_e=1.0, building_height=5.0, street_width=20.0):
    """PL_b [dB] for each link given its (outdoor) LOS state."""
    los = np.asarray(los, bool)
    if family == "uma":
        pl_l = uma_los(d2d, d3d, h_bs, h_ut, fc_hz, h_e)
        pl_n = uma_nlos(d2d, d3d, h_bs, h_ut, fc_hz, h_e)
    elif family == "umi":
        pl_l = umi_los(d2d, d3d, h_bs, h_ut, fc_hz)
        pl_n = umi_nlos(d2d, d3d, h_bs, h_ut, fc_hz)
    elif family == "rma":
        pl_l = rma_los(d2d, d3d, h_bs, h_ut, fc_hz, building_height)
        pl_n = rma_nlos(d2d, d3d, h_bs, h_ut, fc_hz, building_height,
                        street_width)
    elif family == "inh":
        pl_l = inh_los(d3d, fc_hz)
        pl_n = inh_nlos(d3d, fc_hz)
    else:
        raise ValueError(f"unknown scenario family {family!r}")
    return np.where(los, pl_l, pl_n)


def link_condition(los, o2i):
    """LOS / NLOS / O2I code per link (O2I wins for indoor UTs)."""
    los, o2i = np.broadcast_arrays(np.asarray(los, bool), np.asarray(o2i, bool))
    return np.where(o2i, O2I, np.where(los, LOS, NLOS))


def shadow_fading_std_db(family: str, condition, d2d=None, h_bs=None,
                         h_ut=None, fc_hz=None):
    """Shadow-fading standard deviation [dB] per link condition."""
    s_los, s_nlos, s_o2i = _SF_STD_DB[family]
    cond = np.asarray(condition)
    if family == "rma":
        d_bp = rma_breakpoint(h_bs, h_ut, fc_hz)
        s_los = np.where(np.asarray(d2d) <= d_bp, 4.0, 6.0)
    if family == "inh" and np.any(cond == O2I):
        raise ValueError("InH has no O2I links")
    return np.select([cond == LOS, cond == NLOS],
                     [s_los, s_nlos], default=np.nan if s_o2i is None else s_o2i)
