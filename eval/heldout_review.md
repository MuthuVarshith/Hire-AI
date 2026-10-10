# Held-out questions: for review

Status: **draft, pending review**. 20 answerable questions with 35 labelled chunks, and 15 unanswerable questions, over 26 synthetic resumes. Source: `eval/heldout.json`.

These questions recalibrate the not-found cutoff and check the LLM judge (`eval/answer_eval_protocol.md`). They must not repeat or paraphrase a benchmark question. For each answerable question, check that every listed chunk belongs and none is missing; for each unanswerable one, that no resume answers it. Edit `eval/heldout.json`, then run `python -m eval.golden validate`.

Overlap check: topic-word Jaccard similarity against every benchmark question; 0.5 or more fails validation. The closest benchmark question is shown for each.

## Answerable

### h01. Which candidates have a master's degree in data science?

*Rationale:* Michael, Priya Nair and Emma hold a Master's in Data Science and Sara an MSc Data Science; every other master's degree in the corpus is in computer science.

Closest benchmark question: q13 (overlap 0.14).

- [1] `resume_02_michael_chen.txt` · education · chunk 4 (Michael Chen)
  > Master's in Data Science, University of Washington
- [2] `resume_05_priya_nair.txt` · education · chunk 4 (Priya Nair)
  > Master's in Data Science, University of California, Berkeley
- [3] `resume_09_emma_thompson.txt` · education · chunk 4 (Emma Thompson)
  > Master's in Data Science, Oregon State University
- [4] `varied/v02_fresher_sara_okafor.md` · education · chunk 1 (Sara Okafor)
  > - MSc Data Science, Northfield University (2025) - BSc Statistics, Northfield University (2023)

Judge check, good answer: Four candidates: Michael Chen, Master's in Data Science from the University of Washington [1]; Priya Nair, from the University of California, Berkeley [2]; Emma Thompson, from Oregon State University [3]; and Sara Okafor, MSc Data Science from Northfield University [4].

Judge check, flawed answer (omission: Sara Okafor (MSc Data Science) is left out.): Michael Chen [1], Priya Nair [2] and Emma Thompson [3] each hold a Master's in Data Science.

### h02. Who has worked at a bank?

*Rationale:* Fatima was a security analyst at Northstar Bank and Tom a systems administrator at Oakridge Bank. Brightline Payments, Lindenpay and Ironclad Insurance are not banks, and Kwame built a banking app for a mobile company.

Closest benchmark question: q01 (overlap 0.00).

- [1] `varied/v13_security_fatima_zahra.txt` · experience · chunk 3 (Fatima Zahra)
  > Security Analyst, Northstar Bank (2018 - 2021) * Triaged penetration-test findings and tracked remediation with engineering teams.
- [2] `varied/v09_no_headings_tom_baker.txt` · header · chunk 0 (Tom Baker)
  > Tom Baker, tom.baker@example.com, (555) 201-0009. I am a DevOps engineer with about seven years of experience. Most recently at Granite Cloud (2021 to now) I run the CI/CD platform: GitHub Actions and Argo CD deploying to three Kubernetes clusters, all managed with Terraform. Before that I was a systems administrator at Oakridge Bank (2017 to 2021), where I automated Linux server patching with Ansible. I hold the Certified Kubernetes Administrator (CKA) certification and an AWS Solutions Architect Associate certification. I studied Network Engineering at Midvale Polytechnic.

Judge check, good answer: Fatima Zahra was a Security Analyst at Northstar Bank from 2018 to 2021 [1], and Tom Baker was a systems administrator at Oakridge Bank from 2017 to 2021 [2].

Judge check, flawed answer (wrong_citation: The two citations are swapped, so neither claim is supported by the excerpt it cites.): Fatima Zahra was a Security Analyst at Northstar Bank [2], and Tom Baker was a systems administrator at Oakridge Bank [1].

### h03. Who has experience with Tableau?

*Rationale:* Aarav built Tableau dashboards in his data internship; Priya lists Tableau in her skills column, and 'experience with' accepts a skills mention.

Closest benchmark question: q01 (overlap 0.00).

- [1] `varied/v01_fresher_aarav_mehta.txt` · experience · chunk 4 (Aarav Mehta)
  > Data Intern, Lumen Analytics (Summer 2025, 10 weeks) Cleaned survey data with pandas and built Tableau dashboards.
- [2] `varied/v08_two_column_style_priya_s.txt` · header · chunk 0 (Priya Subramanian)
  > PRIYA SUBRAMANIAN priya.s@example.com | (555) 201-0008 Data Analyst Austin, TX SKILLS EXPERIENCE SQL (advanced) Senior Data Analyst, Cedar Health (2021 - Present) Python (pandas) Built Looker dashboards used by 200+ clinicians; Looker, Tableau automated monthly KPI reporting in SQL and dbt. dbt Data Analyst, Cedar Health (2019 - 2021) A/B testing Analysed A/B tests for the patient portal.

Judge check, good answer: Aarav Mehta built Tableau dashboards as a data intern at Lumen Analytics [1], and Priya Subramanian lists Tableau among her skills [2].

Judge check, flawed answer (omission: Priya Subramanian is left out.): Aarav Mehta built Tableau dashboards as a data intern at Lumen Analytics [1].

### h04. Who has worked with Redis?

*Rationale:* Mei built a rate limiter backed by Redis and lists Redis; Rachel lists Redis in her skills, which 'worked with' accepts.

Closest benchmark question: q01 (overlap 0.00).

- [1] `varied/v04_fresher_mei_tanaka.txt` · projects · chunk 3 (Mei Tanaka)
  > Built a rate limiter service in Go backed by Redis, load-tested to 5k requests/second on a laptop. Wrote a Kubernetes operator tutorial for a university club using minikube.
- [2] `varied/v04_fresher_mei_tanaka.txt` · skills · chunk 2 (Mei Tanaka)
  > Go, Python, gRPC, Redis, Docker, Kubernetes (minikube), Linux, Bash
- [3] `varied/v06_senior_rachel_kim.txt` · skills · chunk 5 (Rachel Kim)
  > Python, FastAPI, Django, Flask, Kafka, PostgreSQL, MySQL, Redis, Docker, Kubernetes, AWS (EKS, RDS, SQS), Terraform, Pact

Judge check, good answer: Mei Tanaka built a rate limiter service backed by Redis [1] and lists Redis in her skills [2]; Rachel Kim also lists Redis in her skills [3].

Judge check, flawed answer (wrong_citation: The rate-limiter claim cites Mei's skills list [2], which does not mention the rate limiter.): Mei Tanaka built a rate limiter service backed by Redis [2]; Rachel Kim lists Redis in her skills [3].

### h05. Who brought a new kind of automated testing into their team's workflow?

*Rationale:* Rachel introduced contract testing (Pact), Elena end-to-end testing (Playwright), and Fatima embedded static application security testing and dependency scanning in CI. A paraphrase test: the question names no tool.

Closest benchmark question: q01 (overlap 0.00).

- [1] `varied/v06_senior_rachel_kim.txt` · experience · chunk 2 (Rachel Kim)
  > Staff Software Engineer, Tidewater Logistics (2020 - Present) - Led the migration of the shipment-tracking platform from a Django monolith to FastAPI microservices running in production on Kubernetes (EKS), serving 40M requests per day. - Designed the Kafka-based event backbone (30+ topics) for real-time shipment status updates. - Mentored 6 engineers; introduced contract testing with Pact.
- [2] `varied/v10_multipage_elena_petrova.txt` · experience · chunk 3 (Elena Petrova)
  > Tech Lead, Lindenpay (2018 - 2021) - Led the rebuild of the checkout frontend in React and TypeScript with a Node.js BFF. - Introduced end-to-end testing with Playwright, cutting checkout regressions by half.
- [3] `varied/v13_security_fatima_zahra.txt` · experience · chunk 2 (Fatima Zahra)
  > Application Security Engineer, Ironclad Insurance (2021 - Present) * Ran threat-modelling sessions for 25 services; embedded SAST (Semgrep) and dependency scanning in CI for 300 repositories. * Led the response to a leaked API key incident; rotated secrets and moved them to HashiCorp Vault.

Judge check, good answer: Rachel Kim introduced contract testing with Pact at Tidewater Logistics [1]; Elena Petrova introduced end-to-end testing with Playwright at Lindenpay, cutting checkout regressions by half [2]; and Fatima Zahra embedded SAST (Semgrep) and dependency scanning in CI for 300 repositories [3].

Judge check, flawed answer (wrong_citation: Rachel's and Elena's citations are swapped.): Rachel Kim introduced contract testing with Pact [2]; Elena Petrova introduced end-to-end testing with Playwright [1]; and Fatima Zahra embedded SAST and dependency scanning in CI [3].

### h06. Which candidates have completed an internship?

*Rationale:* Aarav was a data intern (summer 2025, 10 weeks) and Chen Wei a research intern (summer 2022). Sara's teaching-assistant job is not an internship.

Closest benchmark question: q01 (overlap 0.00).

- [1] `varied/v01_fresher_aarav_mehta.txt` · experience · chunk 4 (Aarav Mehta)
  > Data Intern, Lumen Analytics (Summer 2025, 10 weeks) Cleaned survey data with pandas and built Tableau dashboards.
- [2] `varied/v14_research_scientist_chen_wei.txt` · experience · chunk 4 (Chen Wei)
  > Research Intern, Halcyon AI (Summer 2022) Prototyped knowledge distillation for speech recognition models in PyTorch.

Judge check, good answer: Aarav Mehta was a Data Intern at Lumen Analytics for 10 weeks in summer 2025 [1], and Chen Wei was a Research Intern at Halcyon AI in summer 2022 [2].

Judge check, flawed answer (omission: Chen Wei is left out.): Aarav Mehta completed a 10-week data internship at Lumen Analytics in summer 2025 [1].

### h07. Who has built forecasting models?

*Rationale:* Priya Nair built and deployed forecasting models at Finverse Labs; Omar forecasted weekly demand with LightGBM at Bluepeak Retail.

Closest benchmark question: q20 (overlap 0.20).

- [1] `resume_05_priya_nair.txt` · experience · chunk 3 (Priya Nair)
  > 2 years ML Engineer | Finverse Labs | 2022-Present Built and deployed forecasting and classification models, and supported production monitoring.
- [2] `varied/v07_ml_engineer_omar_haddad.txt` · experience · chunk 3 (Omar Haddad)
  > Data Scientist, Bluepeak Retail (2020 - 2022) Forecasted weekly demand for 3,000 products with LightGBM; owned the feature store in BigQuery.

Judge check, good answer: Priya Nair built and deployed forecasting and classification models at Finverse Labs [1]; Omar Haddad forecasted weekly demand for 3,000 products with LightGBM at Bluepeak Retail [2].

Judge check, flawed answer (invented_claim: The 95% forecast accuracy is in no excerpt.): Priya Nair built and deployed forecasting and classification models at Finverse Labs [1]; Omar Haddad forecasted weekly demand for 3,000 products with LightGBM at Bluepeak Retail, reaching 95% forecast accuracy [2].

### h08. Who has a Professional Scrum Master certification?

*Rationale:* Only Elena lists it.

Closest benchmark question: q05 (overlap 0.14).

- [1] `varied/v10_multipage_elena_petrova.txt` · certifications · chunk 8 (Elena Petrova)
  > - Professional Scrum Master I

Judge check, good answer: Elena Petrova holds the Professional Scrum Master I certification [1].

Judge check, flawed answer (invented_claim: The PMP certification is invented.): Elena Petrova holds the Professional Scrum Master I and PMP certifications [1].

### h09. Who has worked with Elasticsearch?

*Rationale:* Elena scaled Marktplatz's catalog search on Elasticsearch and lists it in her skills.

Closest benchmark question: q01 (overlap 0.00).

- [1] `varied/v10_multipage_elena_petrova.txt` · experience · chunk 4 (Elena Petrova)
  > Senior Full-Stack Engineer, Marktplatz GmbH (2014 - 2018) - Built seller tools in Ruby on Rails and React; scaled the catalog search on Elasticsearch. - Ran the migration from MySQL to PostgreSQL with zero downtime.
- [2] `varied/v10_multipage_elena_petrova.txt` · skills · chunk 7 (Elena Petrova)
  > Leadership: hiring, mentoring, roadmap planning, incident management Engineering: TypeScript, React, Node.js, Ruby on Rails, PostgreSQL, Elasticsearch, Playwright

Judge check, good answer: Elena Petrova scaled the catalog search on Elasticsearch at Marktplatz GmbH [1] and lists Elasticsearch in her skills [2].

Judge check, flawed answer (wrong_citation: The claim cites her skills list, which does not mention the catalog search.): Elena Petrova scaled the catalog search on Elasticsearch at Marktplatz GmbH [2].

### h10. Who has worked on knowledge distillation?

*Rationale:* Chen Wei prototyped knowledge distillation for speech models as a research intern. 'Worked on' is a doing question, so his skills list and the paper title in his publications are not labelled.

Closest benchmark question: q01 (overlap 0.00).

- [1] `varied/v14_research_scientist_chen_wei.txt` · experience · chunk 4 (Chen Wei)
  > Research Intern, Halcyon AI (Summer 2022) Prototyped knowledge distillation for speech recognition models in PyTorch.

Judge check, good answer: Chen Wei prototyped knowledge distillation for speech recognition models in PyTorch as a research intern at Halcyon AI [1].

Judge check, flawed answer (invented_claim: Nothing says the models were deployed to production.): Chen Wei prototyped knowledge distillation for speech recognition models at Halcyon AI and deployed the distilled models to production [1].

### h11. Who reached a regional final in a programming competition?

*Rationale:* Mei was an ICPC regional finalist in 2025.

Closest benchmark question: q26 (overlap 0.14).

- [1] `varied/v04_fresher_mei_tanaka.txt` · other · chunk 4 (Mei Tanaka)
  > distributed systems, competitive programming (ICPC regional finalist 2025)

Judge check, good answer: Mei Tanaka was an ICPC regional finalist in 2025 [1].

Judge check, flawed answer (invented_claim: She was a finalist; the excerpt does not say she won.): Mei Tanaka won the ICPC regional final in 2025 [1].

### h12. Who has built a tool that checks websites for accessibility problems?

*Rationale:* Liam built a browser extension that flags missing alt text and low colour contrast. His summary's 'accessible web apps' is a self-description and is not labelled.

Closest benchmark question: q28 (overlap 0.11).

- [1] `varied/v03_fresher_liam_novak.txt` · projects · chunk 2 (Liam Novak)
  > * Recipe finder - React and TypeScript single-page app using a public recipes API; deployed on Netlify. * Accessibility audit tool - browser extension that flags missing alt text and low colour contrast.

Judge check, good answer: Liam Novak built an accessibility audit tool, a browser extension that flags missing alt text and low colour contrast [1].

Judge check, flawed answer (invented_claim: The user count is invented.): Liam Novak built an accessibility audit tool, a browser extension that flags missing alt text and low colour contrast and is used by 10,000 people [1].

### h13. Which candidates know Flutter or Dart?

*Rationale:* Kwame built Flutter prototypes at Pixelcraft and lists Flutter and Dart.

Closest benchmark question: q01 (overlap 0.00).

- [1] `varied/v11_inline_headings_kwame_asante.txt` · experience · chunk 2 (Kwame Asante)
  > Android Developer at Savanna Mobile (2022-present) - shipped a Kotlin and Jetpack Compose banking app with 500k installs; Junior Developer at Pixelcraft (2021-2022) - built Flutter prototypes for clients.
- [2] `varied/v11_inline_headings_kwame_asante.txt` · skills · chunk 3 (Kwame Asante)
  > Kotlin, Jetpack Compose, Flutter, Dart, Firebase, REST APIs, Git

Judge check, good answer: Kwame Asante built Flutter prototypes for clients at Pixelcraft [1] and lists Flutter and Dart in his skills [2].

Judge check, flawed answer (wrong_citation: The two citations are swapped.): Kwame Asante built Flutter prototypes for clients at Pixelcraft [2] and lists Flutter and Dart in his skills [1].

### h14. Which candidates studied at a university in Texas?

*Rationale:* Ananya (UT Austin) and Lina (UT Dallas). Priya Subramanian lives in Austin, TX, but her degree is from Pinecrest College, whose location is not given.

Closest benchmark question: q01 (overlap 0.00).

- [1] `resume_01_ananya_patel.txt` · education · chunk 4 (Ananya Patel)
  > Master's in Computer Science, University of Texas at Austin
- [2] `resume_07_lina_fernandez.txt` · education · chunk 4 (Lina Fernandez)
  > Master's in Computer Science, University of Texas at Dallas

Judge check, good answer: Ananya Patel holds a Master's in Computer Science from the University of Texas at Austin [1], and Lina Fernandez one from the University of Texas at Dallas [2].

Judge check, flawed answer (omission: Lina Fernandez is left out.): Ananya Patel studied at the University of Texas at Austin [1].

### h15. Who has an associate's degree?

*Rationale:* Only Owen lists an associate's degree.

Closest benchmark question: q01 (overlap 0.00).

- [1] `resume_06_owen_brooks.txt` · education · chunk 4 (Owen Brooks)
  > Associate's in Information Systems, Boston College

Judge check, good answer: Owen Brooks holds an Associate's in Information Systems from Boston College [1].

Judge check, flawed answer (invented_claim: The honours and the year are invented.): Owen Brooks holds an Associate's in Information Systems from Boston College, completed with honours in 2020 [1].

### h16. Who has run A/B test analyses?

*Rationale:* Priya analysed A/B tests for the patient portal at Cedar Health; her two-column resume is one unlabelled chunk.

Closest benchmark question: q01 (overlap 0.17).

- [1] `varied/v08_two_column_style_priya_s.txt` · header · chunk 0 (Priya Subramanian)
  > PRIYA SUBRAMANIAN priya.s@example.com | (555) 201-0008 Data Analyst Austin, TX SKILLS EXPERIENCE SQL (advanced) Senior Data Analyst, Cedar Health (2021 - Present) Python (pandas) Built Looker dashboards used by 200+ clinicians; Looker, Tableau automated monthly KPI reporting in SQL and dbt. dbt Data Analyst, Cedar Health (2019 - 2021) A/B testing Analysed A/B tests for the patient portal.

Judge check, good answer: Priya Subramanian analysed A/B tests for the patient portal as a data analyst at Cedar Health [1].

Judge check, flawed answer (invented_claim: The 15% increase is invented.): Priya Subramanian analysed A/B tests for the patient portal at Cedar Health, raising sign-ups by 15% [1].

### h17. Who has maintained Flask applications?

*Rationale:* Rachel maintained internal Flask tools at Quarry Labs. Her skills list also names Flask, but this is a doing question.

Closest benchmark question: q01 (overlap 0.00).

- [1] `varied/v06_senior_rachel_kim.txt` · experience · chunk 4 (Rachel Kim)
  > Software Engineer, Quarry Labs (2014 - 2016) - Maintained internal tools in Flask and MySQL.

Judge check, good answer: Rachel Kim maintained internal tools in Flask and MySQL at Quarry Labs from 2014 to 2016 [1].

Judge check, flawed answer (invented_claim: The migration to Django is invented.): Rachel Kim maintained internal tools in Flask and MySQL at Quarry Labs and later migrated them to Django [1].

### h18. Who has worked with Microsoft SQL Server?

*Rationale:* Hannah wrote SQL Server queries as a junior data analyst and lists SQL Server; other candidates list SQL in general, not SQL Server.

Closest benchmark question: q01 (overlap 0.00).

- [1] `varied/v12_career_changer_hannah_lee.txt` · experience · chunk 2 (Hannah Lee)
  > Junior Data Analyst, Brightfield Schools Network (2024 - Present) Built attendance and grade dashboards in Power BI; wrote SQL queries against SQL Server.
- [2] `varied/v12_career_changer_hannah_lee.txt` · skills · chunk 5 (Hannah Lee)
  > SQL Server, Power BI, Excel, Python (pandas, basic), data storytelling

Judge check, good answer: Hannah Lee wrote SQL queries against SQL Server at Brightfield Schools Network [1] and lists SQL Server in her skills [2].

Judge check, flawed answer (wrong_citation: The claim cites her skills list, which does not mention Brightfield or writing queries.): Hannah Lee wrote SQL queries against SQL Server at Brightfield Schools Network [2].

### h19. Who studied at an Indian Institute of Technology?

*Rationale:* Rahul holds a Bachelor's in Electronics Engineering from IIT Delhi.

Closest benchmark question: q01 (overlap 0.00).

- [1] `resume_08_rahul_kumar.txt` · education · chunk 4 (Rahul Kumar)
  > Bachelor's in Electronics Engineering, Indian Institute of Technology Delhi

Judge check, good answer: Rahul Kumar holds a Bachelor's in Electronics Engineering from the Indian Institute of Technology Delhi [1].

Judge check, flawed answer (invented_claim: The master's degree is invented.): Rahul Kumar holds a Bachelor's and a Master's in Electronics Engineering from the Indian Institute of Technology Delhi [1].

### h20. Who has connected products to OpenAI-compatible APIs?

*Rationale:* Daniel connected services with OpenAI-compatible APIs at BluePeak AI. Omar's RAG assistant used 'GPT-class models', which does not say OpenAI APIs.

Closest benchmark question: q01 (overlap 0.00).

- [1] `resume_04_daniel_rivera.txt` · experience · chunk 3 (Daniel Rivera)
  > 3 years Software Engineer | BluePeak AI | 2021-Present Implemented AI features into web products and connected services with OpenAI-compatible APIs.

Judge check, good answer: Daniel Rivera implemented AI features in web products and connected services with OpenAI-compatible APIs at BluePeak AI [1].

Judge check, flawed answer (invented_claim: The claim about Omar Haddad is supported by no excerpt.): Daniel Rivera connected services with OpenAI-compatible APIs at BluePeak AI [1], and Omar Haddad integrated the OpenAI API into a support assistant [1].

## Unanswerable

- **u01.** Who has experience with Rust? *No resume mentions Rust.* Absent terms: 'Rust'. Closest benchmark question: q01 (0.00).
- **u02.** Who has written iOS apps in Swift? *No resume mentions iOS or Swift. Kwame is an Android and cross-platform developer, which does not establish iOS work in Swift.* Absent terms: 'iOS', 'Swift'. Closest benchmark question: q10 (0.20).
- **u03.** Which candidates are certified public accountants? *No accounting qualification appears; Rachel's payment-reconciliation service is software work.* Absent terms: 'CPA', 'accountant', 'accounting'. Closest benchmark question: n03 (0.20).
- **u04.** Who speaks Japanese? *No resume lists Japanese. Mei Tanaka lists no languages, and a language must not be inferred from a name.* Absent terms: 'Japanese'. Closest benchmark question: q25 (0.33).
- **u05.** Who has used Snowflake as a data warehouse? *Diego's warehouse is PostgreSQL and Omar used BigQuery; no resume mentions Snowflake.* Absent terms: 'Snowflake'. Closest benchmark question: q13 (0.17).
- **u06.** Who has implemented SAP ERP systems? *No resume mentions SAP or ERP systems.* Absent terms: 'SAP', 'ERP'. Closest benchmark question: q02 (0.12).
- **u07.** Who holds a pilot's license? *No resume mentions flying or a pilot's license.* Absent terms: 'pilot'. Closest benchmark question: q01 (0.00).
- **u08.** Who has managed a team of more than 50 people? *The largest team stated is Elena's 11 engineers across two teams; Rachel mentored 6. No resume states a team of more than 50.* Absent terms: none (checked by reading). Closest benchmark question: q06 (0.12).
- **u09.** Who has a PMP certification? *Elena holds Professional Scrum Master I, which is not PMP; no resume lists PMP.* Absent terms: 'PMP', 'Project Management Professional'. Closest benchmark question: q05 (0.20).
- **u10.** Who has developed games with Unity or Unreal Engine? *No resume mentions game development.* Absent terms: 'Unity', 'Unreal'. Closest benchmark question: q01 (0.00).
- **u11.** Who has administered Oracle databases? *The databases named are PostgreSQL, MySQL, SQL Server, Redis and BigQuery; none is Oracle.* Absent terms: 'Oracle'. Closest benchmark question: q16 (0.17).
- **u12.** Who has written smart contracts for Ethereum? *No resume mentions blockchain work.* Absent terms: 'Ethereum', 'blockchain', 'Solidity', 'smart contract'. Closest benchmark question: q01 (0.00).
- **u13.** Who holds a government security clearance? *Fatima is a security engineer, but no resume states a security clearance.* Absent terms: 'clearance'. Closest benchmark question: q05 (0.17).
- **u14.** Who has designed printed circuit boards? *Rahul studied electronics engineering, but no resume describes hardware design.* Absent terms: 'PCB', 'circuit board', 'circuit boards'. Closest benchmark question: q01 (0.00).
- **u15.** Who has deployed workloads on Microsoft Azure? *The clouds named are AWS and Google Cloud; no resume mentions Azure.* Absent terms: 'Azure'. Closest benchmark question: q01 (0.00).
