# Hand grip: UT self-blocking and per-antenna hand loss

`ScenarioConfig.ue_self_blocking` gives every UT a hand grip. It has two parts: the self-blocking of TR 38.901 §7.6.4.1, and, since 2026-11-11, an optional loss on the antennas the hand covers, which is not in TR 38.901. Both are off by default.

## Self-blocking (TR 38.901 §7.6.4.1, blockage model A)

- **Grip mode.** Each UT is held in portrait mode (one hand) or landscape mode (two hands), half and half (`self_blocking_landscape_ratio`).
- **Orientation.** Each UT has a random azimuth orientation, uniform over 360°, which also turns its array.
- **Blocked region**, in the UT's own coordinates (Table 7.6.4.1-1):

  | Mode | Azimuth centre | Azimuth span | Zenith centre | Zenith span |
  |---|---|---|---|---|
  | Portrait | 260° | 120° | 100° | 80° |
  | Landscape | 40° | 160° | 110° | 75° |

- **Loss.** A cluster whose centre arrival direction is in the region loses 30 dB (`self_blocking_db`), on all its rays and on every UT port alike. The LOS ray is tested on its own direction.
- **Where it acts.** On every channel matrix, serving and interfering, and on the port-0 RSRP, so on the choice of the serving cell too.

The loss is 30 dB or nothing for a cluster. What a UT loses follows from which of its clusters are hit: over the 10 evaluation drops, 2.4 dB on average and 1.1 dB at the median after it has picked its best cell (`results/cw2lm_ftp1_grip_drops.json`).

## Per-antenna hand loss (`hand_loss_db`)

The self-blocking attenuates a cluster equally on every UT port, so it cannot make one antenna weaker than another. A hand on a handset also covers some of its antennas.

- **Antennas.** Every UT port is one antenna of the handset (4 for the Dense Urban UT).
- **Covered antennas.** The hand covers `hand_covered_antennas[0]` antennas in portrait mode and `[1]` in landscape mode, 1 and 2 by default, picked at random per UT, every antenna equally likely.
- **Loss.** A covered antenna receives `hand_loss_db` less power from every cell and every direction: its row of every channel matrix is scaled, and so is the interference of the cells that are modelled as white noise. The receiver's thermal noise is not scaled, so the antenna's SNR drops by the loss.
- **Not affected.** Cell selection and the coupling gain are those of an uncovered antenna: the loss is the same toward every cell.
- **Random draws.** The covered antennas are drawn after the grip mode and orientation, from the grip's own random stream. A drop with the hand loss is the drop with the grip, with the covered antennas on top; with `hand_loss_db = 0` nothing changes.
- **Hand loss alone.** `self_blocking_db = 0` with `hand_loss_db > 0` gives the covered antennas without the angular blocking.

**The value is yours to choose.** `hand_loss_db` and the number of covered antennas are not from a specification or a measurement. The study set-up below uses 6 dB as a placeholder.

### Effect on the layer imbalance

Singular values of each UT's serving channel (4 × 32, mean in dB over frequency), two drops of the Dense Urban 20 MHz set-up, 2,280 UTs. Gap of layer k to layer 1, median (10th–90th percentile):

| Model | Layer 2 | Layer 3 | Layer 4 |
|---|---|---|---|
| Orientation only (nothing blocked) | 3.2 dB (1.3–5.0) | 8.4 dB (5.4–17.9) | 12.4 dB (8.6–22.3) |
| Hand loss 6 dB alone | 3.6 dB (2.0–5.9) | 9.7 dB (6.6–19.1) | 14.7 dB (11.2–24.8) |
| Self-blocking 30 dB | 3.4 dB (1.4–5.4) | 9.5 dB (5.8–18.9) | 13.7 dB (9.2–23.3) |
| Self-blocking + hand loss 3 dB | 3.6 dB (1.8–5.7) | 9.7 dB (6.2–19.3) | 14.3 dB (9.9–24.1) |
| Self-blocking + hand loss 6 dB | 3.9 dB (2.0–6.4) | 10.6 dB (7.0–20.2) | 16.0 dB (11.7–25.7) |
| Self-blocking + hand loss 10 dB | 4.0 dB (2.1–7.7) | 12.6 dB (7.4–22.1) | 19.2 dB (15.1–28.9) |

- **The hand loss falls on the weakest layer.** Per UT, 6 dB on the covered antennas widens the gap to layer 1 by 0.3 dB (layer 2), 1.2 dB (layer 3) and 2.3 dB (layer 4) at the median, and for layer 4 by more than 1 dB for nine UTs in ten.
- **It is the larger of the two effects on layer 4.** 6 dB on one or two antennas moves the median gap of layer 4 by 2.3 dB, the 30 dB self-blocking by 1.3 dB.
- **The self-blocking is uneven, the hand loss is not.** The self-blocking leaves most UTs alone and costs a fifth of them more than 3 dB on layers 3 and 4; the hand loss costs every UT with a covered antenna about the same.

### First look in the system

Set-up `20mhz-ftp1-grip-hand` of `examples/cw2lm_ftp_eval.py`: the grip set-up `20mhz-ftp1-grip` with `hand_loss_db = 6`, on the grip's arrival rates. Sub-band SVD, MMSE-IRC, OLLA warm + fast start, 20 % load, drops 0 and 1, files that arrived in the first 700 of 1000 slots (`results/ftp1_grip_hand/first-look.jsonl`). Two drops, not a result:

| | Self-blocking | Self-blocking + hand loss 6 dB |
|---|---|---|
| NR: mean UPT | 124.9 Mbit/s | 122.9 Mbit/s (−1.6 %) |
| NR: mean rank, rank-4 share | 2.94, 30 % | 2.90, 26 % |
| LTE style over NR, mean UPT (single drops) | +0.6 % (+0.8, +0.4) | +1.4 % (+1.2, +1.6) |
| 1 CW per layer over NR, mean UPT (single drops) | −0.8 % (−1.8, +0.1) | +0.4 % (+0.6, +0.2) |
| Rank-4 share, LTE style / 1 CW per layer | 41 / 36 % | 39 / 35 % |

NR gives up rank 4 for some users when the fourth layer is weaker; the multi-codeword schemes keep it, with a lower MCS on the weak codeword. On these two drops that is worth about a point of mean UPT to them.

## Final evaluation (2026-11-12)

Set-up `20mhz-ftp1-grip-hand-fair`: the grip with the 6 dB hand loss, the fair baseline (variant `irc-fix-warmfast-pr-rtt4`: one OLLA loop per rank and codeword for every scheme, 4-slot HARQ round trip), and arrival rates calibrated with NR in exactly this configuration (`--calibrate --cal-variant irc-fix-warmfast-pr-rtt4`, drops 0 and 1, 2300 slots: `results/cw2lm_ftp1_grip_hand_fair_rates_20mhz.json`). MMSE-IRC, 10 drops, 180 runs in `results/ftp1_final/`, summary in `results/cw2lm_ftp1_grip_hand_fair_20mhz.json`. The report is [`CW2L_FTP1_hand_grip_report.docx`](CW2L_FTP1_hand_grip_report.docx).

Mean UPT gain over NR, ± the standard error of the 10 single-drop gains, and the drops above zero:

| Precoding | Scheme | 20 % | 50 % | 70 % load |
|---|---|---|---|---|
| Sub-band SVD | LTE style | +2.0 ± 0.5 % (9 of 10) | +1.9 ± 0.3 % (10) | +2.3 ± 0.3 % (10) |
| Sub-band SVD | 1 CW per layer | +2.2 ± 0.6 % (9) | +2.0 ± 0.5 % (9) | +2.4 ± 0.3 % (10) |
| Wideband SVD | LTE style | +1.5 ± 0.4 % (10) | +1.5 ± 0.4 % (8) | +0.8 ± 0.4 % (7) |
| Wideband SVD | 1 CW per layer | +1.8 ± 0.5 % (9) | +1.9 ± 0.4 % (10) | +0.8 ± 0.3 % (8) |

- **Load.** NR's RU in these runs is 19 / 44–45 / 67 %: the 1000- and 2000-slot evaluation runs start from an empty system and land under the calibration's 20 / 50 / 70 %.
- **Against no grip** (`results/cw2lm_ftp1_fair_20mhz.md`, at 17–18 / 44 / 65 % RU): the gain is higher in 8 of the 12 cells and lower in 4, by +0.35 points on average. The grip with a 6 dB hand loss does not change the picture.

```bash
python examples/cw2lm_ftp_eval.py --setup 20mhz-ftp1-grip-hand-fair --summary-only \
    --log "$(ls results/ftp1_final/*.jsonl | paste -sd,)" --summary-drain 1000:300,2000:1000
python examples/cw2lm_final_report.py        # results/cw2lm_final/report_data.json, gain.png
node examples/cw2lm_final_report.js          # docs/CW2L_FTP1_hand_grip_report.docx (text: cw2lm_final_report_text.json)
```

## Running it

```bash
python -c "from nrsls import get_preset; print(get_preset('du-a', ue_self_blocking=True, hand_loss_db=6.0))"
python examples/run_full_buffer.py --preset du-a --self-blocking --codebooks svd --drops 1   # 38.901 grip only
python examples/cw2lm_ftp_eval.py --setup 20mhz-ftp1-grip-hand --cases svd_sb_20ms,svd_20ms \
    --variants irc-fix-warmfast --loads 20,50 --slots 1000 --warmup 0 --drain 0 --drops 10 \
    --log results/ftp1_grip_hand/runs.jsonl
```

`HAND_LOSS_DB` in the script sets the loss of the set-up. The arrival rates are those of the grip set-up; the hand loss raises NR's RU at 20 % load from 18.5 to 18.9 %.

## Limits

- **Hand loss.** One loss for every covered antenna, no dependence on frequency, no change of the antenna's pattern or polarisation, no correlation between the covered antennas and the blocked directions.
- **Antennas.** The UT array is two cross-polarised elements; each of its four ports is treated as an antenna of its own, as on a handset.
- **Self-blocking.** The 30 dB of TR 38.901, hard-edged, the same at every frequency.
- **Single-link harness.** The LLS regression (`engine/single_link.py`) has no grip.
