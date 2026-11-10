# CW2L with ideal CSI for every transmission (FTP model 1, hand grip, MMSE-IRC)

With ideal CSI the network serves NR 16–25 % faster in mean UPT than with 20 ms CSI, but the codeword mappings still gain nothing over NR with MMSE-IRC.
- **LTE split:** −1.7 to +2.7 % mean UPT over NR.
- **One codeword per layer:** −3.6 to +0.4 % mean UPT, and −2.3 to −8.6 % at the 5th percentile.

This holds for the eType-II codebook and for sub-band SVD at 20 / 50 / 70 % RU. The tables are in [results/cw2lm_ftp1_grip_idealcsi_20mhz.md](../results/cw2lm_ftp1_grip_idealcsi_20mhz.md).

## How ideal CSI is modelled

The set-up is `20mhz-ftp1-grip-idealcsi`. Everything is as in the hand-grip set ([cw2lm-hand-grip.md](cw2lm-hand-grip.md)) except the CSI timing:
- **Common settings:** FTP model 1, 0.5 Mbyte files, 20 MHz / 44 dBm, the users' hand grip, MMSE-IRC, OLLA warm + fast start, the HARQ fix, synchronous HARQ, 10 drops.
- **A report every slot:** every UT in the system gets a fresh RI / PMI / CQI every 0.5 ms slot, usable in the next slot. That replaces a report every 20 ms that is 4 ms old when it arrives, and so 4–24 ms old when used.
- **What the report is computed on:** the channel and the interference of the slot it is made in. The channel is refreshed every slot instead of every 2 ms.
- **Precoder:** the eType-II PMI, or the unquantised sub-band SVD, is computed on that channel, so every transmission uses a precoder at most 0.5 ms old.
- **New UTs:** a new UT can be served 0.5 ms after it arrives instead of 4 ms.
- **OLLA:** it stays on. The interference still changes from one slot to the next as the other cells schedule, and the 0.5 ms age does not remove that.
- **Calibration:** the arrival rates were recalibrated for NR with ideal CSI. The calibration runs are 1500 slots, with 300 slots of warm-up, 7 rates and 2 drops.

The resulting arrival rates, in UTs/s per cell:

| Precoder | 20 % RU | 50 % RU | 70 % RU |
|---|---|---|---|
| eType-II | 8.88 | 16.26 | 20.47 |
| Sub-band SVD | 9.44 | 17.46 | 21.92 |
| Sub-band SVD with 20 ms CSI, for comparison | 7.46 | 14.46 | 18.96 |

## Results

Gains over NR [%], 5th-percentile / mean / 95th-percentile UPT:

| Precoder | Scheme | 20 % RU | 50 % RU | 70 % RU |
|---|---|---|---|---|
| eType-II | LTE split | −2.6 / −0.8 / −1.4 | +0.4 / −0.9 / −1.7 | −2.6 / −1.7 / −1.4 |
| eType-II | 1 CW per layer | −2.3 / −2.5 / −6.3 | −3.4 / −2.4 / −2.6 | −5.5 / −3.6 / −3.1 |
| Sub-band SVD | LTE split | −0.4 / +2.7 / −1.3 | −1.0 / +1.2 / −1.3 | −3.8 / +0.6 / +1.5 |
| Sub-band SVD | 1 CW per layer | −4.2 / +0.4 / −2.4 | −3.6 / −1.0 / −2.8 | −8.6 / −1.9 / +0.4 |

NR's UPT [Mbit/s], 5th-percentile / mean / 95th-percentile:

| Precoder | 20 % RU | 50 % RU | 70 % RU |
|---|---|---|---|
| eType-II | 58.6 / 147.3 / 271.1 | 26.2 / 94.2 / 201.9 | 14.1 / 64.9 / 164.7 |
| Sub-band SVD | 65.8 / 157.8 / 308.5 | 27.1 / 98.8 / 230.7 | 13.8 / 69.6 / 181.1 |

- **NR against 20 ms CSI:** with sub-band SVD, ideal CSI raises NR's mean UPT by 16–25 %, its 5th percentile by 7–38 % and its 95th by 20–27 %.
  - **Where it comes from:** better rank and MCS matching, fewer retransmissions, and the shorter wait before a new UT's first transmission.
- **The mappings' gains barely move:**
  - **LTE split, mean UPT:** +0.6 to +2.7 %, against +0.9 to +1.6 % with 20 ms CSI.
  - **One codeword per layer, mean UPT:** −1.9 to +0.4 %, against −0.1 to +1.3 %.
  - **One codeword per layer, 5th percentile:** it loses more, −3.6 to −8.6 % against −2.9 to +0.1 %.
- **Link adaptation is on target:** the first-transmission BLER is 9–12 % on every codeword, including the third and fourth codewords of one codeword per layer.
- **What does not limit MMSE-IRC multi-codeword:** the CSI is no longer stale, so CSI aging was not what kept MMSE-IRC multi-codeword level with NR.

## Limits

- **Interference timing:** the report sees the previous slot's interference, not the interference of the transmission itself, which depends on what every other cell schedules in that same slot. OLLA absorbs the difference.
- **No warm-up:** as in all FTP model 1 runs, the measured NR RU is 20 / 46–47 / 68–69 %.
- **Calibration run length:** the rates were calibrated with 1500-slot runs instead of 2300, to keep the heaviest runs within the cloud workers' 2-hour limit. CSI every slot costs 4–6 times the run time.

## Running it

```bash
python examples/cw2lm_ftp_eval.py --setup 20mhz-ftp1-grip-idealcsi --calibrate --cases etype2_ideal,svd_sb_ideal --cal-drops 2 --cal-slots 1500 --warmup 300 --cal-rates 5,8,11,14,17,20,23 --jobs 4 --log "$(ls results/ftp1_idealcsi_cal/*.jsonl | paste -sd,)"
```

```bash
python examples/cw2lm_ftp_eval.py --setup 20mhz-ftp1-grip-idealcsi --cases etype2_ideal,svd_sb_ideal --variants irc-fix-warmfast --schemes nr,lte,per_layer --drops 10 --slots 1000 --loads 20,50 --warmup 0 --drain 0 --jobs 4 --log results/ftp1_idealcsi/local.jsonl
```

The 70 % runs use `--loads 70 --slots 2000`. The logs in `results/ftp1_idealcsi/` came from 20 cloud workers plus local runs.

```bash
python examples/cw2lm_ftp_eval.py --setup 20mhz-ftp1-grip-idealcsi --summary-only --log "$(ls results/ftp1_idealcsi/*.jsonl | paste -sd,)" --summary-drain 1000:300,2000:1000
```

```bash
python examples/cw2lm_ftp1_idealcsi_report.py
```
