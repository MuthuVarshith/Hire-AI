"""Characterization tests for the resume and job-description parsers."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import jd_parser
import llm
import resume_parser

REPO = Path(__file__).resolve().parent.parent
SNAPSHOT = json.loads((REPO / "tests" / "fixtures" / "parser_snapshot.json").read_text(encoding="utf-8"))


def _fields(obj, names):
    return {name: getattr(obj, name) for name in names}


@pytest.mark.parametrize("path", sorted(SNAPSHOT["resumes"]))
def test_resume_regex_extraction_matches_snapshot(path):
    expected = SNAPSHOT["resumes"][path]
    assert _fields(resume_parser.parse_resume(str(REPO / path)), expected) == expected


@pytest.mark.parametrize("path", sorted(SNAPSHOT["jds"]))
def test_jd_regex_extraction_matches_snapshot(path):
    expected = SNAPSHOT["jds"][path]
    assert _fields(jd_parser.parse_jd(str(REPO / path)), expected) == expected


def test_parsing_is_identical_across_hash_seeds():
    """Skill order used to depend on the per-process hash seed (list(set(...)))."""
    code = (
        "import json, sys; sys.path.insert(0, 'tests/fixtures'); "
        "from make_parser_snapshot import build; print(json.dumps(build()))"
    )
    outputs = []
    for seed in ("1", "2"):
        env = {**os.environ, "PYTHONHASHSEED": seed, "GOOGLE_API_KEY": ""}
        run = subprocess.run([sys.executable, "-c", code], cwd=REPO, env=env,
                             capture_output=True, text=True, check=True)
        outputs.append(json.loads(run.stdout.strip().splitlines()[-1]))
    assert outputs[0] == outputs[1]


def test_jd_parse_text_matches_file_parse():
    path = REPO / "sample_jd" / "jd.txt"
    from_text = jd_parser.parse_jd_text(path.read_text(encoding="utf-8"))
    from_file = jd_parser.parse_jd(str(path))
    assert from_text == from_file


# --- File formats ---------------------------------------------------------

def _minimal_pdf(lines):
    """A valid single-page PDF with one text line per entry, with a correct xref table."""
    text_ops = " ".join(f"({line}) Tj 0 -16 Td" for line in lines)
    stream = f"BT /F1 12 Tf 72 720 Td {text_ops} ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def test_reads_pdf(tmp_path):
    path = tmp_path / "jane.pdf"
    path.write_bytes(_minimal_pdf(["Jane Doe", "jane.doe@example.com", "SKILLS", "Python, Docker"]))
    profile = resume_parser.parse_resume(str(path))
    assert profile.name == "Jane Doe"
    assert profile.email == "jane.doe@example.com"
    assert "Jane Doe" in profile.raw_text


def test_reads_docx(tmp_path):
    from docx import Document

    path = tmp_path / "john.docx"
    doc = Document()
    for line in ("John Smith", "john.smith@example.com", "SKILLS", "Python, FastAPI"):
        doc.add_paragraph(line)
    doc.save(path)
    profile = resume_parser.parse_resume(str(path))
    assert profile.name == "John Smith"
    assert profile.email == "john.smith@example.com"
    assert {"python", "fastapi"} <= set(profile.skills)


def test_unreadable_file_yields_empty_profile(tmp_path):
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"not really a pdf")
    profile = resume_parser.parse_resume(str(path))
    assert profile.raw_text == ""
    assert profile.name == "Unknown"
    assert profile.skills == []


# --- LLM extraction path (mocked; never reaches the network) ---------------

RESUME_JSON = {
    "name": "Ada Lovelace", "email": "ada@example.com", "phone": "555-0100",
    "skills": [" Python ", "FastAPI", 7], "experience_years": 6,
    "education": [{"degree": "Master's", "field": "Math", "institution": "UoL"}],
    "work_history": [{"title": "Engineer", "company": "X", "duration": "2019-2025", "description": "APIs"}],
}


def _enable_llm(monkeypatch, response):
    monkeypatch.setattr(resume_parser, "get_api_key", lambda: "test-key")
    monkeypatch.setattr(jd_parser, "get_api_key", lambda: "test-key")
    calls = []

    def fake_generate(prompt, api_key):
        calls.append((prompt, api_key))
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(llm, "generate_text", fake_generate)
    return calls


@pytest.mark.parametrize("wrapper", ["{}", "```json\n{}\n```", "```\n{}\n```"])
def test_resume_llm_extraction(monkeypatch, wrapper):
    calls = _enable_llm(monkeypatch, wrapper.format(json.dumps(RESUME_JSON)))
    path = REPO / "sample_resumes" / "resume_01_ananya_patel.txt"
    profile = resume_parser.parse_resume(str(path))

    assert len(calls) == 1 and calls[0][1] == "test-key"
    assert profile.name == "Ada Lovelace"
    assert profile.skills == ["python", "fastapi"]  # stripped, lowercased, non-strings dropped
    assert profile.experience_years == 6.0
    assert profile.raw_text == path.read_text(encoding="utf-8")
    assert profile.file_path == str(path)


def test_resume_llm_failure_falls_back_to_regex(monkeypatch):
    _enable_llm(monkeypatch, RuntimeError("quota exceeded"))
    path = "sample_resumes/resume_01_ananya_patel.txt"
    profile = resume_parser.parse_resume(str(REPO / path))
    expected = SNAPSHOT["resumes"][path]
    assert _fields(profile, expected) == expected


def test_resume_llm_invalid_json_falls_back_to_regex(monkeypatch):
    _enable_llm(monkeypatch, "Sorry, I can't help with that.")
    path = "sample_resumes/resume_02_michael_chen.txt"
    expected = SNAPSHOT["resumes"][path]
    assert _fields(resume_parser.parse_resume(str(REPO / path)), expected) == expected


def test_jd_llm_extraction_and_fallback(monkeypatch):
    jd_json = {"title": "ML Engineer", "required_skills": ["Python", "PyTorch"], "preferred_skills": ["AWS"],
               "min_experience_years": 3, "required_education": "Master's", "responsibilities": ["Ship models"]}
    _enable_llm(monkeypatch, json.dumps(jd_json))
    jd = jd_parser.parse_jd_text("any text")
    assert (jd.title, jd.required_skills, jd.preferred_skills) == ("ML Engineer", ["python", "pytorch"], ["aws"])
    assert jd.min_experience_years == 3.0 and jd.raw_text == "any text"

    _enable_llm(monkeypatch, RuntimeError("down"))
    text = (REPO / "sample_jd" / "jd.txt").read_text(encoding="utf-8")
    assert jd_parser.parse_jd_text(text).required_skills == SNAPSHOT["jds"]["sample_jd/jd.txt"]["required_skills"]
