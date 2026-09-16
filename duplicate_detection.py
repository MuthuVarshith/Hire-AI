"""Duplicate candidate detection using email, phone, and fuzzy name matching."""
from fuzzywuzzy import fuzz
from sqlalchemy.orm import Session
from models import Candidate
from typing import List, Tuple, Optional


def normalize_email(email: str) -> str:
    """Normalize email for comparison."""
    if not email:
        return ""
    return email.lower().strip()


def normalize_phone(phone: str) -> str:
    """Remove common phone formatting characters for comparison."""
    if not phone:
        return ""
    return "".join(c for c in phone if c.isdigit())


def is_potential_duplicate(
    session: Session,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    name: Optional[str] = None,
    job_id: Optional[int] = None,
) -> Tuple[bool, Optional[Candidate]]:
    """
    Check if a candidate with the same email/phone already exists.

    Returns:
        (is_duplicate: bool, existing_candidate: Candidate or None)
    """
    query = session.query(Candidate)

    # If job_id specified, only check within that job
    if job_id:
        query = query.filter(Candidate.job_id == job_id)

    # Email match (exact)
    if email:
        normalized_email = normalize_email(email)
        existing = query.filter(Candidate.email == normalized_email).first()
        if existing:
            return True, existing

    # Phone match (exact after normalization)
    if phone:
        normalized_phone = normalize_phone(phone)
        if normalized_phone:  # Only check if phone has digits
            all_candidates = session.query(Candidate).all()
            for candidate in all_candidates:
                if candidate.phone and normalize_phone(candidate.phone) == normalized_phone:
                    if not job_id or candidate.job_id == job_id:
                        return True, candidate

    # Name fuzzy match (high threshold)
    if name:
        all_candidates = query.all()
        for candidate in all_candidates:
            if candidate.name:
                similarity = fuzz.token_set_ratio(name.lower(), candidate.name.lower())
                if similarity > 90:  # 90% match is likely same person
                    return True, candidate

    return False, None


def find_similar_candidates(
    session: Session,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    name: Optional[str] = None,
    threshold: int = 80,
) -> List[Candidate]:
    """
    Find all potentially similar candidates using fuzzy matching.

    Args:
        session: Database session
        email: Candidate email
        phone: Candidate phone
        name: Candidate name
        threshold: Fuzzy match threshold (0-100)

    Returns:
        List of similar candidates
    """
    similar = []
    all_candidates = session.query(Candidate).all()

    for candidate in all_candidates:
        match_score = 0
        weights = 0

        # Email exact match
        if email and candidate.email:
            if normalize_email(email) == normalize_email(candidate.email):
                match_score += 100
                weights += 1

        # Phone exact match
        if phone and candidate.phone:
            norm_phone = normalize_phone(phone)
            norm_candidate_phone = normalize_phone(candidate.phone)
            if norm_phone and norm_phone == norm_candidate_phone:
                match_score += 100
                weights += 1

        # Name fuzzy match
        if name and candidate.name:
            name_sim = fuzz.token_set_ratio(name.lower(), candidate.name.lower())
            match_score += name_sim
            weights += 1

        if weights > 0:
            avg_score = match_score / weights
            if avg_score >= threshold:
                similar.append((candidate, int(avg_score)))

    # Sort by score descending
    similar.sort(key=lambda x: x[1], reverse=True)
    return [c for c, _ in similar]
