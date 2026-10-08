"""Run the frozen retrieval protocol (eval/retrieval_protocol.md) once and write the results.

    python -m eval.measure --postgres-url postgresql+psycopg://hireai:hireai@127.0.0.1:5433/postgres

The admin URL is used to create a throwaway database, which is dropped afterwards.
"""
import argparse
import importlib.metadata as md
import json
import platform
import subprocess
import uuid
from typing import Any

import numpy as np
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from eval.benchmark import ROOT, corpus_files, load, resume_key, squash

CONFIGS: dict[str, dict[str, bool]] = {
    "vector": {"use_vector": True, "use_bm25": False, "use_reranker": False},
    "bm25": {"use_vector": False, "use_bm25": True, "use_reranker": False},
    "hybrid": {"use_vector": True, "use_bm25": True, "use_reranker": False},
    "hybrid+rerank": {"use_vector": True, "use_bm25": True, "use_reranker": True},
}
KS = (1, 5, 10)
RESULTS_JSON = ROOT / "eval" / "retrieval_results.json"
RESULTS_MD = ROOT / "eval" / "retrieval_results.md"
MIN_GAIN = 0.02


def question_metrics(ranked: list[tuple[str, int]], relevant: set[tuple[str, int]]) -> dict[str, float]:
    out = {f"recall@{k}": len(relevant & set(ranked[:k])) / len(relevant) for k in KS}
    first = next((i for i, key in enumerate(ranked[:10], start=1) if key in relevant), None)
    out["mrr@10"] = 1.0 / first if first else 0.0
    return out


def paired_bootstrap(a: list[float], b: list[float], resamples: int = 10_000, seed: int = 0) -> dict[str, float]:
    """Mean of (b - a) and a 95% percentile interval, resampling questions with replacement."""
    diffs = np.array(b) - np.array(a)
    rng = np.random.default_rng(seed)
    means = diffs[rng.integers(0, len(diffs), size=(resamples, len(diffs)))].mean(axis=1)
    return {"mean_diff": float(diffs.mean()), "ci_low": float(np.percentile(means, 2.5)),
            "ci_high": float(np.percentile(means, 97.5))}


def helps(comparison: dict[str, float]) -> bool:
    return comparison["mean_diff"] >= MIN_GAIN and comparison["ci_low"] > 0


def decide(summary: dict[str, dict[str, float]], comparisons: dict[str, dict[str, float]],
           best_single: str) -> dict[str, Any]:
    fusion = helps(comparisons[f"hybrid vs {best_single}"])
    rerank = helps(comparisons["hybrid+rerank vs hybrid"])
    if rerank:
        chosen = "hybrid+rerank"  # reranks the fused list, so it keeps both retrievers
    elif fusion:
        chosen = "hybrid"
    else:
        chosen = best_single
    return {"fusion_helps": fusion, "rerank_helps": rerank, "chosen": chosen,
            "rule": f"keep a component if MRR@10 gain >= {MIN_GAIN} and the bootstrap 95% CI excludes 0"}


def run(admin_url: str) -> dict[str, Any]:
    import indexing
    from database import create_database_engine
    from embeddings import SentenceTransformerProvider
    from models import Candidate, Job, ResumeChunk
    from retrieval import RetrievalConfig, Retriever

    benchmark = load()
    name = f"hireai_bench_{uuid.uuid4().hex[:10]}"
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    engine = create_database_engine(make_url(admin_url).set(database=name).render_as_string(hide_password=False))
    try:
        provider = SentenceTransformerProvider()
        with Session(engine) as session:
            job = Job(title="Benchmark pool", description_text="(benchmark)")
            session.add(job)
            for path in corpus_files():
                session.add(Candidate(name=resume_key(path), job=job, resume_filename=resume_key(path),
                                      resume_text=path.read_text(encoding="utf-8")))
            session.flush()
            for candidate in session.query(Candidate).order_by(Candidate.id):
                indexing.index_candidate(session, candidate, provider)
            session.commit()

            rows = session.query(ResumeChunk, Candidate.resume_filename).join(Candidate).all()
            key_of = {chunk.id: (resume, chunk.chunk_index) for chunk, resume in rows}
            stored: dict[str, list[ResumeChunk]] = {}
            for chunk, resume in rows:
                stored.setdefault(resume, []).append(chunk)

            # Resolve labels against the stored chunks: the indexer's token check may have split further.
            relevant: dict[str, set[tuple[str, int]]] = {}
            for q in benchmark["questions"]:
                keys = set()
                for label in q["relevant"]:
                    found = [c for c in stored.get(label["resume"], [])
                             if c.section == label["section"] and squash(label["contains"]) in squash(c.text)]
                    if len(found) != 1:
                        raise SystemExit(f"{q['id']}: label {label} matched {len(found)} stored chunks")
                    keys.add((label["resume"], found[0].chunk_index))
                relevant[q["id"]] = keys

            retriever = Retriever(session, provider)
            per_question: dict[str, dict[str, dict[str, float]]] = {}
            for config_name, flags in CONFIGS.items():
                config = RetrievalConfig(k=10, pool=50, rrf_k=60, **flags)
                per_question[config_name] = {
                    q["id"]: question_metrics([key_of[h.chunk_id] for h in retriever.search(q["question"], config)],
                                              relevant[q["id"]])
                    for q in benchmark["questions"]
                }
            plan = session.execute(text(
                "EXPLAIN SELECT id FROM resume_chunks WHERE embedding_model = :m "
                "ORDER BY (embedding::vector(384)) <=> CAST(:q AS vector(384)) LIMIT 50"),
                {"m": provider.name, "q": str([0.1] * 384)}).scalars().all()
            hnsw_used = any("ix_resume_chunks_embedding_hnsw_minilm" in line for line in plan)
            chunk_count = len(rows)
    finally:
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()

    ids = [q["id"] for q in benchmark["questions"]]
    summary = {c: {m: round(sum(per_question[c][i][m] for i in ids) / len(ids), 4)
                   for m in ("recall@1", "recall@5", "recall@10", "mrr@10")} for c in CONFIGS}

    def mrr(config_name: str) -> list[float]:
        return [per_question[config_name][i]["mrr@10"] for i in ids]

    best_single = max(("vector", "bm25"), key=lambda c: summary[c]["mrr@10"])
    comparisons = {
        f"hybrid vs {best_single}": paired_bootstrap(mrr(best_single), mrr("hybrid")),
        "hybrid+rerank vs hybrid": paired_bootstrap(mrr("hybrid"), mrr("hybrid+rerank")),
    }
    versions = {d: md.version(d) for d in ("sentence-transformers", "torch", "rank-bm25", "pgvector", "sqlalchemy")}
    return {
        "commit": subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip(),
        "python": platform.python_version(), "versions": versions, "database": "PostgreSQL + pgvector (HNSW)",
        "hnsw_index_used": hnsw_used, "resumes": len(corpus_files()), "chunks": chunk_count,
        "questions": len(ids), "labelled_chunks": sum(len(v) for v in relevant.values()),
        "best_achievable_recall@1": round(sum(1 / len(relevant[i]) for i in ids) / len(ids), 4),
        "summary": summary, "comparisons": comparisons, "decision": decide(summary, comparisons, best_single),
        "per_question": per_question,
    }


def markdown(r: dict[str, Any]) -> str:
    lines = [
        "# Retrieval results",
        "",
        f"Measured once under the frozen protocol (`eval/retrieval_protocol.md`) at commit `{r['commit']}`: "
        f"{r['questions']} questions, {r['labelled_chunks']} labelled chunks, {r['resumes']} synthetic resumes "
        f"({r['chunks']} chunks), {r['database']}. HNSW index used: {r['hnsw_index_used']}.",
        "",
        "| Configuration | Recall@1 | Recall@5 | Recall@10 | MRR@10 |",
        "|---|---|---|---|---|",
    ]
    for name, m in r["summary"].items():
        lines.append(f"| `{name}` | {m['recall@1']:.3f} | {m['recall@5']:.3f} | {m['recall@10']:.3f} | "
                     f"{m['mrr@10']:.3f} |")
    lines += ["", f"Best achievable Recall@1 (some questions have several labelled chunks): "
                  f"{r['best_achievable_recall@1']:.3f}.", "",
              "Component decisions (MRR@10 difference, paired bootstrap 95% CI, 10,000 resamples):", ""]
    for name, c in r["comparisons"].items():
        lines.append(f"- {name}: {c['mean_diff']:+.3f} [{c['ci_low']:+.3f}, {c['ci_high']:+.3f}]")
    d = r["decision"]
    lines += ["", f"Fusion helps: **{d['fusion_helps']}**. Reranker helps: **{d['rerank_helps']}**. "
                  f"Chosen configuration: **`{d['chosen']}`**. Rule: {d['rule']}.", "",
              f"Versions: Python {r['python']}, " + ", ".join(f"{k} {v}" for k, v in r["versions"].items()) + "."]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--postgres-url", required=True, help="admin URL used to create a throwaway database")
    args = parser.parse_args(argv)
    result = run(args.postgres_url)
    RESULTS_JSON.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    RESULTS_MD.write_text(markdown(result), encoding="utf-8")
    print(markdown(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
