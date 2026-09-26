#!/usr/bin/env python3
"""Run large-scale (phase-1) system-level drops and report the calibration KPIs.

Examples
--------
    # TR 38.901 clause 7.8.1-style large-scale calibration, 6 GHz
    python run_sls.py --preset calib-uma calib-umi calib-inh --drops 20 \\
        --plot results/p1_calibration.png --json results/p1_calibration.json

    # the default system: UMa 3.5 GHz, 100 MHz, 32T4R
    python run_sls.py --preset system --drops 20

    # compare against reference CDFs: <dir>/<preset>_coupling.csv and
    # <dir>/<preset>_geometry.csv, two columns "x, cdf"
    python run_sls.py --preset calib-uma --reference-dir refs/
"""

from __future__ import annotations

import argparse
import json
import os
import time

from nrsls.config.scenario import PRESETS, get_preset
from nrsls.engine.simulator import run_large_scale
from nrsls.metrics import calibration, kpi


def _row(name, s):
    cg, g = s["coupling_gain_db"], s["geometry_db"]
    return (f"{name:14s} {s['n_ut']:6d}  "
            f"{cg['p5']:7.1f} {cg['p50']:7.1f} {cg['p95']:7.1f}   "
            f"{g['p5']:6.1f} {g['p50']:6.1f} {g['p95']:6.1f}   "
            f"{s['los_fraction_serving']:5.2f} {s['o2i_fraction']:5.2f}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--preset", nargs="+", default=["system"],
                    choices=sorted(PRESETS))
    ap.add_argument("--drops", type=int, default=20)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--ue-per-cell", type=int, default=None)
    ap.add_argument("--plot", default=None, help="write CDF figure here")
    ap.add_argument("--json", default=None, help="write summary JSON here")
    ap.add_argument("--reference-dir", default=None,
                    help="directory with <preset>_coupling.csv / _geometry.csv")
    args = ap.parse_args(argv)

    overrides = {}
    if args.ue_per_cell is not None:
        overrides["ue_per_cell"] = args.ue_per_cell

    results, summary = {}, {}
    print(f"{'preset':14s} {'UTs':>6s}  {'coupling gain [dB] p5/50/95':>23s}   "
          f"{'geometry [dB] p5/50/95':>20s}   {'LOS':>5s} {'O2I':>5s}")
    for name in args.preset:
        cfg = get_preset(name, **overrides)
        t0 = time.time()
        st = run_large_scale(cfg, args.drops, args.seed, args.jobs)
        s = kpi.large_scale_summary(st)
        s["runtime_s"] = round(time.time() - t0, 2)
        s["config"] = cfg.name
        results[name], summary[name] = st, s
        print(_row(name, s))

        if args.reference_dir:
            for metric, samples in (("coupling", st.coupling_gain_db),
                                    ("geometry", st.geometry_db)):
                path = os.path.join(args.reference_dir, f"{name}_{metric}.csv")
                if os.path.exists(path):
                    rx, rf = calibration.load_reference_csv(path)
                    gaps = calibration.percentile_gaps(samples, rx, rf)
                    s[f"{metric}_gap_db"] = gaps
                    print(f"    {metric} gap vs {path}: " + ", ".join(
                        f"{k} {v:+.2f}" for k, v in gaps.items()))

    if args.json:
        os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
        with open(args.json, "w") as f:
            json.dump(summary, f, indent=2)
    if args.plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from nrsls.plots.cdf import plot_cdfs
        fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))
        plot_cdfs(ax[0], {n: r.coupling_gain_db for n, r in results.items()},
                  "Coupling gain, serving cell [dB]  (= -coupling loss)")
        plot_cdfs(ax[1], {n: r.geometry_db for n, r in results.items()},
                  "Geometry (wideband SINR) [dB]")
        fig.suptitle(f"Large-scale calibration, {args.drops} drops")
        fig.tight_layout()
        os.makedirs(os.path.dirname(args.plot) or ".", exist_ok=True)
        fig.savefig(args.plot, dpi=130)
        print(f"wrote {args.plot}")
    return summary


if __name__ == "__main__":
    main()
