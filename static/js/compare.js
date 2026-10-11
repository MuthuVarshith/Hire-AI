/* Compare 2-4 candidates for one job side by side: scores, skills and gaps. */
(function () {
    'use strict';

    const { api, h, $, seg, render, clear, fillJobSelect, scorePill, skillTags, statusBadge, miniBar,
        screeningOf, candidateScore, isNum, showAlert, hideAlert, isQuiet, errorMessage } = HireAI;

    const MAX = 4;
    let pool = [];
    const chosen = new Set();

    function screeningFor(c, jobId) {
        const s = screeningOf(c);
        if (s && s.job_id === jobId) return s;
        const history = (c.screening_history || []).filter((x) => x && x.job_id === jobId);
        history.sort((a, b) => (a.id || 0) - (b.id || 0));
        return history.length ? history[history.length - 1] : null;
    }

    function updatePicker() {
        $('cmp-go').disabled = chosen.size < 2;
        $('cmp-pick-hint').textContent = `Choose 2 to ${MAX} candidates (${chosen.size} chosen).`;
        $('cmp-candidates').querySelectorAll('input').forEach((box) => {
            box.disabled = !box.checked && chosen.size >= MAX;
            box.closest('label').classList.toggle('checked', box.checked);
        });
    }

    async function loadPool() {
        const jobId = $('cmp-job').value;
        chosen.clear();
        hideAlert($('cmp-error'));
        $('cmp-result-card').classList.add('hidden');
        $('cmp-picker').classList.toggle('hidden', !jobId);
        if (!jobId) return;
        render($('cmp-candidates'), h('div', { class: 'loading', text: 'Loading…' }));
        try {
            pool = await api(`/api/candidates?job_id=${seg(jobId)}&sort_by=score`);
            if (!pool.length) {
                render($('cmp-candidates'), h('div', { class: 'empty-state', text: 'No candidates for this job yet.' }));
            } else {
                render($('cmp-candidates'), pool.map((c) => {
                    const box = h('input', { type: 'checkbox', value: String(c.id) });
                    box.addEventListener('change', () => {
                        if (box.checked) chosen.add(c.id); else chosen.delete(c.id);
                        updatePicker();
                    });
                    return h('label', { class: 'pick-item' }, box, h('span', { class: 'grow', text: c.name }), scorePill(candidateScore(c)));
                }));
            }
            updatePicker();
        } catch (err) {
            if (!isQuiet(err)) showAlert($('cmp-error'), errorMessage(err, 'Could not load candidates.'));
        }
    }

    async function pickTop() {
        try {
            const top = await api(`/api/analytics/top-candidates?job_id=${seg($('cmp-job').value)}&limit=3`);
            chosen.clear();
            (top || []).forEach((t) => chosen.add(t.id));
            $('cmp-candidates').querySelectorAll('input').forEach((box) => { box.checked = chosen.has(Number(box.value)); });
            updatePicker();
            if (chosen.size < 2) showAlert($('cmp-error'), 'Fewer than 2 candidates have scores for this job.', 'warning');
        } catch (err) {
            if (!isQuiet(err)) showAlert($('cmp-error'), errorMessage(err, 'Could not load the top candidates.'));
        }
    }

    function bestIndex(values) {
        const nums = values.filter(isNum);
        if (nums.length < 2) return -1;
        const max = Math.max(...nums);
        return values.filter((v) => v === max).length === 1 ? values.indexOf(max) : -1;
    }

    function row(label, cells, values) {
        const best = values ? bestIndex(values) : -1;
        return h('tr', null, h('td', { text: label }), cells.map((cell, i) => h('td', { class: i === best ? 'best' : null },
            cell, i === best ? h('span', { class: 'best-mark', text: 'Best' }) : null)));
    }

    async function compare() {
        const jobId = parseInt($('cmp-job').value, 10);
        hideAlert($('cmp-error'));
        $('cmp-go').disabled = true;
        const target = $('cmp-result');
        render(target, h('div', { class: 'loading', text: 'Loading…' }));
        $('cmp-result-card').classList.remove('hidden');
        try {
            const [job, ...people] = await Promise.all([api(`/api/jobs/${seg(jobId)}`), ...[...chosen].map((id) => api(`/api/candidates/${seg(id)}`))]);
            const ss = people.map((c) => screeningFor(c, jobId));
            const val = (k) => ss.map((s) => (s && isNum(s[k]) ? s[k] : null));
            const list = (items) => (items && items.length ? h('ul', { class: 'bullets' }, items.map((t) => h('li', { text: t }))) : '—');
            const required = job.required_skills || [];
            $('cmp-result-title').textContent = `Side by side for ${job.title}`;
            render(target, h('table', { class: 'compare-table' },
                h('thead', null, h('tr', null, h('th', { text: '' }), people.map((c) => h('th', null,
                    h('button', { type: 'button', class: 'btn-link', text: c.name, onclick: () => HireAI.openCandidate(c.id) }))))),
                h('tbody', null,
                    row('Status', people.map((c) => statusBadge(c.status))),
                    row('Overall score', ss.map((s, i) => (s ? scorePill(s.composite_score)
                        : h('button', { type: 'button', class: 'btn btn-sm btn-primary', text: 'Score now', onclick: async (e) => {
                            e.currentTarget.disabled = true;
                            const r = await HireAI.screenCandidate(people[i].id, jobId);
                            if (r.ok) compare(); else if (!r.quiet) HireAI.toast(`Scoring failed: ${r.error}`, true);
                        } }))), val('composite_score')),
                    row('Semantic', ss.map((s) => miniBar(s && s.semantic_score)), val('semantic_score')),
                    row('Skills', ss.map((s) => miniBar(s && s.skill_match_score)), val('skill_match_score')),
                    row('Experience', ss.map((s) => miniBar(s && s.experience_score)), val('experience_score')),
                    row('Education', ss.map((s) => miniBar(s && s.education_score)), val('education_score')),
                    row('Years of experience', people.map((c) => `${c.experience_years || 0}`), people.map((c) => c.experience_years || 0)),
                    required.map((skill) => row(skill, ss.map((s) => {
                        if (!s) return '—';
                        if ((s.matched_skills || []).includes(skill)) return h('span', { class: 'mark-yes', text: '✓ has it' });
                        if ((s.missing_skills || []).includes(skill)) return h('span', { class: 'mark-no', text: '✗ missing' });
                        return '—';
                    }))),
                    row('Missing skills', ss.map((s) => (s ? skillTags(s.missing_skills, { variant: 'missing', empty: 'None' }) : '—'))),
                    row('Preferred skills', ss.map((s) => (s ? skillTags(s.matched_preferred_skills, { variant: 'preferred' }) : '—'))),
                    row('Strengths', ss.map((s) => (s ? list(s.strengths) : '—'))),
                    row('Gaps', ss.map((s) => (s ? list(s.skill_gaps) : '—'))))));
        } catch (err) {
            if (!isQuiet(err)) render(target, h('div', { class: 'alert alert-error', text: errorMessage(err, 'Could not load the comparison.') }));
        } finally {
            updatePicker();
        }
    }

    async function load() {
        try {
            const before = $('cmp-job').value;
            fillJobSelect($('cmp-job'), await HireAI.fetchJobs(), 'Choose a job…');
            if ($('cmp-job').value !== before || !pool.length) loadPool();
        } catch (err) {
            if (!isQuiet(err)) showAlert($('cmp-error'), errorMessage(err, 'Could not load jobs.'));
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        $('cmp-job').addEventListener('change', loadPool);
        $('cmp-top').addEventListener('click', pickTop);
        $('cmp-go').addEventListener('click', compare);
    });
    HireAI.views.compare = { title: 'Compare', render: load };
    void clear;
})();
