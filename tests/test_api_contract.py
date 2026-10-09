"""Contract tests for every Flask route, pinning current behavior.

These are the reference the FastAPI migration (Phase 5) must keep passing.
Tests named test_known_issue_* pin behavior that is wrong today; they are
listed in docs/phase-0-notes.md and should be changed deliberately when the
behavior is fixed, not silently.

The embedding model is replaced with None (semantic score 0, exact skill
matching) so results are fast and deterministic; test_score_regression.py
covers scoring with the real model.
"""
import io
import re
import json
from pathlib import Path

import pytest

import interview_generator
import llm
import scorer

REPO = Path(__file__).resolve().parent.parent
SAMPLE_JD = (REPO / "sample_jd" / "jd.txt").read_text(encoding="utf-8")
SNAPSHOT = json.loads((REPO / "tests" / "fixtures" / "parser_snapshot.json").read_text(encoding="utf-8"))

JOB_KEYS = {"id", "title", "description", "required_skills", "preferred_skills", "min_experience_years",
            "required_education", "created_at", "candidates_count", "status"}
CANDIDATE_KEYS = {"id", "name", "email", "phone", "resume_filename", "skills", "experience_years", "education",
                  "work_history", "status", "created_at", "notes", "job_id", "job_title"}
SCREENING_KEYS = {"id", "candidate_id", "job_id", "composite_score", "semantic_score", "skill_match_score",
                  "experience_score", "education_score", "matched_skills", "missing_skills",
                  "matched_preferred_skills", "reasoning", "strengths", "skill_gaps", "created_at"}
TEMPLATE_KEYS = {"id", "name", "description", "semantic_weight", "skill_weight", "experience_weight",
                 "education_weight", "is_default", "created_at"}


@pytest.fixture
def app_module():
    import app as app_module

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
    return app_module.app.test_client()


def make_job(client, title="AI Engineer", text=SAMPLE_JD, **extra):
    response = client.post("/api/jobs", json={"title": title, "description_text": text, **extra})
    assert response.status_code == 201, response.get_json()
    return response.get_json()


def upload(client, job_id, name="resume_01_ananya_patel.txt", data=None):
    payload = data if data is not None else (REPO / "sample_resumes" / name).read_bytes()
    return client.post(f"/api/candidates?job_id={job_id}",
                       data={"resume": (io.BytesIO(payload), name)}, content_type="multipart/form-data")


def screen(client, candidate_id, job_id, **body):
    return client.post(f"/api/screen/{candidate_id}/{job_id}", **({"json": body} if body else {}))


def template_id(client, name):
    return next(t["id"] for t in client.get("/api/scoring-templates").get_json() if t["name"] == name)


# --- Jobs -----------------------------------------------------------------

def test_create_job_parses_requirements(client):
    job = make_job(client)
    expected = SNAPSHOT["jds"]["sample_jd/jd.txt"]
    assert set(job) == JOB_KEYS
    assert job["title"] == "AI Engineer"
    assert job["required_skills"] == expected["required_skills"]
    assert job["preferred_skills"] == expected["preferred_skills"]
    assert job["min_experience_years"] == expected["min_experience_years"]
    assert job["required_education"] == expected["required_education"]
    assert (job["candidates_count"], job["status"], job["description"]) == (0, "Open", SAMPLE_JD)


@pytest.mark.parametrize("body, message", [
    ({"description_text": "x"}, "title is required"),
    ({"title": "x"}, "description_text is required"),
    ({}, "title is required"),
])
def test_create_job_validation(client, body, message):
    response = client.post("/api/jobs", json=body)
    assert (response.status_code, response.get_json()) == (400, {"error": message})


def test_create_job_with_non_json_body_returns_415(client):
    """Regression: was a 500 that leaked the 415 message through a generic except."""
    response = client.post("/api/jobs", data={"title": "x"})
    assert response.status_code == 415
    assert "application/json" in response.get_json()["error"]


def test_list_get_update_delete_job(client):
    first = make_job(client, title="First")
    second = make_job(client, title="Second")
    assert [j["title"] for j in client.get("/api/jobs").get_json()] == ["Second", "First"]  # newest first

    assert client.get(f"/api/jobs/{first['id']}").get_json() == first
    assert client.get("/api/jobs/999").status_code == 404

    updated = client.put(f"/api/jobs/{first['id']}", json={"title": "Renamed", "description_text": "Rust, Go"})
    assert updated.status_code == 200
    body = updated.get_json()
    assert (body["title"], body["description"]) == ("Renamed", "Rust, Go")
    # Requirements are NOT re-extracted when the description changes.
    assert body["required_skills"] == first["required_skills"]
    assert client.put("/api/jobs/999", json={"title": "x"}).status_code == 404

    assert client.delete(f"/api/jobs/{second['id']}").get_json() == {"message": "Job deleted"}
    assert client.get(f"/api/jobs/{second['id']}").status_code == 404
    assert client.delete("/api/jobs/999").status_code == 404


def test_delete_job_cascades_to_candidates_and_screenings(client):
    job = make_job(client)
    candidate = upload(client, job["id"]).get_json()
    screening = screen(client, candidate["id"], job["id"]).get_json()
    client.delete(f"/api/jobs/{job['id']}")
    assert client.get(f"/api/candidates/{candidate['id']}").status_code == 404
    assert client.get(f"/api/screening/{screening['id']}").status_code == 404


def test_delete_job_removes_its_candidates_resume_files(client, tmp_path):
    """Regression: deleting a job used to leave its candidates' resume files (PII) on disk."""
    job = make_job(client)
    other = make_job(client, title="Other")
    doomed = [upload(client, job["id"], name=n).get_json()["resume_filename"]
              for n in ("resume_01_ananya_patel.txt", "resume_02_michael_chen.txt")]
    kept = upload(client, other["id"], name="resume_06_owen_brooks.txt").get_json()["resume_filename"]
    (tmp_path / doomed[1]).unlink()  # an already-missing file must not break the delete

    assert client.delete(f"/api/jobs/{job['id']}").status_code == 200
    assert not (tmp_path / doomed[0]).exists()
    assert (tmp_path / kept).exists()  # other jobs' candidates are untouched


def test_failed_job_delete_keeps_resume_files(client, tmp_path, app_module, monkeypatch):
    job = make_job(client)
    stored = upload(client, job["id"]).get_json()["resume_filename"]

    def failing_commit(self):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(app_module.Session, "commit", failing_commit)
    assert client.delete(f"/api/jobs/{job['id']}").status_code == 500
    assert (tmp_path / stored).exists()


# --- Candidates -------------------------------------------------------------

def test_upload_resume_creates_candidate(client, tmp_path):
    job = make_job(client)
    response = upload(client, job["id"])
    assert response.status_code == 201
    body = response.get_json()
    expected = SNAPSHOT["resumes"]["sample_resumes/resume_01_ananya_patel.txt"]
    assert set(body) == CANDIDATE_KEYS
    assert {k: body[k] for k in ("name", "email", "phone", "skills", "experience_years", "education")} == \
        {k: expected[k] for k in ("name", "email", "phone", "skills", "experience_years", "education")}
    assert (body["status"], body["job_id"], body["job_title"], body["notes"]) == \
        ("Screened", job["id"], "AI Engineer", None)
    assert body["resume_filename"].endswith("_resume_01_ananya_patel.txt")
    assert (tmp_path / body["resume_filename"]).exists()


@pytest.mark.parametrize("query, status, message", [
    ("", 400, "job_id is required"),
    ("?job_id=abc", 400, "job_id must be an integer"),
    ("?job_id=999", 404, "Job 999 not found"),
])
def test_upload_requires_valid_job(client, query, status, message):
    response = client.post(f"/api/candidates{query}", data={"resume": (io.BytesIO(b"x"), "a.txt")},
                           content_type="multipart/form-data")
    assert (response.status_code, response.get_json()) == (status, {"error": message})


def test_upload_accepts_job_id_as_form_field(client):
    job = make_job(client)
    response = client.post("/api/candidates", content_type="multipart/form-data",
                           data={"job_id": str(job["id"]), "resume": (io.BytesIO(b"Jo Bloggs\njo@x.com"), "jo.txt")})
    assert response.status_code == 201


def test_upload_file_validation(client):
    job = make_job(client)
    url = f"/api/candidates?job_id={job['id']}"
    no_file = client.post(url, data={}, content_type="multipart/form-data")
    assert (no_file.status_code, no_file.get_json()) == (400, {"error": "resume file is required"})
    empty_name = client.post(url, data={"resume": (io.BytesIO(b"x"), "")}, content_type="multipart/form-data")
    assert (empty_name.status_code, empty_name.get_json()) == (400, {"error": "No resume file provided"})
    bad_type = upload(client, job["id"], name="cv.exe", data=b"MZ")
    assert (bad_type.status_code, bad_type.get_json()) == (400, {"error": "File type .exe not allowed"})


def test_upload_sanitizes_filename(client, tmp_path):
    job = make_job(client)
    body = upload(client, job["id"], name="../../evil name.txt", data=b"Evil Person\nevil@x.com").get_json()
    assert body["resume_filename"].endswith("_evil_name.txt")
    assert "/" not in body["resume_filename"] and "\\" not in body["resume_filename"]
    assert (tmp_path / body["resume_filename"]).exists()


def test_oversized_upload_returns_413(client):
    """Regression: was a 500 that leaked the 413 message through a generic except."""
    job = make_job(client)
    response = upload(client, job["id"], name="big.txt", data=b"a" * (11 * 1024 * 1024))
    assert response.status_code == 413
    assert response.get_json() == {"error": "The data value transmitted exceeds the capacity limit."}


def test_duplicate_upload_is_rejected_and_file_removed(client, tmp_path):
    job = make_job(client)
    first = upload(client, job["id"]).get_json()
    before = set(p.name for p in tmp_path.iterdir())
    same_person = (REPO / "sample_resumes" / "resume_01_ananya_patel.txt").read_bytes()
    duplicate = upload(client, job["id"])
    assert duplicate.status_code == 409
    assert duplicate.get_json() == {"error": "Duplicate candidate detected", "existing_candidate": {
        "id": first["id"], "name": "Ananya Patel", "email": "ananya.patel@email.com", "status": "Screened"}}
    assert set(p.name for p in tmp_path.iterdir()) == before  # the original's file survives the rejection
    original = client.get(f"/api/candidates/{first['id']}/resume")
    assert original.data == same_person
    original.close()

    # The same person may apply to a different job.
    other = make_job(client, title="Other")
    assert upload(client, other["id"]).status_code == 201


def test_same_named_uploads_never_share_storage(client, tmp_path):
    """Regression: names used to be <timestamp to the second>_<name>, so two same-named uploads
    within one second shared a path and one candidate was served the other's resume."""
    job = make_job(client)
    # Distinct names: duplicate detection fuzzy-matches names, so "Person 1" and "Person 10" would collide.
    names = ["Ada Byron", "Bo Chen", "Cy Dorsey", "Di Evans", "Ed Flores", "Fay Gupta", "Gus Hale", "Hal Ito",
             "Ivy Jones", "Jo Kumar", "Kai Lopez", "Liv Moreno", "Max Nakamura", "Nia Okafor", "Oz Patel",
             "Pia Quinn", "Rex Romero", "Sue Silva", "Ty Tanaka", "Uma Varga"]
    resumes = {n: f"{n}\n{n.split()[0].lower()}@example.com\nPython".encode() for n in names}
    created = {name: upload(client, job["id"], name="resume.txt", data=data).get_json()
               for name, data in resumes.items()}

    stored = [c["resume_filename"] for c in created.values()]
    assert len(set(stored)) == 20
    assert len(list(tmp_path.iterdir())) == 20
    for name, candidate in created.items():
        served = client.get(f"/api/candidates/{candidate['id']}/resume")
        assert served.data == resumes[name]
        assert 'filename=resume.txt' in served.headers["Content-Disposition"]
        served.close()


@pytest.mark.parametrize("original, kept", [
    ("resume.pdf", "_resume.pdf"),
    ("../../evil name.txt", "_evil_name.txt"),
    ("резюме.pdf", "_resume.pdf"),      # secure_filename drops non-ASCII; the extension must survive
    ("Lebenslauf_Müller.DOCX", "_Lebenslauf_Muller.docx"),
])
def test_storage_name_is_unique_and_keeps_extension(app_module, original, kept):
    names = {app_module.storage_name(original) for _ in range(1000)}
    assert len(names) == 1000
    for name in names:
        assert re.fullmatch(r"[0-9a-f]{32}_.+", name) and name.lower().endswith(kept.lower())
        assert "/" not in name and "\\" not in name and ".." not in name


@pytest.mark.parametrize("stored, shown", [
    ("0123456789abcdef0123456789abcdef_resume.pdf", "resume.pdf"),
    ("20260101_120000_resume.pdf", "resume.pdf"),   # stored by older versions
    ("plain.pdf", "plain.pdf"),
])
def test_download_name_strips_storage_prefix(app_module, stored, shown):
    assert app_module.download_name(stored) == shown


def test_non_ascii_pdf_upload_is_read_as_pdf(client):
    from tests.test_parsers import _minimal_pdf

    job = make_job(client)
    pdf = _minimal_pdf(["Jana Novak", "jana.novak@example.com"])
    body = upload(client, job["id"], name="резюме.pdf", data=pdf).get_json()
    assert body["resume_filename"].endswith(".pdf")
    assert (body["name"], body["email"]) == ("Jana Novak", "jana.novak@example.com")


def test_list_candidates_filters_and_sorting(client):
    ai = make_job(client)
    backend = make_job(client, title="Backend")
    ananya = upload(client, ai["id"]).get_json()
    michael = upload(client, ai["id"], name="resume_02_michael_chen.txt").get_json()
    owen = upload(client, backend["id"], name="resume_06_owen_brooks.txt").get_json()
    client.put(f"/api/candidates/{michael['id']}", json={"status": "shortlisted"})

    def ids(query):
        return [c["id"] for c in client.get(f"/api/candidates{query}").get_json()]

    assert ids("") == [owen["id"], michael["id"], ananya["id"]]           # newest first
    assert ids(f"?job_id={ai['id']}") == [michael["id"], ananya["id"]]
    assert ids("?status=SHORTLISTED") == ids("?status=shortlisted") == [michael["id"]]
    assert ids("?status=bogus") == ids("") and ids("?job_id=abc") == ids("")  # invalid filters ignored

    screen(client, ananya["id"], ai["id"])
    screen(client, michael["id"], ai["id"])
    by_score = client.get("/api/candidates?sort_by=score").get_json()
    scores = [c["latest_screening"]["composite_score"] for c in by_score]
    assert scores == sorted(scores, reverse=True)


def test_known_issue_sort_by_score_drops_unscored_candidates(client):
    """sort_by=score inner-joins screening results, so candidates never screened disappear from the list."""
    job = make_job(client)
    scored = upload(client, job["id"]).get_json()
    upload(client, job["id"], name="resume_02_michael_chen.txt")
    screen(client, scored["id"], job["id"])
    assert [c["id"] for c in client.get("/api/candidates?sort_by=score").get_json()] == [scored["id"]]
    assert len(client.get("/api/candidates").get_json()) == 2


def test_get_candidate_includes_screening_history(client):
    job = make_job(client)
    candidate = upload(client, job["id"]).get_json()
    fresh = client.get(f"/api/candidates/{candidate['id']}").get_json()
    assert fresh["screening_history"] == [] and "latest_screening" not in fresh

    first = screen(client, candidate["id"], job["id"]).get_json()
    second = screen(client, candidate["id"], job["id"]).get_json()
    body = client.get(f"/api/candidates/{candidate['id']}").get_json()
    assert [s["id"] for s in body["screening_history"]] == [first["id"], second["id"]]
    assert body["latest_screening"]["id"] == second["id"]
    assert client.get("/api/candidates/999").status_code == 404


def test_update_candidate_status_and_notes(client):
    job = make_job(client)
    cid = upload(client, job["id"]).get_json()["id"]
    for status in ("Shortlisted", "interview", "OFFER", "Hired", "Rejected", "Screened"):
        response = client.put(f"/api/candidates/{cid}", json={"status": status})
        assert response.status_code == 200
        assert response.get_json()["status"] == status.capitalize()
    noted = client.put(f"/api/candidates/{cid}", json={"notes": "Strong systems design"}).get_json()
    assert noted["notes"] == "Strong systems design"
    invalid = client.put(f"/api/candidates/{cid}", json={"status": "promoted"})
    assert (invalid.status_code, invalid.get_json()) == (400, {"error": "Invalid status: promoted"})
    assert client.put("/api/candidates/999", json={"status": "Hired"}).status_code == 404
    assert client.put(f"/api/candidates/{cid}", data="not json").status_code == 200  # body optional, no-op


def test_known_issue_non_string_status_returns_500(client):
    """Should be 400 (request validation arrives with FastAPI). No longer leaks the AttributeError text."""
    job = make_job(client)
    cid = upload(client, job["id"]).get_json()["id"]
    response = client.put(f"/api/candidates/{cid}", json={"status": 5})
    assert (response.status_code, response.get_json()) == (500, {"error": "Internal server error"})


def test_download_and_delete_resume(client, tmp_path):
    job = make_job(client)
    candidate = upload(client, job["id"]).get_json()
    download = client.get(f"/api/candidates/{candidate['id']}/resume")
    assert download.status_code == 200
    assert download.data == (REPO / "sample_resumes" / "resume_01_ananya_patel.txt").read_bytes()
    assert "attachment" in download.headers["Content-Disposition"]
    download.close()

    assert client.get("/api/candidates/999/resume").get_json() == {"error": "Resume not found"}
    (tmp_path / candidate["resume_filename"]).unlink()
    missing = client.get(f"/api/candidates/{candidate['id']}/resume")
    assert (missing.status_code, missing.get_json()) == (404, {"error": "Resume file not found on disk"})

    other = upload(client, job["id"], name="resume_02_michael_chen.txt").get_json()
    assert client.delete(f"/api/candidates/{other['id']}").get_json() == {"message": "Candidate deleted"}
    assert not (tmp_path / other["resume_filename"]).exists()
    assert client.delete(f"/api/candidates/{other['id']}").status_code == 404


# --- Screening ----------------------------------------------------------------

def test_screen_candidate_default_weights(client):
    job = make_job(client)
    candidate = upload(client, job["id"]).get_json()
    response = screen(client, candidate["id"], job["id"])
    assert response.status_code == 201
    body = response.get_json()
    assert set(body) == SCREENING_KEYS

    required = SNAPSHOT["jds"]["sample_jd/jd.txt"]["required_skills"]
    assert body["missing_skills"] == ["machine learning"]
    assert body["matched_skills"] == [s for s in required if s != "machine learning"]
    assert (body["semantic_score"], body["skill_match_score"], body["experience_score"], body["education_score"]) == \
        (0.0, 87.5, 100.0, 100.0)
    assert body["composite_score"] == round(0 * 0.40 + 87.5 * 0.30 + 100 * 0.15 + 100 * 0.15, 2)
    assert body["strengths"] == [
        f"Strong skills match: {', '.join(body['matched_skills'][:3])}",
        f"Exceeds experience requirement ({candidate['experience_years']} years)",
        "Meets or exceeds education requirements",
    ]
    assert body["skill_gaps"] == ["Missing required skills: machine learning"]
    assert body["reasoning"] == f"Composite score {body['composite_score']:.1f}/100. " + ". ".join(body["strengths"])


def test_screen_candidate_uses_job_scoring_template(client):
    job = make_job(client, scoring_template_id=template_id(client, "AI Engineer"))
    candidate = upload(client, job["id"]).get_json()
    body = screen(client, candidate["id"], job["id"]).get_json()
    assert body["composite_score"] == round(0 * 0.35 + 87.5 * 0.35 + 100 * 0.20 + 100 * 0.10, 2)


def test_screen_candidate_not_found(client):
    job = make_job(client)
    candidate = upload(client, job["id"]).get_json()
    assert screen(client, 999, job["id"]).get_json() == {"error": "Candidate not found"}
    assert screen(client, candidate["id"], 999).get_json() == {"error": "Job not found"}


def test_screen_against_another_job_moves_candidate(client):
    first = make_job(client)
    second = make_job(client, title="Second")
    candidate = upload(client, first["id"]).get_json()
    client.put(f"/api/candidates/{candidate['id']}", json={"status": "Interview"})
    screen(client, candidate["id"], second["id"])
    after = client.get(f"/api/candidates/{candidate['id']}").get_json()
    assert (after["job_id"], after["status"]) == (second["id"], "Screened")


def test_screen_with_llm_explanation(client, monkeypatch):
    import config

    monkeypatch.setattr(config, "get_api_key", lambda: "test-key")
    prompts = []
    monkeypatch.setattr(llm, "generate_text", lambda prompt, key: prompts.append(prompt) or "Gemini says hire.")
    job = make_job(client)
    candidate = upload(client, job["id"]).get_json()

    assert screen(client, candidate["id"], job["id"]).get_json()["reasoning"] == "Gemini says hire."
    # prompts[0] is the job-description extraction from POST /api/jobs; the explanation is the last call.
    assert "Ananya Patel" in prompts[-1] and "AI Engineer" in prompts[-1]
    no_llm = screen(client, candidate["id"], job["id"], use_llm=False).get_json()
    assert no_llm["reasoning"].startswith("Composite score ")


def test_known_issue_llm_failure_stores_empty_reasoning(client, monkeypatch):
    """The explanation helper swallows the error and returns "", so no template fallback happens."""
    import config

    def boom(prompt, key):
        raise RuntimeError("quota exceeded")

    monkeypatch.setattr(config, "get_api_key", lambda: "test-key")
    monkeypatch.setattr(llm, "generate_text", boom)
    job = make_job(client)
    candidate = upload(client, job["id"]).get_json()
    assert screen(client, candidate["id"], job["id"]).get_json()["reasoning"] == ""


def test_get_screening_result(client):
    job = make_job(client)
    candidate = upload(client, job["id"]).get_json()
    created = screen(client, candidate["id"], job["id"]).get_json()
    assert client.get(f"/api/screening/{created['id']}").get_json() == created
    assert client.get("/api/screening/999").get_json() == {"error": "Screening result not found"}


# --- Interview questions -------------------------------------------------------

def test_interview_questions_template(client):
    job = make_job(client)
    candidate = upload(client, job["id"]).get_json()
    url = f"/api/candidates/{candidate['id']}/jobs/{job['id']}/interview-questions"
    no_screening = client.get(url)
    assert (no_screening.status_code, no_screening.get_json()) == \
        (404, {"error": "No screening result found for this candidate-job pair"})

    screening = screen(client, candidate["id"], job["id"]).get_json()
    body = client.get(url).get_json()
    assert set(body) == {"technical_questions", "resume_based_questions", "skill_gap_questions",
                         "behavioral_questions", "note"}
    assert [q["question"] for q in body["technical_questions"]] == [
        f"Can you walk us through your experience with {s}? What projects have you built using it?"
        for s in screening["matched_skills"][:3]
    ]
    assert len(body["skill_gap_questions"]) == min(2, len(screening["missing_skills"]))
    assert len(body["behavioral_questions"]) == 3
    assert len(body["resume_based_questions"]) == min(2, len(candidate["work_history"]))
    assert client.get(f"/api/candidates/999/jobs/{job['id']}/interview-questions").status_code == 404
    assert client.get(f"/api/candidates/{candidate['id']}/jobs/999/interview-questions").status_code == 404


def test_interview_questions_llm_groups_by_category(client, monkeypatch):
    import config

    questions = [{"question": f"Q{i}", "category": c} for i, c in
                 enumerate(["technical", "resume", "skill_gap", "knowledge gap", "behavioral", "other"])]
    monkeypatch.setattr(config, "get_api_key", lambda: "test-key")
    monkeypatch.setattr(interview_generator, "get_api_key", lambda: "test-key")
    monkeypatch.setattr(llm, "generate_text", lambda prompt, key: "```json\n" + json.dumps(questions) + "\n```")
    job = make_job(client)
    candidate = upload(client, job["id"]).get_json()
    screen(client, candidate["id"], job["id"], use_llm=False)

    body = client.get(f"/api/candidates/{candidate['id']}/jobs/{job['id']}/interview-questions").get_json()
    grouped = {k: [q["question"] for q in v] for k, v in body.items() if k != "note"}
    assert grouped == {"technical_questions": ["Q0"], "resume_based_questions": ["Q1"],
                       "skill_gap_questions": ["Q2", "Q3"], "behavioral_questions": ["Q4", "Q5"]}


# --- Scoring templates -----------------------------------------------------------

def test_list_and_get_templates(client):
    templates = client.get("/api/scoring-templates").get_json()
    assert [t["name"] for t in templates] == ["AI Engineer", "Data Scientist", "Default", "DevOps Engineer",
                                               "Frontend Developer"]
    assert all(set(t) == TEMPLATE_KEYS for t in templates)
    default = next(t for t in templates if t["name"] == "Default")
    assert (default["is_default"], default["semantic_weight"], default["skill_weight"],
            default["experience_weight"], default["education_weight"]) == (True, 0.40, 0.30, 0.15, 0.15)
    assert client.get(f"/api/scoring-templates/{default['id']}").get_json() == default
    assert client.get("/api/scoring-templates/999").status_code == 404


def test_create_template(client):
    body = {"name": "Backend", "description": "APIs", "semantic_weight": 0.2, "skill_weight": 0.5,
            "experience_weight": 0.2, "education_weight": 0.1}
    response = client.post("/api/scoring-templates", json=body)
    assert response.status_code == 201
    created = response.get_json()
    assert {k: created[k] for k in body} == body and created["is_default"] is False

    defaults = client.post("/api/scoring-templates", json={"name": "Defaults only"}).get_json()
    assert (defaults["semantic_weight"], defaults["skill_weight"]) == (0.40, 0.30)


@pytest.mark.parametrize("body, message", [
    ({"semantic_weight": 0.5}, "name is required"),
    ({"name": "x", "semantic_weight": 0.5}, "Weights must sum to 1.0"),
])
def test_create_template_validation(client, body, message):
    response = client.post("/api/scoring-templates", json=body)
    assert (response.status_code, response.get_json()) == (400, {"error": message})


def test_create_template_rejects_non_numeric_weight(client):
    response = client.post("/api/scoring-templates", json={"name": "x", "skill_weight": "lots"})
    assert response.status_code == 400
    assert response.get_json()["error"].startswith("Invalid weight value:")


def test_duplicate_template_name_returns_409_without_sql(client):
    """Regression: used to return 500 with the INSERT statement and its parameters."""
    duplicate = {"error": "A scoring template with this name already exists"}
    created = client.post("/api/scoring-templates", json={"name": "Default"})
    assert (created.status_code, created.get_json()) == (409, duplicate)

    mine = client.post("/api/scoring-templates", json={"name": "Mine"}).get_json()
    renamed = client.put(f"/api/scoring-templates/{mine['id']}", json={"name": "Default"})
    assert (renamed.status_code, renamed.get_json()) == (409, duplicate)
    assert client.get(f"/api/scoring-templates/{mine['id']}").get_json()["name"] == "Mine"
    same_name = client.put(f"/api/scoring-templates/{mine['id']}", json={"name": "Mine", "skill_weight": 0.3})
    assert same_name.status_code == 200  # keeping your own name is not a duplicate


def test_duplicate_template_race_is_caught_by_the_database(client, app_module, monkeypatch):
    """If two requests pass the pre-check at once, the unique index still yields a clean 409."""
    monkeypatch.setattr(app_module, "_template_name_taken", lambda db, name: False)
    response = client.post("/api/scoring-templates", json={"name": "Default"})
    assert (response.status_code, response.get_json()) == (
        409, {"error": "A scoring template with this name already exists"})


def test_update_template(client):
    tid = client.post("/api/scoring-templates", json={"name": "Mine"}).get_json()["id"]
    updated = client.put(f"/api/scoring-templates/{tid}", json={
        "name": "Mine v2", "semantic_weight": 0.1, "skill_weight": 0.6}).get_json()
    assert (updated["name"], updated["semantic_weight"], updated["skill_weight"]) == ("Mine v2", 0.1, 0.6)

    bad = client.put(f"/api/scoring-templates/{tid}", json={"skill_weight": 0.9})
    assert (bad.status_code, bad.get_json()) == (400, {"error": "Weights must sum to 1.0"})
    assert client.get(f"/api/scoring-templates/{tid}").get_json()["skill_weight"] == 0.6  # rejected change not saved
    assert client.put(f"/api/scoring-templates/{tid}", json={"skill_weight": "x"}).status_code == 400
    assert client.put("/api/scoring-templates/999", json={}).status_code == 404


def test_delete_template(client):
    default_id = template_id(client, "Default")
    blocked = client.delete(f"/api/scoring-templates/{default_id}")
    assert (blocked.status_code, blocked.get_json()) == (400, {"error": "Cannot delete default template"})
    tid = client.post("/api/scoring-templates", json={"name": "Temp"}).get_json()["id"]
    assert client.delete(f"/api/scoring-templates/{tid}").get_json() == {"message": "Template deleted"}
    assert client.delete(f"/api/scoring-templates/{tid}").status_code == 404


# --- Analytics -------------------------------------------------------------------

DASHBOARD_KEYS = {"total_screened", "shortlisted", "in_interview", "offers", "hired", "rejected", "average_score",
                  "score_distribution", "pipeline_stages", "candidates_by_job", "skill_gaps",
                  "top_matched_skills", "shortlist_rate"}


def test_analytics_empty(client):
    body = client.get("/api/analytics/dashboard").get_json()
    assert set(body) == DASHBOARD_KEYS
    assert (body["total_screened"], body["average_score"], body["shortlist_rate"], body["score_distribution"]) == \
        (0, 0.0, 0.0, {})
    assert client.get("/api/analytics/top-candidates").get_json() == []


def test_analytics_reflect_database(client):
    ai = make_job(client)
    other = make_job(client, title="Other")
    a = upload(client, ai["id"]).get_json()
    m = upload(client, ai["id"], name="resume_02_michael_chen.txt").get_json()
    o = upload(client, other["id"], name="resume_06_owen_brooks.txt").get_json()
    scores = {c["id"]: screen(client, c["id"], j["id"]).get_json()["composite_score"]
              for c, j in ((a, ai), (m, ai), (o, other))}
    client.put(f"/api/candidates/{m['id']}", json={"status": "Shortlisted"})
    client.put(f"/api/candidates/{o['id']}", json={"status": "Hired"})

    body = client.get("/api/analytics/dashboard").get_json()
    assert (body["total_screened"], body["shortlisted"], body["hired"]) == (3, 1, 1)
    assert body["average_score"] == round(sum(scores.values()) / 3, 2)
    assert body["shortlist_rate"] == round(1 / 3 * 100, 2)
    assert body["candidates_by_job"] == {"AI Engineer": 2, "Other": 1}
    assert body["pipeline_stages"] == {"Screened": 1, "Shortlisted": 1, "Interview": 0, "Offer": 0, "Hired": 1,
                                       "Rejected": 0}
    assert sum(body["score_distribution"].values()) == 3

    per_job = client.get(f"/api/analytics/dashboard?job_id={ai['id']}").get_json()
    assert per_job["total_screened"] == 2

    job_metrics = client.get(f"/api/analytics/jobs/{ai['id']}").get_json()
    assert job_metrics["total_applications"] == 2
    assert [d["count"] for d in job_metrics["screening_timeline"]] == [2]
    assert client.get("/api/analytics/jobs/999").status_code == 404

    top = client.get("/api/analytics/top-candidates?limit=2").get_json()
    assert [t["score"] for t in top] == sorted(scores.values(), reverse=True)[:2]
    assert set(top[0]) == {"id", "name", "email", "score", "status"}


# --- Dashboard page, health, errors --------------------------------------------

def test_dashboard_health_and_info(client):
    page = client.get("/")
    assert page.status_code == 200 and b"HireAI" in page.data
    page.close()
    assert client.get("/api/health").get_json() == {"status": "OK", "message": "Recruiting Agent Backend is running"}
    info = client.get("/api/info").get_json()
    assert info["name"] == "AI Resume Screening Agent" and "GET /api/health" in info["endpoints"]


def test_unknown_route_returns_json_404(client):
    response = client.get("/api/does-not-exist")
    assert (response.status_code, response.get_json()) == (404, {"error": "Not found"})


def test_known_issue_method_not_allowed_returns_html(client):
    """Every other error is JSON; 405 has no handler and returns Flask's HTML page."""
    response = client.delete("/api/jobs")
    assert response.status_code == 405
    assert response.get_json(silent=True) is None


# --- No internals in error responses ---------------------------------------------

SECRET = "SECRET-db-password=hunter2 /srv/hireai/uploads SELECT * FROM candidates"


class _BrokenSession:
    """A database session where every operation fails with a message full of internals."""

    def __getattr__(self, name):
        if name in ("close", "rollback"):
            return lambda *a, **k: None

        def fail(*args, **kwargs):
            raise RuntimeError(SECRET)
        return fail


def _db_routes(app_module):
    """Every route that touches the database, with ids filled in, from Flask's own route table."""
    skip = {"serve_dashboard", "health_check", "info", "static"}
    for rule in app_module.app.url_map.iter_rules():
        if rule.endpoint in skip:
            continue
        url = re.sub(r"<int:\w+>", "1", rule.rule)
        for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
            yield method, url


def test_server_errors_never_reach_the_client(client, app_module, monkeypatch, caplog):
    monkeypatch.setattr(app_module, "get_db", lambda: _BrokenSession())
    from tests.test_retrieval import KeywordProvider  # /api/ask embeds the question before querying
    monkeypatch.setattr(app_module.embeddings, "get_provider", lambda: KeywordProvider())
    routes = list(_db_routes(app_module))
    assert len(routes) == 23  # 26 routes minus the dashboard page, health and info

    for method, url in routes:
        caplog.clear()
        kwargs = {"json": {"title": "t", "description_text": "d", "name": "n", "status": "Hired", "question": "q"}}
        if (method, url) == ("POST", "/api/candidates"):
            kwargs = {"query_string": {"job_id": 1}, "content_type": "multipart/form-data",
                      "data": {"resume": (io.BytesIO(b"Jo Bloggs\njo@x.com"), "jo.txt")}}
        response = client.open(url, method=method, **kwargs)

        assert response.status_code == 500, (method, url, response.status_code)
        assert response.get_json() == {"error": "Internal server error"}, (method, url)
        assert "hunter2" not in response.get_data(as_text=True), (method, url)
        # ...but the full details are in the server log, with a traceback.
        assert SECRET in caplog.text, (method, url)
        assert any(r.exc_info for r in caplog.records), (method, url)
