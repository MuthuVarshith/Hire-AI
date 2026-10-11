/* Dashboard: headline metrics, recruiter summary, recent candidates, active jobs. */
(function () {
    'use strict';

    const { api, h, $, render, loadingRow, messageRow, metricTiles, scorePill, statusBadge,
        candidateScore, fmt, isQuiet, errorMessage } = HireAI;

    function summary(data, jobs) {
        if (!data.total_screened) {
            return ['No candidates screened yet. Create a job, then upload resumes to get started.'];
        }
        const open = jobs.filter((j) => j.status === 'Open').length;
        const b = (text) => h('strong', { text: String(text) });
        return [
            b(data.total_screened), ' candidate(s) screened across ', b(jobs.length), ` job(s) (${open} open). `,
            'Average screening score is ', b(`${fmt(data.average_score)}/100`),
            ', with a shortlist rate of ', b(`${data.shortlist_rate ?? 0}%`), '. ',
            b(data.offers ?? 0), ' offer(s) out and ', b(data.hired ?? 0), ' hire(s) made.',
        ];
    }

    async function load() {
        const metrics = $('metrics-container');
        const recent = $('recent-candidates');
        const jobsBody = $('dashboard-jobs');
        render(recent, loadingRow(4));
        render(jobsBody, loadingRow(3));
        try {
            const [data, candidates, jobs] = await Promise.all([
                api('/api/analytics/dashboard'),
                api('/api/candidates'),
                HireAI.fetchJobs(),
            ]);

            metricTiles(metrics, [
                ['Total Screened', data.total_screened ?? 0],
                ['Shortlisted', data.shortlisted ?? 0],
                ['In Interview', data.in_interview ?? 0],
                ['Hired', data.hired ?? 0],
            ]);
            const summaryEl = $('recruiter-summary');
            summaryEl.className = '';
            render(summaryEl, summary(data, jobs));

            const latest = [...candidates]
                .sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
                .slice(0, 5);
            render(recent, latest.length ? latest.map((c) => h('tr', null,
                h('td', null, h('button', { type: 'button', class: 'btn-link', text: c.name,
                    onclick: () => HireAI.openCandidate(c.id) })),
                h('td', { text: c.job_title || '—' }),
                h('td', null, statusBadge(c.status)),
                h('td', null, scorePill(candidateScore(c))))) : messageRow(4, 'No candidates yet'));

            render(jobsBody, jobs.length ? jobs.slice(0, 5).map((j) => h('tr', null,
                h('td', null, h('button', { type: 'button', class: 'btn-link', text: j.title,
                    onclick: () => HireAI.showCandidatesForJob(j.id) })),
                h('td', { text: String(j.candidates_count ?? 0) }),
                h('td', null, h('span', { class: 'badge' + (j.status === 'Filled' ? ' good' : ''), text: j.status })))) :
                messageRow(3, 'No jobs yet'));
        } catch (err) {
            if (isQuiet(err)) return;
            console.error('Dashboard load failed:', err);
            render(metrics, h('div', { class: 'alert alert-error', text: errorMessage(err, 'Could not load dashboard data.') }));
            render(recent, messageRow(4, 'Could not load candidates.', true));
            render(jobsBody, messageRow(3, 'Could not load jobs.', true));
        }
    }

    HireAI.views.dashboard = { title: 'Dashboard', render: load };
})();
