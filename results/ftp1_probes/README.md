# FTP model 1 probe runs, 2026-11-11

Short exploratory runs behind the question "what would give LTE style or one codeword per layer a stable 2-5 % UPT gain with MMSE-IRC". They are not a campaign: 2-3 drops per point, 107 runs in all. Set-up `20mhz-ftp1` of `examples/cw2lm_ftp_eval.py` (Dense Urban A, 20 MHz, 30 kHz, 44 dBm, 0.5 Mbyte files, arrival rates of `results/cw2lm_ftp1_rates_20mhz.json`), 1000 slots, no warm-up, seed 1, so each run pairs with the logged `irc-fix-warmfast` run of the same case, load and drop in `results/ftp1_warmfast/` (20 and 50 % load; the logged 70 % runs have 2000 slots and do not pair). Records have the format of the other logs, without the `commit` field; they were produced from commit 910a8b2.

Every probe variant is `irc-fix-warmfast` (OLLA fast start x4 for 20 ACK/NACKs, warm start from loops with >= 20) plus the overrides below, for NR and the multi-codeword schemes alike.

| File | Variant | `FullBufferConfig` overrides | Runs |
|---|---|---|---|
| `harq-rtt.jsonl` | `p-rtt1`, `p-rtt4` | `harq_rtt_slots` = 1, 4 | sub-band SVD at 20 / 50 % (3 drops), `p-rtt4` also at 70 % (2 drops) and wideband SVD at 20 % (3 drops) |
| | `p-rtt8` | none: the reference setting, run with 1000 slots at 70 % to pair with `p-rtt4` | sub-band SVD, 70 %, 2 drops |
| `per-rank-olla-rtt4.jsonl` | `p-pr-rtt4` | `olla_per_rank=True`, `harq_rtt_slots=4` | sub-band SVD, 20 % (3 drops), 50 % (2 drops) |
| `ideal-la.jsonl` | `p-ideal` | `ideal_la=True`, no OLLA start options | sub-band SVD, 20 / 50 %, 3 drops |
| `bler05.jsonl` | `p-bler05` | `target_bler=0.05` | sub-band SVD, 20 %, 3 drops |
| `file-2mbyte.jsonl` | `irc-fix-warmfast@x4` | `ftp_file_bytes=2e6`, a quarter of the arrival rate, 4000 slots | sub-band SVD, 20 %, NR and LTE, 2 drops |
| `sic-residual.jsonl` | `p-sic-r20`, `p-sic-r10` | `receiver='sic'` with 1 % / 10 % of a cancelled codeword's power left as interference | sub-band SVD, 20 %, LTE, 2 drops |

`sic-residual.jsonl` cannot be reproduced from the repository: the residual was a scratch patch to `sic_layer_sinr` and the CSI's SIC SINR (cancelled layers scaled by the square root of the residual instead of removed). Everything else uses repository code with the overrides above.

Mean UPT gain over NR run with the same setting, files that arrived in the first 700 slots (the 300-slot summary drain of the published tables), sub-band SVD unless noted:

| Setting | 20 %: LTE / 1 CW per layer | 50 %: LTE / 1 CW per layer | 70 %: LTE / 1 CW per layer |
|---|---|---|---|
| Reference, same drops | +2.2 / +1.5 | +1.1 / -0.2 | +1.4 / +0.4 |
| HARQ round trip 4 slots | +3.8 / +4.2 | +2.0 / +2.6 | +1.0 / +0.5 |
| HARQ round trip 1 slot | +4.4 / +4.3 | +2.5 / +3.2 | |
| Round trip 4 slots, per-rank OLLA for every scheme | +1.7 / +2.6 | +1.2 / +1.9 | |
| Ideal link adaptation | +0.7 / -1.2 | +2.0 / +0.3 | |
| BLER target 5 % | +4.2 / +3.6 | | |
| Round trip 4 slots, wideband SVD | +1.5 / +1.9 | | |

What the settings do to NR itself, against the reference NR: round trip 4 slots +2.1 / +2.4 % UPT (20 / 50 %), per-rank OLLA a further +3.3 / +3.5 %, ideal link adaptation +40 / +71 %, BLER target 5 % -2.7 % (20 %). With 2 Mbyte files LTE style gains +0.9 % at 20 % load, against +3.7 % with 0.5 Mbyte files on the same two drops. LTE style with SIC at 20 % load: +5.1 % with a 1 % residual, +4.0 % with 10 %, +11.9 % with ideal cancellation on the same two drops.
