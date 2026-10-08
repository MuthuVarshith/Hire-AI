# Retrieval benchmark: labels for review

Status: **approved rules applied; labels being updated**. 30 questions, 52 labelled chunks, 3 negative questions, over 26 synthetic resumes.

A label marks a chunk that directly evidences the answer. For each question, check that every listed chunk belongs, and that no chunk that should be listed is missing. Edit `eval/retrieval_benchmark.json`, then run `python -m eval.benchmark validate`.

## q01. Who has run FastAPI services in production?

*Rationale:* Rachel migrated to FastAPI microservices 'running in production'; Omar deployed FastAPI model services on Cloud Run. Distractor: Aarav (v01) built a FastAPI API for coursework that was explicitly 'Not deployed', and skills lists that only name FastAPI are not evidence of production use.

- `varied/v06_senior_rachel_kim.txt` · experience · chunk 2
  > Staff Software Engineer, Tidewater Logistics (2020 - Present) - Led the migration of the shipment-tracking platform from a Django monolith to FastAPI microservices running in production on Kubernetes (EKS), serving 40M requests per day. - Designed the Kafka-based event backbone (30+ topics) for real-time shipment status updates. - Mentored 6 engineers; introduced contract testing with Pact.
- `varied/v07_ml_engineer_omar_haddad.txt` · experience · chunk 2
  > Machine Learning Engineer, Northwind AI (2022 - Present) Built a retrieval-augmented generation (RAG) assistant over 2M support articles using pgvector, a cross-encoder reranker and GPT-class models; cut average handling time by 18%. Set up offline evaluation with RAGAS and a 400-question golden set. Deployed model services with FastAPI and Docker on Google Cloud Run.

## q02. Which candidates have built retrieval-augmented generation (RAG) systems?

*Rationale:* All three describe building a RAG system (Aarav's as a student project, which still counts as having built one). Javier (resume_10) 'connected retrieval systems to user products', which is adjacent but not RAG, so it is not labelled.

- `resume_01_ananya_patel.txt` · experience · chunk 3
  > 6 years Applied AI Engineer | Nova AI Labs | 2019-Present Built retrieval-augmented generation systems, deployed LLM-powered workflows, and optimized model inference pipelines.
- `varied/v07_ml_engineer_omar_haddad.txt` · experience · chunk 2
  > Machine Learning Engineer, Northwind AI (2022 - Present) Built a retrieval-augmented generation (RAG) assistant over 2M support articles using pgvector, a cross-encoder reranker and GPT-class models; cut average handling time by 18%. Set up offline evaluation with RAGAS and a 400-question golden set. Deployed model services with FastAPI and Docker on Google Cloud Run.
- `varied/v01_fresher_aarav_mehta.txt` · projects · chunk 2
  > Campus Chatbot (2025) Built a retrieval-augmented chatbot over university policy PDFs using LangChain, FAISS and a small open-source LLM. Answered 300+ student questions during orientation week. Expense Splitter API (2024) REST API in FastAPI with PostgreSQL and SQLAlchemy; containerized with Docker for a class demo. Not deployed beyond the course.

## q03. Who has hands-on Kafka experience?

*Rationale:* Rachel designed a Kafka backbone in production; Diego built a Kafka producer/consumer demo. Both are hands-on; the recruiter can weigh depth from the cited text.

- `varied/v06_senior_rachel_kim.txt` · experience · chunk 2
  > Staff Software Engineer, Tidewater Logistics (2020 - Present) - Led the migration of the shipment-tracking platform from a Django monolith to FastAPI microservices running in production on Kubernetes (EKS), serving 40M requests per day. - Designed the Kafka-based event backbone (30+ topics) for real-time shipment status updates. - Mentored 6 engineers; introduced contract testing with Pact.
- `varied/v05_fresher_diego_ramos.txt` · projects · chunk 2
  > City bike trips pipeline: Airflow DAG that ingests daily CSV dumps into a PostgreSQL warehouse, with dbt models for daily station usage. Ran locally with Docker Compose. Streaming demo: Kafka producer and consumer in Python that simulated sensor readings.

## q04. Find candidates with a Certified Kubernetes Administrator (CKA) certification.

*Rationale:* Only Tom holds the CKA. His resume has no headings, so the answer is in an unlabelled chunk: a deliberate hard case.

- `varied/v09_no_headings_tom_baker.txt` · header · chunk 0
  > Tom Baker, tom.baker@example.com, (555) 201-0009. I am a DevOps engineer with about seven years of experience. Most recently at Granite Cloud (2021 to now) I run the CI/CD platform: GitHub Actions and Argo CD deploying to three Kubernetes clusters, all managed with Terraform. Before that I was a systems administrator at Oakridge Bank (2017 to 2021), where I automated Linux server patching with Ansible. I hold the Certified Kubernetes Administrator (CKA) certification and an AWS Solutions Architect Associate certification. I studied Network Engineering at Midvale Polytechnic.

## q05. Who has security certifications such as OSCP or CISSP?

*Rationale:* Fatima's certifications section lists both. Keyword-heavy question, should favour BM25.

- `varied/v13_security_fatima_zahra.txt` · certifications · chunk 4
  > OSCP, CISSP

## q06. Which candidates have managed or mentored engineers?

*Rationale:* Rachel mentored engineers; Elena manages two teams. Elena's skills chunk mentions 'mentoring' as a word but is not evidence of having done it, so it is not labelled.

- `varied/v06_senior_rachel_kim.txt` · experience · chunk 2
  > Staff Software Engineer, Tidewater Logistics (2020 - Present) - Led the migration of the shipment-tracking platform from a Django monolith to FastAPI microservices running in production on Kubernetes (EKS), serving 40M requests per day. - Designed the Kafka-based event backbone (30+ topics) for real-time shipment status updates. - Mentored 6 engineers; introduced contract testing with Pact.
- `varied/v10_multipage_elena_petrova.txt` · experience · chunk 2
  > Engineering Manager, Lindenpay (2021 - Present) - Manage two teams (11 engineers) owning checkout and fraud detection. - Hired 9 engineers; built the interview loop and leveling guide. - Drove the adoption of feature flags and trunk-based development; deploy frequency rose from weekly to 20+ times per day. - Partnered with data science to ship a fraud model that reduced chargebacks by 23%.

## q07. Who has worked with Terraform?

*Rationale:* 'Has worked with' accepts a skills mention: Rachel lists Terraform; Tom manages clusters with Terraform (in his unlabelled chunk).

- `varied/v06_senior_rachel_kim.txt` · skills · chunk 5
  > Python, FastAPI, Django, Flask, Kafka, PostgreSQL, MySQL, Redis, Docker, Kubernetes, AWS (EKS, RDS, SQS), Terraform, Pact
- `varied/v09_no_headings_tom_baker.txt` · header · chunk 0
  > Tom Baker, tom.baker@example.com, (555) 201-0009. I am a DevOps engineer with about seven years of experience. Most recently at Granite Cloud (2021 to now) I run the CI/CD platform: GitHub Actions and Argo CD deploying to three Kubernetes clusters, all managed with Terraform. Before that I was a systems administrator at Oakridge Bank (2017 to 2021), where I automated Linux server patching with Ansible. I hold the Certified Kubernetes Administrator (CKA) certification and an AWS Solutions Architect Associate certification. I studied Network Engineering at Midvale Polytechnic.

## q08. Find freshers who built a chatbot project.

*Rationale:* Aarav is a fresher (graduating 2026) with a campus chatbot project. No other fresher built a chatbot.

- `varied/v01_fresher_aarav_mehta.txt` · projects · chunk 2
  > Campus Chatbot (2025) Built a retrieval-augmented chatbot over university policy PDFs using LangChain, FAISS and a small open-source LLM. Answered 300+ student questions during orientation week. Expense Splitter API (2024) REST API in FastAPI with PostgreSQL and SQLAlchemy; containerized with Docker for a class demo. Not deployed beyond the course.

## q09. Who knows React and TypeScript?

*Rationale:* Liam and Elena both evidence React and TypeScript in a project/experience chunk and in skills; all four chunks answer the question.

- `varied/v03_fresher_liam_novak.txt` · projects · chunk 2
  > * Recipe finder - React and TypeScript single-page app using a public recipes API; deployed on Netlify. * Accessibility audit tool - browser extension that flags missing alt text and low colour contrast.
- `varied/v03_fresher_liam_novak.txt` · skills · chunk 3
  > JavaScript, TypeScript, React, HTML, CSS, Tailwind, Jest, Figma
- `varied/v10_multipage_elena_petrova.txt` · experience · chunk 3
  > Tech Lead, Lindenpay (2018 - 2021) - Led the rebuild of the checkout frontend in React and TypeScript with a Node.js BFF. - Introduced end-to-end testing with Playwright, cutting checkout regressions by half.
- `varied/v10_multipage_elena_petrova.txt` · skills · chunk 7
  > Leadership: hiring, mentoring, roadmap planning, incident management Engineering: TypeScript, React, Node.js, Ruby on Rails, PostgreSQL, Elasticsearch, Playwright

## q10. Who has built Android apps?

*Rationale:* Kwame shipped an Android banking app. His resume uses inline headings ('Experience: ...'), a format test.

- `varied/v11_inline_headings_kwame_asante.txt` · experience · chunk 2
  > Android Developer at Savanna Mobile (2022-present) - shipped a Kotlin and Jetpack Compose banking app with 500k installs; Junior Developer at Pixelcraft (2021-2022) - built Flutter prototypes for clients.

## q11. Which candidate has compressed large language models to run on a laptop?

*Rationale:* Paraphrase test: 'compressed ... to run on a laptop' vs 'Quantized ... for laptop inference'. Should favour vector search.

- `varied/v14_research_scientist_chen_wei.txt` · experience · chunk 3
  > Research Scientist, Corvid Labs (2024 - Present) Quantized 7B-parameter language models to 4-bit for laptop inference with under 2% accuracy loss.

## q12. Who has published research papers?

*Rationale:* Only Chen Wei lists publications. Emma (resume_09) 'benchmarked NLP systems' but lists no publications.

- `varied/v14_research_scientist_chen_wei.txt` · other · chunk 5
  > - "Pruning Heads You Can Afford to Lose", workshop paper, 2023 - "Tiny but Mighty: Distilling Speech Models", conference paper, 2022

## q13. Who has built data pipelines with Airflow or dbt?

*Rationale:* Diego built an Airflow + dbt pipeline; Priya automated reporting with dbt. Priya's two-column layout leaves everything in one unlabelled chunk: a format hard case.

- `varied/v05_fresher_diego_ramos.txt` · projects · chunk 2
  > City bike trips pipeline: Airflow DAG that ingests daily CSV dumps into a PostgreSQL warehouse, with dbt models for daily station usage. Ran locally with Docker Compose. Streaming demo: Kafka producer and consumer in Python that simulated sensor readings.
- `varied/v08_two_column_style_priya_s.txt` · header · chunk 0
  > PRIYA SUBRAMANIAN priya.s@example.com | (555) 201-0008 Data Analyst Austin, TX SKILLS EXPERIENCE SQL (advanced) Senior Data Analyst, Cedar Health (2021 - Present) Python (pandas) Built Looker dashboards used by 200+ clinicians; Looker, Tableau automated monthly KPI reporting in SQL and dbt. dbt Data Analyst, Cedar Health (2019 - 2021) A/B testing Analysed A/B tests for the patient portal.

## q14. Who has built dashboards in Power BI?

*Rationale:* Hannah built Power BI dashboards. Priya built dashboards in Looker, not Power BI, so she is not labelled.

- `varied/v12_career_changer_hannah_lee.txt` · experience · chunk 2
  > Junior Data Analyst, Brightfield Schools Network (2024 - Present) Built attendance and grade dashboards in Power BI; wrote SQL queries against SQL Server.

## q15. Find a candidate who moved into tech from teaching.

*Rationale:* Hannah was a teacher for 6 years before data analysis. Sara (v02) was a teaching assistant during her degree, which is not a career change.

- `varied/v12_career_changer_hannah_lee.txt` · summary · chunk 1
  > Former high-school chemistry teacher (6 years) who moved into data analysis through a bootcamp. Strong at explaining results to non-technical audiences.

## q16. Who has experience with vector databases or semantic search?

*Rationale:* 'Has experience with' question, so skills lists count. Sophia built semantic search and lists vector databases; Javier lists vector databases; Omar used pgvector in a RAG system and lists pgvector and FAISS; Aarav used FAISS in his chatbot project and lists it (reviewer decision: FAISS counts as vector database experience).

- `resume_03_sophia_nguyen.txt` · experience · chunk 3
  > 5 years AI Engineer | VectorWorks | 2018-Present Built semantic search systems, ranking pipelines, and APIs for AI-driven knowledge assistants.
- `resume_03_sophia_nguyen.txt` · skills · chunk 2
  > Python, PyTorch, NLP, embeddings, vector databases, LangChain, Hugging Face, SQL, pandas, Git, GitHub, pytest
- `resume_10_javier_lopez.txt` · skills · chunk 2
  > Python, LLMs, LangChain, vector databases, embeddings, SQL, Docker, Git, GitHub, pandas
- `varied/v07_ml_engineer_omar_haddad.txt` · experience · chunk 2
  > Machine Learning Engineer, Northwind AI (2022 - Present) Built a retrieval-augmented generation (RAG) assistant over 2M support articles using pgvector, a cross-encoder reranker and GPT-class models; cut average handling time by 18%. Set up offline evaluation with RAGAS and a 400-question golden set. Deployed model services with FastAPI and Docker on Google Cloud Run.
- `varied/v01_fresher_aarav_mehta.txt` · projects · chunk 2
  > Campus Chatbot (2025) Built a retrieval-augmented chatbot over university policy PDFs using LangChain, FAISS and a small open-source LLM. Answered 300+ student questions during orientation week. Expense Splitter API (2024) REST API in FastAPI with PostgreSQL and SQLAlchemy; containerized with Docker for a class demo. Not deployed beyond the course.
- `varied/v01_fresher_aarav_mehta.txt` · skills · chunk 3
  > Python, FastAPI, PostgreSQL, Docker (coursework), LangChain, FAISS, Git
- `varied/v07_ml_engineer_omar_haddad.txt` · skills · chunk 4
  > Python, PyTorch, Hugging Face, LangChain, pgvector, FAISS, RAGAS, FastAPI, Docker, GCP, BigQuery

## q17. Who has evaluated an LLM system with a golden dataset?

*Rationale:* Omar ran offline evaluation with RAGAS and a golden set. Michael and Emma mention 'evaluation' generally but not a golden dataset.

- `varied/v07_ml_engineer_omar_haddad.txt` · experience · chunk 2
  > Machine Learning Engineer, Northwind AI (2022 - Present) Built a retrieval-augmented generation (RAG) assistant over 2M support articles using pgvector, a cross-encoder reranker and GPT-class models; cut average handling time by 18%. Set up offline evaluation with RAGAS and a 400-question golden set. Deployed model services with FastAPI and Docker on Google Cloud Run.

## q18. Which candidates list MLflow experience?

*Rationale:* 'List' question, so skills lists count; MLflow appears only in Michael's and Maya's skills lists. (Reworded from 'have used': under the rules no resume shows MLflow being used in a job or project.)

- `resume_02_michael_chen.txt` · skills · chunk 2
  > Python, PyTorch, TensorFlow, NLP, LLMs, MLflow, pandas, NumPy, SQL, AWS, Docker, Git, GitHub
- `resume_11_maya_chen.txt` · skills · chunk 2
  > Python, PyTorch, TensorFlow, NLP, LLMs, AWS, Docker, Kubernetes, Git, GitHub, MLflow

## q19. Which candidates hold a PhD?

*Rationale:* Only Chen Wei. Tests matching 'PhD' against 'Ph.D.'.

- `varied/v14_research_scientist_chen_wei.txt` · education · chunk 2
  > Ph.D. Computer Science, Ashford University, 2024. Thesis: "Structured pruning for small language models". M.S. Computer Science, Ashford University, 2020

## q20. Who has fine-tuned transformer models?

*Rationale:* 'Has fine-tuned' is a doing question, so a job or project passage is needed. Michael built fine-tuning pipelines (job) and Sara fine-tuned DistilBERT (project). Lina's summary says she is 'experienced in ... fine-tuning', but that is a self-description and her job passage does not mention fine-tuning, so she is not labelled.

- `resume_02_michael_chen.txt` · experience · chunk 3
  > 4 years ML Engineer | Northwind AI | 2020-Present Developed fine-tuning pipelines, experiment tracking systems, and cloud-hosted AI services.
- `varied/v02_fresher_sara_okafor.md` · projects · chunk 2
  > ### Churn prediction for a telecom dataset Gradient-boosted trees (XGBoost) with SHAP explanations; AUC 0.87 on a held-out set. ### Reproducing a sentiment paper Fine-tuned a DistilBERT model with PyTorch and Hugging Face Transformers on movie reviews.

## q21. Who made a slow nightly batch job much faster?

*Rationale:* Paraphrase with almost no keyword overlap ('reduced nightly job time from 5 hours to 40 minutes').

- `varied/v06_senior_rachel_kim.txt` · experience · chunk 3
  > Senior Software Engineer, Brightline Payments (2016 - 2020) - Built the payment-reconciliation service in Python and PostgreSQL; reduced nightly job time from 5 hours to 40 minutes with partitioned tables. - Owned on-call for the ledger service; wrote the incident runbooks.

## q22. Who has led a migration from a monolith to microservices?

*Rationale:* Rachel led exactly this. Elena's MySQL-to-PostgreSQL migration is a database migration, not monolith-to-microservices.

- `varied/v06_senior_rachel_kim.txt` · experience · chunk 2
  > Staff Software Engineer, Tidewater Logistics (2020 - Present) - Led the migration of the shipment-tracking platform from a Django monolith to FastAPI microservices running in production on Kubernetes (EKS), serving 40M requests per day. - Designed the Kafka-based event backbone (30+ topics) for real-time shipment status updates. - Mentored 6 engineers; introduced contract testing with Pact.

## q23. Who has introduced feature flags or trunk-based development?

*Rationale:* Elena drove the adoption (experience) and spoke about it (projects). Two chunks from one candidate: tests that both surface.

- `varied/v10_multipage_elena_petrova.txt` · experience · chunk 2
  > Engineering Manager, Lindenpay (2021 - Present) - Manage two teams (11 engineers) owning checkout and fraud detection. - Hired 9 engineers; built the interview loop and leveling guide. - Drove the adoption of feature flags and trunk-based development; deploy frequency rose from weekly to 20+ times per day. - Partnered with data science to ship a fraud model that reduced chargebacks by 23%.
- `varied/v10_multipage_elena_petrova.txt` · projects · chunk 6
  > - Open-source maintainer of a small React form-validation library (1.2k GitHub stars). - Speaker at a regional JavaScript meetup on trunk-based development.

## q24. Who has worked on fraud detection?

*Rationale:* Elena's teams own fraud detection and shipped a fraud model.

- `varied/v10_multipage_elena_petrova.txt` · experience · chunk 2
  > Engineering Manager, Lindenpay (2021 - Present) - Manage two teams (11 engineers) owning checkout and fraud detection. - Hired 9 engineers; built the interview loop and leveling guide. - Drove the adoption of feature flags and trunk-based development; deploy frequency rose from weekly to 20+ times per day. - Partnered with data science to ship a fraud model that reduced chargebacks by 23%.

## q25. Who speaks German?

*Rationale:* Elena's Languages section. Her header mentions Berlin, which is not evidence of speaking German.

- `varied/v10_multipage_elena_petrova.txt` · other · chunk 10
  > English (fluent), German (native), Russian (native)

## q26. Who knows the Go programming language?

*Rationale:* Mei (skills and a Go project) and Fatima (skills). 'Go' is a short, ambiguous token; a known weak spot for keyword search.

- `varied/v04_fresher_mei_tanaka.txt` · skills · chunk 2
  > Go, Python, gRPC, Redis, Docker, Kubernetes (minikube), Linux, Bash
- `varied/v04_fresher_mei_tanaka.txt` · projects · chunk 3
  > Built a rate limiter service in Go backed by Redis, load-tested to 5k requests/second on a laptop. Wrote a Kubernetes operator tutorial for a university club using minikube.
- `varied/v13_security_fatima_zahra.txt` · skills · chunk 5
  > Threat modelling, OWASP Top 10, Semgrep, Burp Suite, HashiCorp Vault, Python, Go, AWS IAM

## q27. Who has used gradient boosting models such as XGBoost or LightGBM?

*Rationale:* 'Has used' is a doing question: Sara used XGBoost in a project; Omar forecasted demand with LightGBM in a job. Sara's skills list is not counted.

- `varied/v02_fresher_sara_okafor.md` · projects · chunk 2
  > ### Churn prediction for a telecom dataset Gradient-boosted trees (XGBoost) with SHAP explanations; AUC 0.87 on a held-out set. ### Reproducing a sentiment paper Fine-tuned a DistilBERT model with PyTorch and Hugging Face Transformers on movie reviews.
- `varied/v07_ml_engineer_omar_haddad.txt` · experience · chunk 3
  > Data Scientist, Bluepeak Retail (2020 - 2022) Forecasted weekly demand for 3,000 products with LightGBM; owned the feature store in BigQuery.

## q28. Who has managed secrets with a tool like HashiCorp Vault?

*Rationale:* 'Has managed secrets' is a doing question: Fatima rotated secrets into Vault in her job. Her skills list is not counted.

- `varied/v13_security_fatima_zahra.txt` · experience · chunk 2
  > Application Security Engineer, Ironclad Insurance (2021 - Present) * Ran threat-modelling sessions for 25 services; embedded SAST (Semgrep) and dependency scanning in CI for 300 repositories. * Led the response to a leaked API key incident; rotated secrets and moved them to HashiCorp Vault.

## q29. Who built a high-throughput rate limiter?

*Rationale:* Mei's project, load-tested to 5k requests/second.

- `varied/v04_fresher_mei_tanaka.txt` · projects · chunk 3
  > Built a rate limiter service in Go backed by Redis, load-tested to 5k requests/second on a laptop. Wrote a Kubernetes operator tutorial for a university club using minikube.

## q30. Who has worked as a teaching assistant?

*Rationale:* Sara was a TA. Hannah was a teacher, not a teaching assistant: a near-miss distractor.

- `varied/v02_fresher_sara_okafor.md` · experience · chunk 4
  > Teaching Assistant, Northfield University (2024-2025): ran weekly labs for Intro to Statistics.

## Negative questions (no correct answer in the corpus)

- **n01.** Who has COBOL mainframe experience? *No resume mentions COBOL or mainframes.*
- **n02.** Who is a licensed medical doctor? *No resume mentions medicine.*
- **n03.** Who is a certified Salesforce administrator? *No resume mentions Salesforce.*
