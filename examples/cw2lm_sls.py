#!/usr/bin/env python3
"""Codeword-to-layer mapping end to end in the system simulator.

Runs the full-buffer SU-MIMO system with Alt 1 (NR: one codeword up to rank
4), Alt 2 (up to two codewords) and Alt 3 (one codeword per layer).  With
more than one codeword every codeword has its own CQI, MCS, OLLA loop and
HARQ process, and the rank is chosen knowing the codeword split
(``FullBufferConfig.cw_mapping``).  This is the end-to-end counterpart of
the CSI-stage probe ``examples/cw2lm_sls_probe.py``, on the same scenario
(Dense Urban-eMBB A) and the same two CSI cases:

  etype2_20ms  Apple-like: eType-II, CSI every 20 ms, 4 ms delay
  svd_2ms      Nokia-like: unquantised wideband SVD, every 2 ms, no delay

and for both retransmission policies (``harq_adaptive``): 'fixed' keeps the
first transmission's precoder and refills decoded codewords on their
first-transmission CQI; 'adaptive' re-precodes the retransmission slot with
the UT's current report.

    python examples/cw2lm_sls.py [--drops 2] [--slots 160] [--jobs 4]

Writes results/cw2lm_sls.json.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nrsls.config.scenario import get_preset                        # noqa: E402
from nrsls.engine.fullbuffer import (FullBufferConfig, aggregate_drops,  # noqa: E402
                                     run_full_buffer_drop)

OUT = os.path.join(os.path.dirname(__file__), "..", "results")
MAPPINGS = ("alt1", "alt2", "alt3")
HARQ = {"fixed": False, "adaptive": True}
KEYS = ("cell_se", "ue_se_p5", "ue_se_p50", "bler_first", "bler_first_cw", "mean_rank",
        "rank_hist", "mean_codewords", "mean_mcs", "retx_rbg_fraction")


def cases(slots: int, warmup: int) -> dict:
    """The probe's two CSI cases (15 kHz: 1 ms slots)."""
    common = dict(n_slots=slots, warmup_slots=warmup, max_rank=4, rbg_size=4,
                  channel_update_slots=2, pdcch_symbols=2, overhead_re_per_prb=9)
    return {"etype2_20ms": dict(codebook="etype2", csi_period_slots=20, csi_delay_slots=4,
                                **common),
            "svd_2ms": dict(codebook="svd", csi_period_slots=2, csi_delay_slots=0, **common)}


def _worker(args):
    key, cfg, fb, seed, i = args
    t0 = time.time()
    # the same drops (rng [seed, i]) for every configuration
    return key, i, run_full_buffer_drop(cfg, fb, np.random.default_rng([seed, i])), \
        time.time() - t0


def summarize(res: dict) -> None:
    for case, by_harq in res["cases"].items():
        for harq, by_map in by_harq.items():
            base = by_map["alt1"]
            print(f"\n== {case}, HARQ {harq}")
            print("        cell SE   gain   UT p5   gain  UT p50   gain  BLER  "
                  "BLER per CW              rank  CWs   retx")
            for m, r in by_map.items():
                g = {k: 100 * (r[k] / base[k] - 1) if base[k] > 0 else float("nan")
                     for k in ("cell_se", "ue_se_p5", "ue_se_p50")}
                print(f"  {m}  {r['cell_se']:7.3f} {g['cell_se']:+6.1f}% {r['ue_se_p5']:6.3f} "
                      f"{g['ue_se_p5']:+6.1f}% {r['ue_se_p50']:6.3f} {g['ue_se_p50']:+6.1f}% "
                      f"{r['bler_first']:.3f}  {str(np.round(r['bler_first_cw'], 3).tolist()):24s} "
                      f"{r['mean_rank']:.2f}  {r['mean_codewords']:.2f}  "
                      f"{r['retx_rbg_fraction']:.3f}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--drops", type=int, default=2)
    ap.add_argument("--slots", type=int, default=160)
    ap.add_argument("--warmup", type=int, default=40)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--ues", type=int, default=None, help="UTs per cell (default: preset)")
    ap.add_argument("--cases", default="etype2_20ms,svd_2ms")
    ap.add_argument("--harq", default="fixed,adaptive")
    ap.add_argument("--olla-per-rank", action="store_true")
    ap.add_argument("--out", default=os.path.join(OUT, "cw2lm_sls.json"))
    args = ap.parse_args()

    cfg = get_preset("du-a") if args.ues is None else get_preset("du-a", ue_per_cell=args.ues)
    all_cases = cases(args.slots, args.warmup)
    tasks = []
    for case in args.cases.split(","):
        for harq in args.harq.split(","):
            for m in MAPPINGS:
                fb = FullBufferConfig(**all_cases[case], cw_mapping=m,
                                      olla_per_rank=args.olla_per_rank,
                                      harq_adaptive=HARQ[harq])
                tasks += [((case, harq, m), cfg, fb, args.seed, i) for i in range(args.drops)]
    t0 = time.time()
    drops = {}
    with ProcessPoolExecutor(max_workers=args.jobs) as ex:
        for fut in as_completed([ex.submit(_worker, t) for t in tasks]):
            key, i, r, dt = fut.result()
            drops.setdefault(key, {})[i] = r
            print(f"{'/'.join(key)} drop {i}: cell SE {r.cell_se:.3f} ({dt:.0f} s)", flush=True)

    res = {"scenario": cfg.name, "n_drops": args.drops, "n_slots": args.slots,
           "warmup": args.warmup, "olla_per_rank": args.olla_per_rank,
           "cases": {}, "runtime_s": round(time.time() - t0, 1)}
    for (case, harq, m), by_drop in sorted(drops.items(), key=lambda kv: (
            kv[0][0], kv[0][1], MAPPINGS.index(kv[0][2]))):
        agg = aggregate_drops([by_drop[i] for i in sorted(by_drop)])
        out = {k: agg[k] for k in KEYS}
        out["ue_se"] = [round(float(x), 5) for x in agg["ue_se"]]
        res["cases"].setdefault(case, {}).setdefault(harq, {})[m] = out
    summarize(res)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(res, fh, indent=1)
    print("wrote", os.path.normpath(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
