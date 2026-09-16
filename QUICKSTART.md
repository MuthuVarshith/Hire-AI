# Quick Start Guide - AI Recruiting Platform

## Installation (5 minutes)

### 1. Install Python 3.9+
https://www.python.org/downloads/

### 2. Install Dependencies
```bash
cd C:\Hire-AI
pip install -r requirements.txt
```

### 3. Configure Environment (Optional)
```bash
cp .env.example .env
```

Edit `.env` if you want to enable optional LLM features:
```env
GOOGLE_API_KEY=your_api_key_here
```

### 4. Verify Installation
```bash
python -m pytest tests/ -v
```

Expected: All tests pass

---

## Start the Platform (2 steps)

### Step 1: Start Backend Server
```bash
python app.py
```

You should see:
```
Starting Recruiting Agent Backend on 127.0.0.1:5000
WARNING in app.indexing: This is a development server...
```

### Step 2: Open Frontend Dashboard

**Option A: Open the HTML file**
- Double-click `frontend.html` in the project folder
- Or open in your browser: `file:///C:/Hire-AI/frontend.html`

**Option B: Serve via HTTP (Recommended)**
```bash
# In a new terminal window
python -m http.server 8000
```
Then visit: `http://localhost:8000/frontend.html`

---

## Complete Workflow (5 minutes)

### 1. Create a Job
- Click **"+ New Job"** in the dashboard
- Enter job title: "Senior Backend Engineer"
- Paste job description:
```
We're hiring a Senior Backend Engineer with 5+ years of Python experience.
Required Skills: Python, Django, PostgreSQL, Docker, Git
Preferred Skills: Kubernetes, AWS, Redis
Education: Bachelor's in Computer Science
```
- Click **Create Job**

### 2. Upload Resumes
- Click **"📤 Upload Resume"**
- Select the job you just created
- Upload a resume from `sample_resumes/` folder
- System auto-screens the candidate
- Repeat for multiple resumes

### 3. View Results
- Go to **Dashboard** → See metrics
- Go to **Candidates** → View all screened candidates
- See scores, matched skills, and AI analysis

### 4. Track Pipeline
- Click on a candidate
- Update their status (Screened → Shortlisted → Interview → Offer → Hired)
- Add recruiter notes
- View interview questions generated for them

### 5. Analyze Metrics
- Go to **Analytics** 
- See hiring funnel, score distribution, skill gaps
- Identify top candidates and missing skills

---

## API Usage (Optional)

### Health Check
```bash
curl http://localhost:5000/api/health
```

### Create Job
```bash
curl -X POST http://localhost:5000/api/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Python Developer",
    "description_text": "We need a Python developer..."
  }'
```

### Upload Resume
```bash
curl -X POST "http://localhost:5000/api/candidates?job_id=1" \
  -F "resume=@resume.txt"
```

### Screen Candidate
```bash
curl -X POST http://localhost:5000/api/screen/1/1
```

### Get Analytics
```bash
curl http://localhost:5000/api/analytics/dashboard
```

See full API docs in [README.md](README.md#api-endpoints)

---

## Troubleshooting

### Port 5000 Already in Use
```bash
# Edit .env
PORT=5001

# Restart
python app.py
```

### Module Import Errors
```bash
# Reinstall dependencies
pip install -r requirements.txt --upgrade
```

### Database Errors
```bash
# Reset database
rm recruiting_agent.db

# Restart backend (recreates on startup)
python app.py
```

### LLM Features Not Working
- The platform works without API keys
- All features fall back to template-based explanations
- See console for LLM error details

---

## Sample Data

### Pre-loaded Sample Files
- **Job Description:** `sample_jd/jd.txt` (AI Engineer role)
- **Sample Resumes:** `sample_resumes/` (3+ candidates)
- **Expected Output:** `output/ranked_results.json` (demo results)

### Try It Now
1. Create job from `sample_jd/jd.txt`
2. Upload all resumes from `sample_resumes/`
3. Compare your results with `output/ranked_results.json`

---

## Key Features

✅ **AI Resume Screening** - Multi-signal scoring algorithm  
✅ **Candidate Database** - Persistent storage with duplicate detection  
✅ **Pipeline Management** - Track hiring stage for each candidate  
✅ **Custom Templates** - Create role-specific scoring weights  
✅ **Interview Generator** - AI-powered tailored questions  
✅ **Analytics** - Hiring metrics and insights  
✅ **REST API** - Full integration support  

---

## What's Different From CLI?

| Feature | CLI | Platform |
|---------|-----|----------|
| User Interface | Command line | Modern web dashboard |
| Candidate Storage | File-based | Database |
| Pipeline Tracking | None | Full pipeline stages |
| Duplicate Detection | None | Fuzzy matching |
| Custom Scoring | None | Configurable templates |
| Interview Questions | None | AI-generated |
| Analytics | None | Dashboard metrics |
| Resume Management | Folder-based | Database with history |

---

## Next Steps

1. **Play with Sample Data** (5 min)
   - Use provided sample job and resumes
   - Explore dashboard and metrics

2. **Try Real Data** (15 min)
   - Upload your actual job descriptions
   - Screen your real candidate resumes
   - Configure custom scoring templates

3. **Integrate APIs** (30 min)
   - Build custom integrations
   - Connect to your existing systems
   - Automate candidate flow

4. **Deploy to Production** (See README.md)
   - Use PostgreSQL instead of SQLite
   - Add authentication/authorization
   - Deploy to your cloud platform

---

## Support & Resources

- **Full Documentation**: See [README.md](README.md)
- **API Reference**: See [README.md#api-endpoints](README.md#api-endpoints)
- **Tests**: Run `pytest tests/ -v`
- **Sample Outputs**: Check `output/` folder

---

## Questions?

Refer to:
- Main README for detailed documentation
- Test files for usage examples
- Sample outputs for expected results
- API endpoint docs for integration
