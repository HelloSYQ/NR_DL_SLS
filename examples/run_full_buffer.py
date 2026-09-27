#!/usr/bin/env python3
"""Phase 3: full-buffer SU-MIMO spectral efficiency.

Runs the default system (UMa 3.5 GHz, 100 MHz, 32T4R) with Type-I,
Rel-16 eType-II (parameter combination 6) and SVD (ideal-CSI reference)
precoding and writes

  results/p3_full_buffer.json   cell / 5th-percentile / median UT SE, BLER,
                                rank, MCS per configuration
  results/p3_ue_se_cdf.png      CDF of the UT spectral efficiency

    python examples/run_full_buffer.py [--drops 4] [--jobs 4] [--slots 200]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nrsls.config.scenario import get_preset  # noqa: E402
from nrsls.engine.fullbuffer import FullBufferConfig, run_full_buffer  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "results")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preset", default="system")
    ap.add_argument("--drops", type=int, default=4)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--slots", type=int, default=200)
    ap.add_argument("--warmup", type=int, default=40)
    ap.add_argument("--ue-per-cell", type=int, default=10)
    ap.add_argument("--codebooks", nargs="+", default=["type1", "etype2", "svd"])
    ap.add_argument("--tag", default="p3")
    args = ap.parse_args()

    cfg = get_preset(args.preset, ue_per_cell=args.ue_per_cell)
    summary, ue_se = {}, {}
    for cb in args.codebooks:
        fb = FullBufferConfig(n_slots=args.slots, warmup_slots=args.warmup,
                              codebook=cb)
        t0 = time.time()
        r = run_full_buffer(cfg, fb, args.drops, seed=1, n_jobs=args.jobs)
        ue_se[cb] = r["ue_se"]
        summary[cb] = {k: v for k, v in r.items() if k not in ("drops", "ue_se")}
        summary[cb]["runtime_s"] = round(time.time() - t0, 1)
        summary[cb]["n_ut"] = int(len(r["ue_se"]))
        print(f"{cb:6s} cell SE {r['cell_se']:.2f}  UT SE p5 {r['ue_se_p5']:.3f} "
              f"p50 {r['ue_se_p50']:.3f}  BLER1 {r['bler_first']:.3f}  "
              f"rank {r['mean_rank']:.2f}  MCS {r['mean_mcs']:.1f}  "
              f"PMI bits {r['mean_pmi_bits']:.0f}  "
              f"({summary[cb]['runtime_s']} s)", flush=True)

    os.makedirs(OUT, exist_ok=True)
    meta = {"preset": cfg.name, "drops": args.drops, "slots": args.slots,
            "warmup": args.warmup, "ue_per_cell": args.ue_per_cell}
    with open(os.path.join(OUT, f"{args.tag}_full_buffer.json"), "w") as f:
        json.dump({"config": meta, "results": summary}, f, indent=1)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from nrsls.plots import cdf
    fig, ax = plt.subplots(figsize=(6.5, 4.2), facecolor=cdf.SURFACE)
    labels = {"type1": "Type-I codebook", "svd": "SVD (ideal CSI)",
              "etype2": "eType-II codebook"}
    cdf.plot_cdfs(ax, {labels.get(k, k): v for k, v in ue_se.items()},
                  "UT spectral efficiency [bit/s/Hz]",
                  title=f"{cfg.name}: full buffer, SU-MIMO, "
                        f"{args.ue_per_cell} UTs/cell")
    fig.tight_layout()
    path = os.path.join(OUT, f"{args.tag}_ue_se_cdf.png")
    fig.savefig(path, dpi=130, facecolor=cdf.SURFACE)
    print("wrote", os.path.normpath(path))


if __name__ == "__main__":
    main()
