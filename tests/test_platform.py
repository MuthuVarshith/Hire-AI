"""Tests for the professional recruiter platform."""
import os
import sys
import pytest
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from models import (
    init_db, create_default_templates, Base, Job, Candidate,
    ScreeningResult, ScoringTemplate, PipelineStatus
)
from sqlalchemy.orm import sessionmaker
from duplicate_detection import is_potential_duplicate, find_similar_candidates
from analytics_service import AnalyticsService


@pytest.fixture
def test_db():
    """Create in-memory SQLite database for testing."""
    engine = init_db('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    create_default_templates(session)
    yield session
    session.close()


class TestModels:
    """Test database models."""

    def test_create_job(self, test_db):
        """Test creating a job."""
        job = Job(
            title="Python Developer",
            description_text="We need a Python dev",
            required_skills=["python", "django"],
            min_experience_years=3.0,
        )
        test_db.add(job)
        test_db.commit()
        test_db.refresh(job)

        assert job.id is not None
        assert job.title == "Python Developer"
        assert len(job.required_skills) == 2

    def test_create_candidate(self, test_db):
        """Test creating a candidate."""
        job = Job(
            title="Test Job",
            description_text="Test",
            required_skills=["python"],
        )
        test_db.add(job)
        test_db.commit()

        candidate = Candidate(
            name="John Doe",
            email="john@example.com",
            phone="555-1234",
            skills=["python", "django"],
            experience_years=5.0,
            job_id=job.id,
            status=PipelineStatus.SCREENED,
        )
        test_db.add(candidate)
        test_db.commit()
        test_db.refresh(candidate)

        assert candidate.id is not None
        assert candidate.name == "John Doe"
        assert candidate.job_id == job.id

    def test_create_screening_result(self, test_db):
        """Test creating a screening result."""
        job = Job(
            title="Test Job",
            description_text="Test",
        )
        test_db.add(job)
        test_db.commit()

        candidate = Candidate(
            name="Jane Smith",
            email="jane@example.com",
            job_id=job.id,
        )
        test_db.add(candidate)
        test_db.commit()

        screening = ScreeningResult(
            candidate_id=candidate.id,
            job_id=job.id,
            composite_score=85.5,
            semantic_score=80.0,
            skill_match_score=90.0,
            experience_score=80.0,
            education_score=90.0,
            matched_skills=["python"],
            missing_skills=["docker"],
        )
        test_db.add(screening)
        test_db.commit()
        test_db.refresh(screening)

        assert screening.id is not None
        assert screening.composite_score == 85.5

    def test_scoring_template_weights(self, test_db):
        """Test scoring template weight validation."""
        template = ScoringTemplate(
            name="Test Template",
            semantic_weight=0.40,
            skill_weight=0.30,
            experience_weight=0.15,
            education_weight=0.15,
        )
        assert template.validate_weights() is True

        template.semantic_weight = 0.50
        assert template.validate_weights() is False

    def test_default_templates_created(self, test_db):
        """Test that default templates are created on init."""
        templates = test_db.query(ScoringTemplate).all()
        assert len(templates) >= 1
        assert any(t.name == "Default" for t in templates)
        assert any(t.is_default for t in templates)


class TestDuplicateDetection:
    """Test duplicate candidate detection."""

    def test_exact_email_match(self, test_db):
        """Test exact email duplicate detection."""
        job = Job(title="Test", description_text="Test")
        test_db.add(job)
        test_db.commit()

        candidate1 = Candidate(
            name="John Doe",
            email="john@example.com",
            job_id=job.id,
        )
        test_db.add(candidate1)
        test_db.commit()

        is_dup, existing = is_potential_duplicate(
            test_db,
            email="john@example.com",
            job_id=job.id
        )

        assert is_dup is True
        assert existing.id == candidate1.id

    def test_exact_phone_match(self, test_db):
        """Test exact phone duplicate detection."""
        job = Job(title="Test", description_text="Test")
        test_db.add(job)
        test_db.commit()

        candidate1 = Candidate(
            name="Jane Doe",
            phone="555-1234",
            job_id=job.id,
        )
        test_db.add(candidate1)
        test_db.commit()

        is_dup, existing = is_potential_duplicate(
            test_db,
            phone="555-1234",
            job_id=job.id
        )

        assert is_dup is True
        assert existing.id == candidate1.id

    def test_no_duplicate(self, test_db):
        """Test when no duplicate exists."""
        is_dup, existing = is_potential_duplicate(
            test_db,
            email="nonexistent@example.com",
        )

        assert is_dup is False
        assert existing is None

    def test_fuzzy_name_matching(self, test_db):
        """Test fuzzy name matching."""
        job = Job(title="Test", description_text="Test")
        test_db.add(job)
        test_db.commit()

        candidate1 = Candidate(
            name="John Michael Doe",
            job_id=job.id,
        )
        test_db.add(candidate1)
        test_db.commit()

        similar = find_similar_candidates(test_db, name="John M Doe", threshold=80)
        assert len(similar) > 0


class TestAnalytics:
    """Test analytics service."""

    def test_total_screened(self, test_db):
        """Test total screened count."""
        job = Job(title="Test", description_text="Test")
        test_db.add(job)
        test_db.commit()

        candidates = [
            Candidate(name=f"Candidate {i}", job_id=job.id)
            for i in range(5)
        ]
        test_db.add_all(candidates)
        test_db.commit()

        analytics = AnalyticsService(test_db)
        total = analytics.get_total_screened(job.id)

        assert total == 5

    def test_candidates_by_status(self, test_db):
        """Test candidates by status count."""
        job = Job(title="Test", description_text="Test")
        test_db.add(job)
        test_db.commit()

        for i in range(3):
            candidate = Candidate(
                name=f"Candidate {i}",
                job_id=job.id,
                status=PipelineStatus.SHORTLISTED if i < 2 else PipelineStatus.SCREENED
            )
            test_db.add(candidate)
        test_db.commit()

        analytics = AnalyticsService(test_db)
        shortlisted = analytics.get_candidates_by_status(PipelineStatus.SHORTLISTED, job.id)

        assert shortlisted == 2

    def test_average_screening_score(self, test_db):
        """Test average score calculation."""
        job = Job(title="Test", description_text="Test")
        test_db.add(job)
        test_db.commit()

        candidate = Candidate(name="Test", job_id=job.id)
        test_db.add(candidate)
        test_db.commit()

        screening = ScreeningResult(
            candidate_id=candidate.id,
            job_id=job.id,
            composite_score=80.0,
        )
        test_db.add(screening)
        test_db.commit()

        analytics = AnalyticsService(test_db)
        avg_score = analytics.get_average_screening_score(job.id)

        assert avg_score == 80.0

    def test_score_distribution(self, test_db):
        """Test score distribution calculation."""
        job = Job(title="Test", description_text="Test")
        test_db.add(job)
        test_db.commit()

        scores = [95, 75, 45, 25]
        for i, score in enumerate(scores):
            candidate = Candidate(name=f"Candidate {i}", job_id=job.id)
            test_db.add(candidate)
            test_db.commit()

            screening = ScreeningResult(
                candidate_id=candidate.id,
                job_id=job.id,
                composite_score=score,
            )
            test_db.add(screening)
        test_db.commit()

        analytics = AnalyticsService(test_db)
        dist = analytics.get_score_distribution(job.id)

        assert dist["80-100"] == 1
        assert dist["60-80"] == 1
        assert dist["40-60"] == 1
        assert dist["20-40"] == 1

    def test_dashboard_metrics(self, test_db):
        """Test complete dashboard metrics."""
        job = Job(title="Test", description_text="Test")
        test_db.add(job)
        test_db.commit()

        candidate = Candidate(name="Test", job_id=job.id)
        test_db.add(candidate)
        test_db.commit()

        analytics = AnalyticsService(test_db)
        metrics = analytics.get_dashboard_metrics(job.id)

        assert "total_screened" in metrics
        assert "shortlisted" in metrics
        assert "average_score" in metrics
        assert metrics["total_screened"] == 1


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
