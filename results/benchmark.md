# nrsls benchmark scorecard: WARN

Commit `c5284f8`, 2026-11-03. Tier 1: 20 drops per configuration, seed 1. See [docs/benchmark-suite.md](../docs/benchmark-suite.md) for the method.

## Tier 1: large-scale calibration against RP-180524 (peer test)

Deviation = mean |gap| to the consensus over the 5th-95th percentiles [dB]. Companies: the same for each company against the mean of the others (median / 80th percentile / max). Rank among the n + 1 participants (1 = closest to the consensus). Env. = share of the percentiles inside the companies' min-max envelope.

| Configuration | Metric | nrsls deviation | Companies (median / p80 / max) | Rank | Env. | Largest gap | Verdict |
|---|---|---|---|---|---|---|---|
| rural-700m | Coupling gain | 1.04 | 0.62 / 1.05 / 1.88 | 14 / 19 | 84 % | +1.4 dB | **PASS** |
| rural-700m | DL geometry | 0.30 | 0.38 / 0.55 / 0.78 | 8 / 19 | 100 % | −0.6 dB | **PASS** |
| rural-4g | Coupling gain | 0.47 | 0.63 / 1.08 / 1.75 | 6 / 19 | 100 % | −1.3 dB | **PASS** |
| rural-4g | DL geometry | 0.31 | 0.42 / 0.64 / 1.14 | 7 / 19 | 95 % | −0.6 dB | **PASS** |
| rural-lmlc | Coupling gain | 0.44 | 0.65 / 1.14 / 2.15 | 8 / 16 | 100 % | −1.2 dB | **PASS** |
| rural-lmlc | DL geometry | 0.27 | 0.42 / 0.58 / 0.89 | 3 / 16 | 100 % | −0.6 dB | **PASS** |
| umammtc-500m | Coupling gain | 0.32 | 0.86 / 1.63 / 3.79 | 2 / 16 | 100 % | −0.7 dB | **PASS** |
| umammtc-500m | DL geometry | 0.09 | 0.27 / 0.43 / 0.84 | 2 / 16 | 100 % | −0.2 dB | **PASS** |
| umammtc-1732m | Coupling gain | 0.28 | 0.94 / 1.36 / 2.52 | 1 / 16 | 100 % | −0.8 dB | **PASS** |
| umammtc-1732m | DL geometry | 0.15 | 0.32 / 0.42 / 0.97 | 3 / 16 | 100 % | −0.3 dB | **PASS** |
| umaurllc-4g | Coupling gain | 0.35 | 0.63 / 0.93 / 1.43 | 5 / 16 | 95 % | +0.7 dB | **PASS** |
| umaurllc-4g | DL geometry | 0.54 | 0.36 / 0.61 / 0.77 | 11 / 16 | 79 % | −0.9 dB | **WARN** |
| umaurllc-700m | Coupling gain | 0.34 | 0.55 / 1.08 / 2.21 | 3 / 16 | 100 % | +0.8 dB | **PASS** |
| umaurllc-700m | DL geometry | 0.52 | 0.32 / 0.49 / 0.84 | 13 / 16 | 95 % | −0.8 dB | **WARN** |
| inh-12trxp | Coupling gain | 0.22 | 0.36 / 0.59 / 0.70 | 4 / 17 | 100 % | +0.5 dB | **PASS** |
| inh-12trxp | DL geometry | 0.21 | 0.39 / 0.48 / 0.70 | 3 / 17 | 100 % | +0.3 dB | **PASS** |
| inh-36trxp | Coupling gain | 0.06 | 0.25 / 0.64 / 0.89 | 1 / 16 | 100 % | +0.2 dB | **PASS** |
| inh-36trxp | DL geometry | 0.26 | 0.17 / 0.38 / 0.70 | 11 / 16 | 100 % | −0.8 dB | **PASS** |
| du-4g | Coupling gain | 0.23 | 0.55 / 0.96 / 2.08 | 2 / 17 | 100 % | +0.6 dB | **PASS** |
| du-4g | DL geometry | 0.71 | 0.66 / 0.98 / 1.32 | 10 / 17 | 100 % | −1.0 dB | **PASS** |
| du-4g-o2i-mixed (sensitivity) | Coupling gain | 4.71 | 0.55 / 0.96 / 2.08 | 17 / 17 | 0 % | +5.9 dB | **FAIL** |
| du-4g-o2i-mixed (sensitivity) | DL geometry | 0.80 | 0.66 / 0.98 / 1.32 | 10 / 17 | 84 % | −1.1 dB | **PASS** |

Gap to the company mean at the 5 / 10 / 20 / 50 / 80 / 90 / 95th percentiles [dB]:

| Configuration | Coupling gain | Geometry |
|---|---|---|
| rural-700m | −0.2 +0.6 +0.9 +1.1 +1.3 +1.1 +1.4 | −0.3 −0.1 −0.2 −0.4 −0.4 −0.2 +0.1 |
| rural-4g | −1.3 −0.9 −0.7 −0.2 +0.1 +0.2 +0.7 | −0.6 −0.4 −0.3 −0.4 −0.1 −0.1 +0.1 |
| rural-lmlc | −1.2 −0.4 +0.2 +0.5 +0.5 +0.2 −0.3 | −0.6 −0.5 −0.2 −0.1 −0.2 −0.3 +0.0 |
| umammtc-500m | −0.1 −0.4 −0.3 −0.1 −0.4 +0.1 −0.2 | −0.2 −0.1 −0.0 −0.1 +0.0 −0.2 +0.1 |
| umammtc-1732m | +0.5 +0.2 −0.1 −0.1 −0.3 −0.5 −0.8 | −0.2 −0.3 −0.2 −0.2 −0.1 −0.2 −0.2 |
| umaurllc-4g | −0.5 +0.3 +0.3 +0.2 +0.6 +0.7 +0.7 | −0.2 −0.3 −0.3 −0.6 −0.6 −0.9 −0.6 |
| umaurllc-700m | −0.4 −0.1 +0.3 +0.3 +0.4 +0.7 +0.3 | −0.4 −0.3 −0.3 −0.5 −0.6 −0.8 −0.5 |
| inh-12trxp | +0.4 +0.5 +0.3 +0.2 −0.0 +0.1 −0.2 | +0.2 +0.2 +0.3 +0.2 −0.2 −0.3 −0.3 |
| inh-36trxp | +0.1 +0.2 +0.1 −0.0 +0.0 −0.1 +0.2 | +0.1 +0.1 −0.1 −0.1 −0.4 −0.6 −0.8 |
| du-4g | +0.6 +0.5 +0.1 −0.2 −0.0 +0.3 −0.2 | −0.5 −0.7 −0.9 −0.9 −0.5 −0.3 −0.3 |
| du-4g-o2i-mixed | +1.3 +2.8 +4.1 +5.5 +5.3 +4.5 +3.7 | −0.8 −0.9 −1.0 −1.0 −0.6 −0.3 −0.4 |

- **du-4g**: analog-beam calibration (best of 12 DFT beams; random beams for interferers); legacy O2I for channel model A.
- **du-4g-o2i-mixed**: sensitivity: the 20 % high / 80 % low-loss building mix du-a used before 2026-11-03 (and the CW2L studies still pin).

## Tier 2: end-to-end spectral efficiency against TR 37.910

Dense Urban-eMBB config A, 32x4 MU-MIMO, eType-II and ideal CSI (cached results/validation_du_a.json (2026-11-03)): **PASS**.

| Check | Measured | Criterion | Result |
|---|---|---|---|
| V1 eType-II average SE vs TR 37.910 Type II | 10.00 (-9.4 %) | 11.04 ± 15 % | PASS |
| V2 eType-II 5th-percentile SE vs TR 37.910 Type II | 0.348 (-5.9 %) | 0.37 ± 15 % | PASS |
| V3 ideal-CSI bound not below the reference | 12.89 | >= 10.49 | PASS |
| V4 ideal CSI > eType-II (average and 5th percentile) | 12.89 > 10.00, 0.416 > 0.348 | both | PASS |
| V5 ITU-R M.2410 requirement with eType-II | 10.00 / 0.348 | >= 7.8 / >= 0.225 | PASS |
| V6 first-transmission BLER (target 10 %) | 0.099 / 0.092 | 0.07 ... 0.13 | PASS |
| V7 MU-MIMO exercised (co-scheduled UTs per RBG) | 5.69 / 5.79 | >= 2 | PASS |
