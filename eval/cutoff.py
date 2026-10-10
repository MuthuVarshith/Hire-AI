"""Recalibrate the "not found" similarity cutoff on the held-out set (eval/answer_eval_protocol.md, section 6).

    python -m eval.cutoff

Computes the top-1 similarity of the /api/ask retrieval for the 35 held-out questions, applies the
protocol's rule, and checks the result once on the benchmark test set. Writes a proposal to
eval/results/cutoff.json; ask.NOT_FOUND_THRESHOLD is changed only by a separate, reviewed commit.
No LLM is called and nothing leaves the machine.
"""
import argparse
import datetime
import json
import math
from collections.abc import Iterable
from itertools import pairwise
from typing import Any

from eval.benchmark import ROOT
from eval.benchmark import load as load_benchmark
from eval.evaluate import RESULTS_DIR, _git, refusals, retrieve
from eval.golden import load_heldout

CUTOFF_JSON = RESULTS_DIR / "cutoff.json"
MAX_ANSWERABLE_REFUSED = 1  # of the 20 held-out answerable questions (5%), protocol section 6
RULE = ("Maximise held-out unanswerable questions refused (top-1 < cutoff), refusing at most "
        f"{MAX_ANSWERABLE_REFUSED} held-out answerable question. Candidates are midpoints between consecutive "
        "distinct held-out top-1 values; ties go to the lowest. Rounded down to 3 decimals with counts rechecked. "
        "The current cutoff stays unless a candidate refuses more unanswerable questions within the limit.")


def refused(scores: Iterable[float], cutoff: float) -> int:
    return sum(1 for s in scores if s < cutoff)


def candidates(values: Iterable[float]) -> list[float]:
    distinct = sorted(set(values))
    return [(a + b) / 2 for a, b in pairwise(distinct)]


def _round_down(cutoff: float, answerable: list[float], unanswerable: list[float]) -> float:
    """The shortest rounding down (3, then 4 decimals) that refuses exactly the same questions."""
    for places in (3, 4):
        rounded = math.floor(cutoff * 10**places) / 10**places
        if (refused(answerable, rounded), refused(unanswerable, rounded)) == \
                (refused(answerable, cutoff), refused(unanswerable, cutoff)):
            return rounded
    return cutoff


def choose(answerable: list[float], unanswerable: list[float], current: float,
           max_refused: int = MAX_ANSWERABLE_REFUSED) -> dict[str, Any]:
    """Apply the protocol's rule. Returns the proposed cutoff and why."""
    feasible = [t for t in candidates(answerable + unanswerable) if refused(answerable, t) <= max_refused]
    best = max(feasible, key=lambda t: (refused(unanswerable, t), -t), default=None)
    current_ok = refused(answerable, current) <= max_refused
    if best is None or (current_ok and refused(unanswerable, best) <= refused(unanswerable, current)):
        reason = ("kept: no candidate within the limit refuses more held-out unanswerable questions than the "
                  "current cutoff" if current_ok else "kept: no candidate meets the limit")
        return {"proposed": current, "changed": False, "reason": reason}
    proposed = _round_down(best, answerable, unanswerable)
    return {"proposed": proposed, "changed": proposed != current,
            "reason": f"refuses {refused(unanswerable, proposed)} of {len(unanswerable)} held-out unanswerable "
                      f"and {refused(answerable, proposed)} of {len(answerable)} held-out answerable questions"}


def _scores(top1: dict[str, float | None]) -> list[float]:
    # Nothing retrieved is always refused: count it as similarity 0.
    return [s if s is not None else 0.0 for s in top1.values()]


def run() -> dict[str, Any]:
    import ask

    benchmark, heldout = load_benchmark(), load_heldout()
    held_a, held_u = heldout["answerable"], heldout["unanswerable"]
    test_a, test_n = benchmark["questions"], benchmark["negative_questions"]
    runs = retrieve(held_a + held_u + test_a + test_n)

    def top1(questions: list[dict[str, Any]]) -> dict[str, float | None]:
        return {q["id"]: runs[q["id"]]["top1"] for q in questions}

    current = ask.NOT_FOUND_THRESHOLD
    decision = choose(_scores(top1(held_a)), _scores(top1(held_u)), current)
    proposed = decision["proposed"]

    def at(cutoff: float) -> dict[str, Any]:
        return {"cutoff": cutoff,
                "heldout_answerable": refusals(top1(held_a), cutoff),
                "heldout_unanswerable": refusals(top1(held_u), cutoff)}

    def test_set(cutoff: float) -> dict[str, Any]:
        return {"cutoff": cutoff, "benchmark_answerable": refusals(top1(test_a), cutoff),
                "benchmark_negatives": refusals(top1(test_n), cutoff)}

    return {
        "generated_by": "python -m eval.cutoff",
        "protocol": "eval/answer_eval_protocol.md, section 6",
        "commit": _git("rev-parse", "--short", "HEAD"),
        "uncommitted_changes": bool(_git("status", "--porcelain")),
        "date": datetime.date.today().isoformat(),
        "rule": RULE,
        "max_answerable_refused": MAX_ANSWERABLE_REFUSED,
        "current_cutoff": current,
        "proposed_cutoff": proposed,
        "changed": decision["changed"],
        "reason": decision["reason"],
        "heldout_at_current": at(current),
        "heldout_at_proposed": at(proposed),
        # The test set is checked once, after the choice; it cannot change it.
        "test_set_at_current": test_set(current),
        "test_set_at_proposed": test_set(proposed),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.parse_args(argv)
    result = run()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    CUTOFF_JSON.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {CUTOFF_JSON.relative_to(ROOT)}: proposed cutoff {result['proposed_cutoff']} "
          f"({result['reason']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
