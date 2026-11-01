#!/usr/bin/env python3
"""Codeword-to-layer mapping up to rank 4 with FTP model 3 traffic: UPT gain
of LTE style and one codeword per layer over NR at 20 / 50 / 70 % resource
utilisation (RU), the system-level results the 6GR CW2L template collects.

Schemes (``cw_mapping``, layers per codeword at rank 1-4):

  nr         {1} / {2} / {3} / {4}            TS 38.211 Table 7.3.1.3-1
  lte        {1} / {1,1} / {1,2} / {2,2}      TS 36.211 Table 6.3.3.2-1
  per_layer  {1} / {1,1} / {1,1,1} / {1,1,1,1}

Variants: ``irc-olla`` (MMSE-IRC, OLLA per codeword: nr, lte, per_layer) and
``sic-olla`` (codeword-level MMSE-SIC, plain OLLA per codeword: lte,
per_layer; with one codeword SIC is MMSE-IRC, so NR is the IRC run).

Cases, both with CSI every 20 ms that is 4 ms old when used:

  etype2_20ms   Rel-16 eType-II codebook (parameter combination 6)
  svd_sb_20ms   unquantised sub-band SVD of the UT's channel, emulating
                reciprocity-based precoding with ideal SRS on all UT ports

Traffic: FTP model 3, 0.5 Mbyte files, Poisson arrivals per UT.  The arrival
rate of each load is the one that gives NR (MMSE-IRC) 20 / 50 / 70 % RU in
that case, found with ``--calibrate`` on drop 0 and kept in
``results/cw2lm_ftp_rates.json``.  Every scheme runs with the same files and
reports its own RU.  UPT = file size / (completion - arrival) per file; files
still open at the end count with the upper bound size / (end - arrival).

    python examples/cw2lm_ftp_eval.py --calibrate --jobs 4
    python examples/cw2lm_ftp_eval.py --drops 5 --jobs 4                 # all of it
    python examples/cw2lm_ftp_eval.py --cases svd_sb_20ms --loads 70 \\
        --drops 2 --first-drop 3 --log results/part.jsonl               # one slice
    python examples/cw2lm_ftp_eval.py --summary-only --log a.jsonl,b.jsonl

Each finished run is appended to ``--log`` at once and a re-run skips the
runs already there.  Writes ``results/cw2lm_ftp.json``.
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
sys.path.insert(0, os.path.dirname(__file__))

from cw2lm_rank4_eval import _commit, load_log                          # noqa: E402
from nrsls.config.scenario import get_preset                          # noqa: E402
from nrsls.engine.fullbuffer import FullBufferConfig, run_full_buffer_drop  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "results")
RATES = os.path.join(OUT, "cw2lm_ftp_rates.json")
SCHEMES = ("nr", "lte", "per_layer")
VARIANTS = {"irc-olla": "irc", "sic-olla": "sic"}
CASES = {"etype2_20ms": "etype2", "svd_sb_20ms": "svd_sb"}
LOADS = ("20", "50", "70")
FILE_BYTES = 0.5e6
CAL_RATES = (0.4, 0.7, 1.0, 1.3, 1.6)     # files/s per UT tried by --calibrate


def fb_config(case: str, variant: str, scheme: str, rate: float, slots: int, warmup: int,
              drain: int) -> FullBufferConfig:
    extra = {"receiver": "sic"} if VARIANTS[variant] == "sic" else {}
    return FullBufferConfig(
        n_slots=slots, warmup_slots=warmup, codebook=CASES[case], max_rank=4, rbg_size=4,
        channel_update_slots=2, csi_period_slots=20, csi_delay_slots=4, pdcch_symbols=2,
        overhead_re_per_prb=9, harq_adaptive=True, cw_mapping=scheme, traffic="ftp3",
        ftp_file_bytes=FILE_BYTES, ftp_rate_per_ue=rate, ftp_drain_slots=drain, **extra)


def _worker(task):
    case, variant, scheme, load, rate, drop, slots, warmup, drain, seed = task
    t0 = time.time()
    r = run_full_buffer_drop(get_preset("du-a"),
                             fb_config(case, variant, scheme, rate, slots, warmup, drain),
                             np.random.default_rng([seed, drop]))
    rd = lambda a: [round(float(x), -3) for x in a]                  # 1 kbit/s
    return dict(case=case, variant=variant, scheme=scheme, load=load, rate=rate, drop=drop,
                n_slots=slots, warmup=warmup, drain=drain, seed=seed,
                runtime_s=round(time.time() - t0, 1), ru=r.resource_utilization,
                files_counted=r.files_counted, served_se=r.cell_se,
                upt=rd(r.file_upt_bps), upt_ue=r.file_ue.tolist(),
                upt_open=rd(r.file_upt_open_bps), upt_open_ue=r.file_ue_open.tolist(),
                bler_first=r.bler_first, bler_first_cw=list(r.bler_first_cw),
                mean_rank=r.mean_rank, rank_hist=list(r.rank_hist),
                mean_codewords=r.mean_codewords, mean_mcs=r.mean_mcs,
                retx_rbg_fraction=r.retx_rbg_fraction)


def _key(rec) -> tuple:
    return (rec["case"], rec["variant"], rec["scheme"], rec["load"], rec["rate"], rec["drop"],
            rec["n_slots"], rec["warmup"], rec["drain"], rec["seed"])


def run_tasks(tasks: list, jobs: int, log_out: str, log: list) -> None:
    done = {_key(r) for r in log}
    tasks = [t for t in tasks if t not in done]
    # heaviest first: high load, many codewords, SIC
    tasks.sort(key=lambda t: (-float(t[3]) if t[3].isdigit() else -t[4], t[2] == "nr"))
    print(f"{len(tasks)} runs to do ({len(log)} records in the logs)", flush=True)
    commit, t0 = _commit(), time.time()
    with ProcessPoolExecutor(max_workers=jobs) as ex:
        for fut in as_completed([ex.submit(_worker, t) for t in tasks]):
            rec = fut.result()
            rec["commit"] = commit
            fd = os.open(log_out, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
            try:                                   # one write() per record
                os.write(fd, (json.dumps(rec) + "\n").encode())
            finally:
                os.close(fd)
            log.append(rec)
            u = np.array(rec["upt"] + rec["upt_open"])
            print(f"{rec['case']}/{rec['variant']}/{rec['scheme']} load {rec['load']} "
                  f"(rate {rec['rate']:.3f}) drop {rec['drop']}: RU {rec['ru']:.3f}, "
                  f"{rec['files_counted']} files ({len(rec['upt_open'])} open), UPT mean "
                  f"{u.mean() / 1e6 if u.size else 0:.1f} Mbit/s ({rec['runtime_s']:.0f} s, "
                  f"{time.time() - t0:.0f} s elapsed)", flush=True)


# --- calibration -----------------------------------------------------------
def calibrate(log: list, targets=(0.2, 0.5, 0.7)) -> dict:
    """Arrival rate per case for each RU target: piecewise-linear
    interpolation of NR's RU(rate) through (0, 0) and the calibration runs,
    extrapolated from the last two points beyond them."""
    out = {}
    for case in CASES:
        pts = sorted((r["rate"], r["ru"]) for r in log
                     if r["case"] == case and r["load"] == "cal" and r["scheme"] == "nr")
        if not pts:
            continue
        x = np.array([0.0] + [p[0] for p in pts])
        y = np.array([0.0] + [p[1] for p in pts])
        rates = {}
        for ld, t in zip(LOADS, targets):
            if t <= y[-1]:
                rates[ld] = float(np.interp(t, y, x))
            else:
                rates[ld] = float(x[-2] + (t - y[-2]) * (x[-1] - x[-2]) / (y[-1] - y[-2]))
        out[case] = {"rates": {k: round(v, 4) for k, v in rates.items()},
                     "points": [[a, round(b, 4)] for a, b in pts]}
    return out


# --- summary ---------------------------------------------------------------
def _pct(x: float, y: float) -> float:
    return 100 * (x / y - 1) if y > 0 else float("nan")


def _kpis(recs: list) -> dict:
    u = np.concatenate([np.array(r["upt"] + r["upt_open"], float) for r in recs])
    return {"drops": [r["drop"] for r in recs], "rate": recs[0]["rate"],
            "ru": float(np.mean([r["ru"] for r in recs])),
            "files": int(u.size),
            "open_files": int(sum(len(r["upt_open"]) for r in recs)),
            "upt_mean": float(u.mean()), "upt_p5": float(np.percentile(u, 5)),
            "upt_p50": float(np.percentile(u, 50)), "upt_p95": float(np.percentile(u, 95)),
            "upt_mean_per_drop": [float(np.mean(r["upt"] + r["upt_open"])) for r in recs],
            "served_se": float(np.mean([r["served_se"] for r in recs])),
            "bler_first": float(np.mean([r["bler_first"] for r in recs])),
            "bler_first_cw": [float(np.mean([r["bler_first_cw"][k] for r in recs
                                             if len(r["bler_first_cw"]) > k]))
                              for k in range(max(len(r["bler_first_cw"]) for r in recs))],
            "mean_rank": float(np.mean([r["mean_rank"] for r in recs])),
            "rank_hist": np.mean([r["rank_hist"] for r in recs], axis=0).tolist(),
            "retx_rbg_fraction": float(np.mean([r["retx_rbg_fraction"] for r in recs])),
            "runtime_s": float(np.sum([r["runtime_s"] for r in recs]))}


def summarize(log: list) -> dict:
    """Per (case, load, run length): every variant's schemes against NR
    (MMSE-IRC) on the drops both have."""
    groups = {}
    for r in log:
        if r["load"] not in LOADS:
            continue
        g = (r["case"], r["load"], r["n_slots"], r["warmup"], r["drain"], r["seed"])
        groups.setdefault(g, {}).setdefault((r["variant"], r["scheme"]), {})[r["drop"]] = r
    out = []
    for g, by in sorted(groups.items()):
        case, load, slots, warmup, drain, seed = g
        base = by.get(("irc-olla", "nr"), {})
        entry = {"case": case, "load": load, "n_slots": slots, "warmup": warmup,
                 "drain": drain, "seed": seed, "variants": {}}
        for (variant, scheme), recs in sorted(by.items()):
            st = _kpis([recs[d] for d in sorted(recs)])
            common = sorted(set(recs) & set(base))
            if common:
                m = _kpis([recs[d] for d in common])
                b = _kpis([base[d] for d in common])
                st["gain_vs_nr_pct"] = {
                    "drops": common,
                    "upt_mean": _pct(m["upt_mean"], b["upt_mean"]),
                    "upt_p5": _pct(m["upt_p5"], b["upt_p5"]),
                    "upt_p95": _pct(m["upt_p95"], b["upt_p95"]),
                    "upt_mean_per_drop": [_pct(x, y) for x, y in
                                          zip(m["upt_mean_per_drop"], b["upt_mean_per_drop"])]}
            entry["variants"].setdefault(variant, {})[scheme] = st
        out.append(entry)
    return {"scenario": "Dense Urban-eMBB A (du-a)", "traffic": "FTP model 3",
            "file_bytes": FILE_BYTES, "max_rank": 4, "harq": "adaptive", "configurations": out}


def print_summary(summ: dict) -> None:
    for e in summ["configurations"]:
        print(f"\n== {e['case']}, {e['load']} % RU target, {e['n_slots']} slots "
              f"({e['warmup']} warm-up, {e['drain']} drain)")
        print("  variant   scheme      drops   RU    files  open  UPT mean  gain    p5    gain"
              "    p95    gain   BLER per CW                rank")
        for v, by in e["variants"].items():
            for s, st in by.items():
                g = st.get("gain_vs_nr_pct", {})
                f = lambda k: f"{g[k]:+6.1f}%" if k in g else "       "
                print(f"  {v:9s} {s:10s} {len(st['drops']):5d}  {st['ru']:.3f} {st['files']:6d} "
                      f"{st['open_files']:5d} {st['upt_mean'] / 1e6:8.2f} {f('upt_mean')} "
                      f"{st['upt_p5'] / 1e6:6.2f} {f('upt_p5')} {st['upt_p95'] / 1e6:6.1f} "
                      f"{f('upt_p95')}  {str([round(x, 3) for x in st['bler_first_cw']]):26s} "
                      f"{st['mean_rank']:.2f}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=",".join(CASES))
    ap.add_argument("--variants", default=",".join(VARIANTS))
    ap.add_argument("--schemes", default=",".join(SCHEMES))
    ap.add_argument("--loads", default=",".join(LOADS))
    ap.add_argument("--drops", type=int, default=5)
    ap.add_argument("--first-drop", type=int, default=0)
    ap.add_argument("--slots", type=int, default=2300)
    ap.add_argument("--warmup", type=int, default=300)
    ap.add_argument("--drain", type=int, default=500)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--calibrate", action="store_true",
                    help="NR at several arrival rates on drop 0; writes --rates")
    ap.add_argument("--cal-slots", type=int, default=900)
    ap.add_argument("--rates", default=RATES)
    ap.add_argument("--log", default=os.path.join(OUT, "cw2lm_ftp_runs.jsonl"),
                    help="comma-separated JSON-lines logs; new records go to the first")
    ap.add_argument("--out", default=os.path.join(OUT, "cw2lm_ftp.json"))
    ap.add_argument("--summary-only", action="store_true")
    args = ap.parse_args()

    log = load_log(args.log)
    log_out = args.log.split(",")[0]
    cases = args.cases.split(",")
    if args.calibrate:
        tasks = [(c, "irc-olla", "nr", "cal", r, 0, args.cal_slots, args.warmup, 0, args.seed)
                 for c in cases for r in CAL_RATES]
        run_tasks(tasks, args.jobs, log_out, log)
        rates = calibrate(log)
        with open(args.rates, "w") as fh:
            json.dump(rates, fh, indent=1)
        print(json.dumps(rates, indent=1))
        print("wrote", os.path.normpath(args.rates))
        return 0
    if not args.summary_only:
        with open(args.rates) as fh:
            rates = json.load(fh)
        tasks = []
        for c in cases:
            for ld in args.loads.split(","):
                for v in args.variants.split(","):
                    for s in args.schemes.split(","):
                        if s == "nr" and VARIANTS[v] == "sic":
                            continue                   # one codeword: SIC = MMSE-IRC
                        for d in range(args.first_drop, args.first_drop + args.drops):
                            tasks.append((c, v, s, ld, rates[c]["rates"][ld], d, args.slots,
                                          args.warmup, args.drain, args.seed))
        run_tasks(tasks, args.jobs, log_out, log)
    summ = summarize(log)
    print_summary(summ)
    with open(args.out, "w") as fh:
        json.dump(summ, fh, indent=1)
    print("wrote", os.path.normpath(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
