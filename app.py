"""Flask backend for the Recruiting Agent platform."""
import os
import re
import sys
import uuid
import logging
from pathlib import Path
from dotenv import load_dotenv
from functools import wraps

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker, Session
from werkzeug.exceptions import HTTPException
from werkzeug.utils import secure_filename

# Load environment variables
load_dotenv()

# Import our modules
import ask
import embeddings
import indexing
import llm
import scorer
import screening as scoring_inputs
import config as cfg
import jd_parser
import resume_parser
import interview_generator
import duplicate_detection
from models import (
    create_default_templates, Job, Candidate, ScreeningResult, ScoringTemplate, PipelineStatus
)
from analytics_service import AnalyticsService
from database import create_database_engine

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Flask app setup
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = int(os.getenv('MAX_RESUME_SIZE_MB', 10)) * 1024 * 1024
app.config['JSON_SORT_KEYS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

CORS(app, resources={r"/api/*": {"origins": "*"}})

# Database setup
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///recruiting_agent.db')
engine = create_database_engine(DATABASE_URL)  # applies migrations
SessionLocal = sessionmaker(bind=engine)

# Create default templates on startup
try:
    with SessionLocal() as session:
        create_default_templates(session)
except Exception as e:
    logger.warning(f"Could not create default templates: {e}")

# Constants
ALLOWED_RESUME_EXTENSIONS = set(os.getenv('ALLOWED_RESUME_EXTENSIONS', '.txt,.pdf,.docx').split(','))
ALLOWED_JD_EXTENSIONS = {'.txt', '.pdf', '.docx'}

# <32 hex chars>_<name> today; <YYYYmmdd_HHMMSS>_<name> for files stored by older versions.
_STORED_NAME = re.compile(r"^(?:[0-9a-f]{32}|\d{8}_\d{6})_(.+)$")


def storage_name(original_name: str) -> str:
    """Unique on-disk name for an upload: <uuid4 hex>_<sanitized original name>.

    The random prefix means two uploads can never share a path. The validated
    extension is always kept, because secure_filename drops non-ASCII names
    entirely and the parser picks PDF/DOCX/text reading from the suffix.
    """
    path = Path(original_name)
    stem = secure_filename(path.stem) or "resume"
    return f"{uuid.uuid4().hex}_{stem}{path.suffix.lower()}"


def download_name(stored_name: str) -> str:
    """The name a stored file is downloaded as: its sanitized original name."""
    match = _STORED_NAME.match(stored_name)
    return match.group(1) if match else stored_name


def error_response(action: str):
    """Response for an exception caught in a request handler. Call from inside `except`.

    Full details (message and traceback) go to the server log only; clients never see
    exception text, SQL or file paths. Client errors Werkzeug raises while reading the
    request (413 too large, 415 not JSON) keep their status and standard public message.
    """
    exc = sys.exc_info()[1]
    if isinstance(exc, HTTPException) and exc.code is not None and exc.code < 500:
        logger.info("Rejected request while %s: HTTP %s", action, exc.code)
        return jsonify({"error": exc.description}), exc.code
    logger.exception("Unexpected error while %s", action)
    return jsonify({"error": "Internal server error"}), 500


def _index_safely(db: Session, index, record, what: str) -> None:
    """Chunk and embed a record that is already committed. A failure is logged, never raised:
    the upload or job is saved either way, and `python -m indexing --reindex` fills the gap."""
    try:
        index(db, record)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Indexing failed for %s; run `python -m indexing --reindex` to retry", what)


def _remove_upload(stored_name: str) -> None:
    """Delete an uploaded file; a missing file is fine, other errors are logged, not raised."""
    try:
        os.remove(os.path.join(app.config['UPLOAD_FOLDER'], stored_name))
    except FileNotFoundError:
        pass
    except OSError:
        logger.exception("Could not delete uploaded file %s", stored_name)


def get_db() -> Session:
    """Get database session."""
    return SessionLocal()


def require_job(f):
    """Decorator to require job_id parameter."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Accept job_id from the query string, a form field, or a JSON body.
        # get_json(silent=True) returns None for multipart/form-data uploads
        # instead of raising 415.
        payload = request.get_json(silent=True) or {}
        job_id = request.args.get('job_id') or request.form.get('job_id') or payload.get('job_id')
        if not job_id:
            return jsonify({"error": "job_id is required"}), 400
        try:
            job_id = int(job_id)
        except (ValueError, TypeError):
            return jsonify({"error": "job_id must be an integer"}), 400

        db = get_db()
        job = db.query(Job).filter(Job.id == job_id).first()
        db.close()

        if not job:
            return jsonify({"error": f"Job {job_id} not found"}), 404

        kwargs['job_id'] = job_id
        return f(*args, **kwargs)
    return decorated_function


# ============================================================================
# JOB ENDPOINTS
# ============================================================================

@app.route('/api/jobs', methods=['POST'])
def create_job():
    """Create a new job posting."""
    db = get_db()
    try:
        data = request.json or {}

        if not data.get('title'):
            return jsonify({"error": "title is required"}), 400

        if not data.get('description_text'):
            return jsonify({"error": "description_text is required"}), 400

        # Parse JD to extract structured requirements
        api_key = cfg.get_api_key()
        jd_obj = jd_parser.parse_jd_text(data['description_text'], api_key)

        # Create job record
        job = Job(
            title=data.get('title') or jd_obj.title,
            description_text=data['description_text'],
            required_skills=jd_obj.required_skills,
            preferred_skills=jd_obj.preferred_skills,
            min_experience_years=jd_obj.min_experience_years,
            required_education=jd_obj.required_education,
            responsibilities=jd_obj.responsibilities,
            scoring_template_id=data.get('scoring_template_id'),
        )

        db.add(job)
        db.commit()
        db.refresh(job)
        _index_safely(db, indexing.index_job, job, f"job {job.id}")

        logger.info(f"Created job {job.id}: {job.title}")
        return jsonify(job.to_dict()), 201

    except Exception:
        db.rollback()
        return error_response("creating job")
    finally:
        db.close()


@app.route('/api/jobs', methods=['GET'])
def list_jobs():
    """List all jobs."""
    db = get_db()
    try:
        jobs = db.query(Job).order_by(Job.created_at.desc()).all()
        return jsonify([job.to_dict() for job in jobs]), 200
    finally:
        db.close()


@app.route('/api/jobs/<int:job_id>', methods=['GET'])
def get_job(job_id):
    """Get a specific job."""
    db = get_db()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return jsonify({"error": "Job not found"}), 404
        return jsonify(job.to_dict()), 200
    finally:
        db.close()


@app.route('/api/jobs/<int:job_id>', methods=['PUT'])
def update_job(job_id):
    """Update a job."""
    db = get_db()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return jsonify({"error": "Job not found"}), 404

        data = request.json or {}
        if 'title' in data:
            job.title = data['title']
        description_changed = 'description_text' in data and data['description_text'] != job.description_text
        if 'description_text' in data:
            job.description_text = data['description_text']
        if 'scoring_template_id' in data:
            job.scoring_template_id = data['scoring_template_id']

        db.commit()
        if description_changed:
            _index_safely(db, indexing.index_job, job, f"job {job_id}")
        logger.info(f"Updated job {job_id}")
        return jsonify(job.to_dict()), 200

    except Exception:
        db.rollback()
        return error_response("updating job")
    finally:
        db.close()


@app.route('/api/jobs/<int:job_id>', methods=['DELETE'])
def delete_job(job_id):
    """Delete a job and all associated candidates."""
    db = get_db()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return jsonify({"error": "Job not found"}), 404

        resume_files = [c.resume_filename for c in job.candidates if c.resume_filename]
        db.delete(job)
        db.commit()
        # Only after the commit: if the delete fails, candidates still exist and need their files.
        for name in resume_files:
            _remove_upload(name)
        logger.info(f"Deleted job {job_id} and {len(resume_files)} resume file(s)")
        return jsonify({"message": "Job deleted"}), 200

    except Exception:
        db.rollback()
        return error_response("deleting job")
    finally:
        db.close()


# ============================================================================
# CANDIDATE ENDPOINTS
# ============================================================================

@app.route('/api/candidates', methods=['POST'])
@require_job
def upload_candidate(job_id):
    """Upload a resume and create candidate record."""
    db = get_db()
    try:
        if 'resume' not in request.files:
            return jsonify({"error": "resume file is required"}), 400

        file = request.files['resume']
        if not file or file.filename == '':
            return jsonify({"error": "No resume file provided"}), 400

        # Validate file extension
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in ALLOWED_RESUME_EXTENSIONS:
            return jsonify({"error": f"File type {file_ext} not allowed"}), 400

        # Save file
        filename = storage_name(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        # Parse resume (resolves the LLM key internally, falls back to regex)
        resume_profile = resume_parser.parse_resume(filepath)

        # Check for duplicates
        is_dup, existing = duplicate_detection.is_potential_duplicate(
            db,
            email=resume_profile.email,
            phone=resume_profile.phone,
            name=resume_profile.name,
            job_id=job_id
        )

        if is_dup and existing:
            os.remove(filepath)  # Clean up file
            return jsonify({
                "error": "Duplicate candidate detected",
                "existing_candidate": {
                    "id": existing.id,
                    "name": existing.name,
                    "email": existing.email,
                    "status": existing.status.value if existing.status else None
                }
            }), 409

        # Create candidate
        candidate = Candidate(
            name=resume_profile.name,
            email=resume_profile.email,
            phone=resume_profile.phone,
            resume_filename=filename,
            resume_text=resume_profile.raw_text,
            skills=resume_profile.skills,
            experience_years=resume_profile.experience_years,
            education=resume_profile.education,
            work_history=resume_profile.work_history,
            job_id=job_id,
            status=PipelineStatus.SCREENED,
        )

        db.add(candidate)
        db.commit()
        db.refresh(candidate)
        _index_safely(db, indexing.index_candidate, candidate, f"candidate {candidate.id}")

        logger.info(f"Created candidate {candidate.id}: {candidate.name}")
        return jsonify(candidate.to_dict(include_screening=False)), 201

    except Exception:
        db.rollback()
        return error_response("uploading candidate")
    finally:
        db.close()


@app.route('/api/candidates', methods=['GET'])
def list_candidates():
    """List candidates, optionally filtered by job_id and status."""
    db = get_db()
    try:
        query = db.query(Candidate)

        job_id = request.args.get('job_id')
        if job_id:
            try:
                job_id = int(job_id)
                query = query.filter(Candidate.job_id == job_id)
            except ValueError:
                pass

        status = request.args.get('status')
        if status:
            try:
                status_enum = PipelineStatus[status.upper()]
                query = query.filter(Candidate.status == status_enum)
            except KeyError:
                pass

        # Sorting
        sort_by = request.args.get('sort_by', 'created_at')
        if sort_by == 'score':
            query = query.join(ScreeningResult).order_by(ScreeningResult.composite_score.desc())
        else:
            query = query.order_by(Candidate.created_at.desc())

        candidates = query.all()
        return jsonify([c.to_dict(include_screening=True) for c in candidates]), 200

    finally:
        db.close()


@app.route('/api/candidates/<int:candidate_id>', methods=['GET'])
def get_candidate(candidate_id):
    """Get a specific candidate with full details."""
    db = get_db()
    try:
        candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
        if not candidate:
            return jsonify({"error": "Candidate not found"}), 404

        data = candidate.to_dict(include_screening=True)

        # Include all screening results
        screenings = db.query(ScreeningResult).filter(ScreeningResult.candidate_id == candidate_id).all()
        data['screening_history'] = [s.to_dict() for s in screenings]

        return jsonify(data), 200
    finally:
        db.close()


@app.route('/api/candidates/<int:candidate_id>', methods=['PUT'])
def update_candidate(candidate_id):
    """Update candidate status or notes."""
    db = get_db()
    try:
        candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
        if not candidate:
            return jsonify({"error": "Candidate not found"}), 404

        data = request.get_json(silent=True) or {}

        if 'status' in data:
            try:
                status_enum = PipelineStatus[data['status'].upper()]
                candidate.status = status_enum
            except KeyError:
                return jsonify({"error": f"Invalid status: {data['status']}"}), 400

        if 'notes' in data:
            candidate.notes = data['notes']

        db.commit()
        logger.info(f"Updated candidate {candidate_id}")
        return jsonify(candidate.to_dict()), 200

    except Exception:
        db.rollback()
        return error_response("updating candidate")
    finally:
        db.close()


@app.route('/api/candidates/<int:candidate_id>/resume', methods=['GET'])
def download_resume(candidate_id):
    """Download candidate's resume file."""
    db = get_db()
    try:
        candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
        if not candidate or not candidate.resume_filename:
            return jsonify({"error": "Resume not found"}), 404

        filepath = os.path.join(app.config['UPLOAD_FOLDER'], candidate.resume_filename)
        if not os.path.exists(filepath):
            return jsonify({"error": "Resume file not found on disk"}), 404

        return send_file(filepath, as_attachment=True, download_name=download_name(candidate.resume_filename))

    finally:
        db.close()


@app.route('/api/candidates/<int:candidate_id>', methods=['DELETE'])
def delete_candidate(candidate_id):
    """Delete a candidate and associated data."""
    db = get_db()
    try:
        candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
        if not candidate:
            return jsonify({"error": "Candidate not found"}), 404

        # Delete resume file if exists
        if candidate.resume_filename:
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], candidate.resume_filename)
            if os.path.exists(filepath):
                os.remove(filepath)

        db.delete(candidate)
        db.commit()
        logger.info(f"Deleted candidate {candidate_id}")
        return jsonify({"message": "Candidate deleted"}), 200

    except Exception:
        db.rollback()
        return error_response("deleting candidate")
    finally:
        db.close()


# ============================================================================
# SCREENING & SCORING ENDPOINTS
# ============================================================================

@app.route('/api/screen/<int:candidate_id>/<int:job_id>', methods=['POST'])
def screen_candidate(candidate_id, job_id):
    """Score a candidate against a job."""
    db = get_db()
    try:
        candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
        if not candidate:
            return jsonify({"error": "Candidate not found"}), 404

        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return jsonify({"error": "Job not found"}), 404

        # Build the scorer inputs from the stored rows and score with the job's template weights.
        # screening.py is shared with the agent's score_candidate tool, so both compute the same numbers.
        resume_prof, job_req, score_result = scoring_inputs.compute_score(
            db, candidate, job, scorer.load_embedding_model())

        # Generate strengths and gaps
        strengths = []
        if score_result.matched_skills:
            strengths.append(f"Strong skills match: {', '.join(score_result.matched_skills[:3])}")
        if score_result.experience_score >= 100:
            strengths.append(f"Exceeds experience requirement ({resume_prof.experience_years} years)")
        if score_result.education_score >= 100:
            strengths.append("Meets or exceeds education requirements")

        skill_gaps = []
        if score_result.missing_skills:
            skill_gaps.append(f"Missing required skills: {', '.join(score_result.missing_skills[:3])}")
        if score_result.experience_score < 100 and resume_prof.experience_years > 0:
            skill_gaps.append(f"Below experience requirement ({resume_prof.experience_years} vs {job_req.min_experience_years} years)")

        # Generate AI reasoning. The body is optional, so parse it leniently.
        api_key = cfg.get_api_key()
        options = request.get_json(silent=True) or {}
        use_llm = bool(api_key) and options.get('use_llm', True)

        if use_llm and api_key:
            try:
                reasoning = _generate_candidate_explanation(
                    candidate.name,
                    score_result,
                    job.title,
                    resume_prof.experience_years,
                    job.min_experience_years
                )
            except Exception as e:
                logger.warning(f"Error generating LLM explanation: {e}")
                reasoning = f"Composite score {score_result.composite_score:.1f}/100. " + ". ".join(strengths) if strengths else "No significant strengths. "
        else:
            reasoning = f"Composite score {score_result.composite_score:.1f}/100. " + ". ".join(strengths) if strengths else "No significant strengths."

        # Create screening result
        screening = ScreeningResult(
            candidate_id=candidate_id,
            job_id=job_id,
            scoring_template_id=job.scoring_template_id,
            composite_score=score_result.composite_score,
            semantic_score=score_result.semantic_score,
            skill_match_score=score_result.skill_match_score,
            experience_score=score_result.experience_score,
            education_score=score_result.education_score,
            matched_skills=score_result.matched_skills,
            missing_skills=score_result.missing_skills,
            matched_preferred_skills=[s for s in (job.preferred_skills or []) if s in (candidate.skills or [])],
            reasoning=reasoning,
            strengths=strengths,
            skill_gaps=skill_gaps,
        )

        # Update candidate status
        candidate.status = PipelineStatus.SCREENED
        candidate.job_id = job_id

        db.add(screening)
        db.commit()
        db.refresh(screening)

        logger.info(f"Screened candidate {candidate_id} against job {job_id}: score {score_result.composite_score:.2f}")
        return jsonify(screening.to_dict()), 201

    except Exception:
        db.rollback()
        return error_response("screening candidate")
    finally:
        db.close()


def _generate_candidate_explanation(name: str, score_result: cfg.CandidateScore, job_title: str, cand_years: float, req_years: float) -> str:
    """Generate AI explanation for screening results."""
    try:
        api_key = cfg.get_api_key()

        prompt = f"""Write a concise 2-3 sentence recruiter-friendly explanation for this screening result. Be specific.

Candidate: {name}
Job: {job_title}
Composite Score: {score_result.composite_score:.1f}/100
Semantic Match: {score_result.semantic_score:.1f}/100
Skill Match: {score_result.skill_match_score:.1f}/100
Experience: {score_result.experience_score:.1f}/100 (candidate has {cand_years} years, role requires {req_years})
Education: {score_result.education_score:.1f}/100
Matched Skills: {', '.join(score_result.matched_skills) if score_result.matched_skills else 'None'}
Missing Skills: {', '.join(score_result.missing_skills) if score_result.missing_skills else 'None'}

Provide clear, actionable insight for recruiters. No markdown."""

        return llm.generate_text(prompt, api_key)
    except Exception as e:
        logger.warning(f"LLM explanation failed: {e}")
        return ""


@app.route('/api/screening/<int:screening_id>', methods=['GET'])
def get_screening_result(screening_id):
    """Get a specific screening result."""
    db = get_db()
    try:
        screening = db.query(ScreeningResult).filter(ScreeningResult.id == screening_id).first()
        if not screening:
            return jsonify({"error": "Screening result not found"}), 404
        return jsonify(screening.to_dict()), 200
    finally:
        db.close()


# ============================================================================
# INTERVIEW QUESTIONS ENDPOINT
# ============================================================================

@app.route('/api/candidates/<int:candidate_id>/jobs/<int:job_id>/interview-questions', methods=['GET'])
def get_interview_questions(candidate_id, job_id):
    """Get AI-generated interview questions for a candidate."""
    db = get_db()
    try:
        candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
        if not candidate:
            return jsonify({"error": "Candidate not found"}), 404

        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return jsonify({"error": "Job not found"}), 404

        # Get screening result
        screening = db.query(ScreeningResult).filter(
            (ScreeningResult.candidate_id == candidate_id) &
            (ScreeningResult.job_id == job_id)
        ).order_by(ScreeningResult.created_at.desc()).first()

        if not screening:
            return jsonify({"error": "No screening result found for this candidate-job pair"}), 404

        # Generate questions
        use_llm = cfg.get_api_key() is not None and request.args.get('use_llm', 'true').lower() == 'true'
        questions = interview_generator.generate_interview_questions(
            candidate, job, screening, use_llm=use_llm
        )

        return jsonify(questions), 200

    except Exception:
        return error_response("generating interview questions")
    finally:
        db.close()


# ============================================================================
# SCORING TEMPLATES ENDPOINTS
# ============================================================================

def _template_name_taken(db: Session, name: str) -> bool:
    return db.query(ScoringTemplate.id).filter(ScoringTemplate.name == name).first() is not None


def _duplicate_template_response():
    return jsonify({"error": "A scoring template with this name already exists"}), 409


@app.route('/api/scoring-templates', methods=['POST'])
def create_scoring_template():
    """Create a new scoring template."""
    db = get_db()
    try:
        data = request.json or {}

        if not data.get('name'):
            return jsonify({"error": "name is required"}), 400

        # Validate weights
        semantic = float(data.get('semantic_weight', 0.40))
        skill = float(data.get('skill_weight', 0.30))
        exp = float(data.get('experience_weight', 0.15))
        edu = float(data.get('education_weight', 0.15))

        if abs((semantic + skill + exp + edu) - 1.0) > 1e-9:
            return jsonify({"error": "Weights must sum to 1.0"}), 400

        if _template_name_taken(db, data['name']):
            return _duplicate_template_response()

        template = ScoringTemplate(
            name=data['name'],
            description=data.get('description', ''),
            semantic_weight=semantic,
            skill_weight=skill,
            experience_weight=exp,
            education_weight=edu,
            is_default=data.get('is_default', False),
        )

        db.add(template)
        db.commit()
        db.refresh(template)

        logger.info(f"Created scoring template {template.id}: {template.name}")
        return jsonify(template.to_dict()), 201

    except ValueError as e:
        return jsonify({"error": f"Invalid weight value: {e}"}), 400
    except IntegrityError:
        # Backstop for two requests creating the same name at once; the pre-check covers the normal case.
        db.rollback()
        return _duplicate_template_response()
    except Exception:
        db.rollback()
        return error_response("creating template")
    finally:
        db.close()


@app.route('/api/scoring-templates', methods=['GET'])
def list_scoring_templates():
    """List all scoring templates."""
    db = get_db()
    try:
        templates = db.query(ScoringTemplate).order_by(ScoringTemplate.name).all()
        return jsonify([t.to_dict() for t in templates]), 200
    finally:
        db.close()


@app.route('/api/scoring-templates/<int:template_id>', methods=['GET'])
def get_scoring_template(template_id):
    """Get a specific scoring template."""
    db = get_db()
    try:
        template = db.query(ScoringTemplate).filter(ScoringTemplate.id == template_id).first()
        if not template:
            return jsonify({"error": "Template not found"}), 404
        return jsonify(template.to_dict()), 200
    finally:
        db.close()


@app.route('/api/scoring-templates/<int:template_id>', methods=['PUT'])
def update_scoring_template(template_id):
    """Update a scoring template."""
    db = get_db()
    try:
        template = db.query(ScoringTemplate).filter(ScoringTemplate.id == template_id).first()
        if not template:
            return jsonify({"error": "Template not found"}), 404

        data = request.json or {}

        # Check before assigning: queries autoflush pending changes, which would hit the unique index.
        if 'name' in data and data['name'] != template.name and _template_name_taken(db, data['name']):
            return _duplicate_template_response()

        if 'name' in data:
            template.name = data['name']
        if 'description' in data:
            template.description = data['description']
        if 'semantic_weight' in data:
            template.semantic_weight = float(data['semantic_weight'])
        if 'skill_weight' in data:
            template.skill_weight = float(data['skill_weight'])
        if 'experience_weight' in data:
            template.experience_weight = float(data['experience_weight'])
        if 'education_weight' in data:
            template.education_weight = float(data['education_weight'])

        # Validate weights
        if not template.validate_weights():
            return jsonify({"error": "Weights must sum to 1.0"}), 400

        db.commit()
        logger.info(f"Updated template {template_id}")
        return jsonify(template.to_dict()), 200

    except ValueError as e:
        db.rollback()
        return jsonify({"error": f"Invalid weight value: {e}"}), 400
    except IntegrityError:
        db.rollback()
        return _duplicate_template_response()
    except Exception:
        db.rollback()
        return error_response("updating template")
    finally:
        db.close()


@app.route('/api/scoring-templates/<int:template_id>', methods=['DELETE'])
def delete_scoring_template(template_id):
    """Delete a scoring template."""
    db = get_db()
    try:
        template = db.query(ScoringTemplate).filter(ScoringTemplate.id == template_id).first()
        if not template:
            return jsonify({"error": "Template not found"}), 404

        if template.is_default:
            return jsonify({"error": "Cannot delete default template"}), 400

        db.delete(template)
        db.commit()
        logger.info(f"Deleted template {template_id}")
        return jsonify({"message": "Template deleted"}), 200

    except Exception:
        db.rollback()
        return error_response("deleting template")
    finally:
        db.close()


# ============================================================================
# ANALYTICS ENDPOINTS
# ============================================================================

@app.route('/api/analytics/dashboard', methods=['GET'])
def get_dashboard():
    """Get overall dashboard metrics."""
    db = get_db()
    try:
        analytics = AnalyticsService(db)
        job_id = request.args.get('job_id')
        if job_id:
            try:
                job_id = int(job_id)
            except ValueError:
                job_id = None

        metrics = analytics.get_dashboard_metrics(job_id)
        return jsonify(metrics), 200
    finally:
        db.close()


@app.route('/api/analytics/jobs/<int:job_id>', methods=['GET'])
def get_job_analytics(job_id):
    """Get detailed analytics for a specific job."""
    db = get_db()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return jsonify({"error": "Job not found"}), 404

        analytics = AnalyticsService(db)
        metrics = analytics.get_job_metrics(job_id)
        return jsonify(metrics), 200
    finally:
        db.close()


@app.route('/api/analytics/top-candidates', methods=['GET'])
def get_top_candidates():
    """Get top-scoring candidates."""
    db = get_db()
    try:
        analytics = AnalyticsService(db)
        job_id = request.args.get('job_id')
        limit = int(request.args.get('limit', 10))

        if job_id:
            try:
                job_id = int(job_id)
            except ValueError:
                job_id = None

        candidates = analytics.get_top_candidates(job_id, limit)
        return jsonify(candidates), 200
    finally:
        db.close()


# ============================================================================
# ASK THE CANDIDATE POOL
# ============================================================================

ASK_MAX_BODY_BYTES = 16 * 1024  # a 500-character question plus job_id fits easily


@app.route('/api/ask', methods=['POST'])
def ask_candidate_pool():
    """Answer a question from resume chunks only, citing the passages used."""
    if request.content_length is not None and request.content_length > ASK_MAX_BODY_BYTES:
        return jsonify({"error": "request body is too large"}), 413
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        body = {}
    question = body.get('question')
    job_id = body.get('job_id')
    if not isinstance(question, str) or not question.strip():
        return jsonify({"error": "question is required"}), 400
    # bool is a subclass of int, so {"job_id": true} would otherwise be read as job 1.
    if job_id is not None and (isinstance(job_id, bool) or not isinstance(job_id, int)):
        return jsonify({"error": "job_id must be an integer"}), 400
    db = get_db()
    try:
        if job_id is not None and db.get(Job, job_id) is None:
            return jsonify({"error": "Job not found"}), 404
        result = ask.answer_question(db, question, embeddings.get_provider(), job_id=job_id,
                                     api_key=cfg.get_api_key())
        return jsonify(result.to_dict()), 200
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        return error_response("answering a question")
    finally:
        db.close()


# ============================================================================
# HEALTH & INFO ENDPOINTS
# ============================================================================

@app.route('/', methods=['GET'])
def serve_dashboard():
    """Serve the recruiter dashboard.

    Served from Flask so the page shares an origin with /api. Opening
    frontend.html via file:// gives the page an opaque origin, which Chrome
    blocks from reaching localhost regardless of CORS headers.
    """
    return send_file(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'frontend.html'))


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({"status": "OK", "message": "Recruiting Agent Backend is running"}), 200


@app.route('/api/info', methods=['GET'])
def info():
    """Get API information."""
    return jsonify({
        "name": "AI Resume Screening Agent",
        "version": "2.0.0",
        "endpoints": [
            "GET /api/health",
            "GET /api/jobs",
            "POST /api/jobs",
            "GET /api/candidates",
            "POST /api/candidates",
            "POST /api/screen/<candidate_id>/<job_id>",
            "GET /api/scoring-templates",
            "POST /api/scoring-templates",
            "GET /api/analytics/dashboard",
            "POST /api/ask",
        ]
    }), 200


# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(400)
def bad_request(e):
    return jsonify({"error": "Bad request"}), 400


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Internal server error"}), 500


if __name__ == '__main__':
    host = os.getenv('HOST', '127.0.0.1')
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'

    scorer.load_embedding_model()

    logger.info(f"Starting Recruiting Agent Backend on {host}:{port}")
    # The reloader restarts the process when torch is imported, killing screening requests.
    app.run(host=host, port=port, debug=debug, use_reloader=False)
