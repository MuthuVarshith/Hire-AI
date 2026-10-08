"""Tests for the Resume Screening Agent."""
import os
import json
import csv
import sys

# Ensure imports work from the project directory
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config import ResumeProfile, JobRequirements, CandidateScore, WEIGHTS
import utils
import scorer


# --- Config Tests ---

def test_config_weights_sum_to_one():
    """Scoring weights must sum to 1.0."""
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9, "Weights must sum to 1.0"


def test_resume_profile_defaults():
    """ResumeProfile should have sensible defaults."""
    rp = ResumeProfile()
    assert rp.name == "Unknown"
    assert rp.skills == []
    assert rp.experience_years == 0.0


def test_resume_profile_custom():
    """ResumeProfile should accept custom values."""
    rp = ResumeProfile(
        name="John Doe", email="john@example.com", phone="555-1234",
        skills=["python", "django"], experience_years=5.0,
        education=[{"degree": "Bachelor's", "field": "CS", "institution": "MIT"}],
        work_history=[], raw_text="sample text", file_path="/path/to/resume.txt"
    )
    assert rp.name == "John Doe"
    assert "python" in rp.skills
    assert rp.experience_years == 5.0


def test_job_requirements_defaults():
    """JobRequirements should have sensible defaults."""
    jr = JobRequirements()
    assert jr.title == ""
    assert jr.required_skills == []
    assert jr.required_education == "Bachelor's"


def test_candidate_score_defaults():
    """CandidateScore should have sensible defaults."""
    cs = CandidateScore()
    assert cs.composite_score == 0.0
    assert cs.matched_skills == []
    assert cs.missing_skills == []


# --- Utils Tests ---

def test_discover_files(tmp_path):
    """discover_files should find .txt and .pdf but not .csv."""
    (tmp_path / "test1.txt").write_text("Hello")
    (tmp_path / "test2.pdf").write_bytes(b"PDF")
    (tmp_path / "test3.csv").write_text("CSV")
    (tmp_path / "test4.docx").write_bytes(b"DOCX")

    found = utils.discover_files(str(tmp_path))
    filenames = [os.path.basename(f) for f in found]

    assert "test1.txt" in filenames
    assert "test2.pdf" in filenames
    assert "test4.docx" in filenames
    assert "test3.csv" not in filenames


def test_discover_files_empty(tmp_path):
    """discover_files should return empty list for empty directory."""
    found = utils.discover_files(str(tmp_path))
    assert found == []


def test_save_json(tmp_path):
    """save_json should write valid JSON."""
    data = [{"rank": 1, "name": "John", "composite_score": 85.5}]
    out_file = str(tmp_path / "out.json")
    utils.save_json(data, out_file)

    with open(out_file, "r") as f:
        loaded = json.load(f)
    assert loaded[0]["name"] == "John"
    assert loaded[0]["rank"] == 1
    assert loaded[0]["composite_score"] == 85.5


def test_save_csv(tmp_path):
    """save_csv should write valid CSV with correct headers."""
    data = [{"rank": 1, "name": "John", "composite_score": 85.5,
             "semantic_score": 70.0, "skill_match_score": 90.0,
             "experience_score": 100.0, "education_score": 100.0,
             "matched_skills": ["python"], "missing_skills": [],
             "reasoning": "Good match", "file": "resume.txt"}]
    out_file = str(tmp_path / "out.csv")
    utils.save_csv(data, out_file)

    with open(out_file, "r", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert rows[0]["name"] == "John"
    assert rows[0]["rank"] == "1"


# --- Scorer Tests ---

def test_experience_score_zero():
    """Zero experience should give zero score."""
    assert scorer.compute_experience_score(0, 5) == 0.0


def test_experience_score_exact():
    """Exact match should give full score."""
    assert scorer.compute_experience_score(5, 5) == 100.0


def test_experience_score_exceeds():
    """Exceeding requirement should give full score."""
    assert scorer.compute_experience_score(10, 5) == 100.0


def test_experience_score_partial():
    """Partial experience should give proportional score."""
    assert scorer.compute_experience_score(2.5, 5) == 50.0


def test_experience_score_no_requirement():
    """No experience requirement should give full score."""
    assert scorer.compute_experience_score(0, 0) == 100.0


def test_education_score_meets():
    """Meeting education requirement should give full score."""
    edu = [{"degree": "Master's", "field": "CS", "institution": "MIT"}]
    assert scorer.compute_education_score(edu, "Master's") == 100.0


def test_education_score_exceeds():
    """Exceeding education requirement should give full score."""
    edu = [{"degree": "PhD", "field": "CS", "institution": "MIT"}]
    assert scorer.compute_education_score(edu, "Master's") == 100.0


def test_education_score_below():
    """Below education requirement should give reduced score."""
    edu = [{"degree": "Bachelor's", "field": "CS", "institution": "MIT"}]
    score = scorer.compute_education_score(edu, "Master's")
    assert 0 < score < 100


def test_education_score_no_education():
    """No education should give zero score."""
    assert scorer.compute_education_score([], "Bachelor's") == 0.0


def test_score_candidate_returns_valid():
    """score_candidate should return a valid CandidateScore with all fields."""
    resume = ResumeProfile(
        name="Test", skills=["python", "django"],
        experience_years=5.0,
        education=[{"degree": "Bachelor's", "field": "CS", "institution": "Test U"}],
        raw_text="Python developer with Django experience",
        file_path="test.txt"
    )
    jd = JobRequirements(
        title="Python Dev", required_skills=["python", "django", "postgresql"],
        min_experience_years=3.0, required_education="Bachelor's",
        raw_text="Looking for a Python developer"
    )
    # Pass None for model to skip semantic scoring
    result = scorer.score_candidate(resume, jd, None)

    assert isinstance(result, CandidateScore)
    assert result.name == "Test"
    assert 0 <= result.composite_score <= 100
    assert len(result.matched_skills) + len(result.missing_skills) == 3
