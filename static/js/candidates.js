/* Candidates: upload, list (filters and sort), profile, status and notes, resume download,
   screening and delete. */
(function () {
    'use strict';

    const { api, request, readJson, messageFor, ApiError, h, $, seg, render, clear, loadingRow, messageRow,
        scorePill, skillTags, statusBadge, miniBar, screeningOf, candidateScore, formatDate, formatDateTime,
        truncate, fillJobSelect, openModal, closeModal, setModalBusy, toast, showAlert, hideAlert, isQuiet,
        errorMessage, PIPELINE_STATUSES } = HireAI;

    const AFFECTED = ['candidates', 'dashboard', 'jobs', 'analytics'];
    const MAX_RESUME_BYTES = 10 * 1024 * 1024;
    let cache = [];
    let pendingJob = null;
    let loadSeq = 0;

    // ---- Screening (shared with upload, the list, the profile and the comparison) -------------

    async function screenCandidate(candidateId, jobId) {
        try {
            const data = await api(`/api/screen/${seg(candidateId)}/${seg(jobId)}`, { method: 'POST', json: {} });
            return { ok: true, score: Number(data && data.composite_score), screening: data };
        } catch (err) {
            if (isQuiet(err)) return { ok: false, quiet: true, error: '' };
            return { ok: false, error: errorMessage(err, 'The server did not respond.') };
        }
    }

    // ---- List ----------------------------------------------------------------------------------

    async function load() {
        const seq = ++loadSeq;
        const tbody = $('candidates-list');
        render(tbody, loadingRow(8));
        const jobFilter = $('cand-job-filter');
        try {
            const jobs = await HireAI.fetchJobs();
            if (seq !== loadSeq) return;
            fillJobSelect(jobFilter, jobs, 'All jobs');
            if (pendingJob !== null) {
                jobFilter.value = String(pendingJob);
                pendingJob = null;
            }
            const params = new URLSearchParams();
            if (jobFilter.value) params.set('job_id', jobFilter.value);
            if ($('cand-status-filter').value) params.set('status', $('cand-status-filter').value);
            if ($('cand-sort').value === 'score') params.set('sort_by', 'score');
            const query = params.toString();
            const candidates = await api('/api/candidates' + (query ? `?${query}` : ''));
            if (seq !== loadSeq) return; // a newer filter change won
            cache = Array.isArray(candidates) ? candidates : [];
            renderRows();
        } catch (err) {
            if (isQuiet(err) || seq !== loadSeq) return;
            console.error('Candidates load failed:', err);
            render(tbody, messageRow(8, errorMessage(err, 'Could not load candidates.'), true));
        }
    }

    function renderRows() {
        const term = $('cand-search').value.trim().toLowerCase();
        const jobId = $('cand-job-filter').value;
        const status = $('cand-status-filter').value;
        const sort = $('cand-sort').value;

        const rows = cache.filter((c) => {
            if (jobId && String(c.job_id) !== jobId) return false;
            if (status && c.status !== status) return false;
            if (!term) return true;
            return [c.name, c.email, ...(c.skills || [])].join(' ').toLowerCase().includes(term);
        });
        rows.sort((a, b) => {
            if (sort === 'name') return (a.name || '').localeCompare(b.name || '');
            if (sort === 'recent') return new Date(b.created_at) - new Date(a.created_at);
            return (candidateScore(b) ?? -1) - (candidateScore(a) ?? -1); // unscored last
        });

        const tbody = $('candidates-list');
        if (!rows.length) {
            render(tbody, messageRow(8, cache.length || jobId || status
                ? 'No candidates match these filters.'
                : 'No candidates yet. Upload a resume to get started.'));
            return;
        }
        render(tbody, rows.map((c) => {
            const s = screeningOf(c) || {};
            const unscored = candidateScore(c) === null;
            return h('tr', null,
                h('td', null,
                    h('button', { type: 'button', class: 'btn-link', text: c.name, onclick: () => openCandidate(c.id) }),
                    h('div', { class: 'text-muted small', text: `${c.experience_years || 0} yrs` })),
                h('td', { text: c.email || '—' }),
                h('td', { text: c.job_title || '—' }),
                h('td', null, scorePill(candidateScore(c))),
                h('td', null, statusBadge(c.status)),
                h('td', null, skillTags(s.matched_skills, { limit: 3 })),
                h('td', null, skillTags(s.missing_skills, { limit: 3, variant: 'missing' })),
                h('td', { class: 'nowrap' },
                    unscored && c.job_id ? h('button', { type: 'button', class: 'btn btn-sm btn-primary', text: 'Score',
                        onclick: (e) => scoreFromList(e.currentTarget, c) }) : null,
                    unscored && c.job_id ? ' ' : null,
                    h('button', { type: 'button', class: 'btn btn-sm btn-secondary', text: 'View',
                        onclick: () => openCandidate(c.id) })));
        }));
    }

    async function scoreFromList(button, candidate) {
        button.disabled = true;
        button.textContent = 'Scoring…';
        const result = await screenCandidate(candidate.id, candidate.job_id);
        if (result.ok) {
            toast(`${candidate.name} scored ${result.score.toFixed(1)}/100.`);
            HireAI.refreshViews(AFFECTED);
        } else {
            if (!result.quiet) toast(`Scoring failed: ${result.error}`, true);
            button.disabled = false;
            button.textContent = 'Score';
        }
    }

    /** Open the Candidates view filtered to one job. */
    function showCandidatesForJob(jobId) {
        pendingJob = jobId;
        $('cand-search').value = '';
        $('cand-status-filter').value = '';
        HireAI.go('candidates');
    }

    // ---- Profile -------------------------------------------------------------------------------

    function educationText(education) {
        return (education || [])
            .map((e) => (e && typeof e === 'object' ? [e.degree, e.field, e.institution].filter(Boolean).join(', ') : String(e)))
            .filter(Boolean);
    }

    function screeningSection(c, s) {
        if (!s) {
            return h('div', { class: 'card mt' },
                h('div', { class: 'card-title', text: 'Screening' }),
                h('p', { class: 'text-muted', text: 'Not scored yet.' }),
                c.job_id ? h('button', { type: 'button', class: 'btn btn-primary btn-sm mt', text: 'Score against the job',
                    onclick: (e) => rescore(c, e.currentTarget) }) : null);
        }
        const list = (items) => (items && items.length
            ? h('ul', { class: 'bullets' }, items.map((t) => h('li', { text: t })))
            : h('span', { class: 'text-muted', text: '—' }));
        return h('div', { class: 'card mt' },
            h('div', { class: 'section-head' },
                h('div', { class: 'card-title', text: 'Screening' }),
                h('span', { class: 'text-muted small', text: `Scored ${formatDateTime(s.created_at)}` })),
            h('dl', { class: 'detail-grid' },
                h('dt', { text: 'Overall score' }), h('dd', null, scorePill(s.composite_score)),
                h('dt', { text: 'Semantic match' }), h('dd', null, miniBar(s.semantic_score)),
                h('dt', { text: 'Skill match' }), h('dd', null, miniBar(s.skill_match_score)),
                h('dt', { text: 'Experience' }), h('dd', null, miniBar(s.experience_score)),
                h('dt', { text: 'Education' }), h('dd', null, miniBar(s.education_score)),
                h('dt', { text: 'Matched skills' }), h('dd', null, skillTags(s.matched_skills)),
                h('dt', { text: 'Missing skills' }), h('dd', null, skillTags(s.missing_skills, { variant: 'missing' })),
                h('dt', { text: 'Preferred skills' }), h('dd', null, skillTags(s.matched_preferred_skills, { variant: 'preferred' })),
                h('dt', { text: 'Strengths' }), h('dd', null, list(s.strengths)),
                h('dt', { text: 'Gaps' }), h('dd', null, list(s.skill_gaps))),
            s.reasoning ? [
                h('div', { class: 'card-subtitle', text: 'AI-generated analysis' }),
                h('p', { class: 'prewrap', text: s.reasoning })] : null);
    }

    function workHistory(items) {
        const entries = (items || []).filter((w) => w && typeof w === 'object');
        if (!entries.length) return null;
        return [
            h('div', { class: 'card-subtitle', text: 'Work history' }),
            h('ul', { class: 'plain' }, entries.map((w) => h('li', { class: 'passage-item' },
                h('strong', { text: [w.title, w.company].filter(Boolean).join(' · ') || 'Role' }),
                w.duration ? h('span', { class: 'text-muted small', text: ` (${w.duration})` }) : null,
                w.description ? h('div', { class: 'passage-snippet', text: truncate(w.description, 300) }) : null))),
        ];
    }

    function pipelineSection(c) {
        const select = h('select', { id: 'cand-status-select', 'aria-label': 'Pipeline status' },
            PIPELINE_STATUSES.map((st) => h('option', { value: st, text: st, selected: st === c.status })));
        select.addEventListener('change', () => updateCandidate(c, { status: select.value }, select));
        const notes = h('textarea', { id: 'cand-notes', rows: 3, maxlength: 10000, placeholder: 'Private notes for the hiring team' });
        notes.value = c.notes || '';
        const saveNotes = h('button', { type: 'button', class: 'btn btn-secondary btn-sm', text: 'Save notes',
            onclick: () => updateCandidate(c, { notes: notes.value }, saveNotes) });
        return h('div', { class: 'card mt' },
            h('div', { class: 'card-title', text: 'Pipeline' }),
            h('div', { class: 'form-group' }, h('label', { for: 'cand-status-select', text: 'Status' }), select),
            h('div', { class: 'form-group' }, h('label', { for: 'cand-notes', text: 'Notes' }), notes,
                h('div', { class: 'row-gap mt' }, saveNotes)));
    }

    async function openCandidate(candidateId) {
        const body = $('candidate-detail');
        $('candidate-modal-title').textContent = 'Candidate Profile';
        render(body, h('div', { class: 'loading', text: 'Loading…' }));
        openModal('candidate-modal');
        try {
            const c = await api(`/api/candidates/${seg(candidateId)}`);
            const s = screeningOf(c);
            const education = educationText(c.education);
            $('candidate-modal-title').textContent = c.name || 'Candidate Profile';
            render(body,
                h('dl', { class: 'detail-grid' },
                    h('dt', { text: 'Status' }), h('dd', null, statusBadge(c.status)),
                    h('dt', { text: 'Email' }), h('dd', { text: c.email || '—' }),
                    h('dt', { text: 'Phone' }), h('dd', { text: (c.phone || '—').trim() }),
                    h('dt', { text: 'Applied job' }), h('dd', { text: c.job_title || '—' }),
                    h('dt', { text: 'Experience' }), h('dd', { text: `${c.experience_years || 0} years` }),
                    h('dt', { text: 'Education' }), h('dd', null, education.length
                        ? h('ul', { class: 'plain' }, education.map((e) => h('li', { text: e })))
                        : h('span', { class: 'text-muted', text: '—' })),
                    h('dt', { text: 'Skills' }), h('dd', null, skillTags(c.skills, { limit: 24 })),
                    h('dt', { text: 'Added' }), h('dd', { text: formatDate(c.created_at) })),
                workHistory(c.work_history),
                screeningSection(c, s),
                pipelineSection(c),
                h('div', { class: 'row-gap mt' },
                    c.resume_filename ? h('button', { type: 'button', class: 'btn btn-secondary', text: '⬇ Download resume',
                        onclick: (e) => downloadResume(c, e.currentTarget) }) : null,
                    s && c.job_id ? h('button', { type: 'button', class: 'btn btn-secondary', text: 'Re-score',
                        onclick: (e) => rescore(c, e.currentTarget) }) : null,
                    h('button', { type: 'button', class: 'btn btn-danger', text: 'Delete candidate',
                        onclick: (e) => deleteCandidate(c, e.currentTarget) })));
        } catch (err) {
            if (isQuiet(err)) return;
            console.error('Candidate load failed:', err);
            render(body, h('div', { class: 'alert alert-error', text: errorMessage(err, 'Could not load this candidate.') }));
        }
    }

    async function updateCandidate(c, changes, control) {
        control.disabled = true;
        try {
            await api(`/api/candidates/${seg(c.id)}`, { method: 'PUT', json: changes });
            if (changes.status !== undefined) {
                c.status = changes.status;
                toast(`Status updated to ${changes.status}.`);
            } else {
                c.notes = changes.notes;
                toast('Notes saved.');
            }
            HireAI.refreshViews(AFFECTED);
        } catch (err) {
            if (isQuiet(err)) return;
            toast(`Could not update the candidate. ${errorMessage(err)}`, true);
            if (changes.status !== undefined) control.value = c.status; // put the select back
        } finally {
            control.disabled = false;
        }
    }

    async function rescore(c, button) {
        button.disabled = true;
        const label = button.textContent;
        button.textContent = 'Scoring…';
        const result = await screenCandidate(c.id, c.job_id);
        if (result.ok) {
            toast(`${c.name} scored ${result.score.toFixed(1)}/100.`);
            HireAI.refreshViews(AFFECTED);
            openCandidate(c.id);
        } else {
            if (!result.quiet) toast(`Scoring failed: ${result.error}`, true);
            button.disabled = false;
            button.textContent = label;
        }
    }

    function filenameFrom(disposition) {
        if (!disposition) return null;
        let name = null;
        const star = /filename\*\s*=\s*(?:UTF-8|utf-8)''([^;]+)/.exec(disposition);
        if (star) {
            try { name = decodeURIComponent(star[1].trim()); } catch (e) { name = null; }
        }
        if (!name) {
            const plain = /filename\s*=\s*"?([^";]+)"?/.exec(disposition);
            if (plain) name = plain[1].trim();
        }
        // eslint-disable-next-line no-control-regex
        return name ? name.replace(/[\\/\u0000-\u001f]/g, '_') : null;
    }

    async function downloadResume(c, button) {
        button.disabled = true;
        try {
            const res = await request(`/api/candidates/${seg(c.id)}/resume`, { accept: '*/*' });
            if (!res.ok) {
                const payload = await readJson(res);
                throw new ApiError(res.status, messageFor(res.status, payload), payload);
            }
            const blob = await res.blob();
            const ext = /\.(pdf|docx|txt)$/i.exec(c.resume_filename || '');
            const name = filenameFrom(res.headers.get('content-disposition')) || `resume-${c.id}${ext ? ext[0] : ''}`;
            const url = URL.createObjectURL(blob);
            const link = h('a', { href: url, download: name, class: 'hidden' });
            document.body.appendChild(link);
            link.click();
            link.remove();
            setTimeout(() => URL.revokeObjectURL(url), 10000);
        } catch (err) {
            if (isQuiet(err)) return;
            toast(`Could not download the resume. ${errorMessage(err)}`, true);
        } finally {
            button.disabled = false;
        }
    }

    async function deleteCandidate(c, button) {
        if (!window.confirm(`Delete ${c.name || 'this candidate'} and their resume? This cannot be undone.`)) return;
        button.disabled = true;
        try {
            await api(`/api/candidates/${seg(c.id)}`, { method: 'DELETE' });
            toast(`${c.name || 'Candidate'} deleted.`);
            closeModal('candidate-modal');
            HireAI.refreshViews([...AFFECTED, 'compare']);
        } catch (err) {
            button.disabled = false;
            if (isQuiet(err)) return;
            toast(`Could not delete the candidate. ${errorMessage(err)}`, true);
        }
    }

    // ---- Upload --------------------------------------------------------------------------------

    function setUploadBusy(busy, label) {
        $('upload-submit-btn').disabled = busy;
        $('upload-cancel-btn').disabled = busy;
        $('upload-submit-btn').textContent = busy ? (label || 'Uploading…') : 'Upload';
        setModalBusy('upload-modal', busy);
    }

    async function openUpload() {
        hideAlert($('upload-form-error'));
        $('upload-job-select').classList.remove('invalid');
        $('resume-file-input').classList.remove('invalid');
        setUploadBusy(false);
        openModal('upload-modal');
        const select = $('upload-job-select');
        try {
            const jobs = await HireAI.fetchJobs();
            fillJobSelect(select, jobs, 'Select a job…');
            const filtered = $('cand-job-filter').value;
            if (!select.value && filtered) select.value = filtered;
            if (!jobs.length) showAlert($('upload-form-error'), 'Create a job first, then upload resumes against it.', 'warning');
        } catch (err) {
            if (isQuiet(err)) return;
            clear(select);
            select.appendChild(new Option('Could not load jobs', ''));
        }
    }

    async function submitUpload(event) {
        event.preventDefault();
        const jobSelect = $('upload-job-select');
        const fileInput = $('resume-file-input');
        const errorBox = $('upload-form-error');
        const jobId = jobSelect.value;
        const file = fileInput.files[0];
        hideAlert(errorBox);
        jobSelect.classList.toggle('invalid', !jobId);
        fileInput.classList.toggle('invalid', !file);
        if (!jobId || !file) {
            const missing = [!jobId && 'a job', !file && 'a resume file'].filter(Boolean);
            showAlert(errorBox, `Please select ${missing.join(' and ')}.`);
            return;
        }
        if (file.size > MAX_RESUME_BYTES) {
            fileInput.classList.add('invalid');
            showAlert(errorBox, `"${file.name}" is ${(file.size / 1048576).toFixed(1)} MB. The limit is 10 MB.`);
            return;
        }

        const form = new FormData();
        form.append('resume', file);
        setUploadBusy(true);
        try {
            const candidate = await api(`/api/candidates?job_id=${seg(jobId)}`, { method: 'POST', body: form });
            setUploadBusy(true, 'Screening…');
            const screening = await screenCandidate(candidate.id, jobId);
            setUploadBusy(false);
            closeModal('upload-modal');
            fileInput.value = '';
            if (screening.ok) {
                toast(`${candidate.name} added. Score: ${screening.score.toFixed(1)}/100.`);
            } else if (!screening.quiet) {
                toast(`${candidate.name} was added, but scoring failed: ${screening.error} ` +
                    'Use "Score" in the Candidates list to retry.', true);
            }
            HireAI.refreshViews(AFFECTED);
        } catch (err) {
            setUploadBusy(false);
            if (isQuiet(err)) return;
            console.error('Upload failed:', err);
            if (err.status === 409) {
                const dup = (err.payload && err.payload.existing_candidate) || {};
                showAlert(errorBox, `${dup.name || 'This candidate'} has already been added for this job ` +
                    `(status: ${dup.status || 'unknown'}).`);
            } else {
                showAlert(errorBox, `Could not upload the resume. ${errorMessage(err)}`);
            }
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        $('cand-search').addEventListener('input', renderRows);
        $('cand-job-filter').addEventListener('change', load);
        $('cand-status-filter').addEventListener('change', load);
        $('cand-sort').addEventListener('change', load);
        $('cand-upload-btn').addEventListener('click', openUpload);
        $('upload-form').addEventListener('submit', submitUpload);
    });

    Object.assign(HireAI, { openCandidate, openUpload, showCandidatesForJob, screenCandidate });
    HireAI.views.candidates = { title: 'Candidates', render: load };
})();
