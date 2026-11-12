FTP model 1, 20 MHz / 44 dBm, MMSE-IRC, OLLA warm + fast start, HARQ refill fix, 10 drops.  Before: one OLLA loop per UT and codeword, 8-slot HARQ round trip.  Fair baseline: one loop per transmission rank and codeword for every scheme (NR: one per rank) and a 4-slot round trip.  Gains vs NR compare a scheme with NR under the same setting; 'own UPT' compares a scheme with itself across the two settings (same drops and arrivals).

## Mean UPT gain over NR, fair baseline

Mean over the files of all 10 drops, with the standard error of the 10 single-drop gains (paired drops) after the ±.

| Precoding | Scheme | 20 % | 50 % | 70 % load | Single drops above zero |
|---|---|---|---|---|---|
| Sub-band SVD | LTE | +2.3 ± 0.5 % | +1.1 ± 0.5 % | +1.3 ± 0.5 % | 9 of 10 / 7 of 10 / 9 of 10 |
| Sub-band SVD | 1 CW per layer | +2.7 ± 0.5 % | +1.5 ± 0.6 % | +1.2 ± 0.4 % | 9 of 10 / 7 of 10 / 9 of 10 |
| Wideband SVD | LTE | +0.9 ± 0.4 % | +1.0 ± 0.3 % | +1.5 ± 0.6 % | 7 of 10 / 8 of 10 / 8 of 10 |
| Wideband SVD | 1 CW per layer | +0.7 ± 0.5 % | +1.6 ± 0.3 % | +1.1 ± 0.3 % | 8 of 10 / 9 of 10 / 9 of 10 |

NR's resource utilisation in the fair baseline (the arrival rates are those calibrated for 20 / 50 / 70 % with plain OLLA and an 8-slot round trip; NR is 4–6 % faster here): Sub-band SVD 18 / 43 / 65 %; Wideband SVD 17 / 44 / 65 %.

The fair-baseline runs used a buffer-estimate cap of 7.406 instead of 7.4 bit per RE and layer (see docs/qam1024-50mhz.md).  12 of them were repeated with 7.4: 7 were identical, the other 5 moved a run's mean UPT by −0.5 to +0.02 %.

### Sub-band SVD, 20 % load

| Scheme | Drops | BLER per CW [%]: before → fair | Gain vs NR, mean / p5 / p95 [%]: before → fair | Mean gain of the single drops, fair [%] | Own UPT, fair vs before, mean / p5 / p95 [%] | Mean rank |
|---|---|---|---|---|---|---|
| NR | 10 | 10.8 → 11.3 | — | — | +5.6 / +6.0 / +0.0 | 2.98 |
| LTE | 10 | 11.2 / 11.3 → 11.6 / 11.8 | +2.3 / −1.2 / −0.3 → +2.3 / +4.3 / −0.4 | −0.0 to +4.9 (9 of 10 above zero) | +5.6 / +11.8 / −0.0 | 3.15 |
| 1 CW per layer | 10 | 11.2 / 11.2 / 12.7 / 14.5 → 11.2 / 11.6 / 13.1 / 13.9 | +1.5 / +1.1 / −1.9 → +2.7 / +3.5 / −1.1 | −0.2 to +5.3 (9 of 10 above zero) | +6.8 / +8.5 / +0.8 | 3.11 |

### Sub-band SVD, 50 % load

| Scheme | Drops | BLER per CW [%]: before → fair | Gain vs NR, mean / p5 / p95 [%]: before → fair | Mean gain of the single drops, fair [%] | Own UPT, fair vs before, mean / p5 / p95 [%] | Mean rank |
|---|---|---|---|---|---|---|
| NR | 10 | 11.0 → 11.5 | — | — | +6.3 / +4.4 / +5.1 | 2.70 |
| LTE | 10 | 12.0 / 11.4 → 12.2 / 11.8 | +0.7 / +0.1 / −1.1 → +1.1 / +4.3 / +0.8 | −1.2 to +3.4 (7 of 10 above zero) | +6.7 / +8.8 / +7.1 | 2.82 |
| 1 CW per layer | 10 | 11.9 / 11.5 / 12.8 / 14.3 → 12.3 / 12.0 / 13.2 / 14.2 | +0.0 / −1.9 / −1.0 → +1.5 / +3.9 / +1.1 | −0.3 to +4.7 (7 of 10 above zero) | +7.9 / +10.7 / +7.3 | 2.80 |

### Sub-band SVD, 70 % load

| Scheme | Drops | BLER per CW [%]: before → fair | Gain vs NR, mean / p5 / p95 [%]: before → fair | Mean gain of the single drops, fair [%] | Own UPT, fair vs before, mean / p5 / p95 [%] | Mean rank |
|---|---|---|---|---|---|---|
| NR | 10 | 11.0 → 11.2 | — | — | +5.4 / +2.7 / +4.1 | 2.62 |
| LTE | 10 | 11.7 / 11.1 → 11.9 / 11.4 | +0.4 / −2.5 / +0.7 → +1.3 / +2.4 / +1.0 | −0.8 to +4.3 (9 of 10 above zero) | +6.3 / +7.9 / +4.4 | 2.69 |
| 1 CW per layer | 10 | 11.8 / 11.4 / 12.1 / 13.0 → 12.0 / 11.6 / 12.2 / 12.7 | −1.4 / −5.5 / −0.7 → +1.2 / −1.1 / +2.5 | −0.3 to +4.6 (9 of 10 above zero) | +8.1 / +7.5 / +7.5 | 2.68 |

### Wideband SVD, 20 % load

| Scheme | Drops | BLER per CW [%]: before → fair | Gain vs NR, mean / p5 / p95 [%]: before → fair | Mean gain of the single drops, fair [%] | Own UPT, fair vs before, mean / p5 / p95 [%] | Mean rank |
|---|---|---|---|---|---|---|
| NR | 10 | 10.5 → 11.0 | — | — | +4.4 / +5.7 / −1.2 | 2.86 |
| LTE | 10 | 10.5 / 11.1 → 10.9 / 11.5 | −0.1 / +1.5 / −2.7 → +0.9 / +1.3 / −0.8 | −1.1 to +3.2 (7 of 10 above zero) | +5.5 / +5.6 / +0.6 | 2.98 |
| 1 CW per layer | 10 | 10.4 / 10.8 / 12.5 / 15.0 → 10.8 / 11.1 / 12.8 / 14.7 | −1.0 / +2.4 / −5.9 → +0.7 / +3.4 / −3.4 | −2.7 to +2.7 (8 of 10 above zero) | +6.2 / +6.7 / +1.4 | 2.95 |

### Wideband SVD, 50 % load

| Scheme | Drops | BLER per CW [%]: before → fair | Gain vs NR, mean / p5 / p95 [%]: before → fair | Mean gain of the single drops, fair [%] | Own UPT, fair vs before, mean / p5 / p95 [%] | Mean rank |
|---|---|---|---|---|---|---|
| NR | 10 | 10.7 → 10.9 | — | — | +5.5 / +2.6 / +4.1 | 2.54 |
| LTE | 10 | 10.8 / 10.9 → 11.0 / 11.4 | +0.3 / −1.2 / +0.9 → +1.0 / +0.1 / +0.9 | −0.4 to +2.0 (8 of 10 above zero) | +6.2 / +4.0 / +4.1 | 2.60 |
| 1 CW per layer | 10 | 10.7 / 10.8 / 12.4 / 15.1 → 11.1 / 11.2 / 12.7 / 14.6 | −0.0 / −1.8 / −0.0 → +1.6 / +0.6 / +1.8 | −0.5 to +2.8 (9 of 10 above zero) | +7.2 / +5.1 / +6.0 | 2.57 |

### Wideband SVD, 70 % load

| Scheme | Drops | BLER per CW [%]: before → fair | Gain vs NR, mean / p5 / p95 [%]: before → fair | Mean gain of the single drops, fair [%] | Own UPT, fair vs before, mean / p5 / p95 [%] | Mean rank |
|---|---|---|---|---|---|---|
| NR | 10 | 10.7 → 10.9 | — | — | +4.6 / +4.6 / +1.1 | 2.45 |
| LTE | 10 | 10.9 / 10.9 → 11.1 / 11.2 | −0.3 / −1.6 / −1.0 → +1.5 / −1.1 / +2.3 | −1.6 to +4.3 (8 of 10 above zero) | +6.5 / +5.2 / +4.4 | 2.47 |
| 1 CW per layer | 10 | 10.9 / 10.9 / 12.0 / 13.9 → 11.0 / 11.0 / 12.1 / 14.3 | −1.1 / −2.3 / −0.6 → +1.1 / −1.5 / +2.9 | −0.6 to +2.7 (9 of 10 above zero) | +7.0 / +5.5 / +4.7 | 2.45 |

