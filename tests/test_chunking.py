"""Section-aware chunking of resumes and job descriptions."""
import re
from pathlib import Path

import pytest

import chunking
from chunking import chunk_job_description, chunk_resume

REPO = Path(__file__).resolve().parent.parent
NL = chr(10)
SAMPLE_RESUMES = sorted((REPO / "sample_resumes").glob("*.txt"))
SAMPLE_JDS = [REPO / "sample_jd" / "jd.txt", REPO / "tests" / "fixtures" / "jd_backend_engineer.txt"]
SEPARATOR = re.compile(r"^\s*[=\-*_~#]{3,}\s*$")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _assert_lossless(source: str, chunks: list[chunking.Chunk]) -> None:
    """Every content character is in exactly one chunk; only headings, separators and whitespace are left out."""
    owner = [-1] * len(source)
    for chunk in chunks:
        assert source[chunk.start:chunk.end] == chunk.text
        assert chunk.text == chunk.text.strip() and chunk.text
        for i in range(chunk.start, chunk.end):
            assert owner[i] == -1, f"overlap at {i}"
            owner[i] = chunk.index
    headings = {c.heading for c in chunks if c.heading}
    position = 0
    for line in source.splitlines(keepends=True):
        stripped = line.strip()
        uncovered = [i for i in range(position, position + len(line)) if owner[i] == -1 and not source[i].isspace()]
        if uncovered:
            leftover = "".join(source[i] for i in uncovered)
            # Allowed outside chunks: separator lines and heading text (alone, or before an inline colon).
            assert SEPARATOR.match(line) or any(leftover.startswith(h.replace(" ", "")[:3]) for h in headings) \
                or stripped in headings, f"content lost: {stripped!r}"
        position += len(line)
    assert [c.index for c in chunks] == list(range(len(chunks)))


@pytest.mark.parametrize("path", SAMPLE_RESUMES, ids=lambda p: p.stem)
def test_sample_resumes_split_into_their_sections(path):
    source = _read(path)
    chunks = chunk_resume(source)
    _assert_lossless(source, chunks)
    assert chunks[0].section == "header" and chunks[0].heading is None
    assert {c.section for c in chunks} == {"header", "summary", "skills", "experience", "education"}
    assert all(len(c.text) <= chunking.DEFAULT_MAX_CHARS for c in chunks)


@pytest.mark.parametrize("path, expected", [
    (SAMPLE_JDS[0], ["summary", "summary", "about", "summary", "responsibilities", "requirements",
                     "preferred", "benefits"]),
    (SAMPLE_JDS[1], ["summary", "summary", "responsibilities", "requirements", "preferred"]),
], ids=["sample_jd", "backend_jd"])
def test_sample_job_descriptions(path, expected):
    source = _read(path)
    chunks = chunk_job_description(source)
    _assert_lossless(source, chunks)
    assert [c.section for c in chunks] == expected
    assert not any("---" in c.text or "===" in c.text for c in chunks)


def test_heading_with_parenthetical_qualifier():
    """'NICE TO HAVE (PREFERRED SKILLS)' was once filed under requirements."""
    chunks = chunk_job_description("REQUIREMENTS\n- Python\n\nNICE TO HAVE (PREFERRED SKILLS)\n- Rust\n")
    assert [(c.section, c.text) for c in chunks] == [("requirements", "- Python"), ("preferred", "- Rust")]


VARIED_RESUME = """JORDAN LEE
jordan.lee@example.com | (555) 010-2020

## Professional Summary
Backend engineer focused on data-heavy APIs.

=== WORK EXPERIENCE ===
Senior Engineer, Acme (2021 - 2026)
Built an event pipeline on Kafka processing 2M messages a day.

Engineer, Initech (2018 - 2021)
Maintained the billing service.

PROJECTS
Resume Ranker - FastAPI service that scores resumes with sentence embeddings.

Skills: Python, FastAPI, PostgreSQL, Docker

Certifications:
AWS Certified Developer

EDUCATION
B.Sc. Computer Science, State University
"""


def test_varied_heading_styles():
    chunks = chunk_resume(VARIED_RESUME)
    _assert_lossless(VARIED_RESUME, chunks)
    assert [(c.section, c.heading) for c in chunks] == [
        ("header", None),
        ("summary", "## Professional Summary"),
        ("experience", "=== WORK EXPERIENCE ==="),
        ("projects", "PROJECTS"),
        ("skills", "Skills"),
        ("certifications", "Certifications:"),
        ("education", "EDUCATION"),
    ]
    experience = next(c for c in chunks if c.section == "experience")
    assert "Acme" in experience.text and "Initech" in experience.text  # paragraphs packed together
    assert next(c for c in chunks if c.section == "skills").text == "Python, FastAPI, PostgreSQL, Docker"


def test_names_and_sentences_are_not_headings():
    text = "SKILLS JOHNSON\nI have experience with Python.\n\nExperience\nBuilt things.\n"
    chunks = chunk_resume(text)
    assert [(c.section, c.text) for c in chunks] == [
        ("header", "SKILLS JOHNSON\nI have experience with Python."),
        ("experience", "Built things."),
    ]


def test_resume_without_headings_is_kept_whole():
    text = "Alex Kim\nalex@example.com\n\nPython developer with five years of Django work.\n"
    chunks = chunk_resume(text)
    _assert_lossless(text, chunks)
    assert {c.section for c in chunks} == {"header"}
    assert "Django" in chunks[-1].text


def test_windows_line_endings():
    text = VARIED_RESUME.replace("\n", "\r\n")
    chunks = chunk_resume(text)
    _assert_lossless(text, chunks)
    assert [c.section for c in chunks] == [c.section for c in chunk_resume(VARIED_RESUME)]


def test_long_sections_split_on_boundaries_within_the_limit():
    jobs = "\n\n".join(f"Engineer {i}, Company {i} (20{i:02d})\n" + "Shipped features and fixed bugs. " * 12
                       for i in range(8))
    text = f"Sam Roe\n\nExperience\n{jobs}\n\nEducation\nBSc"
    chunks = chunk_resume(text, max_chars=500)
    _assert_lossless(text, chunks)
    experience = [c for c in chunks if c.section == "experience"]
    assert len(experience) > 1
    assert all(len(c.text) <= 500 for c in chunks)
    assert all(c.text.endswith((".", ")")) or c.text[-1].isalnum() for c in experience)


def test_unbreakable_text_is_hard_split():
    text = "Experience\n" + "x" * 2000
    chunks = chunk_resume(text, max_chars=300)
    _assert_lossless(text, chunks)
    assert all(len(c.text) <= 300 for c in chunks)
    assert "".join(c.text for c in chunks) == "x" * 2000


def test_empty_and_tiny_inputs():
    assert chunk_resume("") == [] and chunk_resume("   \n\n ") == []
    with pytest.raises(ValueError):
        chunk_resume("text", max_chars=10)


def test_embedding_text_carries_the_section_label():
    skills = next(c for c in chunk_resume(VARIED_RESUME) if c.section == "skills")
    assert skills.embedding_text == "Skills: Python, FastAPI, PostgreSQL, Docker"


def test_fits_check_splits_further_and_stays_lossless():
    def short_enough(chunk):
        return len(chunk.embedding_text) <= 90

    chunks = chunk_resume(VARIED_RESUME, fits=short_enough)
    _assert_lossless(VARIED_RESUME, chunks)
    assert all(short_enough(c) for c in chunks)
    assert len(chunks) > len(chunk_resume(VARIED_RESUME))
    assert [c.section for c in chunks if c.section == "experience"]  # sections survive the extra split


DENSE_SKILLS = "Skills\n" + "Kubernetes, Terraform, PostgreSQL, Redis, Kafka, gRPC, TypeScript, React, PyTorch. " * 30


@pytest.fixture(scope="module")
def tokenizer_model():
    import scorer

    model = scorer.load_embedding_model()
    if model is None:
        pytest.skip("embedding model unavailable")
    return model


def _tokens(model, chunk):
    return len(model.tokenizer(chunk.embedding_text)["input_ids"])


@pytest.mark.slow
def test_character_limit_alone_does_not_fit_dense_text(tokenizer_model):
    """Why `fits` exists: 800 characters of tool names exceed the model's 256-token input."""
    chunks = chunk_resume(DENSE_SKILLS)
    assert max(_tokens(tokenizer_model, c) for c in chunks) > tokenizer_model.max_seq_length


@pytest.mark.slow
def test_with_tokenizer_check_every_chunk_is_embedded_whole(tokenizer_model):
    def fits(chunk):
        return _tokens(tokenizer_model, chunk) <= tokenizer_model.max_seq_length

    documents = [(_read(p), chunk_resume) for p in SAMPLE_RESUMES]
    documents += [(_read(p), chunk_job_description) for p in SAMPLE_JDS]
    documents.append((DENSE_SKILLS, chunk_resume))
    for source, chunker in documents:
        chunks = chunker(source, fits=fits)
        _assert_lossless(source, chunks)
        assert all(fits(c) for c in chunks)


def test_internship_and_research_interest_headings():
    """Found in the varied synthetic resumes: these headings were merged into the previous section."""
    text = (NL * 2).join([
        "Ann Lee",
        "Research Interests" + NL + "Model compression.",
        "SKILLS" + NL + "Python",
        "INTERNSHIP" + NL + "Data Intern, Lumen",
    ])
    assert [(c.section, c.text) for c in chunk_resume(text)] == [
        ("header", "Ann Lee"), ("summary", "Model compression."), ("skills", "Python"),
        ("experience", "Data Intern, Lumen")]
