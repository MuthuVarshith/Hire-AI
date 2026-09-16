"""Analytics engine for recruiter dashboard metrics."""
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from models import Candidate, Job, ScreeningResult, PipelineStatus
from datetime import datetime, timedelta


class AnalyticsService:
    """Service for calculating hiring analytics and metrics."""

    def __init__(self, session: Session):
        self.session = session

    def get_dashboard_metrics(self, job_id: Optional[int] = None) -> Dict[str, Any]:
        """Get overall dashboard metrics."""
        return {
            "total_screened": self.get_total_screened(job_id),
            "shortlisted": self.get_candidates_by_status(PipelineStatus.SHORTLISTED, job_id),
            "in_interview": self.get_candidates_by_status(PipelineStatus.INTERVIEW, job_id),
            "offers": self.get_candidates_by_status(PipelineStatus.OFFER, job_id),
            "hired": self.get_candidates_by_status(PipelineStatus.HIRED, job_id),
            "rejected": self.get_candidates_by_status(PipelineStatus.REJECTED, job_id),
            "average_score": self.get_average_screening_score(job_id),
            "score_distribution": self.get_score_distribution(job_id),
            "pipeline_stages": self.get_candidates_by_pipeline_stage(job_id),
            "candidates_by_job": self.get_candidates_by_job(),
            "skill_gaps": self.get_skill_gap_analysis(job_id),
            "top_matched_skills": self.get_most_common_matched_skills(job_id),
            "shortlist_rate": self.get_shortlist_rate(job_id),
        }

    def get_total_screened(self, job_id: Optional[int] = None) -> int:
        """Get total number of screened candidates."""
        query = self.session.query(func.count(Candidate.id))
        if job_id:
            query = query.filter(Candidate.job_id == job_id)
        return query.scalar() or 0

    def get_candidates_by_status(self, status: PipelineStatus, job_id: Optional[int] = None) -> int:
        """Get count of candidates with given status."""
        query = self.session.query(func.count(Candidate.id)).filter(Candidate.status == status)
        if job_id:
            query = query.filter(Candidate.job_id == job_id)
        return query.scalar() or 0

    def get_average_screening_score(self, job_id: Optional[int] = None) -> float:
        """Get average composite score across all candidates."""
        query = self.session.query(func.avg(ScreeningResult.composite_score))
        if job_id:
            query = query.join(Candidate).filter(Candidate.job_id == job_id)
        avg = query.scalar()
        return round(float(avg), 2) if avg else 0.0

    def get_score_distribution(self, job_id: Optional[int] = None, bins: int = 5) -> Dict[str, int]:
        """Get distribution of scores in bins."""
        query = self.session.query(ScreeningResult.composite_score)
        if job_id:
            query = query.join(Candidate).filter(Candidate.job_id == job_id)

        scores = [s[0] for s in query.all()]
        if not scores:
            return {}

        distribution = {
            "80-100": 0,
            "60-80": 0,
            "40-60": 0,
            "20-40": 0,
            "0-20": 0,
        }

        for score in scores:
            if score >= 80:
                distribution["80-100"] += 1
            elif score >= 60:
                distribution["60-80"] += 1
            elif score >= 40:
                distribution["40-60"] += 1
            elif score >= 20:
                distribution["20-40"] += 1
            else:
                distribution["0-20"] += 1

        return distribution

    def get_candidates_by_job(self) -> Dict[str, int]:
        """Get candidate count per job."""
        jobs = self.session.query(Job).all()
        return {
            job.title: len(job.candidates)
            for job in jobs
        }

    def get_candidates_by_pipeline_stage(self, job_id: Optional[int] = None) -> Dict[str, int]:
        """Get candidate count at each pipeline stage."""
        stages = {}
        for status in PipelineStatus:
            count = self.get_candidates_by_status(status, job_id)
            stages[status.value] = count
        return stages

    def get_screening_volume_over_time(self, job_id: Optional[int] = None, days: int = 30) -> List[Dict]:
        """Get screening volume trend over the past N days."""
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        query = self.session.query(
            func.date(Candidate.created_at).label("date"),
            func.count(Candidate.id).label("count")
        ).filter(Candidate.created_at >= cutoff_date)

        if job_id:
            query = query.filter(Candidate.job_id == job_id)

        query = query.group_by(func.date(Candidate.created_at)).order_by("date")

        return [
            {
                # SQLite's date() returns a string; other databases return a date.
                "date": row[0] if isinstance(row[0], str) else row[0].isoformat(),
                "count": row[1]
            }
            for row in query.all()
        ]

    def get_top_candidates(self, job_id: Optional[int] = None, limit: int = 10) -> List[Dict]:
        """Get top-scoring candidates."""
        query = self.session.query(
            Candidate,
            ScreeningResult.composite_score
        ).join(ScreeningResult, ScreeningResult.candidate_id == Candidate.id)

        if job_id:
            query = query.filter(Candidate.job_id == job_id)

        query = query.order_by(ScreeningResult.composite_score.desc()).limit(limit)

        return [
            {
                "id": candidate.id,
                "name": candidate.name,
                "email": candidate.email,
                "score": round(score, 2),
                "status": candidate.status.value if candidate.status else None,
            }
            for candidate, score in query.all()
        ]

    def get_skill_gap_analysis(self, job_id: Optional[int] = None) -> Dict[str, int]:
        """Get most common missing skills across candidates."""
        query = self.session.query(ScreeningResult.missing_skills)
        if job_id:
            query = query.join(Candidate).filter(Candidate.job_id == job_id)

        skill_counts = {}
        for result in query.all():
            if result[0]:
                for skill in result[0]:
                    skill_counts[skill] = skill_counts.get(skill, 0) + 1

        # Sort by frequency
        return dict(sorted(skill_counts.items(), key=lambda x: x[1], reverse=True)[:10])

    def get_most_common_matched_skills(self, job_id: Optional[int] = None) -> Dict[str, int]:
        """Get most common matched skills across candidates."""
        query = self.session.query(ScreeningResult.matched_skills)
        if job_id:
            query = query.join(Candidate).filter(Candidate.job_id == job_id)

        skill_counts = {}
        for result in query.all():
            if result[0]:
                for skill in result[0]:
                    skill_counts[skill] = skill_counts.get(skill, 0) + 1

        # Sort by frequency
        return dict(sorted(skill_counts.items(), key=lambda x: x[1], reverse=True)[:10])

    def get_job_metrics(self, job_id: int) -> Dict[str, Any]:
        """Get detailed metrics for a specific job."""
        job = self.session.query(Job).filter(Job.id == job_id).first()
        if not job:
            return {}

        return {
            "job_id": job.id,
            "job_title": job.title,
            "total_applications": len(job.candidates),
            "shortlist_rate": self.get_shortlist_rate(job_id),
            "average_score": self.get_average_screening_score(job_id),
            "score_distribution": self.get_score_distribution(job_id),
            "pipeline_stage": self.get_candidates_by_pipeline_stage(job_id),
            "top_skills": self.get_most_common_matched_skills(job_id),
            "skill_gaps": self.get_skill_gap_analysis(job_id),
            "screening_timeline": self.get_screening_volume_over_time(job_id, days=30),
        }

    def get_shortlist_rate(self, job_id: Optional[int] = None) -> float:
        """Get percentage of screened candidates that are shortlisted."""
        total = self.get_total_screened(job_id)
        if total == 0:
            return 0.0

        shortlisted = self.get_candidates_by_status(PipelineStatus.SHORTLISTED, job_id)
        return round((shortlisted / total) * 100, 2)
