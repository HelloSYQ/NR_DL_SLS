#!/usr/bin/env python3
"""Benchmark: is the nrsls system-level evaluation aligned with the other
companies?  See docs/benchmark-suite.md.

Tier 1, large-scale calibration (nrsls.validation.calibration_bench): every
RP-180524 configuration nrsls can set up (channel model A), coupling gain
and DL geometry CDFs against the 15-18 companies' curves, as a peer test.

Tier 2, end to end (nrsls.validation.du_a): full-buffer MU-MIMO spectral
efficiency of Dense Urban-eMBB config A against the TR 37.910 11-company
average.  Taken from the last run (results/validation_du_a.json) unless
``--e2e`` reruns it (~27 min on 4 cores).

    python examples/benchmark.py                     # tier 1 (~10 min) + cached tier 2
    python examples/benchmark.py --tier 1 --cases du-4g,umaurllc-4g --drops 10
    python examples/benchmark.py --e2e               # rerun tier 2 too

Writes results/benchmark.json, results/benchmark.md and
results/benchmark_calibration.png.  Exit code 1 if a scored check fails.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nrsls.validation import calibration_bench as cb  # noqa: E402
from nrsls.validation import du_a  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "results")
LABEL = {"coupling_gain": "Coupling gain", "geometry": "DL geometry"}


def _commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
                                       cwd=os.path.dirname(__file__), text=True).strip()
    except Exception:
        return "unknown"


def tier1(cases, n_drops, seed, jobs) -> list:
    out = []
    for case in cases:
        t0 = time.time()
        r = cb.run_case(case, n_drops, seed, jobs)
        r["runtime_s"] = round(time.time() - t0, 1)
        out.append(r)
        m = r["metrics"]
        print(f"{case.name:16s} " + "  ".join(
            f"{LABEL[k]}: {v['deviation_db']:.2f} dB (companies p80 "
            f"{v['company_deviation_db']['p80']:.2f}, max {v['company_deviation_db']['max']:.2f}; "
            f"rank {v['rank']}/{v['n_companies'] + 1}; env {100 * v['envelope_share']:.0f} %) "
            f"{v['verdict']}" for k, v in m.items())
            + f"  -> {r['verdict']}{'' if case.scored else ' (not scored)'}"
            f"  [{r['runtime_s']:.0f} s]", flush=True)
    return out


def tier2(rerun: bool, jobs: int) -> dict:
    path = os.path.join(OUT, "validation_du_a.json")
    if rerun:
        r = du_a.run(n_jobs=jobs)
        checks = du_a.evaluate(r)
        data = {"reference": du_a.REFERENCE, "results": r,
                "checks": [c.__dict__ for c in checks]}
        with open(path, "w") as f:
            json.dump(data, f, indent=1)
        with open(os.path.join(OUT, "validation_du_a.md"), "w") as f:
            f.write(du_a.report(r, checks) + "\n")
        source = "run now"
    elif os.path.exists(path):
        with open(path) as f:
            data = json.load(f)
        mtime = datetime.datetime.fromtimestamp(os.path.getmtime(path))
        source = f"cached {os.path.relpath(path, os.path.join(OUT, '..'))} ({mtime:%Y-%m-%d})"
    else:
        return {"source": "missing: run with --e2e", "verdict": "NOT RUN", "checks": []}
    ok = all(c["passed"] for c in data["checks"])
    return {"source": source, "reference": data["reference"],
            "results": {k: v for k, v in data["results"].items() if k != "_meta"},
            "meta": data["results"].get("_meta", {}), "checks": data["checks"],
            "verdict": "PASS" if ok else "FAIL"}


def overall(t1: list, t2: dict) -> str:
    v = [r["verdict"] for r in t1 if r["scored"]]
    if t2.get("verdict") in ("PASS", "FAIL"):
        v.append(t2["verdict"])
    return cb.combine(v) if v else "NOT RUN"


def scorecard(t1: list, t2: dict, meta: dict) -> str:
    f = lambda x: f"{x:+.1f}".replace("-", "−")
    L = [f"# nrsls benchmark scorecard: {meta['overall']}", "",
         f"Commit `{meta['commit']}`, {meta['date']}. Tier 1: {meta['drops']} drops per "
         f"configuration, seed {meta['seed']}. See [docs/benchmark-suite.md]"
         "(../docs/benchmark-suite.md) for the method.", ""]
    if t1:
        L += ["## Tier 1: large-scale calibration against RP-180524 (peer test)", "",
              "Deviation = mean |gap| to the consensus over the 5th-95th percentiles [dB]. "
              "Companies: the same for each company against the mean of the others "
              "(median / 80th percentile / max). Rank among the n + 1 participants "
              "(1 = closest to the consensus). Env. = share of the percentiles inside the "
              "companies' min-max envelope.", "",
              "| Configuration | Metric | nrsls deviation | Companies (median / p80 / max) | Rank "
              "| Env. | Largest gap | Verdict |",
              "|---|---|---|---|---|---|---|---|"]
        for r in t1:
            for k, m in r["metrics"].items():
                c = m["company_deviation_db"]
                name = r["case"] + ("" if r["scored"] else " (sensitivity)")
                L.append(f"| {name} | {LABEL[k]} | {m['deviation_db']:.2f} | {c['median']:.2f} / "
                         f"{c['p80']:.2f} / {c['max']:.2f} | {m['rank']} / "
                         f"{m['n_companies'] + 1} | {100 * m['envelope_share']:.0f} % | "
                         f"{f(max(m['gap_db'].values(), key=abs))} dB "
                         f"| **{m['verdict']}** |")
        L += ["", "Gap to the company mean at the 5 / 10 / 20 / 50 / 80 / 90 / 95th "
              "percentiles [dB]:", "",
              "| Configuration | Coupling gain | Geometry |", "|---|---|---|"]
        for r in t1:
            g = {k: " ".join(f(m["gap_db"][f"p{p}"]) for p in (5, 10, 20, 50, 80, 90, 95))
                 for k, m in r["metrics"].items()}
            L.append(f"| {r['case']} | {g['coupling_gain']} | {g['geometry']} |")
        notes = [r for r in t1 if r["note"]]
        if notes:
            L += [""] + [f"- **{r['case']}**: {r['note']}." for r in notes]
        L.append("")
    L += ["## Tier 2: end-to-end spectral efficiency against TR 37.910", "",
          f"Dense Urban-eMBB config A, 32x4 MU-MIMO, eType-II and ideal CSI "
          f"({t2['source']}): **{t2['verdict']}**.", ""]
    if t2.get("checks"):
        L += ["| Check | Measured | Criterion | Result |", "|---|---|---|---|"]
        L += [f"| {c['id']} {c['description']} | {c['measured']} | {c['criterion']} | "
              f"{'PASS' if c['passed'] else 'FAIL'} |" for c in t2["checks"]]
    return "\n".join(L) + "\n"


def figure(t1: list, path: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from nrsls.plots.cdf import AXIS, INK, INK_2, MUTED, SERIES, SURFACE, style_axes
    rows = t1[::-1]
    fig, axs = plt.subplots(1, 2, figsize=(11, 0.42 * len(rows) + 1.6), facecolor=SURFACE,
                            sharey=True)
    for ax, metric in zip(axs, cb.METRICS):
        style_axes(ax)
        ax.grid(False, axis="y")
        for y, r in enumerate(rows):
            m = r["metrics"][metric]
            dev = m["company_deviations_db"]
            ax.plot(dev, [y] * len(dev), "o", ms=4, mfc=MUTED, mec=SURFACE, mew=0.6,
                    alpha=0.8, zorder=2)
            q = m["company_deviation_db"]["p80"]
            ax.plot([q, q], [y - 0.28, y + 0.28], color=INK_2, lw=1.2, zorder=2)
            ax.plot([m["deviation_db"]], [y], "D", ms=7, mfc=SERIES[0], mec=SURFACE,
                    mew=1.2, zorder=3)
            ax.text(1.0, y, f" {m['verdict']}", transform=ax.get_yaxis_transform(),
                    va="center", ha="left", fontsize=7.5, color=INK_2)
        ax.set_xlim(left=0)
        ax.set_title(LABEL[metric], fontsize=10, loc="left", color=INK)
        ax.set_xlabel("Mean |gap| to the consensus of the others, 5th-95th pct [dB]",
                      fontsize=8.5)
    axs[0].set_yticks(range(len(rows)))
    axs[0].set_yticklabels([r["case"] + ("" if r["scored"] else " *") for r in rows],
                           fontsize=8.5)
    handles = [plt.Line2D([], [], ls="", marker="o", ms=4, mfc=MUTED, mec=SURFACE),
               plt.Line2D([], [], color=INK_2, lw=1.2),
               plt.Line2D([], [], ls="", marker="D", ms=7, mfc=SERIES[0], mec=SURFACE)]
    leg = fig.legend(handles, ["a company (leave one out)", "80th percentile of companies",
                               "nrsls"], loc="upper left", bbox_to_anchor=(0.005, 0.97),
                     ncol=3, frameon=False, fontsize=8)
    for t in leg.get_texts():
        t.set_color(INK_2)
    fig.suptitle("Calibration peer test against RP-180524 (channel model A)", x=0.01,
                 y=0.995, ha="left", fontsize=11, color=INK)
    fig.text(0.01, 0.005, "* sensitivity run, not scored.", fontsize=7.5, color=MUTED)
    fig.tight_layout(rect=(0, 0.02, 0.97, 0.93))
    fig.savefig(path, dpi=130, facecolor=SURFACE)
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", choices=("1", "2", "all"), default="all")
    ap.add_argument("--cases", default="", help="comma-separated tier-1 case names")
    ap.add_argument("--drops", type=int, default=20)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--e2e", action="store_true", help="rerun tier 2 (~27 min)")
    ap.add_argument("--out", default=os.path.join(OUT, "benchmark"))
    args = ap.parse_args()

    names = [c for c in args.cases.split(",") if c]
    unknown = set(names) - {c.name for c in cb.CASES}
    if unknown:
        ap.error(f"unknown cases {sorted(unknown)}; known: {[c.name for c in cb.CASES]}")
    cases = [c for c in cb.CASES if not names or c.name in names]
    t1 = tier1(cases, args.drops, args.seed, args.jobs) if args.tier in ("1", "all") else []
    t2 = (tier2(args.e2e, args.jobs) if args.tier in ("2", "all")
          else {"source": "not requested", "verdict": "NOT RUN", "checks": []})
    meta = {"commit": _commit(), "date": f"{datetime.date.today()}", "drops": args.drops,
            "seed": args.seed}
    meta["overall"] = overall(t1, t2)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out + ".json", "w") as f:
        json.dump({"meta": meta, "tier1": t1, "tier2": t2}, f, indent=1)
    with open(args.out + ".md", "w") as f:
        f.write(scorecard(t1, t2, meta))
    if t1:
        figure(t1, args.out + "_calibration.png")
    print(f"overall: {meta['overall']}  (wrote {os.path.normpath(args.out)}.json/.md)")
    return 1 if meta["overall"] == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
