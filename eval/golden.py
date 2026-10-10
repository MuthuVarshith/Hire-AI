"""Golden answers for the benchmark questions: validation and a review page.

    python -m eval.golden validate     # every key fact resolves to exactly one labelled chunk
    python -m eval.golden review       # writes eval/golden_review.md for a human reviewer

Key facts are located the way benchmark labels are (eval/benchmark.py): resume file, section, and a
quote the chunk must contain, compared with whitespace squashed.
"""
import argparse
import json
from typing import Any

from chunking import Chunk
from eval.benchmark import ROOT, chunks_by_resume, resolve, squash
from eval.benchmark import load as load_benchmark

GOLDEN = ROOT / "eval" / "golden.json"
GOLDEN_REVIEW = ROOT / "eval" / "golden_review.md"
NOT_FOUND = "Not found in resumes."


def load_golden() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(GOLDEN.read_text(encoding="utf-8"))
    return data


def resume_text(chunks: list[Chunk]) -> str:
    """The resume's text, squashed and lowercased, for name checks."""
    return squash(" ".join(c.text for c in chunks)).lower()


def labelled_chunks(question: dict[str, Any], corpus: dict[str, list[Chunk]]) -> set[tuple[str, int]]:
    """(resume, chunk index) of every chunk a benchmark question labels."""
    return {(m.resume, m.chunk_index) for label in question["relevant"] for m in resolve(label, corpus)}


def validate_golden(golden: dict[str, Any], benchmark: dict[str, Any], corpus: dict[str, list[Chunk]]) -> list[str]:
    problems: list[str] = []
    bench = {q["id"]: q for q in benchmark["questions"]}
    ids = [q["id"] for q in golden["questions"]]
    if sorted(ids) != sorted(bench) or len(ids) != len(set(ids)):
        problems.append(f"golden questions {ids} do not match the benchmark's {sorted(bench)} one to one")
    fact_ids: set[str] = set()
    for q in golden["questions"]:
        qid = q["id"]
        source = bench.get(qid)
        if source is None:
            continue
        if q["question"] != source["question"]:
            problems.append(f"{qid}: question text differs from the benchmark")
        for key in ("reference_answer", "rationale"):
            if not str(q.get(key, "")).strip():
                problems.append(f"{qid}: missing {key}")
        if not q.get("key_facts"):
            problems.append(f"{qid}: no key facts")
        allowed = labelled_chunks(source, corpus)
        covered: set[str] = set()
        for fact in q.get("key_facts", []):
            fid = fact.get("id", "")
            if not fid.startswith(f"{qid}.f") or fid in fact_ids:
                problems.append(f"{qid}: key fact id '{fid}' is missing, misnamed or repeated")
            fact_ids.add(fid)
            for key in ("candidate", "fact", "resume", "section", "contains"):
                if not str(fact.get(key, "")).strip():
                    problems.append(f"{fid}: missing {key}")
            matches = resolve(fact, corpus)
            if len(matches) != 1:
                problems.append(f"{fid}: {fact.get('resume')} [{fact.get('section')}] '{fact.get('contains')}' "
                                f"matched {len(matches)} chunks")
                continue
            match = matches[0]
            if (match.resume, match.chunk_index) not in allowed:
                problems.append(f"{fid}: resolves to {match.resume} chunk {match.chunk_index}, "
                                f"which is not a labelled chunk of {qid}")
            covered.add(match.resume)
            name = str(fact.get("candidate", "")).lower()
            if name and name not in resume_text(corpus[match.resume]):
                problems.append(f"{fid}: candidate '{fact.get('candidate')}' does not appear in {match.resume}")
            if name and name not in q.get("reference_answer", "").lower():
                problems.append(f"{fid}: candidate '{fact.get('candidate')}' is not named in the reference answer")
        missing = sorted({label["resume"] for label in source["relevant"]} - covered)
        if missing:
            problems.append(f"{qid}: no key fact for labelled resume(s) {', '.join(missing)}")
    negatives = {n["id"]: n for n in benchmark["negative_questions"]}
    golden_negatives = {n["id"]: n for n in golden.get("negative_questions", [])}
    if set(golden_negatives) != set(negatives):
        problems.append(f"golden negatives {sorted(golden_negatives)} do not match {sorted(negatives)}")
    for nid, n in golden_negatives.items():
        if nid in negatives and n["question"] != negatives[nid]["question"]:
            problems.append(f"{nid}: question text differs from the benchmark")
        if n.get("reference_answer") != NOT_FOUND or not str(n.get("rationale", "")).strip():
            problems.append(f"{nid}: reference answer must be '{NOT_FOUND}', with a rationale")
    return problems


def golden_review_page(golden: dict[str, Any], corpus: dict[str, list[Chunk]]) -> str:
    facts = sum(len(q["key_facts"]) for q in golden["questions"])
    lines = [
        "# Golden answers: for review",
        "",
        f"Status: **{golden['status']}**. {len(golden['questions'])} questions with {facts} required key facts, "
        f"and {len(golden['negative_questions'])} negative questions. Source: `eval/golden.json`; "
        "the questions and labels are the benchmark's (`eval/retrieval_benchmark.json`).",
        "",
        "For each question, check that the reference answer says only what the cited chunks say, that every "
        "required key fact is needed for a correct answer, and that nothing required is missing. Edit "
        "`eval/golden.json`, then run `python -m eval.golden validate`.",
        "",
        "Writing rules:",
        "",
    ]
    lines += [f"- {rule}" for rule in golden["writing_rules"]]
    lines.append("")
    for q in golden["questions"]:
        lines += [f"## {q['id']}. {q['question']}", "", f"**Reference answer.** {q['reference_answer']}", "",
                  f"*Rationale:* {q['rationale']}", "", "Required key facts:", ""]
        for fact in q["key_facts"]:
            lines.append(f"- **{fact['id']}** {fact['candidate']}: {fact['fact']}")
            for m in resolve(fact, corpus):
                lines.append(f"  - evidence: `{m.resume}` · {m.chunk.section} · chunk {m.chunk_index}")
                lines.append(f"    > {squash(m.chunk.text)}")
        lines.append("")
    lines += ["## Negative questions", ""]
    lines += [f"- **{n['id']}.** {n['question']} Reference: \"{n['reference_answer']}\" *{n['rationale']}*"
              for n in golden["negative_questions"]]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("command", choices=["validate", "review"])
    args = parser.parse_args(argv)
    golden, benchmark, corpus = load_golden(), load_benchmark(), chunks_by_resume()
    problems = validate_golden(golden, benchmark, corpus)
    for problem in problems:
        print("GOLDEN PROBLEM:", problem)
    if args.command == "review":
        GOLDEN_REVIEW.write_text(golden_review_page(golden, corpus), encoding="utf-8")
        print(f"wrote {GOLDEN_REVIEW.relative_to(ROOT)}")
    if not problems:
        facts = sum(len(q["key_facts"]) for q in golden["questions"])
        print(f"OK golden: {len(golden['questions'])} questions, {facts} key facts, each resolving to exactly "
              "one labelled chunk")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
