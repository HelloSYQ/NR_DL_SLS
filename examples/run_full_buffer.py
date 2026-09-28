#!/usr/bin/env python3
"""Full-buffer SU-MIMO (phase 3) or MU-MIMO spectral efficiency.

Runs the default system (UMa 3.5 GHz, 100 MHz, 32T4R) with Type-I,
Rel-16 eType-II (parameter combination 6) and SVD (ideal-CSI reference)
reports and writes

  results/<tag>_full_buffer.json   cell / 5th-percentile / median UT SE, BLER,
                                   rank, MCS, co-scheduling per configuration,
                                   and the per-UT SE samples
  results/<tag>_ue_se_cdf.png      CDF of the UT spectral efficiency

    python examples/run_full_buffer.py [--drops 4] [--jobs 4] [--slots 200]
    python examples/run_full_buffer.py --mu --max-rank 2 --tag p4_mu
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
    ap.add_argument("--mu", action="store_true", help="MU-MIMO scheduling")
    ap.add_argument("--max-rank", type=int, default=4, help="CSI rank restriction")
    ap.add_argument("--mu-max-ues", type=int, default=4)
    ap.add_argument("--mu-max-layers", type=int, default=8)
    args = ap.parse_args()

    cfg = get_preset(args.preset, ue_per_cell=args.ue_per_cell)
    summary, ue_se = {}, {}
    for cb in args.codebooks:
        fb = FullBufferConfig(n_slots=args.slots, warmup_slots=args.warmup,
                              codebook=cb, max_rank=args.max_rank, mu_mimo=args.mu,
                              mu_max_ues=args.mu_max_ues,
                              mu_max_layers=args.mu_max_layers)
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
              f"UTs/RBG {r['mean_ues_per_rbg']:.2f}  layers/RBG "
              f"{r['mean_layers_per_rbg']:.2f}  MU TBs {r['mu_tb_fraction']:.2f}  "
              f"({summary[cb]['runtime_s']} s)", flush=True)

    os.makedirs(OUT, exist_ok=True)
    meta = {"preset": cfg.name, "drops": args.drops, "slots": args.slots,
            "warmup": args.warmup, "ue_per_cell": args.ue_per_cell,
            "mu_mimo": args.mu, "max_rank": args.max_rank,
            "mu_max_ues": args.mu_max_ues, "mu_max_layers": args.mu_max_layers}
    with open(os.path.join(OUT, f"{args.tag}_full_buffer.json"), "w") as f:
        json.dump({"config": meta, "results": summary,
                   "ue_se": {k: [round(float(x), 5) for x in v] for k, v in ue_se.items()}},
                  f, indent=1)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from nrsls.plots import cdf
    fig, ax = plt.subplots(figsize=(6.5, 4.2), facecolor=cdf.SURFACE)
    labels = {"type1": "Type-I codebook", "svd": "SVD (ideal CSI)",
              "etype2": "eType-II codebook"}
    cdf.plot_cdfs(ax, {labels.get(k, k): v for k, v in ue_se.items()},
                  "UT spectral efficiency [bit/s/Hz]",
                  title=f"{cfg.name}: full buffer, {'MU' if args.mu else 'SU'}-MIMO, "
                        f"{args.ue_per_cell} UTs/cell")
    fig.tight_layout()
    path = os.path.join(OUT, f"{args.tag}_ue_se_cdf.png")
    fig.savefig(path, dpi=130, facecolor=cdf.SURFACE)
    print("wrote", os.path.normpath(path))


if __name__ == "__main__":
    main()
