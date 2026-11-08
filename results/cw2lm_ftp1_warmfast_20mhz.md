FTP model 1, 20 MHz / 44 dBm, MMSE-IRC + OLLA + HARQ fix, 10 drops.  Published: plain OLLA (loops start at 0 dB).  Warm + fast: a new UT's loops start from the mean of the loops with >= 20 ACK/NACKs and move x4 for their first 20 ACK/NACKs (NR too).  Gains vs NR compare each scheme with NR under the same link adaptation; 'own UPT' compares a scheme with itself across the two (same drops and arrivals).  Retx share: RBGs of retransmissions.

### svd_sb_20ms, 20 % load

| Scheme | Drops | BLER per CW [%]: published → warm + fast | Retx share (RBGs) | Gain vs NR, mean / p5 / p95 [%]: published → warm + fast | Own UPT, warm + fast vs published, mean / p5 / p95 [%] |
|---|---|---|---|---|---|
| NR | 10 of 10 | 13.3 → 10.8 | 3.3 → 2.6 % | — | +0.6 / +6.4 / −0.1 |
| LTE | 10 of 10 | 13.6 / 14.4 → 11.2 / 11.3 | 4.5 → 3.6 % | +1.9 / +4.1 / −0.1 → +2.3 / −1.2 / −0.3 | +0.9 / +1.0 / −0.3 |
| Twisted LTE | 10 of 10 | 12.6 / 13.7 → 11.0 / 10.9 | 4.3 → 3.6 % | +1.3 / +3.8 / +0.2 → +2.1 / +0.6 / −0.1 | +1.3 / +3.1 / −0.3 |
| 1 CW per layer | 10 of 10 | 13.2 / 13.7 / 17.5 / 21.0 → 11.2 / 11.2 / 12.7 / 14.5 | 5.4 → 4.5 % | +1.1 / +4.0 / −0.4 → +1.5 / +1.1 / −1.9 | +1.0 / +3.5 / −1.6 |

### svd_sb_20ms, 50 % load

| Scheme | Drops | BLER per CW [%]: published → warm + fast | Retx share (RBGs) | Gain vs NR, mean / p5 / p95 [%]: published → warm + fast | Own UPT, warm + fast vs published, mean / p5 / p95 [%] |
|---|---|---|---|---|---|
| NR | 10 of 10 | 13.5 → 11.0 | 7.0 → 5.4 % | — | +1.3 / +0.5 / +0.9 |
| LTE | 10 of 10 | 15.4 / 13.8 → 12.0 / 11.4 | 10.9 → 8.4 % | +0.0 / −0.9 / +1.1 → +0.7 / +0.1 / −1.1 | +2.0 / +1.5 / −1.3 |
| Twisted LTE | 10 of 10 | 14.7 / 13.4 → 11.9 / 11.2 | 10.6 → 8.3 % | +0.4 / −1.6 / −0.3 → +0.7 / +0.2 / +0.1 | +1.6 / +2.3 / +1.3 |
| 1 CW per layer | 10 of 10 | 15.3 / 14.2 / 17.1 / 21.0 → 11.9 / 11.5 / 12.8 / 14.3 | 13.0 → 10.1 % | −0.6 / −4.1 / −1.6 → +0.0 / −1.9 / −1.0 | +1.9 / +2.8 / +1.5 |

### svd_sb_20ms, 70 % load

| Scheme | Drops | BLER per CW [%]: published → warm + fast | Retx share (RBGs) | Gain vs NR, mean / p5 / p95 [%]: published → warm + fast | Own UPT, warm + fast vs published, mean / p5 / p95 [%] |
|---|---|---|---|---|---|
| NR | 10 of 10 | 12.8 → 11.0 | 8.8 → 6.9 % | — | +0.3 / +0.4 / −1.1 |
| LTE | 10 of 10 | 14.3 / 12.7 → 11.7 / 11.1 | 14.6 → 11.3 % | −1.4 / −4.9 / −2.1 → +0.4 / −2.5 / +0.7 | +2.2 / +3.0 / +1.7 |
| Twisted LTE | 10 of 10 | 14.1 / 12.6 → 11.7 / 11.0 | 14.4 → 11.3 % | −0.6 / −3.2 / −2.3 → −0.2 / −1.5 / −0.4 | +0.8 / +2.2 / +0.9 |
| 1 CW per layer | 10 of 10 | 14.3 / 13.2 / 15.2 / 18.2 → 11.8 / 11.4 / 12.1 / 13.0 | 17.7 → 13.8 % | −3.0 / −6.4 / −2.4 → −1.4 / −5.5 / −0.7 | +2.0 / +1.4 / +0.6 |

### svd_20ms, 20 % load

| Scheme | Drops | BLER per CW [%]: published → warm + fast | Retx share (RBGs) | Gain vs NR, mean / p5 / p95 [%]: published → warm + fast | Own UPT, warm + fast vs published, mean / p5 / p95 [%] |
|---|---|---|---|---|---|
| NR | 10 of 10 | 12.0 → 10.5 | 2.8 → 2.3 % | — | +0.1 / +3.3 / +0.3 |
| LTE | 10 of 10 | 11.6 / 13.7 → 10.5 / 11.1 | 3.9 → 3.4 % | −0.2 / +4.5 / −2.7 → −0.1 / +1.5 / −2.7 | +0.2 / +0.3 / +0.3 |
| Twisted LTE | 10 of 10 | 11.0 / 12.8 → 10.3 / 10.8 | 3.7 → 3.3 % | −0.6 / +0.7 / −0.8 → −0.6 / +1.2 / −2.1 | +0.1 / +3.8 / −1.0 |
| 1 CW per layer | 10 of 10 | 11.3 / 12.1 / 16.9 / 22.8 → 10.4 / 10.8 / 12.5 / 15.0 | 4.7 → 4.1 % | −1.1 / +3.2 / −4.8 → −1.0 / +2.4 / −5.9 | +0.2 / +2.5 / −0.9 |

### svd_20ms, 50 % load

| Scheme | Drops | BLER per CW [%]: published → warm + fast | Retx share (RBGs) | Gain vs NR, mean / p5 / p95 [%]: published → warm + fast | Own UPT, warm + fast vs published, mean / p5 / p95 [%] |
|---|---|---|---|---|---|
| NR | 10 of 10 | 12.2 → 10.7 | 6.2 → 5.1 % | — | +0.7 / +1.6 / +0.3 |
| LTE | 10 of 10 | 12.5 / 12.9 → 10.8 / 10.9 | 9.3 → 7.8 % | +0.1 / −1.0 / +1.3 → +0.3 / −1.2 / +0.9 | +0.9 / +1.5 / −0.1 |
| Twisted LTE | 10 of 10 | 12.1 / 12.5 → 10.7 / 10.7 | 9.0 → 7.7 % | +0.7 / −0.2 / +1.0 → +0.2 / −1.3 / −0.5 | +0.1 / +0.6 / −1.2 |
| 1 CW per layer | 10 of 10 | 12.5 / 12.6 / 16.9 / 24.6 → 10.7 / 10.8 / 12.4 / 15.1 | 10.9 → 9.1 % | −0.0 / −1.5 / −0.8 → −0.0 / −1.8 / −0.0 | +0.7 / +1.3 / +1.1 |

### svd_20ms, 70 % load

| Scheme | Drops | BLER per CW [%]: published → warm + fast | Retx share (RBGs) | Gain vs NR, mean / p5 / p95 [%]: published → warm + fast | Own UPT, warm + fast vs published, mean / p5 / p95 [%] |
|---|---|---|---|---|---|
| NR | 10 of 10 | 11.9 → 10.7 | 8.0 → 6.8 % | — | −0.0 / −0.0 / +0.0 |
| LTE | 10 of 10 | 12.2 / 12.3 → 10.9 / 10.9 | 12.8 → 10.9 % | −0.7 / −1.2 / −0.8 → −0.3 / −1.6 / −1.0 | +0.4 / −0.5 / −0.1 |
| Twisted LTE | 10 of 10 | 12.0 / 12.1 → 10.8 / 10.8 | 12.6 → 10.8 % | −0.6 / −3.1 / −0.1 → +0.1 / −1.9 / −1.0 | +0.7 / +1.2 / −0.9 |
| 1 CW per layer | 10 of 10 | 12.2 / 12.2 / 15.7 / 23.3 → 10.9 / 10.9 / 12.0 / 13.9 | 15.0 → 12.6 % | −1.2 / −3.9 / −0.5 → −1.1 / −2.3 / −0.6 | +0.1 / +1.7 / −0.1 |

## Codeword-level SIC with warm + fast OLLA

No plain-OLLA SIC run under FTP model 1 to compare with; the gains are against NR with MMSE-IRC and the same warm + fast OLLA.

| Case | Load | Scheme | Drops | BLER per CW [%] | Retx share (RBGs) | Gain vs NR, mean / p5 / p95 [%] | Mean rank |
|---|---|---|---|---|---|---|---|
| svd_sb_20ms | 20 % | LTE | 10 | 11.4 / 11.0 | 2.7 % | +10.3 / +10.1 / +1.2 | 3.46 |
| svd_sb_20ms | 20 % | 1 CW per layer | 10 | 11.1 / 11.5 / 11.4 / 11.5 | 3.2 % | +12.4 / +9.8 / +1.3 | 3.63 |
| svd_sb_20ms | 50 % | LTE | 10 | 11.9 / 11.1 | 6.5 % | +9.6 / +11.7 / +11.9 | 3.16 |
| svd_sb_20ms | 50 % | 1 CW per layer | 10 | 12.1 / 11.8 / 11.7 / 11.8 | 7.7 % | +11.3 / +9.2 / +12.1 | 3.36 |
| svd_sb_20ms | 70 % | LTE | 10 | 11.8 / 11.0 | 9.0 % | +10.0 / +6.7 / +8.6 | 3.02 |
| svd_sb_20ms | 70 % | 1 CW per layer | 10 | 11.8 / 11.5 / 11.3 / 11.4 | 10.7 % | +12.1 / +7.8 / +12.9 | 3.22 |
| svd_20ms | 20 % | LTE | 10 | 10.6 / 11.2 | 2.5 % | +8.3 / +7.0 / +1.1 | 3.40 |
| svd_20ms | 20 % | 1 CW per layer | 10 | 10.5 / 10.7 / 11.5 / 12.2 | 2.8 % | +11.8 / +7.8 / +1.2 | 3.68 |
| svd_20ms | 50 % | LTE | 10 | 10.8 / 11.0 | 6.0 % | +9.3 / +5.8 / +11.9 | 3.07 |
| svd_20ms | 50 % | 1 CW per layer | 10 | 10.8 / 10.9 / 11.5 / 12.2 | 6.9 % | +11.0 / +4.3 / +13.9 | 3.41 |
| svd_20ms | 70 % | LTE | 10 | 10.9 / 10.9 | 8.6 % | +8.3 / +5.5 / +6.1 | 2.93 |
| svd_20ms | 70 % | 1 CW per layer | 10 | 10.9 / 10.9 / 11.1 / 11.6 | 10.0 % | +10.2 / +4.2 / +9.1 | 3.27 |

