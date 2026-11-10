# NR Downlink System-Level Simulator (`nrsls`)

A multi-cell, multi-UE NR downlink system-level simulator built on the
link-level simulator [`nrdlsim`](https://github.com/HelloSYQ/Claude). It
follows TR 38.901 (scenarios, propagation, calibration), TS 38.211/212/214
(numerology, MCS/TBS, CSI) and ITU-R M.2412 (KPIs).

- **Design:** [`docs/module-plan.md`](docs/module-plan.md)
- **Phase 1 (large-scale geometry):** done, see
  [`docs/calibration-p1.md`](docs/calibration-p1.md).
- **Phase 2 (TR 38.901 fast fading):** LSPs, clusters and rays, multipath
  port-0 RSRP and channel matrices H(f, t). The simulator matches the 3GPP
  IMT-2020 calibration data (RP-180524 / TR 37.910 Annex A) in all 9
  configurations it covers; see [`docs/calibration-p2.md`](docs/calibration-p2.md).
- **Phase 3 (full-buffer SU-MIMO):** MMSE-IRC, Type-I and Rel-16 eType-II
  CSI (plus SVD reference), PF scheduler, OLLA, HARQ, MIESM L2S. UMa 3.5 GHz
  32T4R: cell SE 5.83 / 6.13 / 6.27 bit/s/Hz (Type-I / eType-II / SVD); see
  [`docs/results-p3.md`](docs/results-p3.md).
- **LLS ↔ SLS regression:** one SLS link on the `nrdlsim` CDL channel
  reproduces the LLS `run_point` within 2.5 % SE (CDL-A/C/D, 4T2R to 32T4R,
  −5 to 30 dB); see [`docs/lls-regression.md`](docs/lls-regression.md).
- **MU-MIMO:** greedy per-RBG pairing (≤ 6 UTs / 12 layers), regularised
  ZF on the reported precoders, MU OLLA, co-scheduled HARQ retransmissions.
  UMa 32T4R: cell SE 8.20 / 9.83 / 9.88 bit/s/Hz (Type-I / eType-II / SVD),
  +41–60 % over SU, 5th percentile +17–36 %; see
  [`docs/results-p4-mu.md`](docs/results-p4-mu.md).
- **Benchmark against the 3GPP IMT-2020 self-evaluation** (TR 37.910, Dense
  Urban-eMBB A, FDD 10 MHz, 32×4 MU-MIMO): the 11-company Type II average of
  11.04 bit/s/Hz/TRxP (0.37 at the 5th percentile) lies between the
  simulator's eType-II result, 9.82 / 0.362, and its ideal-CSI bound,
  12.55 / 0.438; see
  [`docs/benchmark-tr37910.md`](docs/benchmark-tr37910.md).
- **Validation case** with pass/fail criteria on this set-up
  (`python examples/validate_du_a.py`): PASS 7/7; see
  [`docs/validation-du-a.md`](docs/validation-du-a.md).
- **Benchmark suite: is nrsls aligned with the other companies?**
  (`python examples/benchmark.py`). Tier 1 is a peer test against the
  RP-180524 per-company calibration curves: nrsls is scored as one more
  company, with tolerances set by the companies' own spread, on 10
  configurations, now including Dense Urban config A with its analog-beam
  calibration. 8 pass and 2 warn (UMa URLLC geometry about 0.5 dB low), and
  none is further from the consensus than every company. It also found that
  `du-a` used channel model B's building-loss mix (4.7 dB too much coupling
  gain against the channel-model-A companies, geometry unchanged); `du-a`
  now uses the M.2412 channel-model-A loss, and the TR 37.910 check still
  passes 7/7 (eType-II 10.00 / 0.348). Tier 2 is that end-to-end check. See
  [`docs/benchmark-suite.md`](docs/benchmark-suite.md).
- **Codeword-to-layer mapping probe** (`python examples/cw2lm_sls_probe.py`).
  In the Dense Urban A system with one codeword per UT, the CSI-stage gain
  of one codeword per layer, with codeword-aware rank adaptation, is +1.2 %
  (Apple R1-2608231 reports +1.6 %); at fixed rank 4 it is +9.7 %. Per-layer
  SINR predictions are off by 3–4 dB (standard deviation). See
  [`docs/cw2lm-sls-probe.md`](docs/cw2lm-sls-probe.md).
- **Multi-codeword SU-MIMO** (`FullBufferConfig.cw_mapping`): Alt 1 (NR),
  Alt 2 (≤ 2 codewords) or Alt 3 (one per layer), with per-codeword CQI,
  codeword-aware RI, OLLA per codeword (optionally per rank), one TB and HARQ
  process per codeword, and fixed or adaptive retransmissions. Alt 1 is
  bit-identical to before. On Dense Urban A with MMSE-IRC more codewords do
  not gain: with OLLA converged, one codeword per layer loses 1–2 % cell SE
  and 2.5–4 % at the median and 5th percentile (Apple-like and Nokia-like
  CSI); in 160-slot runs, and with non-adaptive retransmissions, up to 7 %.
  See [`docs/cw2lm-sls.md`](docs/cw2lm-sls.md).
- **Codeword mapping up to rank 4: NR, LTE style, one codeword per layer**
  (`python examples/cw2lm_rank4_eval.py`), with converged OLLA, a
  codeword-level MMSE-SIC receiver (`receiver='sic'`) and ideal link
  adaptation (`ideal_la`) as references. With MMSE-IRC, NR's single codeword
  is best: LTE style loses 0.7–1.1 % cell SE, one codeword per layer
  1.6–1.8 %. With SIC, LTE style gains 4.2–5.5 % cell SE, about neutral at
  the cell edge, if OLLA skips propagated failures (`olla_sic_conditional`;
  about 2 % otherwise), and 6–9 % with ideal link adaptation; one codeword
  per layer gains no more and loses 3–6 % at the 5th percentile. See
  [`docs/cw2lm-rank4.md`](docs/cw2lm-rank4.md).
- **The same mappings with FTP model 3 traffic at 20 / 50 / 70 % RU**
  (`FullBufferConfig.traffic='ftp3'`, `python examples/cw2lm_ftp_eval.py`),
  with eType-II and reciprocity-based (sub-band SVD) precoding, which fills
  the "SLS rank 1-4" sheet of `6GR_DL_CW2L_template_v003.xlsx`
  (`examples/fill_cw2l_template.py`). Bursty traffic magnifies the
  difference: with MMSE-IRC, LTE style loses 6–10 % mean UPT and one codeword
  per layer 15–21 % (12–27 % at the 5th percentile); with a codeword-level
  SIC receiver and plain OLLA, LTE style gains 4–9 % mean UPT and is about
  neutral to +4 % at the 5th percentile. See
  [`docs/cw2lm-ftp.md`](docs/cw2lm-ftp.md).
  The same study at 20 MHz, 30 kHz SCS and 44 dBm with 10 drops
  (`--setup 20mhz`, loads recalibrated to 21 / 51 / 71 % RU) gives the same
  picture: MMSE-IRC, LTE style −3 to −7 % and one codeword per layer −10 to
  −14 % mean UPT; SIC, +5 to +10 % and +5 to +12 %. See
  [`docs/cw2lm-ftp-20mhz.md`](docs/cw2lm-ftp-20mhz.md) and
  `6GR_DL_CW2L_template_v003_20MHz_44dBm.xlsx`.

## Guided tour

[`notebooks/NR_System_Level_Simulator_Guide.ipynb`](notebooks/NR_System_Level_Simulator_Guide.ipynb)
walks through every module with a live demo (layout, antenna, propagation,
calibration, channel, CSI, MU-MIMO, the slot loop, the LLS regression), shows
the full-scale results and explains the Dense Urban validation test, including
how its criteria catch injected faults. Regenerate it with
`pip install -e .[notebook] && python notebooks/build_guide.py`, then execute it
with `jupyter nbconvert --to notebook --execute --inplace notebooks/NR_System_Level_Simulator_Guide.ipynb`
(under a minute; the full-scale results and the validation run are read from `results/`).

## Install

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt     # includes nrdlsim pinned to a commit
pip install -e .
```

`nrdlsim` is a git dependency pinned in `pyproject.toml` / `requirements.txt`.
Bump the commit hash there to pick up link-level changes.

## Run

```bash
# large-scale drops for one or more presets
python run_sls.py --preset system --drops 20
python run_sls.py --preset calib-uma calib-umi calib-inh --drops 50 --jobs 4 \
    --plot results/calib.png --json results/calib.json

# the phase-1 figures in results/
python examples/plot_large_scale.py

# phase 3: full-buffer SU-MIMO, Type-I vs eType-II vs SVD
python examples/run_full_buffer.py --drops 4 --jobs 4

# MU-MIMO (RI <= 2, RZF, <= 6 UTs / 12 layers per RBG) and the SU vs MU figure
python examples/run_full_buffer.py --mu --max-rank 2 --tag p4_mu
python examples/plot_su_vs_mu.py

# LLS <-> SLS single-link regression sweep (the test is in the pytest suite)
python examples/lls_regression.py --jobs 4

# codeword-to-layer mapping: one run, and the Alt 1/2/3 study
python examples/run_full_buffer.py --cw-mapping alt3 --harq-adaptive
python examples/cw2lm_sls.py --drops 2 --slots 160 --jobs 4
python examples/run_full_buffer.py --preset du-a --cw-mapping lte --receiver sic \
    --olla-sic-conditional --harq-adaptive --codebooks svd --drops 1 --tag du_lte_sic
python examples/cw2lm_rank4_eval.py --summary-only --plot results/cw2lm_rank4.png

# the same with FTP model 3 traffic, and the 6GR CW2L template
python examples/cw2lm_ftp_eval.py --summary-only --log "$(ls results/ftp_parts/*.jsonl | paste -sd,)"
python examples/plot_cw2lm_ftp.py
python examples/fill_cw2l_template.py results/cw2lm_ftp.json 6GR_DL_CW2L_template_v003.xlsx
python examples/cw2lm_ftp_eval.py --setup 20mhz --summary-only --log "$(ls results/ftp20_parts/*.jsonl | paste -sd,)"
python examples/fill_cw2l_template.py results/cw2lm_ftp_20mhz.json 6GR_DL_CW2L_template_v003_20MHz_44dBm.xlsx

# benchmark against the other companies (tier 1 ~3 min; --e2e reruns tier 2)
python examples/benchmark.py

# tests
python -m pytest
```

| Preset | Scenario |
|---|---|
| `system` | UMa, 3.5 GHz, 100 MHz (273 PRB, 30 kHz), 53 dBm, 32T4R |
| `uma`, `umi`, `rma`, `inh-open`, `inh-mixed` | TR 38.901 §7.2 deployments |
| `calib-uma`, `calib-umi`, `calib-inh` | TR 38.901 Table 7.8-1-style large-scale calibration at 6 GHz |
| `du-a` | ITU-R M.2412 Dense Urban-eMBB config A, FDD 10 MHz, 32T4R, 200 m ISD (TR 37.910 benchmark) |
| `rp-rural-700m`, `rp-rural-4g`, `rp-rural-lmlc`, `rp-mmtc-500m`, `rp-mmtc-1732m`, `rp-urllc-4g`, `rp-urllc-700m`, `rp-inh-12trxp`, `rp-inh-36trxp` | RP-180524 IMT-2020 calibration set-ups (reference data in `refs/rp180524/`) |

Every field of `nrsls.ScenarioConfig` can be overridden:
`get_preset("system", ue_per_cell=20, o2i_model="legacy")`.
For example, `ue_self_blocking=True` adds the users' hand grip: the UT
self-blocking of TR 38.901 §7.6.4.1 (blockage model A). Each UT is held in
portrait or landscape mode, half and half, with a random orientation, and a
cluster that arrives in the grip's region loses 30 dB; see
[docs/cw2lm-hand-grip.md](docs/cw2lm-hand-grip.md).

`--jobs N` spreads drops over N spawned processes with single-threaded BLAS.
Results do not depend on N, because drop *i* always uses the random stream
`(seed, i)`.

## Layout

```
nrsls/
  config/scenario.py     ScenarioConfig, BS/UT antenna configs, presets
  topology/              hexagonal grid + wrap-around, InH hall, UT drop
  antenna/array.py       panel + TXRU virtualisation (element pattern from nrdlsim)
  propagation/           pathloss, LOS, O2I / in-car loss, LSPs, clusters/rays, H(f,t),
                         UT self-blocking (hand grip)
  link/                  noise, geometry, multipath port-0 RSRP; association
  phy/                   IRC SINR, Type-I / eType-II codebooks, CSI (RI/PMI/CQI)
  mac/                   CQI -> MCS, OLLA; MU-MIMO pairing and zero forcing
  engine/                one drop (drop.py), multi-drop driver (simulator.py),
                         full-buffer SU-MIMO loop (fullbuffer.py), per-TB steps
                         (link.py), one isolated link (single_link.py)
  validation/            LLS <-> SLS single-link regression (lls.py)
  metrics/               CDFs, percentiles, reference-curve comparison
  plots/                 CDF plotting
run_sls.py               command-line runner
examples/                figures, reference-data import, calibration comparison
refs/                    TR 37.910 Annex A curves, RP-180524 per-company data
tests/                   pytest suite
notebooks/               guided-tour notebook and its generator
```
