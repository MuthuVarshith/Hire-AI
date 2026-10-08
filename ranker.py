"""Module to rank candidates and generate reasoning."""
from typing import List, Optional

import llm
from config import CandidateScore

try:
    from colorama import Fore, Style
except ImportError:
    class Fore:
        RED = YELLOW = GREEN = CYAN = ""
    class Style:
        RESET_ALL = ""


def _generate_reasoning_template(score: CandidateScore, rank: int) -> str:
    """Template-based fallback reasoning."""
    total_skills = len(score.matched_skills) + len(score.missing_skills)
    matched_str = ", ".join(score.matched_skills[:5]) if score.matched_skills else "none"
    missing_str = ", ".join(score.missing_skills[:3]) if score.missing_skills else "none"
    extra = "..." if len(score.missing_skills) > 3 else ""

    parts = [f"Ranked #{rank} with a composite score of {score.composite_score:.1f}/100."]

    if total_skills > 0:
        parts.append(f"Matched {len(score.matched_skills)}/{total_skills} required skills ({matched_str}).")

    if score.missing_skills:
        parts.append(f"Key gaps: missing {missing_str}{extra}.")
    else:
        parts.append("No missing required skills - strong skill alignment.")

    if score.experience_score >= 100:
        parts.append("Meets experience requirements.")
    elif score.experience_score > 0:
        parts.append(f"Experience partially meets requirements ({score.experience_score:.0f}%).")
    else:
        parts.append("No relevant experience detected.")

    return " ".join(parts)


def _generate_reasoning_llm(score: CandidateScore, rank: int, api_key: str) -> str:
    """Use Gemini to generate a 2-3 sentence reasoning."""
    try:
        prompt = f"""You are evaluating a job candidate. Write a concise 2-3 sentence reasoning explaining why this candidate is ranked at position #{rank}. Highlight their strengths and key gaps. Do not use markdown formatting. Be specific.

Candidate: {score.name}
Rank: #{rank}
Composite Score: {score.composite_score:.1f}/100
Semantic Relevance: {score.semantic_score:.1f}/100
Skill Match: {score.skill_match_score:.1f}/100
Experience: {score.experience_score:.1f}/100
Education: {score.education_score:.1f}/100
Matched Skills: {', '.join(score.matched_skills) if score.matched_skills else 'None'}
Missing Skills: {', '.join(score.missing_skills) if score.missing_skills else 'None'}"""

        return llm.generate_text(prompt, api_key)
    except Exception as e:
        print(f"{Fore.YELLOW}  [!] LLM reasoning failed for {score.name}, using template: {e}{Style.RESET_ALL}")
        return _generate_reasoning_template(score, rank)


def rank_candidates(scores: List[CandidateScore], api_key: Optional[str] = None) -> List[dict]:
    """Sort candidates by composite score and generate reasoning for each."""
    sorted_scores = sorted(scores, key=lambda x: x.composite_score, reverse=True)

    results = []
    for i, score in enumerate(sorted_scores, 1):
        if api_key:
            reasoning = _generate_reasoning_llm(score, i, api_key)
        else:
            reasoning = _generate_reasoning_template(score, i)

        score.reasoning = reasoning

        results.append({
            'rank': i,
            'name': score.name,
            'file': score.file_path,
            'composite_score': round(score.composite_score, 2),
            'semantic_score': round(score.semantic_score, 2),
            'skill_match_score': round(score.skill_match_score, 2),
            'experience_score': round(score.experience_score, 2),
            'education_score': round(score.education_score, 2),
            'matched_skills': score.matched_skills,
            'missing_skills': score.missing_skills,
            'reasoning': reasoning
        })

    return results
