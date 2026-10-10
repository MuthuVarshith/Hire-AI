# Golden answers: for review

Status: **draft, pending review**. 30 questions with 45 required key facts, and 3 negative questions. Source: `eval/golden.json`; the questions and labels are the benchmark's (`eval/retrieval_benchmark.json`).

For each question, check that the reference answer says only what the cited chunks say, that every required key fact is needed for a correct answer, and that nothing required is missing. Edit `eval/golden.json`, then run `python -m eval.golden validate`.

Writing rules:

- Use only the question's labelled chunks: no other chunk, no outside knowledge.
- The reference answer names every labelled candidate and says, for each, what in the labelled chunk answers the question. Extra detail from the same chunks (employers, numbers) is context, not a requirement.
- Required key facts: one per labelled candidate, the minimum a correct answer must state. When a candidate has several labelled chunks, the key fact is tied to the chunk that evidences the act (experience or project before skills for doing questions); the other labelled chunks remain valid citations.
- Each key fact reuses the benchmark label's resume, section and quote, so it resolves to exactly one labelled chunk (checked by `python -m eval.golden validate`).
- The rationale says why the answer is what it is and names the near-miss candidates a correct answer leaves out.

## q01. Who has run FastAPI services in production?

**Reference answer.** Rachel Kim and Omar Haddad. Rachel led the migration of a shipment-tracking platform to FastAPI microservices running in production on Kubernetes (EKS), serving 40M requests per day, at Tidewater Logistics. Omar deployed model services with FastAPI and Docker on Google Cloud Run at Northwind AI.

*Rationale:* Both ran FastAPI in production; Aarav's FastAPI API was coursework 'not deployed beyond the course', so naming him is wrong.

Required key facts:

- **q01.f1** Rachel Kim: Runs FastAPI microservices in production (Tidewater Logistics).
  - evidence: `varied/v06_senior_rachel_kim.txt` · experience · chunk 2
    > Staff Software Engineer, Tidewater Logistics (2020 - Present) - Led the migration of the shipment-tracking platform from a Django monolith to FastAPI microservices running in production on Kubernetes (EKS), serving 40M requests per day. - Designed the Kafka-based event backbone (30+ topics) for real-time shipment status updates. - Mentored 6 engineers; introduced contract testing with Pact.
- **q01.f2** Omar Haddad: Deployed model services with FastAPI on Google Cloud Run (Northwind AI).
  - evidence: `varied/v07_ml_engineer_omar_haddad.txt` · experience · chunk 2
    > Machine Learning Engineer, Northwind AI (2022 - Present) Built a retrieval-augmented generation (RAG) assistant over 2M support articles using pgvector, a cross-encoder reranker and GPT-class models; cut average handling time by 18%. Set up offline evaluation with RAGAS and a 400-question golden set. Deployed model services with FastAPI and Docker on Google Cloud Run.

## q02. Which candidates have built retrieval-augmented generation (RAG) systems?

**Reference answer.** Ananya Patel, Omar Haddad and Aarav Mehta. Ananya built retrieval-augmented generation systems at Nova AI Labs. Omar built a RAG assistant over 2M support articles using pgvector, a cross-encoder reranker and GPT-class models at Northwind AI. Aarav built a retrieval-augmented campus chatbot over university policy PDFs with LangChain, FAISS and a small open-source LLM, as a student project.

*Rationale:* All three built a RAG system, Aarav as a student project; Javier only 'connected retrieval systems to user products', which his resume does not call RAG.

Required key facts:

- **q02.f1** Ananya Patel: Built retrieval-augmented generation systems (Nova AI Labs).
  - evidence: `resume_01_ananya_patel.txt` · experience · chunk 3
    > 6 years Applied AI Engineer | Nova AI Labs | 2019-Present Built retrieval-augmented generation systems, deployed LLM-powered workflows, and optimized model inference pipelines.
- **q02.f2** Omar Haddad: Built a RAG assistant over 2M support articles (Northwind AI).
  - evidence: `varied/v07_ml_engineer_omar_haddad.txt` · experience · chunk 2
    > Machine Learning Engineer, Northwind AI (2022 - Present) Built a retrieval-augmented generation (RAG) assistant over 2M support articles using pgvector, a cross-encoder reranker and GPT-class models; cut average handling time by 18%. Set up offline evaluation with RAGAS and a 400-question golden set. Deployed model services with FastAPI and Docker on Google Cloud Run.
- **q02.f3** Aarav Mehta: Built a retrieval-augmented chatbot over university policy PDFs (student project).
  - evidence: `varied/v01_fresher_aarav_mehta.txt` · projects · chunk 2
    > Campus Chatbot (2025) Built a retrieval-augmented chatbot over university policy PDFs using LangChain, FAISS and a small open-source LLM. Answered 300+ student questions during orientation week. Expense Splitter API (2024) REST API in FastAPI with PostgreSQL and SQLAlchemy; containerized with Docker for a class demo. Not deployed beyond the course.

## q03. Who has hands-on Kafka experience?

**Reference answer.** Rachel Kim and Diego Ramos. Rachel designed the Kafka-based event backbone (30+ topics) for real-time shipment status updates at Tidewater Logistics. Diego built a Kafka producer and consumer in Python that simulated sensor readings, as a streaming demo project.

*Rationale:* Both did hands-on Kafka work; Diego's was a demo, which an answer may point out without dropping him.

Required key facts:

- **q03.f1** Rachel Kim: Designed a Kafka-based event backbone with 30+ topics (Tidewater Logistics).
  - evidence: `varied/v06_senior_rachel_kim.txt` · experience · chunk 2
    > Staff Software Engineer, Tidewater Logistics (2020 - Present) - Led the migration of the shipment-tracking platform from a Django monolith to FastAPI microservices running in production on Kubernetes (EKS), serving 40M requests per day. - Designed the Kafka-based event backbone (30+ topics) for real-time shipment status updates. - Mentored 6 engineers; introduced contract testing with Pact.
- **q03.f2** Diego Ramos: Built a Kafka producer and consumer in Python (streaming demo project).
  - evidence: `varied/v05_fresher_diego_ramos.txt` · projects · chunk 2
    > City bike trips pipeline: Airflow DAG that ingests daily CSV dumps into a PostgreSQL warehouse, with dbt models for daily station usage. Ran locally with Docker Compose. Streaming demo: Kafka producer and consumer in Python that simulated sensor readings.

## q04. Find candidates with a Certified Kubernetes Administrator (CKA) certification.

**Reference answer.** Tom Baker holds the Certified Kubernetes Administrator (CKA) certification.

*Rationale:* Only Tom states a CKA; his resume has no headings, so the evidence is his single unlabelled chunk.

Required key facts:

- **q04.f1** Tom Baker: Holds the Certified Kubernetes Administrator (CKA) certification.
  - evidence: `varied/v09_no_headings_tom_baker.txt` · header · chunk 0
    > Tom Baker, tom.baker@example.com, (555) 201-0009. I am a DevOps engineer with about seven years of experience. Most recently at Granite Cloud (2021 to now) I run the CI/CD platform: GitHub Actions and Argo CD deploying to three Kubernetes clusters, all managed with Terraform. Before that I was a systems administrator at Oakridge Bank (2017 to 2021), where I automated Linux server patching with Ansible. I hold the Certified Kubernetes Administrator (CKA) certification and an AWS Solutions Architect Associate certification. I studied Network Engineering at Midvale Polytechnic.

## q05. Who has security certifications such as OSCP or CISSP?

**Reference answer.** Fatima Zahra holds both the OSCP and the CISSP.

*Rationale:* Fatima's certifications section lists both; no other resume lists a security certification.

Required key facts:

- **q05.f1** Fatima Zahra: Holds the OSCP and CISSP certifications.
  - evidence: `varied/v13_security_fatima_zahra.txt` · certifications · chunk 4
    > OSCP, CISSP

## q06. Which candidates have managed or mentored engineers?

**Reference answer.** Rachel Kim and Elena Petrova. Rachel mentored 6 engineers at Tidewater Logistics. Elena manages two teams with 11 engineers in total at Lindenpay, and hired 9 engineers.

*Rationale:* Rachel mentored and Elena manages; '11 engineers' is the total across two teams, not two teams of 11, and Elena's skills word 'mentoring' is not evidence on its own.

Required key facts:

- **q06.f1** Rachel Kim: Mentored 6 engineers (Tidewater Logistics).
  - evidence: `varied/v06_senior_rachel_kim.txt` · experience · chunk 2
    > Staff Software Engineer, Tidewater Logistics (2020 - Present) - Led the migration of the shipment-tracking platform from a Django monolith to FastAPI microservices running in production on Kubernetes (EKS), serving 40M requests per day. - Designed the Kafka-based event backbone (30+ topics) for real-time shipment status updates. - Mentored 6 engineers; introduced contract testing with Pact.
- **q06.f2** Elena Petrova: Manages two teams totalling 11 engineers (Lindenpay).
  - evidence: `varied/v10_multipage_elena_petrova.txt` · experience · chunk 2
    > Engineering Manager, Lindenpay (2021 - Present) - Manage two teams (11 engineers) owning checkout and fraud detection. - Hired 9 engineers; built the interview loop and leveling guide. - Drove the adoption of feature flags and trunk-based development; deploy frequency rose from weekly to 20+ times per day. - Partnered with data science to ship a fraud model that reduced chargebacks by 23%.

## q07. Who has worked with Terraform?

**Reference answer.** Rachel Kim and Tom Baker. Rachel lists Terraform in her skills. Tom runs Kubernetes clusters at Granite Cloud that are all managed with Terraform.

*Rationale:* 'Has worked with' accepts a skills mention, so Rachel's list counts; Tom's evidence is in his unlabelled chunk.

Required key facts:

- **q07.f1** Rachel Kim: Lists Terraform in her skills.
  - evidence: `varied/v06_senior_rachel_kim.txt` · skills · chunk 5
    > Python, FastAPI, Django, Flask, Kafka, PostgreSQL, MySQL, Redis, Docker, Kubernetes, AWS (EKS, RDS, SQS), Terraform, Pact
- **q07.f2** Tom Baker: Manages Kubernetes clusters with Terraform (Granite Cloud).
  - evidence: `varied/v09_no_headings_tom_baker.txt` · header · chunk 0
    > Tom Baker, tom.baker@example.com, (555) 201-0009. I am a DevOps engineer with about seven years of experience. Most recently at Granite Cloud (2021 to now) I run the CI/CD platform: GitHub Actions and Argo CD deploying to three Kubernetes clusters, all managed with Terraform. Before that I was a systems administrator at Oakridge Bank (2017 to 2021), where I automated Linux server patching with Ansible. I hold the Certified Kubernetes Administrator (CKA) certification and an AWS Solutions Architect Associate certification. I studied Network Engineering at Midvale Polytechnic.

## q08. Find freshers who built a chatbot project.

**Reference answer.** Aarav Mehta built the Campus Chatbot (2025), a retrieval-augmented chatbot over university policy PDFs using LangChain, FAISS and a small open-source LLM; it answered 300+ student questions during orientation week.

*Rationale:* Aarav is the only fresher with a chatbot project; Omar built a RAG assistant but in a job, not as a fresher.

Required key facts:

- **q08.f1** Aarav Mehta: Built the Campus Chatbot project (2025).
  - evidence: `varied/v01_fresher_aarav_mehta.txt` · projects · chunk 2
    > Campus Chatbot (2025) Built a retrieval-augmented chatbot over university policy PDFs using LangChain, FAISS and a small open-source LLM. Answered 300+ student questions during orientation week. Expense Splitter API (2024) REST API in FastAPI with PostgreSQL and SQLAlchemy; containerized with Docker for a class demo. Not deployed beyond the course.

## q09. Who knows React and TypeScript?

**Reference answer.** Liam Novak and Elena Petrova. Liam built a React and TypeScript single-page app (a recipe finder) and lists both in his skills. Elena led the rebuild of Lindenpay's checkout frontend in React and TypeScript and lists both in her skills.

*Rationale:* Both show React and TypeScript in a project or job and in skills; the skills chunks are valid citations but not separate required facts.

Required key facts:

- **q09.f1** Liam Novak: Built a React and TypeScript single-page app.
  - evidence: `varied/v03_fresher_liam_novak.txt` · projects · chunk 2
    > * Recipe finder - React and TypeScript single-page app using a public recipes API; deployed on Netlify. * Accessibility audit tool - browser extension that flags missing alt text and low colour contrast.
- **q09.f2** Elena Petrova: Rebuilt a checkout frontend in React and TypeScript (Lindenpay).
  - evidence: `varied/v10_multipage_elena_petrova.txt` · experience · chunk 3
    > Tech Lead, Lindenpay (2018 - 2021) - Led the rebuild of the checkout frontend in React and TypeScript with a Node.js BFF. - Introduced end-to-end testing with Playwright, cutting checkout regressions by half.

## q10. Who has built Android apps?

**Reference answer.** Kwame Asante shipped a Kotlin and Jetpack Compose banking app with 500k installs as an Android developer at Savanna Mobile.

*Rationale:* Only Kwame built Android apps; his resume uses inline headings.

Required key facts:

- **q10.f1** Kwame Asante: Shipped a Kotlin and Jetpack Compose Android banking app (Savanna Mobile).
  - evidence: `varied/v11_inline_headings_kwame_asante.txt` · experience · chunk 2
    > Android Developer at Savanna Mobile (2022-present) - shipped a Kotlin and Jetpack Compose banking app with 500k installs; Junior Developer at Pixelcraft (2021-2022) - built Flutter prototypes for clients.

## q11. Which candidate has compressed large language models to run on a laptop?

**Reference answer.** Chen Wei quantized 7B-parameter language models to 4-bit for laptop inference with under 2% accuracy loss, as a research scientist at Corvid Labs.

*Rationale:* Quantizing models for laptop inference is compressing them to run on a laptop.

Required key facts:

- **q11.f1** Chen Wei: Quantized 7B-parameter language models to 4-bit for laptop inference.
  - evidence: `varied/v14_research_scientist_chen_wei.txt` · experience · chunk 3
    > Research Scientist, Corvid Labs (2024 - Present) Quantized 7B-parameter language models to 4-bit for laptop inference with under 2% accuracy loss.

## q12. Who has published research papers?

**Reference answer.** Chen Wei has published two papers: the workshop paper 'Pruning Heads You Can Afford to Lose' (2023) and the conference paper 'Tiny but Mighty: Distilling Speech Models' (2022).

*Rationale:* Only Chen Wei lists publications; Emma 'benchmarked NLP systems' but lists none.

Required key facts:

- **q12.f1** Chen Wei: Has published a workshop paper (2023) and a conference paper (2022).
  - evidence: `varied/v14_research_scientist_chen_wei.txt` · other · chunk 5
    > - "Pruning Heads You Can Afford to Lose", workshop paper, 2023 - "Tiny but Mighty: Distilling Speech Models", conference paper, 2022

## q13. Who has built data pipelines with Airflow or dbt?

**Reference answer.** Diego Ramos and Priya Subramanian. Diego built an Airflow DAG that ingests daily CSV dumps into a PostgreSQL warehouse, with dbt models for daily station usage. Priya automated monthly KPI reporting in SQL and dbt at Cedar Health.

*Rationale:* Diego used Airflow and dbt in a project and Priya used dbt in her job; her two-column resume is one unlabelled chunk.

Required key facts:

- **q13.f1** Diego Ramos: Built an Airflow DAG with dbt models (city bike trips pipeline project).
  - evidence: `varied/v05_fresher_diego_ramos.txt` · projects · chunk 2
    > City bike trips pipeline: Airflow DAG that ingests daily CSV dumps into a PostgreSQL warehouse, with dbt models for daily station usage. Ran locally with Docker Compose. Streaming demo: Kafka producer and consumer in Python that simulated sensor readings.
- **q13.f2** Priya Subramanian: Automated monthly KPI reporting in SQL and dbt (Cedar Health).
  - evidence: `varied/v08_two_column_style_priya_s.txt` · header · chunk 0
    > PRIYA SUBRAMANIAN priya.s@example.com | (555) 201-0008 Data Analyst Austin, TX SKILLS EXPERIENCE SQL (advanced) Senior Data Analyst, Cedar Health (2021 - Present) Python (pandas) Built Looker dashboards used by 200+ clinicians; Looker, Tableau automated monthly KPI reporting in SQL and dbt. dbt Data Analyst, Cedar Health (2019 - 2021) A/B testing Analysed A/B tests for the patient portal.

## q14. Who has built dashboards in Power BI?

**Reference answer.** Hannah Lee built attendance and grade dashboards in Power BI as a junior data analyst at Brightfield Schools Network.

*Rationale:* Priya built dashboards in Looker, not Power BI, so she is left out.

Required key facts:

- **q14.f1** Hannah Lee: Built attendance and grade dashboards in Power BI (Brightfield Schools Network).
  - evidence: `varied/v12_career_changer_hannah_lee.txt` · experience · chunk 2
    > Junior Data Analyst, Brightfield Schools Network (2024 - Present) Built attendance and grade dashboards in Power BI; wrote SQL queries against SQL Server.

## q15. Find a candidate who moved into tech from teaching.

**Reference answer.** Hannah Lee, a former high-school chemistry teacher (6 years), moved into data analysis through a bootcamp.

*Rationale:* Sara was a teaching assistant during her degree, which is not a career change.

Required key facts:

- **q15.f1** Hannah Lee: Former high-school chemistry teacher who moved into data analysis.
  - evidence: `varied/v12_career_changer_hannah_lee.txt` · summary · chunk 1
    > Former high-school chemistry teacher (6 years) who moved into data analysis through a bootcamp. Strong at explaining results to non-technical audiences.

## q16. Who has experience with vector databases or semantic search?

**Reference answer.** Sophia Nguyen, Javier Lopez, Omar Haddad and Aarav Mehta. Sophia built semantic search systems at VectorWorks and lists vector databases. Javier lists vector databases. Omar built a RAG assistant using pgvector and lists pgvector and FAISS. Aarav used FAISS in his campus chatbot project and lists it.

*Rationale:* 'Has experience with' accepts skills lists, and FAISS counts as vector-database experience (reviewer decision in the benchmark).

Required key facts:

- **q16.f1** Sophia Nguyen: Built semantic search systems (VectorWorks).
  - evidence: `resume_03_sophia_nguyen.txt` · experience · chunk 3
    > 5 years AI Engineer | VectorWorks | 2018-Present Built semantic search systems, ranking pipelines, and APIs for AI-driven knowledge assistants.
- **q16.f2** Javier Lopez: Lists vector databases in his skills.
  - evidence: `resume_10_javier_lopez.txt` · skills · chunk 2
    > Python, LLMs, LangChain, vector databases, embeddings, SQL, Docker, Git, GitHub, pandas
- **q16.f3** Omar Haddad: Built a RAG assistant using pgvector (Northwind AI).
  - evidence: `varied/v07_ml_engineer_omar_haddad.txt` · experience · chunk 2
    > Machine Learning Engineer, Northwind AI (2022 - Present) Built a retrieval-augmented generation (RAG) assistant over 2M support articles using pgvector, a cross-encoder reranker and GPT-class models; cut average handling time by 18%. Set up offline evaluation with RAGAS and a 400-question golden set. Deployed model services with FastAPI and Docker on Google Cloud Run.
- **q16.f4** Aarav Mehta: Used FAISS in his campus chatbot project.
  - evidence: `varied/v01_fresher_aarav_mehta.txt` · projects · chunk 2
    > Campus Chatbot (2025) Built a retrieval-augmented chatbot over university policy PDFs using LangChain, FAISS and a small open-source LLM. Answered 300+ student questions during orientation week. Expense Splitter API (2024) REST API in FastAPI with PostgreSQL and SQLAlchemy; containerized with Docker for a class demo. Not deployed beyond the course.

## q17. Who has evaluated an LLM system with a golden dataset?

**Reference answer.** Omar Haddad set up offline evaluation with RAGAS and a 400-question golden set at Northwind AI.

*Rationale:* Michael and Emma mention evaluation in general, not a golden dataset.

Required key facts:

- **q17.f1** Omar Haddad: Set up offline evaluation with RAGAS and a 400-question golden set (Northwind AI).
  - evidence: `varied/v07_ml_engineer_omar_haddad.txt` · experience · chunk 2
    > Machine Learning Engineer, Northwind AI (2022 - Present) Built a retrieval-augmented generation (RAG) assistant over 2M support articles using pgvector, a cross-encoder reranker and GPT-class models; cut average handling time by 18%. Set up offline evaluation with RAGAS and a 400-question golden set. Deployed model services with FastAPI and Docker on Google Cloud Run.

## q18. Which candidates list MLflow experience?

**Reference answer.** Michael Chen and Maya Chen list MLflow in their skills.

*Rationale:* A 'list' question, so skills lists are the evidence; no resume shows MLflow used in a job or project.

Required key facts:

- **q18.f1** Michael Chen: Lists MLflow in his skills.
  - evidence: `resume_02_michael_chen.txt` · skills · chunk 2
    > Python, PyTorch, TensorFlow, NLP, LLMs, MLflow, pandas, NumPy, SQL, AWS, Docker, Git, GitHub
- **q18.f2** Maya Chen: Lists MLflow in her skills.
  - evidence: `resume_11_maya_chen.txt` · skills · chunk 2
    > Python, PyTorch, TensorFlow, NLP, LLMs, AWS, Docker, Kubernetes, Git, GitHub, MLflow

## q19. Which candidates hold a PhD?

**Reference answer.** Chen Wei holds a Ph.D. in Computer Science from Ashford University (2024).

*Rationale:* Only Chen Wei; the resume writes the degree as 'Ph.D.'.

Required key facts:

- **q19.f1** Chen Wei: Holds a Ph.D. in Computer Science (Ashford University, 2024).
  - evidence: `varied/v14_research_scientist_chen_wei.txt` · education · chunk 2
    > Ph.D. Computer Science, Ashford University, 2024. Thesis: "Structured pruning for small language models". M.S. Computer Science, Ashford University, 2020

## q20. Who has fine-tuned transformer models?

**Reference answer.** Michael Chen and Sara Okafor. Michael developed fine-tuning pipelines as an ML engineer at Northwind AI. Sara fine-tuned a DistilBERT model with PyTorch and Hugging Face Transformers on movie reviews, in a project reproducing a sentiment paper.

*Rationale:* A doing question needs a job or project passage; Lina's summary self-describes fine-tuning but no passage shows it, so naming her rests on weaker evidence.

Required key facts:

- **q20.f1** Michael Chen: Developed fine-tuning pipelines (Northwind AI).
  - evidence: `resume_02_michael_chen.txt` · experience · chunk 3
    > 4 years ML Engineer | Northwind AI | 2020-Present Developed fine-tuning pipelines, experiment tracking systems, and cloud-hosted AI services.
- **q20.f2** Sara Okafor: Fine-tuned a DistilBERT model (sentiment project).
  - evidence: `varied/v02_fresher_sara_okafor.md` · projects · chunk 2
    > ### Churn prediction for a telecom dataset Gradient-boosted trees (XGBoost) with SHAP explanations; AUC 0.87 on a held-out set. ### Reproducing a sentiment paper Fine-tuned a DistilBERT model with PyTorch and Hugging Face Transformers on movie reviews.

## q21. Who made a slow nightly batch job much faster?

**Reference answer.** Rachel Kim reduced a nightly job's run time from 5 hours to 40 minutes with partitioned tables, on the payment-reconciliation service at Brightline Payments.

*Rationale:* Paraphrase of 'reduced nightly job time from 5 hours to 40 minutes'; no other resume describes speeding up a batch job.

Required key facts:

- **q21.f1** Rachel Kim: Reduced nightly job time from 5 hours to 40 minutes (Brightline Payments).
  - evidence: `varied/v06_senior_rachel_kim.txt` · experience · chunk 3
    > Senior Software Engineer, Brightline Payments (2016 - 2020) - Built the payment-reconciliation service in Python and PostgreSQL; reduced nightly job time from 5 hours to 40 minutes with partitioned tables. - Owned on-call for the ledger service; wrote the incident runbooks.

## q22. Who has led a migration from a monolith to microservices?

**Reference answer.** Rachel Kim led the migration of the shipment-tracking platform from a Django monolith to FastAPI microservices at Tidewater Logistics.

*Rationale:* Elena's MySQL-to-PostgreSQL migration is a database migration, not monolith to microservices.

Required key facts:

- **q22.f1** Rachel Kim: Led the migration from a Django monolith to FastAPI microservices (Tidewater Logistics).
  - evidence: `varied/v06_senior_rachel_kim.txt` · experience · chunk 2
    > Staff Software Engineer, Tidewater Logistics (2020 - Present) - Led the migration of the shipment-tracking platform from a Django monolith to FastAPI microservices running in production on Kubernetes (EKS), serving 40M requests per day. - Designed the Kafka-based event backbone (30+ topics) for real-time shipment status updates. - Mentored 6 engineers; introduced contract testing with Pact.

## q23. Who has introduced feature flags or trunk-based development?

**Reference answer.** Elena Petrova drove the adoption of feature flags and trunk-based development at Lindenpay, raising deploy frequency from weekly to 20+ times per day, and spoke about trunk-based development at a regional JavaScript meetup.

*Rationale:* The meetup talk (projects) supports it, but the required fact is the adoption she drove.

Required key facts:

- **q23.f1** Elena Petrova: Drove the adoption of feature flags and trunk-based development (Lindenpay).
  - evidence: `varied/v10_multipage_elena_petrova.txt` · experience · chunk 2
    > Engineering Manager, Lindenpay (2021 - Present) - Manage two teams (11 engineers) owning checkout and fraud detection. - Hired 9 engineers; built the interview loop and leveling guide. - Drove the adoption of feature flags and trunk-based development; deploy frequency rose from weekly to 20+ times per day. - Partnered with data science to ship a fraud model that reduced chargebacks by 23%.

## q24. Who has worked on fraud detection?

**Reference answer.** Elena Petrova manages teams at Lindenpay that own fraud detection, and partnered with data science to ship a fraud model that reduced chargebacks by 23%.

*Rationale:* Only Elena's resume mentions fraud.

Required key facts:

- **q24.f1** Elena Petrova: Her teams own fraud detection at Lindenpay.
  - evidence: `varied/v10_multipage_elena_petrova.txt` · experience · chunk 2
    > Engineering Manager, Lindenpay (2021 - Present) - Manage two teams (11 engineers) owning checkout and fraud detection. - Hired 9 engineers; built the interview loop and leveling guide. - Drove the adoption of feature flags and trunk-based development; deploy frequency rose from weekly to 20+ times per day. - Partnered with data science to ship a fraud model that reduced chargebacks by 23%.

## q25. Who speaks German?

**Reference answer.** Elena Petrova speaks German (native); she also lists English (fluent) and Russian (native).

*Rationale:* Her languages section is the evidence; living in Berlin is not.

Required key facts:

- **q25.f1** Elena Petrova: Speaks German (native).
  - evidence: `varied/v10_multipage_elena_petrova.txt` · other · chunk 10
    > English (fluent), German (native), Russian (native)

## q26. Who knows the Go programming language?

**Reference answer.** Mei Tanaka and Fatima Zahra. Mei built a rate limiter service in Go backed by Redis and lists Go in her skills. Fatima lists Go in her skills.

*Rationale:* 'Knows' accepts a skills mention, so Fatima's list counts; 'Go' is the programming language here.

Required key facts:

- **q26.f1** Mei Tanaka: Built a rate limiter service in Go.
  - evidence: `varied/v04_fresher_mei_tanaka.txt` · projects · chunk 3
    > Built a rate limiter service in Go backed by Redis, load-tested to 5k requests/second on a laptop. Wrote a Kubernetes operator tutorial for a university club using minikube.
- **q26.f2** Fatima Zahra: Lists Go in her skills.
  - evidence: `varied/v13_security_fatima_zahra.txt` · skills · chunk 5
    > Threat modelling, OWASP Top 10, Semgrep, Burp Suite, HashiCorp Vault, Python, Go, AWS IAM

## q27. Who has used gradient boosting models such as XGBoost or LightGBM?

**Reference answer.** Sara Okafor and Omar Haddad. Sara used gradient-boosted trees (XGBoost) with SHAP explanations for telecom churn prediction (AUC 0.87). Omar forecasted weekly demand for 3,000 products with LightGBM at Bluepeak Retail.

*Rationale:* 'Has used' needs a project or job passage; both have one, and skills lists alone would not count.

Required key facts:

- **q27.f1** Sara Okafor: Used gradient-boosted trees (XGBoost) for churn prediction (project).
  - evidence: `varied/v02_fresher_sara_okafor.md` · projects · chunk 2
    > ### Churn prediction for a telecom dataset Gradient-boosted trees (XGBoost) with SHAP explanations; AUC 0.87 on a held-out set. ### Reproducing a sentiment paper Fine-tuned a DistilBERT model with PyTorch and Hugging Face Transformers on movie reviews.
- **q27.f2** Omar Haddad: Forecasted weekly demand with LightGBM (Bluepeak Retail).
  - evidence: `varied/v07_ml_engineer_omar_haddad.txt` · experience · chunk 3
    > Data Scientist, Bluepeak Retail (2020 - 2022) Forecasted weekly demand for 3,000 products with LightGBM; owned the feature store in BigQuery.

## q28. Who has managed secrets with a tool like HashiCorp Vault?

**Reference answer.** Fatima Zahra led the response to a leaked API key incident at Ironclad Insurance, rotating secrets and moving them to HashiCorp Vault.

*Rationale:* A doing question, so her job passage is the evidence; her skills list alone would not count.

Required key facts:

- **q28.f1** Fatima Zahra: Rotated secrets and moved them to HashiCorp Vault (Ironclad Insurance).
  - evidence: `varied/v13_security_fatima_zahra.txt` · experience · chunk 2
    > Application Security Engineer, Ironclad Insurance (2021 - Present) * Ran threat-modelling sessions for 25 services; embedded SAST (Semgrep) and dependency scanning in CI for 300 repositories. * Led the response to a leaked API key incident; rotated secrets and moved them to HashiCorp Vault.

## q29. Who built a high-throughput rate limiter?

**Reference answer.** Mei Tanaka built a rate limiter service in Go backed by Redis, load-tested to 5k requests per second on a laptop.

*Rationale:* Only Mei built a rate limiter.

Required key facts:

- **q29.f1** Mei Tanaka: Built a rate limiter service in Go, load-tested to 5k requests/second.
  - evidence: `varied/v04_fresher_mei_tanaka.txt` · projects · chunk 3
    > Built a rate limiter service in Go backed by Redis, load-tested to 5k requests/second on a laptop. Wrote a Kubernetes operator tutorial for a university club using minikube.

## q30. Who has worked as a teaching assistant?

**Reference answer.** Sara Okafor was a teaching assistant at Northfield University (2024-2025), running weekly labs for Intro to Statistics.

*Rationale:* Hannah was a teacher, not a teaching assistant.

Required key facts:

- **q30.f1** Sara Okafor: Teaching Assistant at Northfield University (2024-2025).
  - evidence: `varied/v02_fresher_sara_okafor.md` · experience · chunk 4
    > Teaching Assistant, Northfield University (2024-2025): ran weekly labs for Intro to Statistics.

## Negative questions

- **n01.** Who has COBOL mainframe experience? Reference: "Not found in resumes." *No resume mentions COBOL or mainframes; any named candidate is wrong.*
- **n02.** Who is a licensed medical doctor? Reference: "Not found in resumes." *No resume mentions medicine; any named candidate is wrong.*
- **n03.** Who is a certified Salesforce administrator? Reference: "Not found in resumes." *No resume mentions Salesforce; any named candidate is wrong.*
