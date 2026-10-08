"""Scoring engine — computes multi-signal relevance scores for candidates."""
import numpy as np
from typing import List, Tuple
from config import ResumeProfile, JobRequirements, CandidateScore, WEIGHTS, EMBEDDING_MODEL

try:
    from colorama import Fore, Style
except ImportError:
    class Fore:
        RED = YELLOW = GREEN = CYAN = ""
    class Style:
        RESET_ALL = ""


_cached_model = None


def load_embedding_model():
    """Load and cache the SentenceTransformer embedding model."""
    global _cached_model
    if _cached_model is not None:
        return _cached_model
    try:
        from sentence_transformers import SentenceTransformer
        print(f"{Fore.CYAN}Loading embedding model '{EMBEDDING_MODEL}'...{Style.RESET_ALL}")
        _cached_model = SentenceTransformer(EMBEDDING_MODEL)
        print(f"{Fore.GREEN}[OK] Embedding model loaded successfully.{Style.RESET_ALL}")
        return _cached_model
    except Exception as e:
        print(f"{Fore.RED}[ERROR] Failed to load embedding model: {e}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}   The agent will still work but semantic scoring will be disabled.{Style.RESET_ALL}")
        return None


def compute_semantic_score(resume_text: str, jd_text: str, model) -> float:
    """Compute cosine similarity between resume and JD embeddings. Returns [0, 100]."""
    if not model or not resume_text or not jd_text:
        return 0.0
    try:
        emb_resume = model.encode([resume_text])[0]
        emb_jd = model.encode([jd_text])[0]

        # Cosine similarity
        dot = np.dot(emb_resume, emb_jd)
        norm = np.linalg.norm(emb_resume) * np.linalg.norm(emb_jd)
        if norm == 0:
            return 0.0
        sim = dot / norm

        # Scale to [0, 100] — cosine sim for text is typically in [0.2, 0.8] range
        return max(0.0, min(100.0, float(sim) * 100))
    except Exception as e:
        print(f"{Fore.RED}Semantic score error: {e}{Style.RESET_ALL}")
        return 0.0


def compute_skill_match_score(resume_skills: List[str], required_skills: List[str], model) -> Tuple[float, List[str], List[str]]:
    """Compute skill match score using exact + semantic matching.

    Returns (score [0-100], matched_skills, missing_skills).
    """
    if not required_skills:
        return 100.0, [], []
    if not resume_skills:
        return 0.0, [], list(required_skills)

    matched = []
    missing = []

    # Pre-compute embeddings for semantic matching
    req_embs = None
    res_embs = None
    try:
        if model:
            res_embs = model.encode(resume_skills)
            req_embs = model.encode(required_skills)
    except Exception:
        model = None

    for i, req in enumerate(required_skills):
        found = False

        # 1. Exact substring match (case-insensitive)
        for res in resume_skills:
            if req.lower() in res.lower() or res.lower() in req.lower():
                found = True
                break

        # 2. Semantic similarity match (threshold > 0.7)
        if not found and model and req_embs is not None and res_embs is not None:
            for j in range(len(resume_skills)):
                dot = np.dot(req_embs[i], res_embs[j])
                norm = np.linalg.norm(req_embs[i]) * np.linalg.norm(res_embs[j])
                if norm > 0:
                    sim = dot / norm
                    if sim > 0.7:
                        found = True
                        break

        if found:
            matched.append(req)
        else:
            missing.append(req)

    score = (len(matched) / len(required_skills)) * 100
    return score, matched, missing


def compute_experience_score(candidate_years: float, required_years: float) -> float:
    """Compute experience score. Returns [0, 100].

    Full score if candidate meets or exceeds requirement.
    Proportional score otherwise.
    """
    if required_years <= 0:
        return 100.0
    if candidate_years >= required_years:
        return 100.0
    if candidate_years <= 0:
        return 0.0

    return max(0.0, min(100.0, (candidate_years / required_years) * 100))


def compute_education_score(candidate_education: List[dict], required_education: str) -> float:
    """Compute education score based on degree hierarchy. Returns [0, 100].

    Degree hierarchy: PhD(100) > Master's(85) > Bachelor's(70) > Associate's(50) > Bootcamp(30)
    """
    hierarchy = {
        'phd': 100, 'doctorate': 100, 'ph.d': 100,
        'master': 85, 'm.s': 85, 'm.tech': 85, 'mba': 85, 'm.eng': 85,
        'bachelor': 70, 'b.s': 70, 'b.tech': 70, 'b.a': 70, 'b.eng': 70,
        'associate': 50,
        'bootcamp': 30, 'certificate': 30, 'diploma': 30,
        'high school': 10,
    }

    # Determine required level
    req_level = 0
    req_lower = required_education.lower() if required_education else ""
    for kw, val in hierarchy.items():
        if kw in req_lower:
            req_level = val
            break
    if req_level == 0:
        req_level = 70  # Default to Bachelor's

    # Determine candidate's highest level
    cand_level = 0
    if not candidate_education:
        return 0.0

    for edu in candidate_education:
        degree = edu.get('degree', '').lower() if isinstance(edu, dict) else str(edu).lower()
        for kw, val in hierarchy.items():
            if kw in degree and val > cand_level:
                cand_level = val

    if cand_level >= req_level:
        return 100.0

    # One level below: 70%, otherwise proportional
    diff = req_level - cand_level
    if diff <= 15:
        return 70.0

    return max(0.0, min(100.0, (cand_level / req_level) * 100))


def score_candidate(resume: ResumeProfile, jd: JobRequirements, model) -> CandidateScore:
    """Compute all 4 scores and combine into a weighted composite score."""
    semantic = compute_semantic_score(resume.raw_text, jd.raw_text, model)
    skills_score, matched, missing = compute_skill_match_score(
        resume.skills, jd.required_skills, model
    )
    experience = compute_experience_score(resume.experience_years, jd.min_experience_years)
    education = compute_education_score(resume.education, jd.required_education)

    composite = (
        semantic * WEIGHTS["semantic"] +
        skills_score * WEIGHTS["skills"] +
        experience * WEIGHTS["experience"] +
        education * WEIGHTS["education"]
    )

    return CandidateScore(
        name=resume.name,
        file_path=resume.file_path,
        semantic_score=round(semantic, 2),
        skill_match_score=round(skills_score, 2),
        experience_score=round(experience, 2),
        education_score=round(education, 2),
        composite_score=round(composite, 2),
        matched_skills=matched,
        missing_skills=missing,
        reasoning=""
    )
