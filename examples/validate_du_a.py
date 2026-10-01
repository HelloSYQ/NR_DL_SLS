#!/usr/bin/env python3
"""Run the Dense Urban-eMBB A validation case (nrsls.validation.du_a) and
print the PASS/FAIL report.  Writes results/validation_du_a.json and .md.

    python examples/validate_du_a.py [--drops 2] [--slots 200] [--jobs 4]

Exit code 0 when all acceptance criteria pass, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nrsls.validation import du_a  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "results")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--drops", type=int, default=2)
    ap.add_argument("--slots", type=int, default=200)
    ap.add_argument("--warmup", type=int, default=40)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--jobs", type=int, default=4)
    args = ap.parse_args()

    r = du_a.run(args.drops, args.slots, args.warmup, args.seed, args.jobs)
    checks = du_a.evaluate(r)
    text = du_a.report(r, checks)
    print(text)
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "validation_du_a.json"), "w") as f:
        json.dump({"reference": du_a.REFERENCE, "results": r,
                   "checks": [c.__dict__ for c in checks]}, f, indent=1)
    with open(os.path.join(OUT, "validation_du_a.md"), "w") as f:
        f.write(text + "\n")
    return 0 if all(c.passed for c in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
