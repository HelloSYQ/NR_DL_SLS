#!/usr/bin/env python3
"""Error propagation with the codeword-level SIC receiver.

Runs one drop of the rank <= 4 codeword-mapping study (see
``examples/cw2lm_rank4_eval.py``) and counts, over the first transmissions
of codewords 1, 2, ... after warm-up, how often they fail when an earlier
codeword of the same transmission failed, and when all earlier ones decoded.
It wraps the engine's ``decode_tb`` to see every decoding outcome.

    python examples/cw2lm_sic_error_propagation.py                    # ~10 min
    python examples/cw2lm_sic_error_propagation.py --variant sic-olla-cond \
        --scheme per_layer --case etype2_20ms
"""

from __future__ import annotations

import argparse
import os
import sys

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np                                                     # noqa: E402

from cw2lm_rank4_eval import VARIANTS, cases, fb_config                # noqa: E402
from nrsls.config.scenario import DU_A_MIXED_O2I, get_preset  # noqa: E402
from nrsls.engine import fullbuffer                                   # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="svd_2ms", choices=sorted(cases(1, 0)))
    ap.add_argument("--variant", default="sic-olla", choices=sorted(VARIANTS))
    ap.add_argument("--scheme", default="lte", choices=["lte", "per_layer"])
    ap.add_argument("--slots", type=int, default=200)
    ap.add_argument("--warmup", type=int, default=80)
    ap.add_argument("--drop", type=int, default=0)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()

    # decoding outcomes, grouped by transmission: the TBs of one
    # transmission are decoded one after another, in codeword order
    groups, last = [], {"tx": None, "cw": -1}
    decode = fullbuffer.decode_tb

    def traced(tb, *a, **k):
        first = tb["ntx"] == 0
        ok = decode(tb, *a, **k)
        if "tx" in tb:
            if tb["tx"] != last["tx"] or tb["cw"] <= last["cw"]:
                groups.append([])
            last.update(tx=tb["tx"], cw=tb["cw"])
            groups[-1].append((tb["cw"], ok, first, tb["due"]))
        return ok

    fullbuffer.decode_tb = traced
    r = fullbuffer.run_full_buffer_drop(
        get_preset("du-a", **DU_A_MIXED_O2I),     # as in the published study
        fb_config(args.case, args.variant, args.scheme, args.slots, args.warmup),
        np.random.default_rng([args.seed, args.drop]))

    counts = {"all earlier codewords decoded": [0, 0], "an earlier codeword failed": [0, 0]}
    for g in groups:
        failed = False
        for cw, ok, first, due in g:
            if cw > 0 and first and due >= args.warmup:
                c = counts["an earlier codeword failed" if failed else
                           "all earlier codewords decoded"]
                c[0] += 1
                c[1] += int(not ok)
            failed |= not ok
    print(f"{args.case} / {args.variant} / {args.scheme}, drop {args.drop}, "
          f"{args.slots} slots ({args.warmup} warm-up): cell SE {r.cell_se:.3f}, "
          f"first-tx BLER per codeword {[round(x, 3) for x in r.bler_first_cw]}")
    for k, (n, f) in counts.items():
        print(f"  codewords 1+, first transmission, {k}: {n} TBs, BLER "
              f"{f / max(n, 1):.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
