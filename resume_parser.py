"""Module to parse and extract structured data from resumes."""
import re
from pathlib import Path

import llm
from config import ResumeProfile, get_api_key

try:
    from colorama import Fore, Style
except ImportError:
    class Fore:
        RED = YELLOW = GREEN = CYAN = ""
    class Style:
        RESET_ALL = ""


def _read_file(path: Path) -> str:
    """Read PDF, DOCX, or TXT files."""
    text = ""
    try:
        if path.suffix.lower() == '.pdf':
            from PyPDF2 import PdfReader
            with open(path, 'rb') as f:
                reader = PdfReader(f)
                for page in reader.pages:
                    text += (page.extract_text() or "") + "\n"
        elif path.suffix.lower() == '.docx':
            from docx import Document
            doc = Document(path)
            for para in doc.paragraphs:
                text += para.text + "\n"
        else:
            with open(path, 'r', encoding='utf-8') as f:
                text = f.read()
    except Exception as e:
        print(f"{Fore.RED}Error reading {path}: {e}{Style.RESET_ALL}")
    return text


def _extract_with_llm(text: str, api_key: str) -> ResumeProfile:
    """Use Gemini to extract structured data."""
    prompt = f"""Extract the following information from this resume and return ONLY a valid JSON object (no markdown, no code fences).

Keys required:
- "name" (string): Full name of the candidate
- "email" (string): Email address
- "phone" (string): Phone number
- "skills" (list of strings): ALL technical skills, tools, frameworks, and languages mentioned
- "experience_years" (float): TOTAL years of professional experience across all positions
- "education" (list of objects): Each with "degree", "field", "institution"
- "work_history" (list of objects): Each with "title", "company", "duration", "description"

If information is not found, use empty string or empty list.
Return ONLY the JSON, nothing else.

Resume text:
{text[:4000]}"""

    data = llm.parse_json_response(llm.generate_text(prompt, api_key))

    skills = [s.strip().lower() for s in data.get('skills', []) if isinstance(s, str)]

    return ResumeProfile(
        name=data.get('name', 'Unknown'),
        email=data.get('email', ''),
        phone=data.get('phone', ''),
        skills=skills,
        experience_years=float(data.get('experience_years', 0.0)),
        education=data.get('education', []),
        work_history=data.get('work_history', [])
    )


def _extract_with_regex(text: str) -> ResumeProfile:
    """Fallback regex extraction."""
    profile = ResumeProfile()
    lines = [line.strip() for line in text.split('\n') if line.strip()]

    # Name: first non-empty, non-separator line
    for line in lines:
        # Skip separator lines (===, ---, ***)
        if re.match(r'^[=\-*_~#]{3,}$', line):
            continue
        # Skip lines that look like section headers or contact info
        if '@' in line or line.lower().startswith(('email', 'phone', 'linkedin', 'github', 'location')):
            continue
        # This should be the name
        profile.name = line.strip()
        break

    # Email
    email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text)
    if email_match:
        profile.email = email_match.group(0)

    # Phone
    phone_match = re.search(r'[\+]?[(]?[0-9]{1,4}[)]?[-\s./0-9]{7,}', text)
    if phone_match:
        profile.phone = phone_match.group(0)

    # Skills: look for skills section and extract items
    skills = []
    skills_section = False
    for line in lines:
        lower_line = line.lower()

        # Skip separator lines
        if re.match(r'^[=\-*_~]{3,}$', line):
            if skills_section:
                # A separator after skills section means section ended
                continue
            continue

        # Detect skills section headers
        if any(header in lower_line for header in ['technical skills', 'skills', 'technologies', 'tools & technologies']):
            skills_section = True
            # Check if skills are on the same line (e.g., "Skills: Python, Java")
            if ':' in line and not lower_line.startswith(('-', '*')):
                after_colon = line.split(':', 1)[1]
                parts = re.split(r'[,|]', after_colon)
                skills.extend([p.strip().lower() for p in parts if p.strip()])
            continue

        if skills_section:
            # Stop at next section (look for ALL CAPS section header or known headers)
            if (lower_line in ['experience', 'education', 'projects', 'certifications',
                              'work experience', 'professional experience', 'work history',
                              'professional summary', 'summary', 'objective', 'contact'] or
                (line.isupper() and len(line) > 3 and not re.match(r'^[=\-*_~]{3,}$', line))):
                skills_section = False
                continue

            # Parse "- Category: Skill1, Skill2, Skill3" format
            if ':' in line:
                after_colon = line.split(':', 1)[1]
                parts = re.split(r'[,|]', after_colon)
                skills.extend([p.strip().lower() for p in parts if p.strip() and len(p.strip()) < 50])
            else:
                # Simple comma/bullet separated
                cleaned = line.strip('*-• ')
                parts = re.split(r'[,|]', cleaned)
                skills.extend([p.strip().lower() for p in parts if p.strip() and len(p.strip()) < 50])

    # dict.fromkeys de-duplicates while keeping first-seen order; set() order varies per process.
    profile.skills = list(dict.fromkeys(s for s in skills if s and len(s) > 1))

    # Experience years: look for explicit mention or calculate from work dates
    exp_match = re.search(r'(\d+)\+?\s*years?', text, re.IGNORECASE)
    if exp_match:
        try:
            profile.experience_years = float(exp_match.group(1))
        except ValueError:
            pass

    # Education: look for degree keywords
    education = []
    edu_patterns = [
        (r'(?:Ph\.?D|Doctorate)', 'PhD'),
        (r'(?:M\.?S\.?|Master|M\.?Tech|M\.?Eng|MBA)', "Master's"),
        (r'(?:B\.?S\.?|Bachelor|B\.?Tech|B\.?Eng|B\.?A\.?)', "Bachelor's"),
        (r'(?:Associate)', "Associate's"),
    ]
    for pattern, degree_name in edu_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            education.append({'degree': degree_name, 'field': '', 'institution': ''})
            break  # Take highest degree found

    profile.education = education

    return profile


def parse_resume(file_path: str) -> ResumeProfile:
    """Main entry point to parse a resume.

    Uses LLM extraction if API key is available, falls back to regex.
    """
    path = Path(file_path)
    print(f"  [*] Parsing: {path.name}")
    text = _read_file(path)

    profile = None
    api_key = get_api_key()

    if api_key:
        try:
            profile = _extract_with_llm(text, api_key)
        except Exception as e:
            print(f"{Fore.YELLOW}  [!] LLM extraction failed, falling back to regex: {e}{Style.RESET_ALL}")

    if not profile:
        profile = _extract_with_regex(text)

    profile.raw_text = text
    profile.file_path = str(file_path)

    print(f"  [OK] Extracted: {profile.name} ({len(profile.skills)} skills found)")
    return profile
