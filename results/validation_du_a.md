Dense Urban-eMBB A, FDD 10 MHz, 32x4 MU-MIMO: 2 drops x 200 slots (40 warm-up), seed 1, 1597 s

| Report | Average SE | 5th pct | Median | 1st-tx BLER | UTs / layers per RBG |
|---|---|---|---|---|---|
| etype2 | 9.77 | 0.358 | 0.823 | 0.099 | 5.65 / 11.17 |
| svd_sb | 12.59 | 0.445 | 1.049 | 0.094 | 5.77 / 11.50 |

Reference: 3GPP TR 37.910 Table 5.4.1.2.1-1(a): NR FDD, Dense Urban-eMBB config A, 32x4 MU-MIMO, Type II, (8,8,2,1,1;2,8), 15 kHz, channel model A, 10 MHz (11 companies): 11.04 / 0.37

| Check | Description | Measured | Criterion | Result |
|---|---|---|---|---|
| V1 | eType-II average SE vs TR 37.910 Type II | 9.77 (-11.5 %) | 11.04 ± 15 % | PASS |
| V2 | eType-II 5th-percentile SE vs TR 37.910 Type II | 0.358 (-3.2 %) | 0.37 ± 15 % | PASS |
| V3 | ideal-CSI bound not below the reference | 12.59 | >= 10.49 | PASS |
| V4 | ideal CSI > eType-II (average and 5th percentile) | 12.59 > 9.77, 0.445 > 0.358 | both | PASS |
| V5 | ITU-R M.2410 requirement with eType-II | 9.77 / 0.358 | >= 7.8 / >= 0.225 | PASS |
| V6 | first-transmission BLER (target 10 %) | 0.099 / 0.094 | 0.07 ... 0.13 | PASS |
| V7 | MU-MIMO exercised (co-scheduled UTs per RBG) | 5.65 / 5.77 | >= 2 | PASS |

**PASS** (7/7 checks)
