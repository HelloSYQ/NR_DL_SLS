# System-level probe for codeword-to-layer mapping

The simulator transmits one codeword per UT, as NR does up to rank 4 (Alt 1 of the RAN1 #126 agreement). `examples/cw2lm_sls_probe.py` runs it unchanged and measures, inside the running system, what more codewords could gain:

- Alt 2: one codeword for rank 1, two codewords for ranks 2–4.
- Alt 3: one codeword per layer.

This is the system-level counterpart of the link-level comparison of Nokia R1-2607066 and Apple R1-2608231 in nrdlsim: `docs/cw2lm-nokia.md` and `docs/cw2lm-apple.md` in HelloSYQ/Claude.

The simulator can now transmit the mappings end to end, with per-codeword CQI, OLLA and HARQ; that study is in [cw2lm-sls.md](cw2lm-sls.md).

```bash
python examples/cw2lm_sls_probe.py --drops 2 --slots 160 --warmup 40 --jobs 2   # ~37 min
```

## What it measures

1. **CSI-stage potential.** This is Apple's "aggregate expected TBS" check. At every CSI report, for each mapping, the probe takes the rank 1–4 that maximises Σ_CW TBS·(1 − BLER) at the per-codeword CQI MCS: the highest MCS with BLER ≤ 10 %. This is codeword-aware rank adaptation, and the probe sums the resulting expected bits. The CQI comes from MIESM over the codeword's layers, using the report's precoder and the whitened channel at the report. The same sum at fixed rank 4 is also kept.
2. **Per-layer SINR error.** For every first transmission, the probe takes the per-layer SINR the transmission actually gets: MMSE-IRC with the report's precoder on the current channel and interference. It subtracts the per-layer SINR the report predicted, both averaged in dB over the transmission's frequency points. Layer 1 is the strongest. A per-codeword MCS is chosen on the prediction, so this error is what each codeword's OLLA has to absorb.

## Case

Dense Urban-eMBB A preset:
- 19 sites × 3, ISD 200 m, 4 GHz, 10 MHz at 15 kHz.
- 32T (8,8,2;2,8), UT (1,2,2), 10 UTs per cell (570 UTs).
- 80 % indoor at 3 km/h, 20 % in car at 30 km/h.

SU-MIMO with up to 4 layers, full buffer, 2 drops × 160 slots with 40 slots of warm-up. Two CSI cases:

| Case | Codebook | CSI period / delay |
|---|---|---|
| `etype2_20ms` (Apple-like) | Rel-16 eType-II, combination 6 | 20 ms / 4 ms |
| `svd_2ms` (closer to Nokia's ideal precoding) | wideband SVD, unquantised | 2 ms / 0 |

## Results

| | eType-II, 20 ms / 4 ms | wideband SVD, 2 ms / 0 |
|---|---|---|
| cell SE (Alt 1, as simulated) | 4.60 bit/s/Hz | 5.06 bit/s/Hz |
| 1st-tx BLER (Alt 1) | 0.163 | 0.147 |
| CSI-stage gain, CW-aware RI, Alt 2 / Alt 3 | **+0.8 % / +1.2 %** | **+0.3 % / +0.5 %** |
| CSI-stage gain at fixed rank 4, Alt 2 / Alt 3 | +9.0 % / +9.7 % | +8.5 % / +9.0 % |
| reported rank 1 / 2 / 3 / 4 (Alt 3) | 1 / 72 / 24 / 4 % | 1 / 52 / 38 / 8 % |
| rank 2: per-layer SINR error mean / std (dB), layer 1 and layer 2 | −4.2 / 3.5, −2.6 / 3.5 | −2.7 / 3.3, −2.6 / 3.4 |
| rank 2: reported median SINR, layers 1 / 2 | 24.3 / 20.3 dB | 23.0 / 20.2 dB |
| rank 4: per-layer SINR error std (dB) | 4.0 / 3.9 / 4.0 / 4.1 | 3.2 / 3.2 / 3.3 / 3.2 |

Apple R1-2608231 reports a CSI-stage gain of +1.6 % for Alt 3 and +0.4 % for Alt 2 in its dense-urban SLS. The probe gives +1.2 % / +0.8 % with Apple-like CSI.

## Observations

- **The CSI-stage potential is about 1 % with rank adaptation, and about 9 % at fixed rank 4.** Rank adaptation decides the potential, not CSI quality: with the near-ideal wideband SVD it is even smaller (0.5 %), because better CSI makes the single codeword's rank choice better too.
- **Most reports are rank 2.** At rank 2 Alt 2 and Alt 3 are the same mapping. Alt 3 can only add something over Alt 2 at ranks 3–4, in 28–46 % of the reports.
- **Per-layer SINR predictions are off by 3–4 dB (standard deviation).** This holds even with CSI 2 ms old and unquantised. The interference changes from slot to slot, as the neighbours' PF decisions change their precoders. The error is as large as the gap between the two layers at rank 2, which is the imbalance a per-layer MCS is meant to exploit.
- **The mean error is negative, −2 to −4 dB.** The rank and precoder are chosen on the measured channel and interference, so the reported SINR is optimistically biased (selection bias). Channel ageing adds to this with eType-II at 20 ms. OLLA removes the mean of this error; its spread remains. A single codeword averages the spread over its layers, while each per-layer codeword sees it in full.
- **The first-transmission BLER of 15–16 % is above the 10 % target.** 120 measured slots with full-buffer interference is short for OLLA to settle. This affects the simulated Alt 1 throughput, not the probe's CSI-stage numbers.

## Limitations

- The system transmits one codeword. Alt 2 and Alt 3 are not simulated end to end with their own OLLA loops, HARQ and transport blocks. The probe gives their potential at the CSI stage and the error their link adaptation would face.
- There is no SIC or ML receiver in the system simulator: MMSE-IRC only.
- Full buffer is used, where Apple uses FTP 1 at 30–50 % load and Nokia FTP 3. Full buffer gives every cell the maximum interference variation.
