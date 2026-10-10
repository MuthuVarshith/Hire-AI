"""Concurrent screening through the API never mixes up jobs' scoring weights.

The screening endpoint used to apply a job's template by overwriting the shared
config.WEIGHTS dict, scoring, and restoring it. Concurrent requests for jobs with
different templates could then score a candidate with the other job's weights.
"""
import io
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import scorer

REPO = Path(__file__).resolve().parent.parent
JD_TEXT = (REPO / "sample_jd" / "jd.txt").read_text(encoding="utf-8")
SKILLS_ONLY = {"semantic_weight": 0.0, "skill_weight": 1.0, "experience_weight": 0.0, "education_weight": 0.0}
EDUCATION_ONLY = {"semantic_weight": 0.0, "skill_weight": 0.0, "experience_weight": 0.0, "education_weight": 1.0}
THREADS = 8
ROUNDS = 3


@pytest.fixture
def app_module():
    import legacy_flask_app as app_module

    return app_module


@pytest.fixture
def client(app_module, tmp_path, monkeypatch):
    from models import Base, create_default_templates

    Base.metadata.drop_all(app_module.engine)
    Base.metadata.create_all(app_module.engine)
    with app_module.SessionLocal() as session:
        create_default_templates(session)
    monkeypatch.setitem(app_module.app.config, "UPLOAD_FOLDER", str(tmp_path))
    monkeypatch.setattr(scorer, "load_embedding_model", lambda: None)

    real_semantic = scorer.compute_semantic_score

    def slow_semantic(*args, **kwargs):
        # Widen the window between choosing weights and using them, so a leak would show up.
        time.sleep(0.005)
        return real_semantic(*args, **kwargs)

    monkeypatch.setattr(scorer, "compute_semantic_score", slow_semantic)
    return app_module.app.test_client()


def _setup_two_jobs(client):
    jobs = {}
    for label, weights in (("skills", SKILLS_ONLY), ("education", EDUCATION_ONLY)):
        template = client.post("/api/scoring-templates", json={"name": f"{label} only", **weights}).get_json()
        jobs[label] = client.post("/api/jobs", json={"title": f"Job ({label})", "description_text": JD_TEXT,
                                                    "scoring_template_id": template["id"]}).get_json()["id"]
    resumes = sorted((REPO / "sample_resumes").glob("*.txt"))
    candidates = {"skills": [], "education": []}
    for i, path in enumerate(resumes):
        label = "skills" if i % 2 == 0 else "education"
        created = client.post(f"/api/candidates?job_id={jobs[label]}", content_type="multipart/form-data",
                              data={"resume": (io.BytesIO(path.read_bytes()), path.name)})
        assert created.status_code == 201, created.get_json()
        candidates[label].append(created.get_json()["id"])
    return jobs, candidates


def test_concurrent_screening_uses_each_jobs_own_weights(client, app_module):
    jobs, candidates = _setup_two_jobs(client)
    work = [(label, cid) for _ in range(ROUNDS) for label in ("skills", "education") for cid in candidates[label]]
    start = threading.Barrier(THREADS)
    local = threading.local()

    def screen(item):
        label, cid = item
        if not hasattr(local, "client"):
            local.client = app_module.app.test_client()
            start.wait()  # release every thread at once
        response = local.client.post(f"/api/screen/{cid}/{jobs[label]}")
        assert response.status_code == 201, response.get_json()
        return label, response.get_json()

    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        results = list(pool.map(screen, work))

    assert len(results) == len(work) == ROUNDS * 12
    wrong = []
    for label, body in results:
        # With one-hot weights the composite must equal exactly the component its job weighs.
        expected = body["skill_match_score"] if label == "skills" else body["education_score"]
        if body["composite_score"] != expected:
            wrong.append((label, body["candidate_id"], body["composite_score"], expected))
    assert not wrong, f"{len(wrong)} of {len(results)} scores used the other job's weights: {wrong[:5]}"

    # The check only means something if the two jobs' weights give different answers.
    distinguishable = sum(body["skill_match_score"] != body["education_score"] for _, body in results)
    assert distinguishable >= len(results) // 2
