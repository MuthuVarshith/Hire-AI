"""Golden answers for the benchmark questions and the held-out set: validation and review pages.

    python -m eval.golden validate     # key facts and held-out labels resolve; no overlap with the benchmark
    python -m eval.golden review       # writes eval/golden_review.md and eval/heldout_review.md

Key facts and held-out labels are located the way benchmark labels are (eval/benchmark.py): resume
file, section, and a quote the chunk must contain, compared with whitespace squashed.
"""
import argparse
import json
import re
from itertools import combinations
from typing import Any

from chunking import Chunk
from eval.benchmark import ROOT, chunks_by_resume, resolve, squash
from eval.benchmark import load as load_benchmark

GOLDEN = ROOT / "eval" / "golden.json"
GOLDEN_REVIEW = ROOT / "eval" / "golden_review.md"
HELDOUT = ROOT / "eval" / "heldout.json"
HELDOUT_REVIEW = ROOT / "eval" / "heldout_review.md"
NOT_FOUND = "Not found in resumes."
FLAWS = ("omission", "invented_claim", "wrong_citation")
# Two questions whose topic words overlap this much (Jaccard) are treated as duplicates or paraphrases.
OVERLAP_LIMIT = 0.5
# Words every recruiter question uses; left out so the overlap check compares topics, not phrasing.
_GENERIC = frozenset("""
a an and any are as at be been by can candidate candidates do does experience find for from has have
held hold holds in into is know knows kind like list lists new of on or other someone such that the
their them they to type use used using who whom whose which with work worked working built build
""".split())
_TOKEN = re.compile(r"[a-z0-9][a-z0-9+#]*")
_MARKER = re.compile(r"\[(\d+)\]")


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


# --- held-out set ------------------------------------------------------------------------
def load_heldout() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(HELDOUT.read_text(encoding="utf-8"))
    return data


def topic_words(question: str) -> set[str]:
    """Lowercased topic words: generic recruiter words dropped, a plural 's' removed."""
    words = set()
    for token in _TOKEN.findall(question.lower()):
        if token in _GENERIC or len(token) < 2:
            continue
        if len(token) > 3 and token.endswith("s") and not token.endswith(("ss", "us", "is", "as")):
            token = token[:-1]
        words.add(token)
    return words


def overlap(a: str, b: str) -> float:
    """Jaccard similarity of two questions' topic words (0 when either has none)."""
    wa, wb = topic_words(a), topic_words(b)
    return len(wa & wb) / len(wa | wb) if wa and wb else 0.0


def closest_benchmark(question: str, benchmark: dict[str, Any]) -> tuple[str, float]:
    """The benchmark question (answerable or negative) whose topic words overlap most, and the overlap."""
    pool = benchmark["questions"] + benchmark["negative_questions"]
    best = max(pool, key=lambda q: overlap(question, q["question"]))
    return best["id"], overlap(question, best["question"])


def absent(term: str, corpus: dict[str, list[Chunk]]) -> bool:
    """True when the term appears in no resume (case-insensitive, whole words, whitespace squashed)."""
    pattern = re.compile(rf"(?<![a-z0-9]){re.escape(squash(term).lower())}(?![a-z0-9])")
    return not any(pattern.search(resume_text(chunks)) for chunks in corpus.values())


def validate_heldout(heldout: dict[str, Any], benchmark: dict[str, Any],
                     corpus: dict[str, list[Chunk]]) -> tuple[list[str], list[str]]:
    """Returns (problems, warnings). Warnings are shown to the reviewer but don't fail validation."""
    problems: list[str] = []
    warnings: list[str] = []
    answerable, unanswerable = heldout["answerable"], heldout["unanswerable"]
    bench_ids = {q["id"] for q in benchmark["questions"] + benchmark["negative_questions"]}
    ids = [q["id"] for q in answerable + unanswerable]
    if len(ids) != len(set(ids)) or set(ids) & bench_ids:
        problems.append("held-out ids must be unique and different from the benchmark's")
    bench_sets = {q["id"]: labelled_chunks(q, corpus) for q in benchmark["questions"]}
    for q in answerable:
        qid = q["id"]
        if not qid.startswith("h") or not q["question"].strip() or not q.get("rationale", "").strip():
            problems.append(f"{qid}: answerable ids start with 'h' and need a question and a rationale")
        if not q.get("relevant"):
            problems.append(f"{qid}: an answerable question needs labelled chunks")
        seen: set[tuple[str, int]] = set()
        for label in q.get("relevant", []):
            matches = resolve(label, corpus)
            if len(matches) != 1:
                problems.append(f"{qid}: {label['resume']} [{label['section']}] '{label['contains']}' "
                                f"matched {len(matches)} chunks")
                continue
            key = (matches[0].resume, matches[0].chunk_index)
            if key in seen:
                problems.append(f"{qid}: duplicate label for {key[0]} chunk {key[1]}")
            seen.add(key)
            name = str(label.get("candidate", "")).lower()
            if not name or name not in resume_text(corpus[matches[0].resume]):
                problems.append(f"{qid}: candidate '{label.get('candidate')}' does not appear in {label['resume']}")
        for bid, chunks in bench_sets.items():
            if seen and seen == chunks:
                warnings.append(f"{qid} has exactly the evidence of benchmark {bid}; confirm it asks about a "
                                "different fact")
        problems += _check_judge_items(q)
    for q in unanswerable:
        qid = q["id"]
        if not qid.startswith("u") or not q["question"].strip() or not q.get("rationale", "").strip():
            problems.append(f"{qid}: unanswerable ids start with 'u' and need a question and a rationale")
        for term in q.get("absent_terms", []):
            if not absent(term, corpus):
                problems.append(f"{qid}: '{term}' appears in the corpus, so the question may be answerable")
    for q in answerable + unanswerable:
        bid, score = closest_benchmark(q["question"], benchmark)
        if score >= OVERLAP_LIMIT:
            problems.append(f"{q['id']} overlaps benchmark {bid} ({score:.2f} >= {OVERLAP_LIMIT}): "
                            "a duplicate or paraphrase")
    for a, b in combinations(answerable + unanswerable, 2):
        if overlap(a["question"], b["question"]) >= OVERLAP_LIMIT:
            problems.append(f"{a['id']} and {b['id']} overlap ({overlap(a['question'], b['question']):.2f})")
    return problems, warnings


def _check_judge_items(q: dict[str, Any]) -> list[str]:
    """The judge check's good and flawed answers: known flaw type, citation numbers within the labels."""
    qid, check = q["id"], q.get("judge_check") or {}
    problems = []
    labels = len(q.get("relevant", []))
    good, flawed = check.get("good_answer", ""), check.get("flawed_answer", "")
    if check.get("flaw") not in FLAWS or not str(check.get("flaw_note", "")).strip():
        problems.append(f"{qid}: judge_check needs a flaw in {FLAWS} and a flaw_note")
    if not good.strip() or not flawed.strip() or good == flawed:
        problems.append(f"{qid}: judge_check needs a good and a different flawed answer")
    for name, text in (("good_answer", good), ("flawed_answer", flawed)):
        cited = {int(n) for n in _MARKER.findall(text)}
        if not cited or not cited <= set(range(1, labels + 1)):
            problems.append(f"{qid}: {name} cites {sorted(cited)}, but only [1]..[{labels}] exist")
    if {int(n) for n in _MARKER.findall(good)} != set(range(1, labels + 1)):
        problems.append(f"{qid}: the good answer must cite every label")
    return problems


def heldout_review_page(heldout: dict[str, Any], benchmark: dict[str, Any], corpus: dict[str, list[Chunk]],
                        warnings: list[str]) -> str:
    answerable, unanswerable = heldout["answerable"], heldout["unanswerable"]
    labels = sum(len(q["relevant"]) for q in answerable)
    lines = [
        "# Held-out questions: for review",
        "",
        f"Status: **{heldout['status']}**. {len(answerable)} answerable questions with {labels} labelled chunks, "
        f"and {len(unanswerable)} unanswerable questions, over {len(corpus)} synthetic resumes. "
        "Source: `eval/heldout.json`.",
        "",
        "These questions recalibrate the not-found cutoff and check the LLM judge "
        "(`eval/answer_eval_protocol.md`). They must not repeat or paraphrase a benchmark question. "
        "For each answerable question, check that every listed chunk belongs and none is missing; for each "
        "unanswerable one, that no resume answers it. Edit `eval/heldout.json`, then run "
        "`python -m eval.golden validate`.",
        "",
        f"Overlap check: topic-word Jaccard similarity against every benchmark question; {OVERLAP_LIMIT} or more "
        "fails validation. The closest benchmark question is shown for each.",
        "",
    ]
    if warnings:
        lines += ["**Warnings:**", ""] + [f"- {w}" for w in warnings] + [""]
    lines += ["## Answerable", ""]
    for q in answerable:
        bid, score = closest_benchmark(q["question"], benchmark)
        check = q["judge_check"]
        lines += [f"### {q['id']}. {q['question']}", "", f"*Rationale:* {q['rationale']}", "",
                  f"Closest benchmark question: {bid} (overlap {score:.2f}).", ""]
        for i, label in enumerate(q["relevant"], start=1):
            for m in resolve(label, corpus):
                lines.append(f"- [{i}] `{m.resume}` · {m.chunk.section} · chunk {m.chunk_index} ({label['candidate']})")
                lines.append(f"  > {squash(m.chunk.text)}")
        lines += ["", f"Judge check, good answer: {check['good_answer']}", "",
                  f"Judge check, flawed answer ({check['flaw']}: {check['flaw_note']}): {check['flawed_answer']}", ""]
    lines += ["## Unanswerable", ""]
    for q in unanswerable:
        bid, score = closest_benchmark(q["question"], benchmark)
        terms = ", ".join(f"'{t}'" for t in q["absent_terms"]) or "none (checked by reading)"
        lines.append(f"- **{q['id']}.** {q['question']} *{q['rationale']}* Absent terms: {terms}. "
                     f"Closest benchmark question: {bid} ({score:.2f}).")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("command", choices=["validate", "review"])
    args = parser.parse_args(argv)
    golden, heldout, benchmark, corpus = load_golden(), load_heldout(), load_benchmark(), chunks_by_resume()
    problems = validate_golden(golden, benchmark, corpus)
    held_problems, warnings = validate_heldout(heldout, benchmark, corpus)
    for problem in problems:
        print("GOLDEN PROBLEM:", problem)
    for problem in held_problems:
        print("HELD-OUT PROBLEM:", problem)
    for warning in warnings:
        print("HELD-OUT WARNING:", warning)
    if args.command == "review":
        GOLDEN_REVIEW.write_text(golden_review_page(golden, corpus), encoding="utf-8")
        HELDOUT_REVIEW.write_text(heldout_review_page(heldout, benchmark, corpus, warnings), encoding="utf-8")
        print(f"wrote {GOLDEN_REVIEW.relative_to(ROOT)} and {HELDOUT_REVIEW.relative_to(ROOT)}")
    if not problems:
        facts = sum(len(q["key_facts"]) for q in golden["questions"])
        print(f"OK golden: {len(golden['questions'])} questions, {facts} key facts, each resolving to exactly "
              "one labelled chunk")
    if not held_problems:
        labels = sum(len(q["relevant"]) for q in heldout["answerable"])
        print(f"OK held-out: {len(heldout['answerable'])} answerable ({labels} labels, each matching exactly one "
              f"chunk), {len(heldout['unanswerable'])} unanswerable, no overlap with the benchmark")
    return 1 if problems or held_problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
