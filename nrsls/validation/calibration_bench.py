"""Calibration benchmark: is nrsls aligned with the other companies?

The 3GPP IMT-2020 self-evaluation calibration (RP-180524, the source of
TR 37.910 Annex A) collected coupling-gain and DL-geometry CDFs from 12-20
companies per configuration.  This module treats nrsls as one more company
and asks whether it sits inside the industry spread.

Peer test
---------
For a configuration and metric, take every curve at the percentiles
``PCT`` (5, 10, ..., 95).  Each company's deviation is the mean absolute
gap between its curve and the mean of the *other* companies (leave one
out), in dB.  nrsls' deviation is the mean absolute gap between its curve
and the mean of all companies.  Both are distances from the consensus of
everybody else, so they are directly comparable, and the companies'
deviations set the tolerance: no fixed "within x dB" has to be chosen.

Verdict per (configuration, metric):

  PASS  nrsls' deviation <= the 80th percentile of the company deviations,
        and >= 80 % of the percentiles inside the company min-max envelope
  WARN  deviation <= the largest company deviation (as far from the
        consensus as the least typical company), or the envelope share is
        between 60 and 80 %
  FAIL  otherwise (further from the consensus than every company)

A configuration passes if both metrics pass.  Also reported: the gap to
the company mean at every percentile, nrsls' rank among the n + 1
participants by deviation (1 = closest to the consensus) and the largest
absolute gap.
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field

import numpy as np

REFS = os.path.join(os.path.dirname(__file__), "..", "..", "refs", "rp180524")
PCT = np.arange(5, 100, 5)
METRICS = ("coupling_gain", "geometry")
PEER_QUANTILE = 0.8          # PASS: deviation within the 80th pct of the companies
ENVELOPE_PASS, ENVELOPE_WARN = 0.8, 0.6


@dataclass
class Case:
    """One RP-180524 configuration: the nrsls preset (and overrides) that
    sets it up and the workbook sheet with the company curves."""

    name: str
    preset: str
    sheet: str
    overrides: dict = field(default_factory=dict)
    scored: bool = True        # False: a sensitivity run, reported only
    note: str = ""


CASES = [
    Case("rural-700m", "rp-rural-700m", "Rural_700M_ModelA"),
    Case("rural-4g", "rp-rural-4g", "Rural_4GHz_ModelA"),
    Case("rural-lmlc", "rp-rural-lmlc", "Rural_LMLC_ModelA"),
    Case("umammtc-500m", "rp-mmtc-500m", "UMa_mMTC_500m_ModelA"),
    Case("umammtc-1732m", "rp-mmtc-1732m", "UMa_mMTC_1732m_ModelA"),
    Case("umaurllc-4g", "rp-urllc-4g", "UMa_URLLC_4GHz_ModelA"),
    Case("umaurllc-700m", "rp-urllc-700m", "UMa_URLLC_700MHz_ModelA"),
    Case("inh-12trxp", "rp-inh-12trxp", "InH_4GHz_12TRxP_ModelA"),
    Case("inh-36trxp", "rp-inh-36trxp", "InH_4GHz_36TRxP_ModelA"),
    Case("du-4g", "rp-du-4g", "DenseUrban_4GHz_ModelA",
         note="analog-beam calibration (best of 12 DFT beams; random beams "
              "for interferers); legacy O2I for channel model A"),
    Case("du-4g-o2i-mixed", "rp-du-4g", "DenseUrban_4GHz_ModelA",
         overrides={"channel_model_a_o2i": "mixed"}, scored=False,
         note="sensitivity: the 20 % high / 80 % low-loss building mix that "
              "the du-a system preset uses"),
]


def load_companies(sheet: str, metric: str):
    """Company curves of an RP-180524 sheet: (pct, names, values) with
    values (n_companies, n_pct) in dB at the integer percentiles ``pct``."""
    path = os.path.join(REFS, f"{sheet}_{metric}.csv")
    with open(path) as fh:
        rows = [r for r in csv.reader(fh) if r and not r[0].startswith("#")]
    head, body = rows[0], rows[1:]
    skip = {"pct", "mean", "min", "max"}
    cols = [i for i, h in enumerate(head) if h.strip() not in skip]
    pct = np.array([float(r[0]) for r in body])
    vals = np.array([[float(r[i]) if i < len(r) and r[i].strip() not in ("", "nan")
                      else np.nan for r in body] for i in cols])
    return pct, [head[i].strip() for i in cols], vals


def _at(pct_grid, values, pct=PCT):
    idx = [int(np.argmin(np.abs(pct_grid - p))) for p in pct]
    return values[..., idx]


def peer_stats(sim_samples, pct_grid, companies, pct=PCT) -> dict:
    """Peer test of simulated samples against company curves (module doc)."""
    x = np.percentile(np.asarray(sim_samples, float), pct)
    c = _at(pct_grid, companies, pct)                     # (n, P)
    n = c.shape[0]
    mean = np.nanmean(c, axis=0)
    dev_sim = float(np.mean(np.abs(x - mean)))
    dev_c = []
    for i in range(n):
        others = np.nanmean(np.delete(c, i, axis=0), axis=0)
        ok = ~np.isnan(c[i])
        dev_c.append(float(np.mean(np.abs(c[i, ok] - others[ok]))))
    dev_c = np.array(dev_c)
    inside = (x >= np.nanmin(c, axis=0)) & (x <= np.nanmax(c, axis=0))
    gap = x - mean
    return {
        "n_companies": int(n),
        "deviation_db": round(dev_sim, 3),
        "company_deviation_db": {"median": round(float(np.median(dev_c)), 3),
                                 f"p{int(PEER_QUANTILE * 100)}":
                                     round(float(np.quantile(dev_c, PEER_QUANTILE)), 3),
                                 "max": round(float(dev_c.max()), 3)},
        "company_deviations_db": sorted(round(float(v), 3) for v in dev_c),
        "rank": int(np.sum(dev_c < dev_sim)) + 1,            # of n + 1
        "envelope_share": round(float(np.mean(inside)), 3),
        "max_abs_gap_db": round(float(np.max(np.abs(gap))), 2),
        "gap_db": {f"p{p}": round(float(g), 2) for p, g in zip(pct, gap)},
    }


def verdict(st: dict) -> str:
    q = st["company_deviation_db"][f"p{int(PEER_QUANTILE * 100)}"]
    if st["deviation_db"] <= q and st["envelope_share"] >= ENVELOPE_PASS:
        return "PASS"
    if (st["deviation_db"] <= st["company_deviation_db"]["max"]
            and st["envelope_share"] >= ENVELOPE_WARN):
        return "WARN"
    return "FAIL"


def combine(verdicts) -> str:
    v = list(verdicts)
    return "FAIL" if "FAIL" in v else "WARN" if "WARN" in v else "PASS"


def evaluate_case(case: Case, coupling_gain_db, geometry_db) -> dict:
    out = {"case": case.name, "preset": case.preset, "sheet": case.sheet,
           "overrides": case.overrides, "scored": case.scored, "note": case.note,
           "metrics": {}}
    for metric, samples in (("coupling_gain", coupling_gain_db), ("geometry", geometry_db)):
        pct_grid, _, comp = load_companies(case.sheet, metric)
        st = peer_stats(samples, pct_grid, comp)
        st["verdict"] = verdict(st)
        out["metrics"][metric] = st
    out["verdict"] = combine(m["verdict"] for m in out["metrics"].values())
    return out


def run_case(case: Case, n_drops: int = 20, seed: int = 1, n_jobs: int = 1) -> dict:
    from ..config.scenario import get_preset
    from ..engine.simulator import run_large_scale
    st = run_large_scale(get_preset(case.preset, **case.overrides), n_drops,
                         seed=seed, n_jobs=n_jobs)
    r = evaluate_case(case, st.coupling_gain_db, st.geometry_db)
    r["n_ues"] = int(st.coupling_gain_db.size)
    r["n_drops"] = n_drops
    return r
