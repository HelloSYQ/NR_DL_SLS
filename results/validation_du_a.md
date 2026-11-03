Dense Urban-eMBB A, FDD 10 MHz, 32x4 MU-MIMO: 2 drops x 200 slots (40 warm-up), seed 1, 721 s

| Report | Average SE | 5th pct | Median | 1st-tx BLER | UTs / layers per RBG |
|---|---|---|---|---|---|
| etype2 | 10.00 | 0.348 | 0.848 | 0.099 | 5.69 / 11.26 |
| svd_sb | 12.89 | 0.416 | 1.108 | 0.092 | 5.79 / 11.53 |

Reference: 3GPP TR 37.910 Table 5.4.1.2.1-1(a): NR FDD, Dense Urban-eMBB config A, 32x4 MU-MIMO, Type II, (8,8,2,1,1;2,8), 15 kHz, channel model A, 10 MHz (11 companies): 11.04 / 0.37

| Check | Description | Measured | Criterion | Result |
|---|---|---|---|---|
| V1 | eType-II average SE vs TR 37.910 Type II | 10.00 (-9.4 %) | 11.04 ± 15 % | PASS |
| V2 | eType-II 5th-percentile SE vs TR 37.910 Type II | 0.348 (-5.9 %) | 0.37 ± 15 % | PASS |
| V3 | ideal-CSI bound not below the reference | 12.89 | >= 10.49 | PASS |
| V4 | ideal CSI > eType-II (average and 5th percentile) | 12.89 > 10.00, 0.416 > 0.348 | both | PASS |
| V5 | ITU-R M.2410 requirement with eType-II | 10.00 / 0.348 | >= 7.8 / >= 0.225 | PASS |
| V6 | first-transmission BLER (target 10 %) | 0.099 / 0.092 | 0.07 ... 0.13 | PASS |
| V7 | MU-MIMO exercised (co-scheduled UTs per RBG) | 5.69 / 5.79 | >= 2 | PASS |

**PASS** (7/7 checks)
