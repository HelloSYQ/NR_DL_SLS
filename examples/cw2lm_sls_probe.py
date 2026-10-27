#!/usr/bin/env python3
"""System-level probe for codeword-to-layer mapping (Apple R1-2608231 vs
Nokia R1-2607066).

The system simulator transmits one codeword (NR, Alt 1).  This probe runs
it unchanged and measures, inside the running system, the two quantities
that decide whether more codewords (Alt 2: <= 2 CW, Alt 3: one CW per
layer) can gain:

1. CSI-stage potential (Apple's "aggregate expected TBS" check).  At every
   CSI report, for each mapping, the rank 1..4 that maximises
   sum_CW TBS (1 - BLER) at the per-codeword CQI MCS (CW-aware RI), and the
   resulting expected bits; also at fixed rank 4.
2. Per-layer SINR prediction error.  For each first transmission, the
   per-layer SINR it actually gets (MMSE-IRC, current channel and
   interference, report's precoder) minus the per-layer SINR the report
   predicted, split by layer (layer 1 = strongest).  A per-codeword MCS is
   chosen from the latter, so its error is the error each codeword's OLLA
   has to absorb.

    python examples/cw2lm_sls_probe.py [--drops 2] [--slots 160] [--jobs 4]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nrdlsim import mcs_tables, tbs as tbs_mod                     # noqa: E402
from nrdlsim.link_abstraction import _waterfall, effective_sinr_miesm  # noqa: E402

from nrsls.config.scenario import get_preset                        # noqa: E402
from nrsls.engine import fullbuffer as fbm                           # noqa: E402
from nrsls.engine import link as link_mod                            # noqa: E402
from nrsls.engine.fullbuffer import FullBufferConfig                 # noqa: E402
from nrsls.engine.link import tb_precoder                            # noqa: E402
from nrsls.phy import csi as csi_mod                                 # noqa: E402
from nrsls.phy.sinr import mmse_sinr                                 # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "results")
MAPPINGS = {"alt1": 1, "alt2": 2, "alt3": 4}


def layer_groups(r: int, max_cw: int):
    """NR-style split of r layers into min(r, max_cw) codewords, smaller first."""
    n = max(1, min(max_cw, r))
    sizes = [r // n + (1 if k >= n - r % n else 0) for k in range(n)]
    return [list(range(sum(sizes[:k]), sum(sizes[:k + 1]))) for k in range(n)]


_TAB = {}


def _table(n_layers, n_re, n_prb):
    key = (n_layers, n_re, n_prb)
    if key not in _TAB:
        rows = []
        for i in range(mcs_tables.num_mcs(2)):
            info = mcs_tables.get_mcs(i, 2)
            tb = tbs_mod.compute_tbs(n_re, n_prb, info.modulation_order,
                                     info.target_code_rate, n_layers)
            thr, sl = _waterfall(info.modulation_order, info.target_code_rate, tb)
            rows.append((info.modulation_order, tb, thr, sl))
        a = np.array(rows, float)
        _TAB[key] = (a[:, 0].astype(int), a[:, 1], a[:, 2], a[:, 3],
                     a[:, 2] + np.log(9.0) / a[:, 3])          # required at 10 %
    return _TAB[key]


def cqi_bits(sinr, n_layers, n_re, n_prb):
    """Expected bits TBS (1 - BLER) at the highest MCS with BLER <= 10 %."""
    qm, tbs, thr, sl, req = _table(n_layers, n_re, n_prb)
    eff = {q: effective_sinr_miesm(sinr, q) for q in (2, 4, 6, 8)}
    e = np.array([eff[q] for q in qm])
    ok = np.flatnonzero(e >= req)
    i = int(ok[-1]) if ok.size else 0
    return tbs[i] * (1 - 1 / (1 + np.exp(sl[i] * (e[i] - thr[i]))))


STATS = {}


def _install(n_re):
    orig_select = csi_mod.CSIProcessor.select
    orig_new_tb = link_mod.new_tb
    orig_decode = fbm.decode_tb
    st = {"bits": {m: 0.0 for m in MAPPINGS}, "bits_r4": {m: 0.0 for m in MAPPINGS},
          "rank": {m: np.zeros(5) for m in MAPPINGS}, "n_reports": 0,
          "err": {r: [[] for _ in range(r)] for r in (1, 2, 3, 4)},
          "rep_sinr": {r: [[] for _ in range(r)] for r in (1, 2, 3, 4)}}
    STATS.update(st)

    def select(self, hw, subband_of_f, rb_per_f, slot):
        rep = orig_select(self, hw, subband_of_f, rb_per_f, slot)
        n_prb = hw.shape[0] * rb_per_f
        per_rank = {}
        for q in range(1, min(self.max_rank, hw.shape[1]) + 1):
            if self.codebook == "etype2":
                if not self._et2.supports(q):
                    continue
                w, _ = self._et2.derive(hw, subband_of_f, q)
                s = mmse_sinr(hw @ w[subband_of_f])
            else:                                   # svd: wideband eigenvectors
                cov = np.einsum("fus,fut->st", np.conj(hw), hw)
                _, vec = np.linalg.eigh(cov)
                s = mmse_sinr(hw @ (vec[:, ::-1][:, :q] / np.sqrt(q)))
            per_rank[q] = s
            if q == rep.rank:
                rep._layer_sinr = s
        for m, max_cw in MAPPINGS.items():
            val = {q: sum(cqi_bits(s[:, g].ravel(), len(g), n_re, n_prb)
                          for g in layer_groups(q, max_cw)) for q, s in per_rank.items()}
            q_best = max(val, key=val.get)
            STATS["bits"][m] += val[q_best]
            STATS["rank"][m][q_best] += 1
            if 4 in val:
                STATS["bits_r4"][m] += val[4]
        STATS["n_reports"] += 1
        return rep

    def new_tb(la, u, cell, rep, sinr_sb, rbgs, rb_per_rbg, n_re_, mcs_table, slot):
        tb = orig_new_tb(la, u, cell, rep, sinr_sb, rbgs, rb_per_rbg, n_re_, mcs_table, slot)
        tb["rep_sinr"] = getattr(rep, "_layer_sinr", None)
        return tb

    def decode_tb(tb, hw_u, fm, rbg_f, nrb_f, rng, sinr=None):
        if tb["ntx"] == 0 and tb.get("rep_sinr") is not None and sinr is None:
            act = mmse_sinr(hw_u[fm] @ tb_precoder(tb, fm, rbg_f))
            rep = tb["rep_sinr"][fm]
            r = act.shape[1]
            for k in range(r):
                a_db = 10 * np.log10(np.mean(act[:, k]))
                p_db = 10 * np.log10(np.mean(rep[:, k]))
                STATS["err"][r][k].append(a_db - p_db)
                STATS["rep_sinr"][r][k].append(p_db)
        return orig_decode(tb, hw_u, fm, rbg_f, nrb_f, rng, sinr)

    csi_mod.CSIProcessor.select = select
    link_mod.new_tb = new_tb                   # called by link.new_txs
    fbm.decode_tb = decode_tb


def _worker(args):
    cfg, fb, seed, i, n_re = args
    _install(n_re)
    r = fbm.run_full_buffer_drop(cfg, fb, np.random.default_rng([seed, i]))
    st = {"bits": STATS["bits"], "bits_r4": STATS["bits_r4"],
          "rank": {m: v.tolist() for m, v in STATS["rank"].items()},
          "n_reports": STATS["n_reports"],
          "err": {r_: [list(map(float, x)) for x in v] for r_, v in STATS["err"].items()},
          "rep_sinr": {r_: [list(map(float, x)) for x in v]
                       for r_, v in STATS["rep_sinr"].items()}}
    return {"cell_se": r.cell_se, "bler_first": r.bler_first, "mean_rank": r.mean_rank}, st


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--drops", type=int, default=2)
    ap.add_argument("--slots", type=int, default=160)
    ap.add_argument("--warmup", type=int, default=40)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--ues", type=int, default=None, help="UTs per cell (default: preset)")
    args = ap.parse_args()

    cfg = get_preset("du-a") if args.ues is None else get_preset("du-a", ue_per_cell=args.ues)
    cases = {
        # Apple-like CSI: eType-II, 20 ms period, 4 ms delay (15 kHz: 1 ms slots)
        "etype2_20ms": FullBufferConfig(n_slots=args.slots, warmup_slots=args.warmup,
                                        codebook="etype2", max_rank=4, rbg_size=4,
                                        channel_update_slots=2, csi_period_slots=20,
                                        csi_delay_slots=4, pdcch_symbols=2,
                                        overhead_re_per_prb=9),
        # Nokia-like CSI: unquantised wideband SVD, every 2 ms, no delay
        "svd_2ms": FullBufferConfig(n_slots=args.slots, warmup_slots=args.warmup,
                                    codebook="svd", max_rank=4, rbg_size=4,
                                    channel_update_slots=2, csi_period_slots=2,
                                    csi_delay_slots=0, pdcch_symbols=2,
                                    overhead_re_per_prb=9),
    }
    out = {"scenario": cfg.name, "n_drops": args.drops, "n_slots": args.slots, "cases": {}}
    for name, fb in cases.items():
        n_re = tbs_mod.re_per_rb(14 - fb.pdcch_symbols, 24, fb.overhead_re_per_prb)
        t0 = time.time()
        with ProcessPoolExecutor(max_workers=args.jobs) as ex:
            res = list(ex.map(_worker, [(cfg, fb, args.seed, i, n_re)
                                        for i in range(args.drops)]))
        bits = {m: sum(r[1]["bits"][m] for r in res) for m in MAPPINGS}
        bits4 = {m: sum(r[1]["bits_r4"][m] for r in res) for m in MAPPINGS}
        rank = {m: np.sum([r[1]["rank"][m] for r in res], axis=0) for m in MAPPINGS}
        err = {rk: [sum((r[1]["err"][rk][k] for r in res), []) for k in range(rk)]
               for rk in (1, 2, 3, 4)}
        rsn = {rk: [sum((r[1]["rep_sinr"][rk][k] for r in res), []) for k in range(rk)]
               for rk in (1, 2, 3, 4)}
        c = {"cell_se": float(np.mean([r[0]["cell_se"] for r in res])),
             "bler_first": float(np.mean([r[0]["bler_first"] for r in res])),
             "mean_rank_alt1_system": float(np.mean([r[0]["mean_rank"] for r in res])),
             "csi_stage_gain_pct": {m: 100 * (bits[m] / bits["alt1"] - 1) for m in MAPPINGS},
             "csi_stage_gain_rank4_pct": {m: 100 * (bits4[m] / bits4["alt1"] - 1)
                                          for m in MAPPINGS},
             "ri_distribution": {m: (rank[m][1:] / rank[m].sum()).tolist() for m in MAPPINGS},
             "layer_sinr_error_db": {
                 str(rk): [{"mean": float(np.mean(e)), "std": float(np.std(e)),
                            "p10": float(np.percentile(e, 10)),
                            "p90": float(np.percentile(e, 90)), "n": len(e)}
                           for e in err[rk] if len(e)]
                 for rk in (1, 2, 3, 4)},
             "reported_layer_sinr_db_median": {
                 str(rk): [float(np.median(x)) for x in rsn[rk] if len(x)]
                 for rk in (1, 2, 3, 4)},
             "runtime_s": round(time.time() - t0, 1)}
        out["cases"][name] = c
        print(f"\n== {name} ({c['runtime_s']:.0f} s): cell SE {c['cell_se']:.2f}, "
              f"1st-tx BLER {c['bler_first']:.3f}, mean rank {c['mean_rank_alt1_system']:.2f}")
        print("  CSI-stage expected-bits gain vs Alt 1, CW-aware RI:",
              {m: round(v, 2) for m, v in c["csi_stage_gain_pct"].items()})
        print("  same at fixed rank 4:", {m: round(v, 2) for m, v in c["csi_stage_gain_rank4_pct"].items()})
        print("  RI distribution (ranks 1-4):",
              {m: np.round(v, 3).tolist() for m, v in c["ri_distribution"].items()})
        for rk in (2, 3, 4):
            s = c["layer_sinr_error_db"][str(rk)]
            if s:
                print(f"  rank {rk}: per-layer SINR error actual - reported (dB), mean/std/p10/p90:",
                      [f"{x['mean']:+.1f}/{x['std']:.1f}/{x['p10']:+.1f}/{x['p90']:+.1f}" for x in s],
                      " reported median SINR:", np.round(c["reported_layer_sinr_db_median"][str(rk)], 1).tolist())
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "cw2lm_sls_probe.json"), "w") as fh:
        json.dump(out, fh, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
