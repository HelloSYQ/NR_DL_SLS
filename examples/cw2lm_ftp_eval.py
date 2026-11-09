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
per_layer; with one codeword SIC is MMSE-IRC, so NR is the IRC run).  These
two are the published runs and refill every decoded codeword of a
retransmission (``harq_refill='always'``).  The screening variants of
2026-11-06 (docs/cw2lm-ftp-screen.md) add:

  *-fix     harq_refill='fresh': refill a decoded codeword only with the UT's
            current CSI at the transmission's rank and data in its buffer,
            else retransmit the failed codewords alone
  *-a       SIC: the RI metric weights codeword k by 0.9^k (error propagation)
  *-b       per-rank OLLA and an RI metric on the OLLA-corrected CQIs; the NR
            reference of a -b variant is NR with B (irc-fix-b)
  *-fast    OLLA fast start, x4 steps for a loop's first 20 ACK/NACKs, on
            every loop; NR runs with it too
  *-fastw   the same on every codeword but codeword 0 (the strongest
            layer); NR is the published run
  *-warmfast  FTP model 1: a new UT's loops start from the mean offset of
            the loops with at least 20 ACK/NACKs (warm start), plus the fast
            start on every loop; NR runs with both (for sic-fix-warmfast, NR
            is the irc-fix-warmfast run)
  *-async   asynchronous HARQ (harq_mode='async'): a due retransmission has
            priority but takes the best free RBGs for the UT's current report
            instead of its own; NR runs with it too

Cases, both with CSI every 20 ms that is 4 ms old when used:

  etype2_20ms   Rel-16 eType-II codebook (parameter combination 6)
  svd_sb_20ms   unquantised sub-band SVD of the UT's channel, emulating
                reciprocity-based precoding with ideal SRS on all UT ports
  svd_20ms      unquantised wideband SVD (one precoder for the whole band)

Set-up ``20mhz-ftp1`` runs FTP model 1 instead (UTs arrive at random places as
a Poisson process per cell, download one file and leave; a pool of 20 UTs per
cell serves the arrivals; rates in UT arrivals per second per cell).

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

Set-ups (``--setup``), both Dense Urban-eMBB A at 4 GHz FDD with 52 PRB:

  10mhz   15 kHz SCS, 10 MHz, 41 dBm (M.2412's 44 dBm per 20 MHz scaled to
          10 MHz); rates in results/cw2lm_ftp_rates.json, summary in
          results/cw2lm_ftp.json
  20mhz   30 kHz SCS, 20 MHz channel, 44 dBm; rates in
          results/cw2lm_ftp_rates_20mhz.json, summary in
          results/cw2lm_ftp_20mhz.json

CSI period (20 ms), CSI delay (4 ms) and channel update (2 ms) are times and
are converted to slots of the set-up's numerology; ``--slots``, ``--warmup``,
``--drain`` and the HARQ round trip (8 slots) are in slots.

Each finished run is appended to ``--log`` at once and a re-run skips the
runs already there.
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
from nrsls.config.scenario import DU_A_MIXED_O2I, CarrierConfig, get_preset  # noqa: E402
from nrsls.engine.fullbuffer import FullBufferConfig, run_full_buffer_drop  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "results")
RATES = os.path.join(OUT, "cw2lm_ftp_rates.json")
SCHEMES = ("nr", "lte", "per_layer", "lte_twisted")
# variant -> FullBufferConfig overrides (module doc)
_LEGACY = {"harq_refill": "always"}
_SIC = {"receiver": "sic"}
_A = {"ri_sic_propagation": True}
_B = {"olla_per_rank": True, "ri_olla": True}
# OLLA fast start: x4 steps for a loop's first 20 ACK/NACKs, on every loop
# (NR's included) or on all codewords but codeword 0 (the strongest layer);
# warm start: a new UT's loops start from the converged loops' mean
_FAST = {"olla_fast_gain": 4.0, "olla_fast_samples": 20}
_FASTW = dict(_FAST, olla_fast_min_cw=1)
VARIANTS = {"irc-olla": dict(_LEGACY), "sic-olla": dict(_SIC, **_LEGACY),
            "irc-fix": {}, "irc-fix-b": dict(_B),
            "sic-fix": dict(_SIC), "sic-fix-a": dict(_SIC, **_A),
            "sic-fix-b": dict(_SIC, **_B), "sic-fix-ab": dict(_SIC, **_A, **_B),
            "irc-fix-fast": dict(_FAST), "irc-fix-fastw": dict(_FASTW),
            "irc-fix-warmfast": dict(_FAST, olla_warm_samples=20),
            "sic-fix-warmfast": dict(_SIC, **_FAST, olla_warm_samples=20),
            "irc-fix-warmfast-async": dict(_FAST, olla_warm_samples=20, harq_mode="async"),
            "sic-fix-warmfast-async": dict(_SIC, **_FAST, olla_warm_samples=20,
                                           harq_mode="async")}
PUBLISHED_VARIANTS = ("irc-olla", "sic-olla")
SCREEN_VARIANTS = ("irc-fix", "irc-fix-b", "sic-fix", "sic-fix-a", "sic-fix-b", "sic-fix-ab")


def nr_reference(variant: str) -> str:
    """The NR run a variant is compared with: NR with the same rank
    adaptation (B), NR with the same OLLA fast start when it applies to NR's
    codeword too, else the published NR run."""
    v = VARIANTS[variant]
    if v.get("ri_olla"):
        return "irc-fix-b"
    if v.get("olla_warm_samples", 0) or (v.get("olla_fast_samples", 0)
                                         and v.get("olla_fast_min_cw", 0) == 0):
        # with one codeword SIC is MMSE-IRC: NR is the MMSE-IRC run with the
        # same OLLA (sic-fix-warmfast -> irc-fix-warmfast)
        return "irc-" + variant[4:] if variant.startswith("sic-") else variant
    return "irc-olla"


CASES = {"etype2_20ms": "etype2", "svd_sb_20ms": "svd_sb", "svd_20ms": "svd"}
LOADS = ("20", "50", "70")
FILE_BYTES = 0.5e6
CSI_PERIOD_S, CSI_DELAY_S, CHANNEL_UPDATE_S = 20e-3, 4e-3, 2e-3
DEFAULT_SETUP = "10mhz"
SETUPS = {
    "10mhz": dict(preset={}, rates=RATES, out=os.path.join(OUT, "cw2lm_ftp.json"),
                  cal_rates=(0.4, 0.7, 1.0, 1.3, 1.6),         # files/s per UT
                  carrier="4 GHz FDD, 15 kHz SCS, 10 MHz (52 PRB)",
                  power="41 dBm per 10 MHz"),
    "20mhz": dict(preset=dict(carrier=CarrierConfig(mu=1, n_size_grid=52),
                              bs_tx_power_dbm=44.0, channel_bandwidth_hz=20e6),
                  rates=os.path.join(OUT, "cw2lm_ftp_rates_20mhz.json"),
                  out=os.path.join(OUT, "cw2lm_ftp_20mhz.json"),
                  cal_rates=(0.65, 0.85, 1.3, 1.5, 1.75, 2.0),
                  carrier="4 GHz FDD, 30 kHz SCS, 20 MHz channel (52 PRB)",
                  power="44 dBm per 20 MHz"),
    # FTP model 1: a pool of 20 UTs per cell for the arriving users; rates
    # are UT (file) arrivals per second per cell
    "20mhz-ftp1": dict(preset=dict(carrier=CarrierConfig(mu=1, n_size_grid=52),
                                   bs_tx_power_dbm=44.0, channel_bandwidth_hz=20e6,
                                   ue_per_cell=20),
                       traffic="ftp1",
                       rates=os.path.join(OUT, "cw2lm_ftp1_rates_20mhz.json"),
                       out=os.path.join(OUT, "cw2lm_ftp1_20mhz.json"),
                       cal_rates=(5.0, 8.0, 11.0, 14.0, 17.0, 20.0),
                       carrier="4 GHz FDD, 30 kHz SCS, 20 MHz channel (52 PRB)",
                       power="44 dBm per 20 MHz"),
    # the same with the users' hand grip (TR 38.901 7.6.4.1 UT self-blocking:
    # portrait / landscape 50 / 50, random orientation, 30 dB); the arrival
    # rates are recalibrated for it
    "20mhz-ftp1-grip": dict(preset=dict(carrier=CarrierConfig(mu=1, n_size_grid=52),
                                        bs_tx_power_dbm=44.0, channel_bandwidth_hz=20e6,
                                        ue_per_cell=20, ue_self_blocking=True),
                            traffic="ftp1",
                            rates=os.path.join(OUT, "cw2lm_ftp1_grip_rates_20mhz.json"),
                            out=os.path.join(OUT, "cw2lm_ftp1_grip_20mhz.json"),
                            cal_rates=(5.0, 8.0, 11.0, 14.0, 17.0, 20.0),
                            carrier="4 GHz FDD, 30 kHz SCS, 20 MHz channel (52 PRB)",
                            power="44 dBm per 20 MHz"),
}
CAL_RATES = SETUPS[DEFAULT_SETUP]["cal_rates"]


def scenario(setup: str = DEFAULT_SETUP):
    # the published results used du-a's former building mix (DU_A_MIXED_O2I)
    return get_preset("du-a", **DU_A_MIXED_O2I, **SETUPS[setup]["preset"])


def _slots(setup: str, seconds: float) -> int:
    return int(round(seconds / scenario(setup).carrier.slot_duration_s))


def fb_config(case: str, variant: str, scheme: str, rate: float, slots: int, warmup: int,
              drain: int, setup: str = DEFAULT_SETUP) -> FullBufferConfig:
    extra = VARIANTS[variant]
    return FullBufferConfig(
        n_slots=slots, warmup_slots=warmup, codebook=CASES[case], max_rank=4, rbg_size=4,
        channel_update_slots=_slots(setup, CHANNEL_UPDATE_S),
        csi_period_slots=_slots(setup, CSI_PERIOD_S),
        csi_delay_slots=_slots(setup, CSI_DELAY_S), pdcch_symbols=2,
        overhead_re_per_prb=9, harq_adaptive=True, cw_mapping=scheme,
        ftp_file_bytes=FILE_BYTES, ftp_drain_slots=drain, **_traffic(setup, rate), **extra)


def _traffic(setup: str, rate: float) -> dict:
    """FTP model 3: ``rate`` files/s per UT; FTP model 1: UTs/s per cell."""
    if SETUPS[setup].get("traffic", "ftp3") == "ftp1":
        return {"traffic": "ftp1", "ftp1_rate_per_cell": rate}
    return {"traffic": "ftp3", "ftp_rate_per_ue": rate}


def _worker(task):
    case, variant, scheme, load, rate, drop, slots, warmup, drain, seed = task[:10]
    setup = task[10] if len(task) > 10 else DEFAULT_SETUP
    t0 = time.time()
    r = run_full_buffer_drop(scenario(setup),
                             fb_config(case, variant, scheme, rate, slots, warmup, drain, setup),
                             np.random.default_rng([seed, drop]))
    rd = lambda a: [round(float(x), -3) for x in a]                  # 1 kbit/s
    return dict(case=case, variant=variant, scheme=scheme, load=load, rate=rate, drop=drop,
                n_slots=slots, warmup=warmup, drain=drain, seed=seed, setup=setup,
                runtime_s=round(time.time() - t0, 1), ru=r.resource_utilization,
                files_counted=r.files_counted, served_se=r.cell_se,
                upt=rd(r.file_upt_bps), upt_ue=r.file_ue.tolist(),
                upt_open=rd(r.file_upt_open_bps), upt_open_ue=r.file_ue_open.tolist(),
                upt_t=[round(float(t), 4) for t in r.file_arrival_s],
                upt_open_t=[round(float(t), 4) for t in r.file_arrival_open_s],
                bler_first=r.bler_first, bler_first_cw=list(r.bler_first_cw),
                mean_rank=r.mean_rank, rank_hist=list(r.rank_hist),
                mean_codewords=r.mean_codewords, mean_mcs=r.mean_mcs,
                retx_rbg_fraction=r.retx_rbg_fraction,
                retx_moved_fraction=r.retx_moved_fraction,
                mean_active_ues=round(r.mean_active_ues, 3),
                arrivals_blocked=r.arrivals_blocked)


def _key(rec) -> tuple:
    return (rec["case"], rec["variant"], rec["scheme"], rec["load"], rec["rate"], rec["drop"],
            rec["n_slots"], rec["warmup"], rec["drain"], rec["seed"],
            rec.get("setup", DEFAULT_SETUP))


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
def calibrate(log: list, targets=(0.2, 0.5, 0.7), setup: str = DEFAULT_SETUP) -> dict:
    """Arrival rate per case for each RU target: piecewise-linear
    interpolation of NR's RU(rate), averaged over the calibration drops,
    through (0, 0), extrapolated from the last two points beyond them."""
    out = {}
    for case in CASES:
        by_rate = {}
        for r in log:
            if (r["case"] == case and r["load"] == "cal" and r["scheme"] == "nr"
                    and r.get("setup", DEFAULT_SETUP) == setup):
                by_rate.setdefault(r["rate"], []).append(r["ru"])
        pts = sorted((x, float(np.mean(v))) for x, v in by_rate.items())
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


def _files(r: dict, drain=None) -> tuple:
    """(completed, open) UPTs of a record; with ``drain`` (slots, or a dict
    run length -> slots) only the files that arrived before the last
    ``drain`` slots of the run (records that log arrival times, ``upt_t``;
    others as run)."""
    if isinstance(drain, dict):
        drain = drain.get(r["n_slots"])
    if drain is None or "upt_t" not in r:
        return r["upt"], r["upt_open"]
    t_max = (r["n_slots"] - drain) * scenario(r.get("setup", DEFAULT_SETUP)).carrier.slot_duration_s
    return ([u for u, t in zip(r["upt"], r["upt_t"]) if t < t_max],
            [u for u, t in zip(r["upt_open"], r["upt_open_t"]) if t < t_max])


def _drain_arg(text: str):
    """--summary-drain: N, or SLOTS:N,SLOTS:N."""
    if ":" not in text:
        return int(text)
    return {int(k): int(v) for k, v in (p.split(":") for p in text.split(","))}


def _stat(u: np.ndarray, f, *args) -> float:
    """f(u, *args), or NaN when no file is counted (e.g. a drain as long as the run)."""
    return float(f(u, *args)) if u.size else float("nan")


def _kpis(recs: list, drain: int | None = None) -> dict:
    fl = [_files(r, drain) for r in recs]
    u = np.concatenate([np.array(a + b, float) for a, b in fl])
    return {"drops": [r["drop"] for r in recs], "rate": recs[0]["rate"],
            "ru": float(np.mean([r["ru"] for r in recs])),
            "files": int(u.size),
            "open_files": int(sum(len(b) for _, b in fl)),
            "upt_mean": _stat(u, np.mean), "upt_p5": _stat(u, np.percentile, 5),
            "upt_p50": _stat(u, np.percentile, 50), "upt_p95": _stat(u, np.percentile, 95),
            "upt_mean_per_drop": [_stat(np.array(a + b, float), np.mean) for a, b in fl],
            "served_se": float(np.mean([r["served_se"] for r in recs])),
            "bler_first": float(np.mean([r["bler_first"] for r in recs])),
            "bler_first_cw": [float(np.mean([r["bler_first_cw"][k] for r in recs
                                             if len(r["bler_first_cw"]) > k]))
                              for k in range(max(len(r["bler_first_cw"]) for r in recs))],
            "mean_rank": float(np.mean([r["mean_rank"] for r in recs])),
            "rank_hist": np.mean([r["rank_hist"] for r in recs], axis=0).tolist(),
            "retx_rbg_fraction": float(np.mean([r["retx_rbg_fraction"] for r in recs])),
            "retx_moved_fraction": float(np.mean([r.get("retx_moved_fraction", 0.0)
                                                  for r in recs])),
            "mean_active_ues": float(np.mean([r.get("mean_active_ues", 0.0) for r in recs])),
            "arrivals_blocked": int(sum(r.get("arrivals_blocked", 0) for r in recs)),
            "runtime_s": float(np.sum([r["runtime_s"] for r in recs]))}


def summarize(log: list, setup: str = DEFAULT_SETUP, drain: int | None = None) -> dict:
    """Per (case, load, run length): every variant's schemes against NR
    (MMSE-IRC; with B, NR with B: ``nr_reference``) on the drops both have."""
    groups = {}
    for r in log:
        if r["load"] not in LOADS or r.get("setup", DEFAULT_SETUP) != setup:
            continue
        g = (r["case"], r["load"], r["n_slots"], r["warmup"], r["drain"], r["seed"])
        groups.setdefault(g, {}).setdefault((r["variant"], r["scheme"]), {})[r["drop"]] = r
    out = []
    for g, by in sorted(groups.items()):
        case, load, slots, warmup, run_drain, seed = g
        entry = {"case": case, "load": load, "n_slots": slots, "warmup": warmup,
                 "drain": run_drain, "seed": seed, "variants": {}}
        if drain is not None:
            entry["summary_drain"] = drain
        for (variant, scheme), recs in sorted(by.items()):
            st = _kpis([recs[d] for d in sorted(recs)], drain)
            st["nr_reference"] = ref = nr_reference(variant) if variant in VARIANTS \
                else "irc-olla"
            base = by.get((ref, "nr"), {})
            common = sorted(set(recs) & set(base))
            if common:
                m = _kpis([recs[d] for d in common], drain)
                b = _kpis([base[d] for d in common], drain)
                st["gain_vs_nr_pct"] = {
                    "drops": common,
                    "upt_mean": _pct(m["upt_mean"], b["upt_mean"]),
                    "upt_p5": _pct(m["upt_p5"], b["upt_p5"]),
                    "upt_p95": _pct(m["upt_p95"], b["upt_p95"]),
                    "upt_mean_per_drop": [_pct(x, y) for x, y in
                                          zip(m["upt_mean_per_drop"], b["upt_mean_per_drop"])]}
            entry["variants"].setdefault(variant, {})[scheme] = st
        out.append(entry)
    car = scenario(setup).carrier
    model = "FTP model 1" if SETUPS[setup].get("traffic") == "ftp1" else "FTP model 3"
    return {"scenario": "Dense Urban-eMBB A (du-a)", "traffic": model,
            "file_bytes": FILE_BYTES, "max_rank": 4, "harq": "adaptive", "setup": setup,
            "carrier": SETUPS[setup]["carrier"], "power": SETUPS[setup]["power"],
            "slot_ms": car.slot_duration_s * 1e3, "configurations": out}


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
    ap.add_argument("--setup", default=DEFAULT_SETUP, choices=list(SETUPS))
    ap.add_argument("--cases", default=",".join(CASES))
    ap.add_argument("--variants", default=",".join(PUBLISHED_VARIANTS))
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
                    help="NR at several arrival rates on --cal-drops drops; writes --rates")
    ap.add_argument("--cal-slots", type=int, default=900)
    ap.add_argument("--cal-drops", type=int, default=1)
    ap.add_argument("--cal-rates", default=None,
                    help="comma-separated files/s per UT (default: the set-up's)")
    ap.add_argument("--rates", default=None, help="default: the set-up's rates file")
    ap.add_argument("--log", default=os.path.join(OUT, "cw2lm_ftp_runs.jsonl"),
                    help="comma-separated JSON-lines logs; new records go to the first")
    ap.add_argument("--out", default=None, help="default: the set-up's summary file")
    ap.add_argument("--summary-only", action="store_true")
    ap.add_argument("--summary-drain", type=_drain_arg, default=None,
                    help="summary: count only files that arrived before the last N slots "
                         "of each run (runs that log arrival times); N, or per run "
                         "length as SLOTS:N,SLOTS:N (e.g. 1000:300,2000:1000)")
    args = ap.parse_args()

    setup = args.setup
    args.rates = args.rates or SETUPS[setup]["rates"]
    args.out = args.out or SETUPS[setup]["out"]
    log = load_log(args.log)
    log_out = args.log.split(",")[0]
    cases = args.cases.split(",")
    if args.calibrate:
        cal = ([float(x) for x in args.cal_rates.split(",")] if args.cal_rates
               else SETUPS[setup]["cal_rates"])
        tasks = [(c, "irc-olla", "nr", "cal", r, d, args.cal_slots, args.warmup, 0, args.seed,
                  setup) for c in cases for r in cal for d in range(args.cal_drops)]
        run_tasks(tasks, args.jobs, log_out, log)
        rates = calibrate(log, setup=setup)
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
                        # one codeword: SIC is MMSE-IRC and there is nothing to
                        # refill, so NR runs as the variant's reference
                        # (irc-olla, or irc-fix-b with B)
                        vr = nr_reference(v) if s == "nr" else v
                        for d in range(args.first_drop, args.first_drop + args.drops):
                            t = (c, vr, s, ld, rates[c]["rates"][ld], d, args.slots,
                                 args.warmup, args.drain, args.seed, setup)
                            if t not in tasks:
                                tasks.append(t)
        run_tasks(tasks, args.jobs, log_out, log)
    summ = summarize(log, setup, args.summary_drain)
    print_summary(summ)
    with open(args.out, "w") as fh:
        json.dump(summ, fh, indent=1)
    print("wrote", os.path.normpath(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
