"""Retrieval benchmark: label resolution, review page, and (after approval) measurement.

    python -m eval.benchmark validate     # every label must match exactly one chunk
    python -m eval.benchmark review       # writes eval/retrieval_benchmark_review.md for a human reviewer
"""
import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from chunking import Chunk, chunk_resume  # noqa: E402

BENCHMARK = ROOT / "eval" / "retrieval_benchmark.json"
REVIEW = ROOT / "eval" / "retrieval_benchmark_review.md"


def squash(value: str) -> str:
    return " ".join(value.split())


def corpus_files() -> list[Path]:
    """Every resume in the benchmark corpus, as paths relative to sample_resumes/."""
    base = ROOT / "sample_resumes"
    return sorted(base.glob("*.txt")) + sorted(p for p in (base / "varied").glob("v*") if p.is_file())


def resume_key(path: Path) -> str:
    return path.relative_to(ROOT / "sample_resumes").as_posix()


@dataclass(frozen=True)
class LabelMatch:
    resume: str
    chunk_index: int
    chunk: Chunk


def load() -> dict:
    return json.loads(BENCHMARK.read_text(encoding="utf-8"))


def chunks_by_resume() -> dict[str, list[Chunk]]:
    return {resume_key(p): chunk_resume(p.read_text(encoding="utf-8")) for p in corpus_files()}


def resolve(label: dict, corpus: dict[str, list[Chunk]]) -> list[LabelMatch]:
    chunks = corpus.get(label["resume"])
    if chunks is None:
        return []
    needle = squash(label["contains"])
    return [LabelMatch(label["resume"], c.index, c) for c in chunks
            if c.section == label["section"] and needle in squash(c.text)]


def validate(benchmark: dict, corpus: dict[str, list[Chunk]]) -> list[str]:
    problems = []
    for q in benchmark["questions"]:
        seen = set()
        for label in q["relevant"]:
            matches = resolve(label, corpus)
            if len(matches) != 1:
                problems.append(f"{q['id']}: {label['resume']} [{label['section']}] '{label['contains']}' "
                                f"matched {len(matches)} chunks")
            for m in matches:
                if (m.resume, m.chunk_index) in seen:
                    problems.append(f"{q['id']}: duplicate label for {m.resume} chunk {m.chunk_index}")
                seen.add((m.resume, m.chunk_index))
    return problems


def review_page(benchmark: dict, corpus: dict[str, list[Chunk]]) -> str:
    lines = [
        "# Retrieval benchmark: labels for review",
        "",
        f"Status: **{benchmark['status']}**. {len(benchmark['questions'])} questions, "
        f"{sum(len(q['relevant']) for q in benchmark['questions'])} labelled chunks, "
        f"{len(benchmark['negative_questions'])} negative questions, over {len(corpus)} synthetic resumes.",
        "",
        "A label marks a chunk that directly evidences the answer. For each question, check that every listed "
        "chunk belongs, and that no chunk that should be listed is missing. Edit "
        "`eval/retrieval_benchmark.json`, then run `python -m eval.benchmark validate`.",
        "",
    ]
    for q in benchmark["questions"]:
        lines += [f"## {q['id']}. {q['question']}", "", f"*Rationale:* {q['rationale']}", ""]
        for label in q["relevant"]:
            for m in resolve(label, corpus):
                lines.append(f"- `{m.resume}` · {m.chunk.section} · chunk {m.chunk_index}")
                lines.append(f"  > {squash(m.chunk.text)}")
        lines.append("")
    lines += ["## Negative questions (no correct answer in the corpus)", ""]
    lines += [f"- **{n['id']}.** {n['question']} *{n['rationale']}*" for n in benchmark["negative_questions"]]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["validate", "review"])
    args = parser.parse_args(argv)
    benchmark, corpus = load(), chunks_by_resume()
    problems = validate(benchmark, corpus)
    for problem in problems:
        print("LABEL PROBLEM:", problem)
    if args.command == "review":
        REVIEW.write_text(review_page(benchmark, corpus), encoding="utf-8")
        print(f"wrote {REVIEW.relative_to(ROOT)}")
    if not problems:
        print(f"OK: {len(benchmark['questions'])} questions, every label matches exactly one chunk")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
