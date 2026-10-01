"""System-level validation case: ITU-R Dense Urban-eMBB config A, FDD 10 MHz,
32x4 MU-MIMO, against the 3GPP IMT-2020 self-evaluation (TR 37.910).

Case
----
ITU-R M.2412 Table 5b, Dense Urban-eMBB evaluation configuration A (macro
layer): 19 sites x 3 TRxPs, ISD 200 m, 4 GHz, FDD 10 MHz at 15 kHz (52 PRB),
41 dBm, gNB (8,8,2,1,1;2,8) = 32 TXRUs, 10 UTs per TRxP with 4 ports, 80 %
indoor at 3 km/h, 20 % in car at 30 km/h, full buffer (preset ``du-a``).
MU-MIMO with the simulator defaults (RI <= 2, RZF on the reports, <= 6 UTs /
12 layers per RBG), CSI every 5 ms with a 4 ms delay on 4-PRB sub-bands,
overhead: 2 PDCCH symbols, 2 DM-RS symbols, 9 REs/PRB/slot for CSI-RS,
CSI-IM, TRS and SSB.  Two report types run on the same drops:

  * ``etype2``: Rel-16 eType-II, parameter combination 6 (the codebook
    under test, compared with the companies' Type II results);
  * ``svd_sb``: unquantised per-sub-band eigenvectors (ideal CSI bound).

Reference
---------
TR 37.910 Table 5.4.1.2.1-1(a), NR FDD, Dense Urban-eMBB config A,
"32x4 MU-MIMO, Type II codebook, gNB config (8,8,2,1,1;2,8)", 15 kHz,
channel model A, BW = 10 MHz, average over 11 companies: average spectral
efficiency 11.04 bit/s/Hz/TRxP, 5th-percentile user spectral efficiency
0.37 bit/s/Hz.  ITU-R M.2410 requirement: 7.8 and 0.225.

Acceptance criteria
-------------------
V1  eType-II average SE within +-15 % of 11.04
V2  eType-II 5th-percentile SE within +-15 % of 0.37
V3  ideal-CSI bound not below the reference: average SE >= 0.95 x 11.04
V4  CSI accuracy is monotonic: ideal CSI > eType-II in average and 5th pct
V5  ITU-R M.2410 met with eType-II: average >= 7.8, 5th pct >= 0.225
V6  link adaptation holds the target: 1st-tx BLER in [0.07, 0.13]
V7  MU-MIMO is exercised: >= 2 co-scheduled UTs per RBG on average

The TR gives the company average only, not its spread, and the companies'
detailed assumptions are not published with it.  +-15 % corresponds to
about +-1 dB of SINR at these spectral efficiencies, the spread of the
RP-180524 calibration (coupling gain / geometry) between companies.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from ..config.scenario import get_preset
from ..engine.fullbuffer import FullBufferConfig, _fb_worker, aggregate_drops

REFERENCE = {
    "source": "3GPP TR 37.910 Table 5.4.1.2.1-1(a): NR FDD, Dense Urban-eMBB "
              "config A, 32x4 MU-MIMO, Type II, (8,8,2,1,1;2,8), 15 kHz, "
              "channel model A, 10 MHz (11 companies)",
    "avg_se": 11.04,
    "p5_se": 0.37,
}
ITU_M2410 = {"avg_se": 7.8, "p5_se": 0.225}
TOLERANCE = 0.15
CODEBOOKS = ("etype2", "svd_sb")


def case(codebook: str, n_slots: int = 200, warmup_slots: int = 40):
    """(ScenarioConfig, FullBufferConfig) of the validation case."""
    cfg = get_preset("du-a")
    fb = FullBufferConfig(n_slots=n_slots, warmup_slots=warmup_slots,
                          codebook=codebook, max_rank=2, mu_mimo=True,
                          rbg_size=4, channel_update_slots=2, csi_period_slots=5,
                          csi_delay_slots=4, pdcch_symbols=2, overhead_re_per_prb=9)
    return cfg, fb


def run(n_drops: int = 2, n_slots: int = 200, warmup_slots: int = 40,
        seed: int = 1, n_jobs: int = 4) -> dict:
    """Run both report types on the same drops; {codebook: KPIs}."""
    from ..engine.simulator import parallel_map
    jobs, owner = [], []
    for cb in CODEBOOKS:
        cfg, fb = case(cb, n_slots, warmup_slots)
        jobs += [(cfg, fb, seed, i) for i in range(n_drops)]
        owner += [cb] * n_drops
    t0 = time.time()
    res = parallel_map(_fb_worker, jobs, n_jobs)
    out = {}
    for cb in CODEBOOKS:
        k = aggregate_drops([r for r, o in zip(res, owner) if o == cb])
        out[cb] = {key: v for key, v in k.items() if key not in ("drops", "ue_se")}
    out["_meta"] = {"n_drops": n_drops, "n_slots": n_slots,
                    "warmup_slots": warmup_slots, "seed": seed,
                    "runtime_s": round(time.time() - t0, 1)}
    return out


@dataclass
class Check:
    id: str
    description: str
    measured: str
    criterion: str
    passed: bool


def evaluate(r: dict) -> list[Check]:
    """Acceptance criteria V1-V7 on the KPIs returned by :func:`run`."""
    e, s = r["etype2"], r["svd_sb"]
    ref_a, ref_p = REFERENCE["avg_se"], REFERENCE["p5_se"]
    da, dp = e["cell_se"] / ref_a - 1, e["ue_se_p5"] / ref_p - 1
    checks = [
        Check("V1", "eType-II average SE vs TR 37.910 Type II",
              f"{e['cell_se']:.2f} ({100 * da:+.1f} %)", f"{ref_a} ± 15 %",
              abs(da) <= TOLERANCE),
        Check("V2", "eType-II 5th-percentile SE vs TR 37.910 Type II",
              f"{e['ue_se_p5']:.3f} ({100 * dp:+.1f} %)", f"{ref_p} ± 15 %",
              abs(dp) <= TOLERANCE),
        Check("V3", "ideal-CSI bound not below the reference",
              f"{s['cell_se']:.2f}", f">= {0.95 * ref_a:.2f}",
              s["cell_se"] >= 0.95 * ref_a),
        Check("V4", "ideal CSI > eType-II (average and 5th percentile)",
              f"{s['cell_se']:.2f} > {e['cell_se']:.2f}, "
              f"{s['ue_se_p5']:.3f} > {e['ue_se_p5']:.3f}", "both",
              s["cell_se"] > e["cell_se"] and s["ue_se_p5"] > e["ue_se_p5"]),
        Check("V5", "ITU-R M.2410 requirement with eType-II",
              f"{e['cell_se']:.2f} / {e['ue_se_p5']:.3f}",
              f">= {ITU_M2410['avg_se']} / >= {ITU_M2410['p5_se']}",
              e["cell_se"] >= ITU_M2410["avg_se"] and e["ue_se_p5"] >= ITU_M2410["p5_se"]),
        Check("V6", "first-transmission BLER (target 10 %)",
              f"{e['bler_first']:.3f} / {s['bler_first']:.3f}", "0.07 ... 0.13",
              all(0.07 <= x["bler_first"] <= 0.13 for x in (e, s))),
        Check("V7", "MU-MIMO exercised (co-scheduled UTs per RBG)",
              f"{e['mean_ues_per_rbg']:.2f} / {s['mean_ues_per_rbg']:.2f}", ">= 2",
              min(e["mean_ues_per_rbg"], s["mean_ues_per_rbg"]) >= 2.0),
    ]
    return checks


def report(r: dict, checks: list[Check]) -> str:
    """Markdown report of one validation run."""
    m = r["_meta"]
    lines = [
        f"Dense Urban-eMBB A, FDD 10 MHz, 32x4 MU-MIMO: {m['n_drops']} drops x "
        f"{m['n_slots']} slots ({m['warmup_slots']} warm-up), seed {m['seed']}, "
        f"{m['runtime_s']:.0f} s",
        "",
        "| Report | Average SE | 5th pct | Median | 1st-tx BLER | UTs / layers per RBG |",
        "|---|---|---|---|---|---|",
    ]
    for cb in CODEBOOKS:
        x = r[cb]
        lines.append(f"| {cb} | {x['cell_se']:.2f} | {x['ue_se_p5']:.3f} | "
                     f"{x['ue_se_p50']:.3f} | {x['bler_first']:.3f} | "
                     f"{x['mean_ues_per_rbg']:.2f} / {x['mean_layers_per_rbg']:.2f} |")
    lines += ["", f"Reference: {REFERENCE['source']}: {REFERENCE['avg_se']} / "
                  f"{REFERENCE['p5_se']}", "",
              "| Check | Description | Measured | Criterion | Result |",
              "|---|---|---|---|---|"]
    for c in checks:
        lines.append(f"| {c.id} | {c.description} | {c.measured} | {c.criterion} | "
                     f"{'PASS' if c.passed else 'FAIL'} |")
    n_pass = sum(c.passed for c in checks)
    lines += ["", f"**{'PASS' if n_pass == len(checks) else 'FAIL'}** "
                  f"({n_pass}/{len(checks)} checks)"]
    return "\n".join(lines)
