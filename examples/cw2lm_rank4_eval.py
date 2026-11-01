#!/usr/bin/env python3
"""Codeword-to-layer mapping for transmissions up to rank 4: NR vs LTE vs one
codeword per layer, end to end in the Dense Urban A system.

Schemes (``FullBufferConfig.cw_mapping``), layers per codeword at rank 1-4:

  nr         {1} / {2} / {3} / {4}            TS 38.211 Table 7.3.1.3-1
  lte        {1} / {1,1} / {1,2} / {2,2}      TS 36.211 Table 6.3.3.2-1
  per_layer  {1} / {1,1} / {1,1,1} / {1,1,1,1}

Every codeword has its own CQI, MCS, OLLA loop, TB and HARQ process, and the
rank is chosen knowing the split.  Variants (``--variants``):

  irc-olla    MMSE-IRC receiver, OLLA per codeword (the practical system)
  irc-ideal   MMSE-IRC, ideal link adaptation: each new TB's MCS is the
              highest meeting the BLER target on the SINR it actually gets
  sic-olla    codeword-level MMSE-SIC receiver (CQIs reported for SIC)
  sic-olla-cond  SIC, OLLA per codeword that skips the transmissions in
              which an earlier codeword failed (error propagation, not CQI
              error)
  sic-ideal   SIC with ideal link adaptation (the MCS of a codeword assumes the
              earlier ones are cancelled; whether they decode is not known)

With one codeword SIC is MMSE-IRC, so 'nr' is not run with SIC; the SIC
variants are compared with the IRC run of 'nr' under the same link
adaptation.  CSI cases as in ``examples/cw2lm_sls.py``:

  etype2_20ms  eType-II, CSI every 20 ms, 4 ms delay (Apple-like)
  svd_2ms      unquantised wideband SVD, every 2 ms, no delay (Nokia-like)

Retransmissions are adaptive (re-precoded with the current report), the
better policy for every scheme in the earlier study.

Each finished drop is appended to ``--log`` (JSON lines) at once, and a
re-run skips the drops already there, so a long study can be resumed:

    python examples/cw2lm_rank4_eval.py --variants irc-olla --drops 2 --jobs 4
    python examples/cw2lm_rank4_eval.py --variants irc-ideal,sic-olla,sic-ideal ...
    python examples/cw2lm_rank4_eval.py --summary-only        # tables, JSON, figure

Writes results/cw2lm_rank4.json (and .png with --plot).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nrsls.config.scenario import get_preset                        # noqa: E402
from nrsls.engine.fullbuffer import FullBufferConfig, run_full_buffer_drop  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "results")
SCHEMES = ("nr", "lte", "per_layer")
# (receiver, ideal link adaptation, OLLA conditional on the earlier codewords)
VARIANTS = {"irc-olla": ("irc", False, False), "irc-ideal": ("irc", True, False),
            "sic-olla": ("sic", False, False), "sic-olla-cond": ("sic", False, True),
            "sic-ideal": ("sic", True, False)}
LABEL = {"nr": "NR", "lte": "LTE", "per_layer": "1 CW/layer"}


def cases(slots: int, warmup: int) -> dict:
    """The two CSI cases of the codeword-mapping study (15 kHz: 1 ms slots)."""
    common = dict(n_slots=slots, warmup_slots=warmup, max_rank=4, rbg_size=4,
                  channel_update_slots=2, pdcch_symbols=2, overhead_re_per_prb=9,
                  harq_adaptive=True)
    return {"etype2_20ms": dict(codebook="etype2", csi_period_slots=20, csi_delay_slots=4,
                                **common),
            "svd_2ms": dict(codebook="svd", csi_period_slots=2, csi_delay_slots=0, **common)}


def fb_config(case: str, variant: str, scheme: str, slots: int, warmup: int
              ) -> FullBufferConfig:
    receiver, ideal, cond = VARIANTS[variant]
    extra = {}
    if receiver != "irc":
        extra["receiver"] = receiver
    if ideal:
        extra["ideal_la"] = True
    if cond:
        extra["olla_sic_conditional"] = True
    return FullBufferConfig(**cases(slots, warmup)[case], cw_mapping=scheme, **extra)


def _commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                              text=True, cwd=os.path.dirname(os.path.abspath(__file__))
                              ).stdout.strip()
    except OSError:
        return ""


def _worker(task):
    case, variant, scheme, drop, slots, warmup, seed, ues = task
    cfg = get_preset("du-a") if ues is None else get_preset("du-a", ue_per_cell=ues)
    t0 = time.time()
    # drop i is the random stream [seed, i] for every configuration
    r = run_full_buffer_drop(cfg, fb_config(case, variant, scheme, slots, warmup),
                             np.random.default_rng([seed, drop]))
    return dict(case=case, variant=variant, scheme=scheme, drop=drop, n_slots=slots,
                warmup=warmup, seed=seed, ue_per_cell=ues, runtime_s=round(time.time() - t0, 1),
                cell_se=r.cell_se, bler_first=r.bler_first,
                bler_first_cw=list(r.bler_first_cw), mean_rank=r.mean_rank,
                rank_hist=list(r.rank_hist), mean_codewords=r.mean_codewords,
                mean_mcs=r.mean_mcs, retx_rbg_fraction=r.retx_rbg_fraction,
                ue_se=[round(float(x), 6) for x in r.ue_se],
                geometry_db=[round(float(x), 2) for x in r.geometry_db])


def _key(rec) -> tuple:
    return (rec["case"], rec["variant"], rec["scheme"], rec["drop"], rec["n_slots"],
            rec["warmup"], rec["seed"], rec.get("ue_per_cell"))


def load_log(paths: str) -> list:
    """Records of the comma-separated JSON-lines logs (missing ones skipped)."""
    out = []
    for path in paths.split(","):
        if os.path.exists(path):
            with open(path) as fh:
                out += [json.loads(line) for line in fh if line.strip()]
    return out


# --- summary ---------------------------------------------------------------
def _stats(recs: list) -> dict:
    """KPIs of one configuration over its drops: cell SE and per-drop means
    averaged, UT SE pooled for the percentiles."""
    ue = np.concatenate([r["ue_se"] for r in recs])
    geo = np.concatenate([r["geometry_db"] for r in recs])
    n_cw = max(len(r["bler_first_cw"]) for r in recs)
    edges = np.percentile(geo, [100 / 3, 200 / 3])
    tercile = np.digitize(geo, edges)
    return {
        "drops": [r["drop"] for r in recs],
        "cell_se": float(np.mean([r["cell_se"] for r in recs])),
        "cell_se_per_drop": [r["cell_se"] for r in recs],
        "ue_se_p5": float(np.percentile(ue, 5)),
        "ue_se_p50": float(np.percentile(ue, 50)),
        "ue_se_mean_by_geometry_tercile": [float(ue[tercile == t].mean()) for t in range(3)],
        "bler_first": float(np.mean([r["bler_first"] for r in recs])),
        "bler_first_cw": [float(np.mean([r["bler_first_cw"][k] for r in recs
                                         if len(r["bler_first_cw"]) > k]))
                          for k in range(n_cw)],
        "mean_rank": float(np.mean([r["mean_rank"] for r in recs])),
        "rank_hist": np.mean([r["rank_hist"] for r in recs], axis=0).tolist(),
        "mean_codewords": float(np.mean([r["mean_codewords"] for r in recs])),
        "mean_mcs": float(np.mean([r["mean_mcs"] for r in recs])),
        "retx_rbg_fraction": float(np.mean([r["retx_rbg_fraction"] for r in recs])),
        "runtime_s": float(np.sum([r["runtime_s"] for r in recs])),
    }


def _pct(x: float, y: float) -> float:
    return 100 * (x / y - 1) if y > 0 else float("nan")


def summarize(log: list) -> dict:
    """Configurations grouped by (case, variant, run length); every scheme
    compared with 'nr' under the same CSI, link adaptation and run length,
    on the drops both have (for SIC: the IRC 'nr' run)."""
    groups = {}
    for r in log:
        g = (r["case"], r["variant"], r["n_slots"], r["warmup"], r["seed"], r.get("ue_per_cell"))
        groups.setdefault(g, {}).setdefault(r["scheme"], {})[r["drop"]] = r
    out = []
    for g, by_scheme in sorted(groups.items()):
        case, variant, slots, warmup, seed, ues = g
        base_variant = "irc-ideal" if VARIANTS[variant][1] else "irc-olla"
        base = groups.get((case, base_variant, slots, warmup, seed, ues), {}).get("nr", {})
        entry = {"case": case, "variant": variant, "n_slots": slots, "warmup": warmup,
                 "seed": seed, "ue_per_cell": ues, "baseline": f"nr/{base_variant}",
                 "schemes": {}}
        for s in SCHEMES:
            if s not in by_scheme:
                continue
            recs = [by_scheme[s][d] for d in sorted(by_scheme[s])]
            st = _stats(recs)
            common = sorted(set(by_scheme[s]) & set(base))
            if common:
                b = _stats([base[d] for d in common])
                m = _stats([by_scheme[s][d] for d in common])
                st["gain_vs_nr_pct"] = {
                    "drops": common,
                    "cell_se": _pct(m["cell_se"], b["cell_se"]),
                    "cell_se_per_drop": [_pct(by_scheme[s][d]["cell_se"], base[d]["cell_se"])
                                         for d in common],
                    "ue_se_p5": _pct(m["ue_se_p5"], b["ue_se_p5"]),
                    "ue_se_p50": _pct(m["ue_se_p50"], b["ue_se_p50"]),
                    "ue_se_by_geometry_tercile": [
                        _pct(x, y) for x, y in zip(m["ue_se_mean_by_geometry_tercile"],
                                                   b["ue_se_mean_by_geometry_tercile"])],
                }
            entry["schemes"][s] = st
        out.append(entry)
    return {"scenario": "Dense Urban-eMBB A (du-a)", "max_rank": 4,
            "harq": "adaptive", "configurations": out}


def print_summary(summ: dict) -> None:
    for e in summ["configurations"]:
        print(f"\n== {e['case']}, {e['variant']}, {e['n_slots']} slots "
              f"({e['warmup']} warm-up), baseline {e['baseline']}")
        print("  scheme      drops  cell SE  gain [per drop]          UT p5   gain  "
              "UT p50   gain  BLER per CW                  rank 1-4 %          retx")
        for s, st in e["schemes"].items():
            g = st.get("gain_vs_nr_pct")
            gs = (f"{g['cell_se']:+5.1f}% [{', '.join(f'{x:+.1f}' for x in g['cell_se_per_drop'])}]"
                  if g else "")
            p5 = f"{g['ue_se_p5']:+5.1f}%" if g else ""
            p50 = f"{g['ue_se_p50']:+5.1f}%" if g else ""
            print(f"  {s:10s}  {len(st['drops']):5d}  {st['cell_se']:7.3f}  {gs:24s} "
                  f"{st['ue_se_p5']:6.3f} {p5:>6s}  {st['ue_se_p50']:6.3f} {p50:>6s}  "
                  f"{str([round(b, 3) for b in st['bler_first_cw']]):28s} "
                  f"{str([round(100 * h) for h in st['rank_hist']]):18s} "
                  f"{st['retx_rbg_fraction']:.3f}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default="etype2_20ms,svd_2ms")
    ap.add_argument("--variants", default="irc-olla")
    ap.add_argument("--schemes", default=",".join(SCHEMES))
    ap.add_argument("--drops", type=int, default=2)
    ap.add_argument("--first-drop", type=int, default=0)
    ap.add_argument("--slots", type=int, default=480)
    ap.add_argument("--warmup", type=int, default=160)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--ues", type=int, default=None, help="UTs per cell (default: preset)")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--log", default=os.path.join(OUT, "cw2lm_rank4_runs.jsonl"),
                    help="JSON-lines log(s), comma-separated: new drops are appended "
                         "to the first, all are read")
    ap.add_argument("--out", default=os.path.join(OUT, "cw2lm_rank4.json"))
    ap.add_argument("--plot", default=None, help="figure path (e.g. results/cw2lm_rank4.png)")
    ap.add_argument("--summary-only", action="store_true")
    args = ap.parse_args()

    log = load_log(args.log)
    if not args.summary_only:
        done = {_key(r) for r in log}
        tasks = []
        for case in args.cases.split(","):
            for variant in args.variants.split(","):
                for s in args.schemes.split(","):
                    if s == "nr" and VARIANTS[variant][0] == "sic":
                        continue                   # one codeword: SIC = MMSE-IRC
                    for d in range(args.first_drop, args.first_drop + args.drops):
                        t = (case, variant, s, d, args.slots, args.warmup, args.seed, args.ues)
                        if (case, variant, s, d, args.slots, args.warmup, args.seed,
                                args.ues) not in done:
                            tasks.append(t)
        # longest first: SVD reports every 2 ms, multi-codeword decoding
        tasks.sort(key=lambda t: (t[0] != "svd_2ms", t[2] == "nr"))
        print(f"{len(tasks)} drop runs to do ({len(log)} already in {args.log})", flush=True)
        commit = _commit()
        log_out = args.log.split(",")[0]
        os.makedirs(os.path.dirname(os.path.abspath(log_out)), exist_ok=True)
        t0 = time.time()
        with ProcessPoolExecutor(max_workers=args.jobs) as ex:
            for fut in as_completed([ex.submit(_worker, t) for t in tasks]):
                rec = fut.result()
                rec["commit"] = commit
                # one write() per record: safe with another runner appending
                fd = os.open(log_out, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
                try:
                    os.write(fd, (json.dumps(rec) + "\n").encode())
                finally:
                    os.close(fd)
                log.append(rec)
                print(f"{rec['case']}/{rec['variant']}/{rec['scheme']} drop {rec['drop']}: "
                      f"cell SE {rec['cell_se']:.3f}, BLER {rec['bler_first']:.3f} "
                      f"({rec['runtime_s']:.0f} s, {time.time() - t0:.0f} s elapsed)",
                      flush=True)
    summ = summarize(log)
    print_summary(summ)
    with open(args.out, "w") as fh:
        json.dump(summ, fh, indent=1)
    print("wrote", os.path.normpath(args.out))
    if args.plot:
        from plot_cw2lm_rank4 import plot
        plot(summ, log, args.plot)
        print("wrote", os.path.normpath(args.plot))
    return 0


if __name__ == "__main__":
    sys.exit(main())
