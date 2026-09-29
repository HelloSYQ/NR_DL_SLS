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
  reproduces the LLS `run_point` within 2 % SE (CDL-A/C/D, 4T2R to 32T4R,
  −5 to 30 dB); see [`docs/lls-regression.md`](docs/lls-regression.md).
- **MU-MIMO:** greedy per-RBG pairing, zero forcing on the reported
  precoders, MU OLLA, co-scheduled HARQ retransmissions, DM-RS overhead.
  UMa 32T4R: cell SE 7.69 / 9.48 / 9.64 bit/s/Hz (Type-I / eType-II / SVD),
  +32–55 % over SU, 5th percentile +15–36 %; see
  [`docs/results-p4-mu.md`](docs/results-p4-mu.md).
- **Benchmark against the 3GPP IMT-2020 self-evaluation** (TR 37.910, Dense
  Urban-eMBB A, FDD 10 MHz, 32×4 MU-MIMO): with ideal sub-band CSI the
  simulator gives 11.02 bit/s/Hz/TRxP against the 11-company Type II average
  of 11.04; eType-II reaches 8.99 (81 %); see
  [`docs/benchmark-tr37910.md`](docs/benchmark-tr37910.md).
- **Next:** FTP traffic and load (P4), or further MU work (RZF, MU-CQI).

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

# MU-MIMO (RI <= 2, <= 4 UTs / 8 layers per RBG) and the SU vs MU figure
python examples/run_full_buffer.py --mu --max-rank 2 --tag p4_mu
python examples/plot_su_vs_mu.py

# LLS <-> SLS single-link regression sweep (the test is in the pytest suite)
python examples/lls_regression.py --jobs 4

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

`--jobs N` spreads drops over N spawned processes with single-threaded BLAS.
Results do not depend on N, because drop *i* always uses the random stream
`(seed, i)`.

## Layout

```
nrsls/
  config/scenario.py     ScenarioConfig, BS/UT antenna configs, presets
  topology/              hexagonal grid + wrap-around, InH hall, UT drop
  antenna/array.py       panel + TXRU virtualisation (element pattern from nrdlsim)
  propagation/           pathloss, LOS, O2I / in-car loss, LSPs, clusters/rays, H(f,t)
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
```
