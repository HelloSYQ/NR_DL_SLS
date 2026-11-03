# Validation case: Dense Urban-eMBB A, 32×4 MU-MIMO, against TR 37.910

A self-contained system-level test with a fixed case definition, a published reference and pass/fail criteria. It checks the whole simulator end to end on one ITU-R evaluation case.

```bash
python examples/validate_du_a.py                          # ~27 min on 4 cores, exit 1 on failure
NRSLS_SLOW=1 python -m pytest tests/test_validation_du_a.py -s   # same, as a test
python -m pytest tests/test_validation_du_a.py            # fast part: case definition and criteria logic
```

The code is in `nrsls/validation/du_a.py`. The last report is in `results/validation_du_a.md` / `.json`.

## Case

| Item | Value |
|---|---|
| Test environment | ITU-R M.2412 Table 5b, Dense Urban-eMBB, evaluation configuration A (macro layer), full buffer |
| Layout | 19 sites × 3 TRxPs, ISD 200 m, wrap-around, BS 25 m |
| Carrier | 4 GHz, FDD, 10 MHz, 15 kHz SCS, 52 PRB; SE normalised by the 10 MHz channel bandwidth |
| Power / noise | 41 dBm per TRxP, UT noise figure 7 dB |
| gNB | (8,8,2,1,1;2,8): 32 TXRUs, element gain 8 dBi |
| UTs | 10 per TRxP, 4 ports. 80 % indoor (3 km/h; building loss of M.2412 channel model A at ≤ 6 GHz, 20 dB + 0.5 d2D-in), 20 % in car (30 km/h) |
| Channel | TR 38.901 UMa (channel model A); 8 strongest interferers explicit, the rest as wideband interference |
| CSI | RI ≤ 2, 4-PRB sub-bands, every 5 ms, 4 ms delay; **eType-II** combination 6 (under test) and **ideal sub-band CSI** (bound), on the same drops |
| MU-MIMO | greedy PF pairing per RBG, ≤ 6 UTs / 12 layers, regularised ZF on the reports, MU OLLA |
| Overhead | 2 PDCCH symbols, 2 DM-RS symbols, 9 REs/PRB/slot for CSI-RS, CSI-IM, TRS and SSB |
| Statistics | 2 drops × 200 slots (40 warm-up), 1140 UTs per report type, seed 1 |

## Reference

TR 37.910 Table 5.4.1.2.1-1(a): NR FDD, Dense Urban-eMBB configuration A, "32x4 MU-MIMO, Type II codebook, gNB Config = (8,8,2,1,1;2,8)", 15 kHz, channel model A, BW 10 MHz. The 11-company average is **11.04 bit/s/Hz/TRxP** average spectral efficiency and **0.37 bit/s/Hz** 5th-percentile user spectral efficiency. The ITU-R M.2410 requirement is 7.8 / 0.225.

## Acceptance criteria

| Check | Criterion | Why |
|---|---|---|
| V1 | eType-II average SE within ±15 % of 11.04 | agreement with the 3GPP companies |
| V2 | eType-II 5th-percentile SE within ±15 % of 0.37 | same, at the cell edge |
| V3 | ideal-CSI average SE ≥ 0.95 × 11.04 | an ideal-CSI bound below the companies' Type II result would mean a loss elsewhere in the chain (geometry, power, overhead, scheduler) |
| V4 | ideal CSI > eType-II, average and 5th percentile | better CSI must not perform worse |
| V5 | eType-II meets ITU-R M.2410 (≥ 7.8, ≥ 0.225) | the requirement the reference was produced for |
| V6 | first-transmission BLER within 0.07–0.13 | link adaptation holds its 10 % target |
| V7 | ≥ 2 co-scheduled UTs per RBG | the case exercises MU-MIMO |

The TR gives the company average only, without its spread or the companies' detailed assumptions. The ±15 % tolerance is about ±1 dB of SINR at these spectral efficiencies, which is the spread between companies in the RP-180524 calibration.

## Result (2026-11-03, commit with this file)

With the ITU-R M.2412 channel-model-A building loss (20 dB + 0.5 d2D-in), which `du-a` uses since 2026-11-03:

| Report | Average SE | 5th pct | Median | 1st-tx BLER | UTs / layers per RBG |
|---|---|---|---|---|---|
| eType-II | 10.00 | 0.348 | 0.848 | 0.099 | 5.69 / 11.26 |
| Ideal sub-band CSI | 12.89 | 0.416 | 1.108 | 0.092 | 5.79 / 11.53 |

| Check | Measured | Criterion | Result |
|---|---|---|---|
| V1 | 10.00 (−9.4 %) | 11.04 ± 15 % | PASS |
| V2 | 0.348 (−5.9 %) | 0.37 ± 15 % | PASS |
| V3 | 12.89 | ≥ 10.49 | PASS |
| V4 | 12.89 > 10.00, 0.416 > 0.348 | both | PASS |
| V5 | 10.00 / 0.348 | ≥ 7.8 / ≥ 0.225 | PASS |
| V6 | 0.099 / 0.092 | 0.07–0.13 | PASS |
| V7 | 5.69 / 5.79 | ≥ 2 | PASS |

**PASS, 7/7.**

**What the building-loss change did.** The previous result (2026-10-01) used the 20 % high-loss / 80 % low-loss mix, which belongs to channel model B:

| | Average SE, eType-II / ideal | 5th pct, eType-II / ideal | Median, eType-II / ideal |
|---|---|---|---|
| 20/80 mix (2026-10-01) | 9.77 / 12.59 | 0.358 / 0.445 | 0.823 / 1.049 |
| Channel model A (2026-11-03) | 10.00 / 12.89 | 0.348 / 0.416 | 0.848 / 1.108 |
| Change | +2.4 % / +2.4 % | −2.8 % / −6.7 % | +2.9 % / +5.6 % |

The model-A loss is higher on average, about 26 dB against about 17 dB for the low-loss buildings that made up 80 % of the mix. That costs the noise-limited deep-indoor UTs at the cell edge. The median and the average rise. The likely reason is that the model-A indoor distance is drawn per link instead of per UT, which spreads each UT's losses to its cells so more UTs find one clearly dominant cell; this was not isolated. BLER, MU set sizes and the MU-SINR estimate error are unchanged. The 4-drop run with the 20/80 mix ([benchmark-tr37910.md](benchmark-tr37910.md)) differed from 2 drops by less than 1 %.

**Margins.** V1 is still the tightest check: eType-II sits 9.4 % below the reference, inside the 15 % band. The companies' Type II result corresponds to 86 % of our ideal-CSI bound, and our eType-II reaches 78 % of it. A change that loses about 6 % of eType-II MU throughput would fail V1. V2 now has a 9-point margin (−5.9 %). That is intended, since this case is the regression guard for the MU / CSI chain.
