/* Agent: run, show steps and the proposed shortlist, approve or reject (reviewer = signed-in user). */
(function () {
    'use strict';

    const { api, h, $, seg, render, scorePill, skillTags, passageItem, fillJobSelect, formatDateTime,
        showAlert, hideAlert, isQuiet, errorMessage } = HireAI;

    // Step errors and unknown tool names can carry model-written text, so only fixed labels show.
    const TOOLS = ['search_candidates', 'get_candidate_profile', 'score_candidate', 'compare_candidates', 'skill_gap_report'];
    const STATUS = {
        running: ['Running', ''], pending_approval: ['Waiting for your approval', 'warn'], answered: ['Answered', ''],
        stopped: ['Stopped', 'muted'], approved: ['Approved', 'good'], rejected: ['Rejected', 'bad'],
        job_deleted: ['Job deleted', 'bad'], candidates_deleted: ['Candidates deleted', 'bad'], error: ['Error', 'bad'],
    };
    let busy = false;

    function badge(status) {
        const [text, cls] = STATUS[status] || [String(status || 'unknown'), 'muted'];
        return h('span', { class: 'badge' + (cls ? ' ' + cls : ''), text });
    }

    function argsText(args) {
        if (!args || typeof args !== 'object') return '';
        return Object.entries(args).map(([k, v]) => `${k}: ${HireAI.truncate(JSON.stringify(v), 80)}`).join(', ');
    }

    function stepItem(s) {
        if (s.type !== 'tool') return h('li', null, h('strong', { text: 'Planner reply refused' }));
        const known = TOOLS.includes(s.tool);
        const hits = s.ok && s.result && Array.isArray(s.result.hits) ? ` (${s.result.hits.length} passages)` : '';
        return h('li', null,
            h('strong', { text: known ? s.tool : 'unknown tool' }), ' ',
            h('span', { class: 'badge ' + (s.ok ? 'good' : 'bad'), text: s.ok ? 'ok' : 'failed' }), hits,
            known ? h('div', { class: 'step-args', text: argsText(s.args) }) : null);
    }

    function entryCard(e, i) {
        return h('div', { class: 'shortlist-entry' },
            h('div', { class: 'entry-head' },
                h('span', { class: 'rank', text: `#${i + 1}` }),
                h('button', { type: 'button', class: 'btn-link', text: e.candidate_name || `Candidate ${e.candidate_id}`,
                    onclick: () => HireAI.openCandidate(e.candidate_id) }),
                scorePill(e.composite_score),
                h('span', { class: 'badge muted', text: e.score_source === 'stored' ? 'stored screening' : 'computed now, not saved' })),
            h('div', { class: 'small' }, 'Matched: ', skillTags(e.matched_skills)),
            h('div', { class: 'small' }, 'Missing: ', skillTags(e.missing_skills, { variant: 'missing' })),
            (e.citations || []).length ? h('ul', { class: 'passage-list mt' },
                e.citations.map((c, n) => passageItem({ ...c, candidate_name: c.candidate_name || e.candidate_name }, n + 1))) : null);
    }

    function decisionBox(body) {
        const note = h('textarea', { rows: 2, maxlength: 2000, id: 'agent-note', placeholder: 'Optional note for the record' });
        const approve = h('button', { type: 'button', class: 'btn btn-good', text: 'Approve' });
        const reject = h('button', { type: 'button', class: 'btn btn-danger', text: 'Reject' });
        const error = h('div', { class: 'alert alert-error hidden mt', role: 'alert' });
        const controls = [approve, reject, note];
        async function decide(decision) {
            if (busy) return;
            busy = true;
            controls.forEach((c) => { c.disabled = true; });
            $('agent-run').disabled = true;
            hideAlert(error);
            try {
                const result = await api(`/api/agent/approve/${seg(body.thread_id)}`,
                    { method: 'POST', json: { decision, note: note.value.trim() || null } });
                busy = false;
                show(result);
            } catch (err) {
                busy = false;
                $('agent-run').disabled = false;
                if (isQuiet(err)) return;
                if (err.status === 410) {
                    show({ ...body, status: err.payload && /job/i.test(err.message) ? 'job_deleted' : 'candidates_deleted', message: err.message });
                    return;
                }
                showAlert(error, errorMessage(err, 'The decision was not recorded.'));
                if (err.status !== 409 && err.status !== 404) controls.forEach((c) => { c.disabled = false; });
            }
        }
        approve.addEventListener('click', () => decide('approve'));
        reject.addEventListener('click', () => decide('reject'));
        const who = HireAI.user && HireAI.user.name ? `You are signed in as ${HireAI.user.name}; your name is recorded as the reviewer.` : 'Your account is recorded as the reviewer.';
        return h('div', { class: 'decision-box' },
            h('div', { class: 'card-subtitle', text: 'Your decision' }),
            h('p', { class: 'text-muted small', text: who }),
            h('div', { class: 'form-group' }, h('label', { for: 'agent-note', text: 'Note (optional)' }), note),
            h('div', { class: 'row-gap' }, approve, reject), error);
    }

    function show(body) {
        const out = $('agent-result');
        out.classList.remove('hidden');
        const p = body.proposal;
        const d = body.decision;
        const sl = body.shortlist;
        render(out,
            h('div', { class: 'card' },
                h('div', { class: 'section-head' }, h('h2', { class: 'card-title', text: 'Result' }), badge(body.status)),
                h('p', { class: 'prewrap', text: body.message || '' }),
                (body.steps || []).length ? [h('div', { class: 'card-subtitle', text: 'Steps' }),
                    h('ol', { class: 'steps-list' }, body.steps.map(stepItem))] : null),
            p ? h('div', { class: 'card' },
                h('h2', { class: 'card-title', text: sl ? 'Approved shortlist' : 'Proposed shortlist' }),
                p.note ? h('p', { class: 'text-muted' }, 'Agent note: ', p.note) : null,
                p.note_removed ? h('p', { class: 'text-muted small', text: 'Part of the agent’s note was removed by a safety filter.' }) : null,
                (p.dropped_ids || []).length ? h('p', { class: 'text-muted small',
                    text: `${p.dropped_ids.length} proposed candidate(s) were left out because they were not in the search results or not on this job.` }) : null,
                ((sl && sl.entries) || p.entries || []).map(entryCard),
                d ? h('div', { class: 'alert ' + (d.decision === 'approve' ? 'alert-success' : 'alert-warning') },
                    `${d.decision === 'approve' ? 'Approved' : 'Rejected'} by ${d.reviewer || 'a reviewer'}.`,
                    d.note ? ` Note: ${d.note}` : '') : null,
                sl ? h('p', { class: 'text-muted small', text: `Shortlist #${sl.id} saved by ${sl.approved_by} at ${formatDateTime(sl.approved_at)}.` }) : null,
                body.status === 'pending_approval' ? decisionBox(body) : null) : null);
    }

    async function run(event) {
        event.preventDefault();
        if (busy) return;
        const text = $('agent-request').value.trim();
        hideAlert($('agent-error'));
        if (!text) { showAlert($('agent-error'), 'Type a request first.'); return; }
        const payload = { request: text };
        if ($('agent-job').value) payload.job_id = parseInt($('agent-job').value, 10);
        busy = true;
        $('agent-run').disabled = true;
        $('agent-run').textContent = 'Running…';
        try {
            show(await api('/api/agent/run', { method: 'POST', json: payload }));
        } catch (err) {
            if (!isQuiet(err)) showAlert($('agent-error'), errorMessage(err, 'The agent could not run.'));
        } finally {
            busy = false;
            $('agent-run').disabled = false;
            $('agent-run').textContent = 'Run';
        }
    }

    async function load() {
        try { fillJobSelect($('agent-job'), await HireAI.fetchJobs(), 'No job'); } catch (e) { /* keep "No job" */ }
    }

    document.addEventListener('DOMContentLoaded', () => $('agent-form').addEventListener('submit', run));
    HireAI.views.agent = { title: 'Agent', render: load };
})();
