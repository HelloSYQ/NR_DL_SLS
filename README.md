# NR Downlink System-Level Simulator (`nrsls`)

A multi-cell, multi-UE NR downlink system-level simulator built on the
link-level simulator [`nrdlsim`](https://github.com/HelloSYQ/Claude). It
follows TR 38.901 (scenarios, propagation, calibration), TS 38.211/212/214
(numerology, MCS/TBS, CSI) and ITU-R M.2412 (KPIs).

- **Design:** [`docs/module-plan.md`](docs/module-plan.md)
- **Phase 1 (large-scale geometry):** implemented and verified. See
  [`docs/calibration-p1.md`](docs/calibration-p1.md).
- **Next:** phase 2 (TR 38.901 §7.5 fast fading), then phase 3 (full-buffer
  SU-MIMO with Type-I / eType-II CSI).

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

# tests
python -m pytest
```

| Preset | Scenario |
|---|---|
| `system` | UMa, 3.5 GHz, 100 MHz (273 PRB, 30 kHz), 53 dBm, 32T4R |
| `uma`, `umi`, `rma`, `inh-open`, `inh-mixed` | TR 38.901 §7.2 deployments |
| `calib-uma`, `calib-umi`, `calib-inh` | TR 38.901 Table 7.8-1-style large-scale calibration at 6 GHz |
| `rp-rural-700m`, `rp-rural-4g`, `rp-rural-lmlc`, `rp-mmtc-500m`, `rp-mmtc-1732m`, `rp-urllc-4g`, `rp-urllc-700m` | RP-180524 IMT-2020 calibration set-ups (reference data in `refs/rp180524/`) |

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
  propagation/           pathloss, LOS probability, O2I / in-car loss, SF fields
  link/                  noise, RSRP, geometry; serving-cell association
  engine/                one drop (drop.py), multi-drop driver (simulator.py)
  metrics/               CDFs, percentiles, reference-curve comparison
  plots/                 CDF plotting
run_sls.py               command-line runner
examples/                phase-1 figures
tests/                   pytest suite
```
