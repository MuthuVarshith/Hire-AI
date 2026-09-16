"""AI-powered interview question generator tailored to candidates."""
import json
from typing import List, Dict, Optional
from config import JobRequirements, ResumeProfile, get_api_key, GEMINI_MODEL
from models import ScreeningResult, Candidate, Job


def generate_interview_questions(
    candidate: Candidate,
    job: Job,
    screening_result: ScreeningResult,
    use_llm: bool = True,
) -> Dict[str, List[Dict]]:
    """
    Generate tailored interview questions for a candidate.

    Args:
        candidate: Candidate profile
        job: Job requirements
        screening_result: Screening result with matched/missing skills
        use_llm: Whether to use LLM for AI-generated questions

    Returns:
        Dictionary with question categories and questions
    """
    api_key = get_api_key() if use_llm else None

    questions = {
        "technical_questions": [],
        "resume_based_questions": [],
        "skill_gap_questions": [],
        "behavioral_questions": [],
        "note": "Questions are AI-generated based on candidate profile and job requirements"
    }

    if api_key:
        questions.update(_generate_llm_questions(candidate, job, screening_result))
    else:
        questions.update(_generate_template_questions(candidate, job, screening_result))

    return questions


def _generate_llm_questions(
    candidate: Candidate,
    job: Job,
    screening_result: ScreeningResult,
) -> Dict[str, List[Dict]]:
    """Generate interview questions using Google Gemini."""
    try:
        import google.generativeai as genai
        api_key = get_api_key()
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(GEMINI_MODEL)

        # Build context
        matched_skills_str = ", ".join(screening_result.matched_skills[:5])
        missing_skills_str = ", ".join(screening_result.missing_skills[:3])
        work_history_str = "\n".join([
            f"- {w.get('title', 'Unknown')}: {w.get('company', 'N/A')} ({w.get('duration', 'N/A')})"
            for w in (candidate.work_history or [])[:3]
        ])

        prompt = f"""Generate tailored interview questions for a candidate applying for: {job.title}

CANDIDATE PROFILE:
- Name: {candidate.name}
- Experience: {candidate.experience_years} years
- Recent roles: {work_history_str if work_history_str else 'N/A'}
- Matched skills: {matched_skills_str if matched_skills_str else 'None'}
- Missing skills: {missing_skills_str if missing_skills_str else 'None'}
- Screening score: {screening_result.composite_score}/100

QUESTIONS NEEDED (return ONLY valid JSON, no markdown):
1. 5 technical questions tailored to their matched skills
2. 3 resume-based questions about their work history
3. 3 skill-gap questions about their missing skills (if any)
4. 3 behavioral questions about problem-solving and teamwork

For each question, include:
- "question": The actual question
- "category": The category
- "evaluating": What competency this evaluates
- "expected_competency": What you're looking for
- "why_asked": Why this question is relevant based on resume

Return JSON array format only. Example:
[{{"question": "Tell us about...", "category": "behavioral", "evaluating": "...", "expected_competency": "...", "why_asked": "..."}}]"""

        response = model.generate_content(prompt)
        response_text = response.text.strip()

        # Clean markdown if present
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.startswith("```"):
            response_text = response_text[3:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]

        questions_list = json.loads(response_text.strip())

        # Organize by category
        result = {
            "technical_questions": [],
            "resume_based_questions": [],
            "skill_gap_questions": [],
            "behavioral_questions": [],
        }

        for q in questions_list:
            category = q.get("category", "behavioral")
            if category == "technical":
                result["technical_questions"].append(q)
            elif category == "resume":
                result["resume_based_questions"].append(q)
            elif category == "skill_gap" or "gap" in category.lower():
                result["skill_gap_questions"].append(q)
            else:
                result["behavioral_questions"].append(q)

        return result

    except Exception as e:
        print(f"Error generating LLM questions: {e}")
        return {}


def _generate_template_questions(
    candidate: Candidate,
    job: Job,
    screening_result: ScreeningResult,
) -> Dict[str, List[Dict]]:
    """Fallback template-based question generation."""
    questions = {
        "technical_questions": [],
        "resume_based_questions": [],
        "skill_gap_questions": [],
        "behavioral_questions": [],
    }

    # Technical questions based on matched skills
    matched_skills = screening_result.matched_skills[:3]
    for skill in matched_skills:
        questions["technical_questions"].append({
            "question": f"Can you walk us through your experience with {skill}? What projects have you built using it?",
            "category": "technical",
            "evaluating": f"Proficiency with {skill}",
            "expected_competency": "Hands-on experience and problem-solving ability",
            "why_asked": f"This skill matched your resume and is required for this role"
        })

    # Resume-based questions
    if candidate.work_history:
        for work in candidate.work_history[:2]:
            title = work.get("title", "Position")
            company = work.get("company", "Company")
            questions["resume_based_questions"].append({
                "question": f"Tell us about your most significant achievement in your role as {title} at {company}.",
                "category": "resume",
                "evaluating": "Impact and accomplishment",
                "expected_competency": "Clear communication and measurable results",
                "why_asked": f"This role aligns with the position we're hiring for"
            })

    # Skill gap questions
    missing_skills = screening_result.missing_skills[:2]
    for skill in missing_skills:
        questions["skill_gap_questions"].append({
            "question": f"While {skill} isn't on your resume, have you worked with similar technologies? How would you approach learning {skill}?",
            "category": "skill_gap",
            "evaluating": f"Learning ability for {skill}",
            "expected_competency": "Self-directed learning and adaptability",
            "why_asked": f"{skill} is required for this role but not listed in your background"
        })

    # Behavioral questions
    questions["behavioral_questions"] = [
        {
            "question": "Tell us about a time you had to learn a new technology quickly. What was the situation and how did you handle it?",
            "category": "behavioral",
            "evaluating": "Learning agility and problem-solving",
            "expected_competency": "Growth mindset and self-directed learning",
            "why_asked": "This role requires continuous learning in a fast-paced environment"
        },
        {
            "question": "Describe a situation where you had to collaborate with a difficult team member. How did you handle it?",
            "category": "behavioral",
            "evaluating": "Teamwork and communication",
            "expected_competency": "Emotional intelligence and conflict resolution",
            "why_asked": "Team collaboration is critical for this position"
        },
        {
            "question": "Tell us about a project that failed. What did you learn from it?",
            "category": "behavioral",
            "evaluating": "Resilience and learning from failure",
            "expected_competency": "Growth mindset and accountability",
            "why_asked": "We value candidates who learn from setbacks"
        },
    ]

    return questions
