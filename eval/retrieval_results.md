# Retrieval results

Measured once under the frozen protocol (`eval/retrieval_protocol.md`) at commit `70f42a8`: 30 questions, 52 labelled chunks, 26 synthetic resumes (137 chunks), PostgreSQL + pgvector (HNSW). HNSW index used: False.

| Configuration | Recall@1 | Recall@5 | Recall@10 | MRR@10 |
|---|---|---|---|---|
| `vector` | 0.552 | 0.781 | 0.830 | 0.833 |
| `bm25` | 0.519 | 0.886 | 0.886 | 0.776 |
| `hybrid` | 0.581 | 0.842 | 0.919 | 0.850 |
| `hybrid+rerank` | 0.652 | 0.864 | 0.914 | 0.889 |

Best achievable Recall@1 (some questions have several labelled chunks): 0.752.

Component decisions (MRR@10 difference, paired bootstrap 95% CI, 10,000 resamples):

- hybrid vs vector: +0.017 [-0.071, +0.106]
- hybrid+rerank vs hybrid: +0.039 [-0.056, +0.133]

Fusion helps: **False**. Reranker helps: **False**. Chosen configuration: **`vector`**. Rule: keep a component if MRR@10 gain >= 0.02 and the bootstrap 95% CI excludes 0.

Versions: Python 3.13.0, sentence-transformers 5.6.1, torch 2.7.1, rank-bm25 0.2.2, pgvector 0.5.0, sqlalchemy 2.0.36.
