"""Module to parse and extract structured data from job descriptions."""
import re
import json
from pathlib import Path
from config import JobRequirements, get_api_key, GEMINI_MODEL

try:
    from colorama import Fore, Style
except ImportError:
    class Fore:
        RED = YELLOW = GREEN = CYAN = ""
    class Style:
        RESET_ALL = ""


def _extract_with_llm(text: str, api_key: str) -> JobRequirements:
    """Use Gemini to extract structured data from JD."""
    import google.generativeai as genai
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(GEMINI_MODEL)

    prompt = f"""Extract the following information from the job description and return ONLY a valid JSON object (no markdown, no code fences).

Keys required:
- "title" (string): Job title
- "required_skills" (list of strings): Must-have skills
- "preferred_skills" (list of strings): Nice-to-have skills
- "min_experience_years" (float): Minimum years of experience required
- "required_education" (string): Required education level (e.g., "Bachelor's", "Master's")
- "responsibilities" (list of strings): Key responsibilities

Job description:
{text[:4000]}"""

    response = model.generate_content(prompt)
    response_text = response.text.strip()

    # Strip markdown code fences if present
    if response_text.startswith('```json'):
        response_text = response_text[7:]
    if response_text.startswith('```'):
        response_text = response_text[3:]
    if response_text.endswith('```'):
        response_text = response_text[:-3]

    data = json.loads(response_text.strip())

    req_skills = [s.strip().lower() for s in data.get('required_skills', []) if isinstance(s, str)]
    pref_skills = [s.strip().lower() for s in data.get('preferred_skills', []) if isinstance(s, str)]

    return JobRequirements(
        title=data.get('title', 'Unknown Title'),
        required_skills=req_skills,
        preferred_skills=pref_skills,
        min_experience_years=float(data.get('min_experience_years', 0.0)),
        required_education=data.get('required_education', "Bachelor's"),
        responsibilities=data.get('responsibilities', [])
    )


def _extract_with_regex(text: str) -> JobRequirements:
    """Fallback regex extraction for JD."""
    jd = JobRequirements()
    lines = [line.strip() for line in text.split('\n') if line.strip()]

    # Title: look for 'Position:' line or first non-separator line
    for line in lines:
        if re.match(r'^[=\-*_~]{3,}$', line):
            continue
        if 'position:' in line.lower():
            jd.title = line.split(':', 1)[-1].strip()
            break
        if 'title:' in line.lower():
            jd.title = line.split(':', 1)[-1].strip()
            break

    # Technology/skill keywords to extract from sentences
    # NOTE: Order matters — longer phrases must come first to avoid partial matches
    known_skills = [
        # Multi-word skills (match first to avoid partial matches)
        'django rest framework', 'rest apis', 'rest api',
        'machine learning', 'deep learning', 'github actions',
        'node.js', 'sql server',
        # Languages
        'python', 'java', 'javascript', 'typescript', 'c\\+\\+', 'c#', 'golang', 'rust', 'ruby',
        # Frameworks
        'django', 'flask', 'fastapi', 'spring', 'react', 'angular', 'vue', 'express',
        'restful', 'graphql', 'grpc',
        # Databases
        'postgresql', 'mysql', 'mongodb', 'redis', 'sqlite', 'oracle',
        # Cloud & DevOps
        'aws', 'azure', 'gcp', 'docker', 'kubernetes', 'k8s',
        'git', 'github', 'gitlab', 'ci/cd', 'jenkins',
        # Testing
        'pytest', 'unittest', 'jest', 'selenium',
        # Tools
        'celery', 'rabbitmq', 'kafka',
        'linux', 'bash', 'terraform', 'ansible',
        # General
        'html', 'css', 'nosql',
        'tensorflow', 'pytorch',
        'pandas', 'numpy', 'spark', 'hadoop',
        'agile', 'scrum', 'jira',
    ]

    # Extract skills from Requirements and Nice-to-Have sections
    req_skills = []
    pref_skills = []
    section_type = None

    for line in lines:
        lower_line = line.lower()

        # Skip separator lines
        if re.match(r'^[=\-*_~]{3,}$', line):
            continue

        # Detect section headers
        if any(kw in lower_line for kw in ['requirements', 'required', 'must have', 'qualifications']):
            section_type = 'required'
            continue
        elif any(kw in lower_line for kw in ['nice to have', 'preferred', 'bonus', 'plus']):
            section_type = 'preferred'
            continue
        elif any(kw in lower_line for kw in ['responsibilities', 'about us', 'about', 'benefits', 'role summary']):
            section_type = None
            continue

        if section_type:
            # Extract known skill keywords using word-boundary matching
            for skill in known_skills:
                # Use word boundary regex to avoid false positives like 'go' in 'django'
                pattern = r'(?:^|[\s,;(])' + skill + r'(?:[\s,;).]|$)'
                if re.search(pattern, lower_line):
                    target = req_skills if section_type == 'required' else pref_skills
                    if skill not in target:
                        target.append(skill)

    jd.required_skills = list(set(req_skills))
    jd.preferred_skills = list(set(pref_skills))

    # Experience
    exp_match = re.search(r'(\d+)[-+]?\s*(?:to\s*\d+\s*)?years?', text, re.IGNORECASE)
    if exp_match:
        try:
            jd.min_experience_years = float(exp_match.group(1))
        except ValueError:
            pass

    # Education
    edu_match = re.search(r"(Bachelor'?s?|Master'?s?|Ph\.?D|B\.S\.|M\.S\.|B\.Tech|M\.Tech)", text, re.IGNORECASE)
    if edu_match:
        jd.required_education = edu_match.group(1)

    return jd


def parse_jd_text(text: str, api_key: str = None) -> JobRequirements:
    """Parse JD from text string (for API usage).

    Args:
        text: Job description text
        api_key: Optional API key for LLM extraction

    Returns:
        JobRequirements object with extracted data
    """
    if not api_key:
        api_key = get_api_key()

    jd = None
    if api_key:
        try:
            jd = _extract_with_llm(text, api_key)
        except Exception as e:
            pass

    if not jd:
        jd = _extract_with_regex(text)

    jd.raw_text = text
    return jd


def parse_jd(file_path: str) -> JobRequirements:
    """Main entry point to parse a JD.

    Uses LLM extraction if API key is available, falls back to regex.
    """
    path = Path(file_path)
    print(f"  [*] Parsing JD: {path.name}")

    try:
        with open(path, 'r', encoding='utf-8') as f:
            text = f.read()
    except Exception as e:
        print(f"{Fore.RED}Error reading {path}: {e}{Style.RESET_ALL}")
        return JobRequirements()

    jd = parse_jd_text(text)

    print(f"  [OK] JD Extracted: {jd.title} ({len(jd.required_skills)} required skills)")
    return jd
