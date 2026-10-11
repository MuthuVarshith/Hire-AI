/* Jobs: list, create, view, edit and delete (GET/POST /api/jobs, GET/PUT/DELETE /api/jobs/{id}). */
(function () {
    'use strict';

    const { api, h, $, seg, render, clear, loadingRow, messageRow, skillTags, formatDate, truncate,
        openModal, closeModal, setModalBusy, toast, showAlert, hideAlert, isQuiet, errorMessage } = HireAI;

    const AFFECTED = ['jobs', 'dashboard', 'candidates', 'analytics', 'compare'];
    let editing = null; // the job being edited, or null when creating

    // ---- List ----------------------------------------------------------------------------------

    function jobStatusBadge(job) {
        return h('span', { class: 'badge' + (job.status === 'Filled' ? ' good' : ''), text: job.status || 'Open' });
    }

    async function load() {
        const tbody = $('jobs-list');
        render(tbody, loadingRow(6));
        try {
            const jobs = await HireAI.fetchJobs();
            if (!jobs.length) {
                render(tbody, messageRow(6, 'No jobs yet. Use “Create New Job” to add one.'));
                return;
            }
            render(tbody, jobs.map((job) => {
                const desc = (job.description || '').replace(/\s+/g, ' ').trim();
                return h('tr', null,
                    h('td', null, h('button', { type: 'button', class: 'btn-link', text: job.title,
                        onclick: () => openDetail(job.id) })),
                    h('td', { class: 'text-muted', title: truncate(desc, 600), text: truncate(desc, 90) || '—' }),
                    h('td', { text: String(job.candidates_count ?? 0) }),
                    h('td', null, jobStatusBadge(job)),
                    h('td', { class: 'nowrap', text: formatDate(job.created_at) }),
                    h('td', { class: 'nowrap' },
                        h('button', { type: 'button', class: 'btn btn-sm btn-secondary', text: 'Candidates',
                            onclick: () => HireAI.showCandidatesForJob(job.id) }), ' ',
                        h('button', { type: 'button', class: 'btn btn-sm btn-secondary', text: 'Edit',
                            onclick: () => openJobForm(job) }), ' ',
                        h('button', { type: 'button', class: 'btn btn-sm btn-danger', text: 'Delete',
                            onclick: (e) => deleteJob(job, e.currentTarget) })));
            }));
        } catch (err) {
            if (isQuiet(err)) return;
            console.error('Jobs load failed:', err);
            render(tbody, messageRow(6, errorMessage(err, 'Could not load jobs.'), true));
        }
    }

    // ---- Create / edit -------------------------------------------------------------------------

    async function fillTemplates(select, isEdit) {
        clear(select);
        select.appendChild(new Option(isEdit ? 'Keep the current template' : 'Default weights', ''));
        try {
            const templates = await api('/api/scoring-templates');
            for (const t of templates) {
                select.appendChild(new Option(t.is_default ? `${t.name} (default)` : t.name, String(t.id)));
            }
        } catch (err) {
            if (!isQuiet(err)) console.warn('Could not load scoring templates:', err);
        }
    }

    function setBusy(busy) {
        const label = editing ? 'Save changes' : 'Create Job';
        $('job-submit-btn').disabled = busy;
        $('job-cancel-btn').disabled = busy;
        $('job-submit-btn').textContent = busy ? (editing ? 'Saving…' : 'Creating…') : label;
        setModalBusy('job-modal', busy);
    }

    function openJobForm(job) {
        editing = job || null;
        $('job-modal-title').textContent = editing ? 'Edit Job' : 'Create New Job';
        $('job-title-input').value = editing ? editing.title || '' : '';
        $('job-desc-input').value = editing ? editing.description || '' : '';
        $('job-title-input').classList.remove('invalid');
        $('job-desc-input').classList.remove('invalid');
        hideAlert($('job-form-error'));
        setBusy(false);
        fillTemplates($('job-template-input'), Boolean(editing));
        openModal('job-modal');
    }

    async function submitJob(event) {
        event.preventDefault();
        const titleEl = $('job-title-input');
        const descEl = $('job-desc-input');
        const title = titleEl.value.trim();
        const description = descEl.value.trim();
        const errorBox = $('job-form-error');
        hideAlert(errorBox);
        titleEl.classList.toggle('invalid', !title);
        descEl.classList.toggle('invalid', !description);
        if (!title || !description) {
            const missing = [!title && 'Job Title', !description && 'Job Description'].filter(Boolean);
            showAlert(errorBox, `Please fill in: ${missing.join(' and ')}.`);
            (title ? descEl : titleEl).focus();
            return;
        }

        const payload = { title, description_text: description };
        const templateId = $('job-template-input').value;
        if (templateId) payload.scoring_template_id = parseInt(templateId, 10);

        setBusy(true);
        try {
            const job = editing
                ? await api(`/api/jobs/${seg(editing.id)}`, { method: 'PUT', json: payload })
                : await api('/api/jobs', { method: 'POST', json: payload });
            setBusy(false);
            closeModal('job-modal');
            toast(editing ? `Job "${job.title}" updated.` : `Job "${job.title}" created.`);
            editing = null;
            HireAI.refreshViews(AFFECTED);
        } catch (err) {
            setBusy(false);
            if (isQuiet(err)) return;
            console.error('Saving job failed:', err);
            showAlert(errorBox, `Could not save the job. ${errorMessage(err)}`);
        }
    }

    // ---- Details and delete --------------------------------------------------------------------

    async function openDetail(jobId) {
        const body = $('job-detail');
        const actions = $('job-detail-actions');
        $('job-detail-title').textContent = 'Job';
        render(body, h('div', { class: 'loading', text: 'Loading…' }));
        clear(actions);
        openModal('job-detail-modal');
        try {
            const job = await api(`/api/jobs/${seg(jobId)}`);
            $('job-detail-title').textContent = job.title;
            render(body,
                h('dl', { class: 'detail-grid' },
                    h('dt', { text: 'Status' }), h('dd', null, jobStatusBadge(job)),
                    h('dt', { text: 'Candidates' }), h('dd', { text: String(job.candidates_count ?? 0) }),
                    h('dt', { text: 'Created' }), h('dd', { text: formatDate(job.created_at) }),
                    h('dt', { text: 'Min. experience' }),
                    h('dd', { text: job.min_experience_years ? `${job.min_experience_years} years` : 'Not specified' }),
                    h('dt', { text: 'Education' }), h('dd', { text: job.required_education || 'Not specified' }),
                    h('dt', { text: 'Required skills' }), h('dd', null, skillTags(job.required_skills, { empty: 'None extracted' })),
                    h('dt', { text: 'Preferred skills' }),
                    h('dd', null, skillTags(job.preferred_skills, { variant: 'preferred', empty: 'None extracted' }))),
                h('div', { class: 'card-subtitle', text: 'Description' }),
                h('div', { class: 'passage-text', text: job.description || '' }));
            render(actions,
                h('button', { type: 'button', class: 'btn btn-danger', text: 'Delete',
                    onclick: (e) => deleteJob(job, e.currentTarget) }),
                h('button', { type: 'button', class: 'btn btn-secondary', text: 'Edit',
                    onclick: () => { closeModal('job-detail-modal'); openJobForm(job); } }),
                h('button', { type: 'button', class: 'btn btn-secondary', text: 'View candidates',
                    onclick: () => { closeModal('job-detail-modal'); HireAI.showCandidatesForJob(job.id); } }),
                h('button', { type: 'button', class: 'btn btn-primary', text: 'Close', 'data-close-modal': 'job-detail-modal' }));
        } catch (err) {
            if (isQuiet(err)) return;
            render(body, h('div', { class: 'alert alert-error', text: errorMessage(err, 'Could not load this job.') }));
            render(actions, h('button', { type: 'button', class: 'btn btn-secondary', text: 'Close', 'data-close-modal': 'job-detail-modal' }));
        }
    }

    async function deleteJob(job, button) {
        const count = job.candidates_count ?? 0;
        const ok = window.confirm(`Delete the job "${job.title}" and its ${count} candidate(s)? ` +
            'Their resumes are deleted too. This cannot be undone.');
        if (!ok) return;
        if (button) button.disabled = true;
        try {
            await api(`/api/jobs/${seg(job.id)}`, { method: 'DELETE' });
            toast(`Job "${job.title}" deleted.`);
            closeModal('job-detail-modal');
            HireAI.refreshViews(AFFECTED);
        } catch (err) {
            if (button) button.disabled = false;
            if (isQuiet(err)) return;
            toast(`Could not delete the job. ${errorMessage(err)}`, true);
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        $('jobs-new-btn').addEventListener('click', () => openJobForm(null));
        $('job-form').addEventListener('submit', submitJob);
    });

    HireAI.openJobForm = openJobForm;
    HireAI.openJobDetail = openDetail;
    HireAI.views.jobs = { title: 'Jobs', render: load };
})();
