"""The live answers the evaluation uses (eval/answer_eval_protocol.md, sections 2 and 3).

Answers are never regenerated: they are read from the live batch files that eval/ask_live.py wrote
(eval/ask_live_batch1.json, eval/ask_live_batch2.json, ...). For each benchmark question the row
used is the first one with a generated answer, in batch-number order; a refusal by the similarity
floor is final, since it makes no LLM call; anything else counts as no generated answer.
"""
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eval.benchmark import ROOT
from eval.benchmark import load as load_benchmark

LIVE_DIR = ROOT / "eval"
LIVE_PATTERN = "ask_live_batch*.json"

# Outcome of a question's row (protocol section 3).
ANSWERED = "answered"                    # found and generated: the LLM wrote a cited answer
REFUSED_GROUNDING = "refused_grounding"  # the LLM said not found, or its answer had no valid citation
REFUSED_SIMILARITY = "refused_similarity"  # top-1 similarity under the cutoff: no LLM call
PASSAGES_ONLY = "passages_only"          # the LLM was unavailable; passages without a summary
NOT_RUN = "not_run"                      # no live row for this question yet
OUTCOMES = (ANSWERED, REFUSED_GROUNDING, REFUSED_SIMILARITY, PASSAGES_ONLY, NOT_RUN)


@dataclass(frozen=True)
class LiveAnswer:
    question_id: str
    kind: str                      # "positive" (answerable) or "negative"
    question: str
    outcome: str
    row: dict[str, Any] | None     # the live row used, None when not run
    file: str | None               # its batch file, relative to the repository
    commit: str | None             # the commit that batch file records
    model: str | None


def batch_number(path: Path) -> int:
    match = re.search(r"batch(\d+)", path.stem)
    return int(match.group(1)) if match else 0


def live_files(directory: Path = LIVE_DIR) -> list[Path]:
    return sorted(directory.glob(LIVE_PATTERN), key=batch_number)


def outcome(row: dict[str, Any]) -> str:
    if row.get("summary_unavailable") is True:
        return PASSAGES_ONLY
    if row.get("found") is True and row.get("generated") is True:
        return ANSWERED
    if row.get("found") is False and row.get("generated") is True:
        return REFUSED_GROUNDING
    if row.get("found") is False and row.get("generated") is False:
        return REFUSED_SIMILARITY
    return PASSAGES_ONLY


def benchmark_questions() -> list[tuple[str, str, str]]:
    """(id, kind, question) for the 30 answerable and 3 negative benchmark questions, in order."""
    data = load_benchmark()
    return ([(q["id"], "positive", q["question"]) for q in data["questions"]]
            + [(q["id"], "negative", q["question"]) for q in data["negative_questions"]])


def select_answers(files: list[Path] | None = None) -> list[LiveAnswer]:
    """One LiveAnswer per benchmark question, chosen by the protocol's rule."""
    files = live_files() if files is None else files
    loaded = [(path, json.loads(path.read_text(encoding="utf-8"))) for path in files]
    answers = []
    for qid, kind, question in benchmark_questions():
        seen: list[tuple[Path, dict[str, Any], dict[str, Any]]] = [
            (path, data, row) for path, data in loaded for row in data.get("results", []) if row.get("id") == qid]
        chosen = (next((s for s in seen if s[2].get("generated") is True), None)
                  or next((s for s in seen if outcome(s[2]) == REFUSED_SIMILARITY), None))
        if chosen is None:
            answers.append(LiveAnswer(qid, kind, question, PASSAGES_ONLY if seen else NOT_RUN, None,
                                      None, None, None))
            continue
        path, data, row = chosen
        answers.append(LiveAnswer(qid, kind, question, outcome(row), row,
                                  path.relative_to(ROOT).as_posix(), data.get("commit"), data.get("model")))
    return answers
