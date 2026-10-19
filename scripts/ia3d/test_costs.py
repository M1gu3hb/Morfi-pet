"""Write the model, costs (USD) and review changes of a published test performance (plain Python).

    python scripts/ia3d/test_costs.py --id opus --creation 1.20 --review 0.40 --publish 0.10 --changes 7 [--model "Claude Opus 5.5"]
    python scripts/ia3d/test_costs.py --id opus --show

Edits web/public/models/tests/<id>.json (made by export_test.py): "costs" {creation, review, publish, total}
and "changes" (the number of changes made in the review). The total is the sum of the three costs unless
--total is given; the lab shows "—" for what is still null. Re-publishing with export_test.py keeps these.
"""
import argparse
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
COSTS = ("creation", "review", "publish", "total")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--id", required=True, help="opus, sonnet, haiku1, haiku2, haiku3")
    ap.add_argument("--model", default=None)
    for k in COSTS:
        ap.add_argument(f"--{k}", type=float, default=None, help=f"USD ({k})")
    ap.add_argument("--changes", type=int, default=None, help="number of changes made in the review")
    ap.add_argument("--note", default=None, help="a short note shown on the card (Spanish); empty string removes it")
    ap.add_argument("--show", action="store_true", help="only print what the entry has")
    a = ap.parse_args(argv)
    path = os.path.join(REPO, "web", "public", "models", "tests", a.id + ".json")
    if not os.path.exists(path):
        sys.exit(f"ERROR: {path} does not exist: publish the performance first (export_test.py)")
    entry = json.load(open(path, encoding="utf-8"))
    costs = dict.fromkeys(COSTS)
    costs.update(entry.get("costs") or {})
    if not a.show:
        for k in COSTS:
            v = getattr(a, k)
            if v is not None:
                costs[k] = round(v, 4)
        if a.total is None and all(costs[k] is not None for k in COSTS[:3]):
            costs["total"] = round(sum(costs[k] for k in COSTS[:3]), 4)
        entry["costs"] = costs
        if a.changes is not None:
            entry["changes"] = a.changes
        if a.model is not None:
            entry["model"] = a.model
        if a.note is not None:
            entry["note"] = a.note.strip() or None
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(entry, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"{a.id}: model {entry.get('model')!r}, costs {costs}, changes {entry.get('changes')}, note {entry.get('note')!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
