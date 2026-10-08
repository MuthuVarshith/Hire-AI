"""Writes the varied synthetic resumes in this folder. All people, contacts and employers are fictional.

Run: python sample_resumes/varied/_generate.py
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent

RESUMES = {
"v01_fresher_aarav_mehta.txt": """Aarav Mehta
aarav.mehta@example.com | +1 (555) 201-0001 | github.com/aarav-example

EDUCATION
B.Tech in Computer Science, Riverbend Institute of Technology, 2026
CGPA 8.7/10. Coursework: Machine Learning, Databases, Operating Systems

PROJECTS
Campus Chatbot (2025)
Built a retrieval-augmented chatbot over university policy PDFs using LangChain, FAISS and a
small open-source LLM. Answered 300+ student questions during orientation week.

Expense Splitter API (2024)
REST API in FastAPI with PostgreSQL and SQLAlchemy; containerized with Docker for a class demo.
Not deployed beyond the course.

SKILLS
Python, FastAPI, PostgreSQL, Docker (coursework), LangChain, FAISS, Git

INTERNSHIP
Data Intern, Lumen Analytics (Summer 2025, 10 weeks)
Cleaned survey data with pandas and built Tableau dashboards.
""",

"v02_fresher_sara_okafor.md": """# Sara Okafor
sara.okafor@example.com · (555) 201-0002

## Education
- MSc Data Science, Northfield University (2025)
- BSc Statistics, Northfield University (2023)

## Projects
### Churn prediction for a telecom dataset
Gradient-boosted trees (XGBoost) with SHAP explanations; AUC 0.87 on a held-out set.

### Reproducing a sentiment paper
Fine-tuned a DistilBERT model with PyTorch and Hugging Face Transformers on movie reviews.

## Skills
Python, PyTorch, scikit-learn, XGBoost, SHAP, Hugging Face Transformers, SQL, R

## Experience
Teaching Assistant, Northfield University (2024-2025): ran weekly labs for Intro to Statistics.
""",

"v03_fresher_liam_novak.txt": """LIAM NOVAK
Email: liam.novak@example.com
Phone: (555) 201-0003

OBJECTIVE
Entry-level frontend developer looking for a first role building accessible web apps.

ACADEMIC PROJECTS
* Recipe finder - React and TypeScript single-page app using a public recipes API; deployed on Netlify.
* Accessibility audit tool - browser extension that flags missing alt text and low colour contrast.

TECHNICAL SKILLS
JavaScript, TypeScript, React, HTML, CSS, Tailwind, Jest, Figma

EDUCATION
Diploma in Web Development, Harbor City College, 2026
""",

"v04_fresher_mei_tanaka.txt": """Mei Tanaka
mei.tanaka@example.com

Education: B.Sc. Software Engineering, Eastvale University, expected 2026
Skills: Go, Python, gRPC, Redis, Docker, Kubernetes (minikube), Linux, Bash
Projects: Built a rate limiter service in Go backed by Redis, load-tested to 5k requests/second
on a laptop. Wrote a Kubernetes operator tutorial for a university club using minikube.
Interests: distributed systems, competitive programming (ICPC regional finalist 2025)
""",

"v05_fresher_diego_ramos.txt": """Diego Ramos | diego.ramos@example.com | (555) 201-0005

=== SUMMARY ===
Final-year student focused on data engineering.

=== PROJECTS ===
City bike trips pipeline: Airflow DAG that ingests daily CSV dumps into a PostgreSQL warehouse,
with dbt models for daily station usage. Ran locally with Docker Compose.

Streaming demo: Kafka producer and consumer in Python that simulated sensor readings.

=== SKILLS ===
Python, SQL, Airflow, dbt, Kafka (demo only), PostgreSQL, Docker Compose

=== EDUCATION ===
B.Sc. Information Systems, Coastline University, 2026
""",

"v06_senior_rachel_kim.txt": """Rachel Kim
rachel.kim@example.com | (555) 201-0006 | Seattle, WA

PROFESSIONAL SUMMARY
Staff backend engineer with 11 years building high-throughput APIs and event-driven systems.

PROFESSIONAL EXPERIENCE
Staff Software Engineer, Tidewater Logistics (2020 - Present)
- Led the migration of the shipment-tracking platform from a Django monolith to FastAPI
  microservices running in production on Kubernetes (EKS), serving 40M requests per day.
- Designed the Kafka-based event backbone (30+ topics) for real-time shipment status updates.
- Mentored 6 engineers; introduced contract testing with Pact.

Senior Software Engineer, Brightline Payments (2016 - 2020)
- Built the payment-reconciliation service in Python and PostgreSQL; reduced nightly job time
  from 5 hours to 40 minutes with partitioned tables.
- Owned on-call for the ledger service; wrote the incident runbooks.

Software Engineer, Quarry Labs (2014 - 2016)
- Maintained internal tools in Flask and MySQL.

SKILLS
Python, FastAPI, Django, Flask, Kafka, PostgreSQL, MySQL, Redis, Docker, Kubernetes, AWS (EKS,
RDS, SQS), Terraform, Pact

EDUCATION
B.S. Computer Engineering, Lakeshore State University, 2014
""",

"v07_ml_engineer_omar_haddad.txt": """Omar Haddad
omar.haddad@example.com · (555) 201-0007

Summary
Machine learning engineer with 5 years of experience shipping NLP and LLM features.

Experience
Machine Learning Engineer, Northwind AI (2022 - Present)
Built a retrieval-augmented generation (RAG) assistant over 2M support articles using pgvector,
a cross-encoder reranker and GPT-class models; cut average handling time by 18%.
Set up offline evaluation with RAGAS and a 400-question golden set.
Deployed model services with FastAPI and Docker on Google Cloud Run.

Data Scientist, Bluepeak Retail (2020 - 2022)
Forecasted weekly demand for 3,000 products with LightGBM; owned the feature store in BigQuery.

Skills
Python, PyTorch, Hugging Face, LangChain, pgvector, FAISS, RAGAS, FastAPI, Docker, GCP, BigQuery

Education
M.S. Computer Science (NLP track), Westbrook University, 2020
""",

"v08_two_column_style_priya_s.txt": """PRIYA SUBRAMANIAN                                   priya.s@example.com | (555) 201-0008
Data Analyst                                        Austin, TX

SKILLS                                              EXPERIENCE
SQL (advanced)                                      Senior Data Analyst, Cedar Health (2021 - Present)
Python (pandas)                                     Built Looker dashboards used by 200+ clinicians;
Looker, Tableau                                     automated monthly KPI reporting in SQL and dbt.
dbt                                                 Data Analyst, Cedar Health (2019 - 2021)
A/B testing                                         Analysed A/B tests for the patient portal.

EDUCATION
B.A. Economics, Pinecrest College, 2019
""",

"v09_no_headings_tom_baker.txt": """Tom Baker, tom.baker@example.com, (555) 201-0009.

I am a DevOps engineer with about seven years of experience. Most recently at Granite Cloud
(2021 to now) I run the CI/CD platform: GitHub Actions and Argo CD deploying to three Kubernetes
clusters, all managed with Terraform. Before that I was a systems administrator at Oakridge
Bank (2017 to 2021), where I automated Linux server patching with Ansible.

I hold the Certified Kubernetes Administrator (CKA) certification and an AWS Solutions
Architect Associate certification. I studied Network Engineering at Midvale Polytechnic.
""",

"v10_multipage_elena_petrova.txt": """Elena Petrova
elena.petrova@example.com | (555) 201-0010 | Berlin, Germany (open to remote)

SUMMARY
Engineering manager and former full-stack engineer with 14 years of experience across fintech
and e-commerce. Comfortable owning roadmaps, hiring, and hands-on architecture reviews.

WORK EXPERIENCE

Engineering Manager, Lindenpay (2021 - Present)
- Manage two teams (11 engineers) owning checkout and fraud detection.
- Hired 9 engineers; built the interview loop and leveling guide.
- Drove the adoption of feature flags and trunk-based development; deploy frequency rose from
  weekly to 20+ times per day.
- Partnered with data science to ship a fraud model that reduced chargebacks by 23%.

Tech Lead, Lindenpay (2018 - 2021)
- Led the rebuild of the checkout frontend in React and TypeScript with a Node.js BFF.
- Introduced end-to-end testing with Playwright, cutting checkout regressions by half.

Senior Full-Stack Engineer, Marktplatz GmbH (2014 - 2018)
- Built seller tools in Ruby on Rails and React; scaled the catalog search on Elasticsearch.
- Ran the migration from MySQL to PostgreSQL with zero downtime.

Software Engineer, Webwerk Agency (2011 - 2014)
- Delivered client sites in PHP and JavaScript.

PROJECTS
- Open-source maintainer of a small React form-validation library (1.2k GitHub stars).
- Speaker at a regional JavaScript meetup on trunk-based development.

SKILLS
Leadership: hiring, mentoring, roadmap planning, incident management
Engineering: TypeScript, React, Node.js, Ruby on Rails, PostgreSQL, Elasticsearch, Playwright

CERTIFICATIONS
- Professional Scrum Master I

EDUCATION
M.Sc. Computer Science, Technical University of Hamburg, 2011

LANGUAGES
English (fluent), German (native), Russian (native)
""",

"v11_inline_headings_kwame_asante.txt": """Kwame Asante - kwame.asante@example.com - (555) 201-0011
Summary: Mobile developer, 4 years, Android and cross-platform.
Experience: Android Developer at Savanna Mobile (2022-present) - shipped a Kotlin and Jetpack
Compose banking app with 500k installs; Junior Developer at Pixelcraft (2021-2022) - built
Flutter prototypes for clients.
Skills: Kotlin, Jetpack Compose, Flutter, Dart, Firebase, REST APIs, Git
Education: B.Sc. Computer Science, Accra Technical University, 2021
""",

"v12_career_changer_hannah_lee.txt": """Hannah Lee
hannah.lee@example.com
(555) 201-0012

Career Summary
Former high-school chemistry teacher (6 years) who moved into data analysis through a
bootcamp. Strong at explaining results to non-technical audiences.

Relevant Experience
Junior Data Analyst, Brightfield Schools Network (2024 - Present)
Built attendance and grade dashboards in Power BI; wrote SQL queries against SQL Server.

Teacher, Westgate High School (2017 - 2023)

Certificates
Data Analytics Bootcamp, Codeway Academy, 2023 (12 weeks, Python, SQL, Power BI)

Skills
SQL Server, Power BI, Excel, Python (pandas, basic), data storytelling
""",

"v13_security_fatima_zahra.txt": """FATIMA ZAHRA
Application Security Engineer | fatima.zahra@example.com | (555) 201-0013

PROFILE
Security engineer specialising in application security, threat modelling and secure SDLC.

EMPLOYMENT HISTORY
Application Security Engineer, Ironclad Insurance (2021 - Present)
* Ran threat-modelling sessions for 25 services; embedded SAST (Semgrep) and dependency scanning
  in CI for 300 repositories.
* Led the response to a leaked API key incident; rotated secrets and moved them to HashiCorp Vault.

Security Analyst, Northstar Bank (2018 - 2021)
* Triaged penetration-test findings and tracked remediation with engineering teams.

CERTIFICATIONS
OSCP, CISSP

TECHNICAL SKILLS
Threat modelling, OWASP Top 10, Semgrep, Burp Suite, HashiCorp Vault, Python, Go, AWS IAM

EDUCATION
BSc Cybersecurity, Kingsbridge University, 2018
""",

"v14_research_scientist_chen_wei.txt": """Chen Wei
chen.wei@example.com | (555) 201-0014

Research Interests
Efficient transformers, model compression, on-device inference.

Education
Ph.D. Computer Science, Ashford University, 2024. Thesis: "Structured pruning for small language models".
M.S. Computer Science, Ashford University, 2020

Experience
Research Scientist, Corvid Labs (2024 - Present)
Quantized 7B-parameter language models to 4-bit for laptop inference with under 2% accuracy loss.
Research Intern, Halcyon AI (Summer 2022)
Prototyped knowledge distillation for speech recognition models in PyTorch.

Publications
- "Pruning Heads You Can Afford to Lose", workshop paper, 2023
- "Tiny but Mighty: Distilling Speech Models", conference paper, 2022

Skills
PyTorch, JAX, CUDA, quantization, knowledge distillation, Python, C++
""",
}

if __name__ == "__main__":
    for name, text in RESUMES.items():
        (HERE / name).write_text(text, encoding="utf-8")
    print(f"wrote {len(RESUMES)} resumes to {HERE}")
