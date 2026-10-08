"""Regenerate parser_snapshot.json from the current regex parsers.

Run only when a parsing change is intentional, then review the diff:
    python tests/fixtures/make_parser_snapshot.py
"""
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
os.environ["GOOGLE_API_KEY"] = ""

import config  # noqa: E402
import jd_parser  # noqa: E402
import resume_parser  # noqa: E402

for module in (config, resume_parser, jd_parser):
    module.get_api_key = lambda: None

RESUME_FIELDS = ("name", "email", "phone", "skills", "experience_years", "education", "work_history")
JD_FIELDS = ("title", "required_skills", "preferred_skills", "min_experience_years", "required_education",
             "responsibilities")
JD_FILES = ("sample_jd/jd.txt", "tests/fixtures/jd_backend_engineer.txt")


def build() -> dict:
    os.chdir(REPO)
    resumes = {
        p.as_posix(): {f: getattr(resume_parser.parse_resume(str(p)), f) for f in RESUME_FIELDS}
        for p in sorted(Path("sample_resumes").glob("*.txt"))
    }
    jds = {path: {f: getattr(jd_parser.parse_jd(path), f) for f in JD_FIELDS} for path in JD_FILES}
    return {"resumes": resumes, "jds": jds}


if __name__ == "__main__":
    out = REPO / "tests" / "fixtures" / "parser_snapshot.json"
    out.write_text(json.dumps(build(), indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out}")
