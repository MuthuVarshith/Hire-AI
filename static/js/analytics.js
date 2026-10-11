/* Analytics: GET /api/analytics/dashboard (optionally per job) and GET /api/analytics/jobs/{id}. */
(function () {
    'use strict';

    const { api, h, $, seg, render, barChart, metricTiles, fmt, fillJobSelect, isQuiet, errorMessage } = HireAI;

    async function load() {
        const metrics = $('analytics-metrics');
        try {
            fillJobSelect($('an-job'), await HireAI.fetchJobs(), 'All jobs');
            const jobId = $('an-job').value;
            const [data, job] = await Promise.all([
                api('/api/analytics/dashboard' + (jobId ? `?job_id=${seg(jobId)}` : '')),
                jobId ? api(`/api/analytics/jobs/${seg(jobId)}`) : Promise.resolve(null),
            ]);
            metricTiles(metrics, [
                ['Total Screened', data.total_screened ?? 0],
                ['Average Score', fmt(data.average_score)],
                ['Shortlist Rate', `${data.shortlist_rate ?? 0}%`],
                ['Offers', data.offers ?? 0],
                ['Hired', data.hired ?? 0],
                ['Rejected', data.rejected ?? 0],
            ]);
            render($('an-score-dist'), barChart(data.score_distribution, 'No screening results yet.'));
            render($('an-pipeline'), barChart(data.pipeline_stages, 'No candidates yet.'));
            render($('an-by-job'), barChart(data.candidates_by_job, 'No jobs yet.'));
            render($('an-skill-gaps'), barChart(data.skill_gaps, 'No skill gaps recorded yet.'));
            render($('an-top-skills'), barChart(data.top_matched_skills, 'No matched skills recorded yet.'));
            const timeline = {};
            ((job && job.screening_timeline) || []).forEach((p) => { timeline[p.date] = p.count; });
            $('an-timeline-card').classList.toggle('hidden', !job);
            render($('an-timeline'), barChart(timeline, 'No screenings in the last 30 days.'));
        } catch (err) {
            if (isQuiet(err)) return;
            console.error('Analytics load failed:', err);
            render(metrics, h('div', { class: 'alert alert-error', text: errorMessage(err, 'Could not load analytics.') }));
        }
    }

    document.addEventListener('DOMContentLoaded', () => $('an-job').addEventListener('change', load));
    HireAI.views.analytics = { title: 'Analytics', render: load };
})();
