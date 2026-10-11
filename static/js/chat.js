/* Ask the candidate pool: POST /api/ask/stream read with fetch + a stream reader (contract
   section 4). Tokens are a provisional draft; only `done` is an answer. Falls back to
   POST /api/ask when streaming is unavailable before any event arrives. */
(function () {
    'use strict';

    const { api, request, readJson, messageFor, h, $, render, clear, fillJobSelect, citationButton,
        passageItem, showAlert, hideAlert, isQuiet } = HireAI;

    const REASONS = {
        llm_disabled: 'The answer writer is turned off on this server.',
        llm_error: 'The answer writer failed for this question.',
    };
    let controller = null;

    /** Minimal SSE parser: handles \n, \r\n and \r line ends, comments and multi-line data. */
    function createSSEParser(onEvent) {
        let buffer = '';
        let type = '';
        let data = [];
        function line(text) {
            if (text === '') {
                if (data.length) onEvent(type || 'message', data.join('\n'));
                type = '';
                data = [];
                return;
            }
            if (text[0] === ':') return; // comment, e.g. ": ping"
            const colon = text.indexOf(':');
            const field = colon === -1 ? text : text.slice(0, colon);
            let value = colon === -1 ? '' : text.slice(colon + 1);
            if (value[0] === ' ') value = value.slice(1);
            if (field === 'event') type = value;
            else if (field === 'data') data.push(value);
        }
        return {
            push(chunk) {
                buffer += chunk;
                let start = 0;
                for (let i = 0; i < buffer.length; i++) {
                    const c = buffer[i];
                    if (c !== '\n' && c !== '\r') continue;
                    if (c === '\r' && i + 1 === buffer.length) break; // may be half of \r\n
                    line(buffer.slice(start, i));
                    if (c === '\r' && buffer[i + 1] === '\n') i++;
                    start = i + 1;
                }
                buffer = buffer.slice(start);
            },
            end() { buffer = ''; type = ''; data = []; }, // an unterminated event is dropped
        };
    }

    /** Answer text with [n] markers turned into passage buttons. */
    function answerNodes(text, byNumber) {
        const out = [];
        const re = /\[(\d+)\]/g;
        let last = 0;
        let m;
        while ((m = re.exec(text)) !== null) {
            if (m.index > last) out.push(text.slice(last, m.index));
            const c = byNumber.get(Number(m[1]));
            out.push(c ? citationButton(Number(m[1]), c) : m[0]);
            last = re.lastIndex;
        }
        if (last < text.length) out.push(text.slice(last));
        return out;
    }

    function createTurn(question) {
        const status = h('div', { class: 'chat-status', text: 'Searching resumes…' });
        const draftText = h('p', { class: 'draft-text' });
        const draftLabel = h('div', { class: 'draft-label', text: 'Draft, still being written and not yet checked against the resumes' });
        const draft = h('div', { class: 'chat-draft streaming hidden' }, draftLabel, draftText);
        const final = h('div', { class: 'hidden' });
        const node = h('article', { class: 'chat-turn' },
            h('div', { class: 'chat-label', text: 'You' }), h('p', { class: 'chat-question', text: question }),
            h('div', { class: 'chat-label', text: 'HireAI' }), status, draft, final);
        $('ask-log').prepend(node);
        const citations = new Map();
        let hasDraft = false;

        function finish() { status.remove(); draft.classList.remove('streaming'); }
        function discardDraft() { draft.remove(); }
        function showFinal(...children) { render(final, children); final.classList.remove('hidden'); }

        function passages(list) {
            return h('ul', { class: 'passage-list' }, list.map((c) => passageItem(c, c.number)));
        }

        return {
            token(text) {
                if (typeof text !== 'string') return;
                hasDraft = true;
                draft.classList.remove('hidden');
                status.textContent = 'Writing a draft…';
                draftText.appendChild(document.createTextNode(text));
            },
            citation(c) { if (c && Number.isInteger(c.number)) citations.set(c.number, c); },
            done(p, note) {
                finish();
                discardDraft();
                const nums = Array.isArray(p.citation_numbers) ? p.citation_numbers : [...citations.keys()];
                const list = nums.map((n) => citations.get(n)).filter(Boolean);
                const meta = note ? h('div', { class: 'chat-meta', text: note }) : null;
                if (!p.found) {
                    showFinal(h('p', { class: 'chat-answer not-found', text: p.answer || 'Not found in resumes.' }),
                        hasDraft ? h('div', { class: 'chat-meta', text: 'The draft was discarded because its citations could not be checked against the resumes.' }) : null,
                        meta);
                } else if (p.summary_unavailable) {
                    showFinal(h('div', { class: 'alert alert-warning' },
                        h('strong', { text: 'Summary unavailable. ' }),
                        REASONS[p.summary_unavailable_reason] || 'No summary could be written.',
                        ' The passages below are search results, not an answer.'),
                    list.length ? passages(list) : h('p', { class: 'text-muted', text: 'No passages.' }), meta);
                } else {
                    showFinal(h('p', { class: 'chat-answer' }, answerNodes(String(p.answer || ''), citations)),
                        list.length ? [h('div', { class: 'card-subtitle', text: 'Sources' }), passages(list)] : null, meta);
                }
            },
            error(message) {
                finish();
                if (hasDraft) {
                    draft.classList.add('incomplete');
                    draftLabel.textContent = 'Incomplete draft. This is not an answer.';
                } else discardDraft();
                showFinal(h('div', { class: 'alert alert-error', text: message || 'The answer could not be completed. Please try again.' }));
            },
        };
    }

    async function fallback(turn, question, jobId, signal) {
        try {
            const r = await api('/api/ask', { method: 'POST', json: { question, job_id: jobId }, signal });
            (r.citations || []).forEach((c) => turn.citation(c));
            turn.done({ ...r, citation_numbers: (r.citations || []).map((c) => c.number) }, 'Answered without streaming.');
        } catch (err) {
            if (err && err.name === 'AbortError') turn.error('Stopped.');
            else if (!isQuiet(err)) turn.error(err.status && err.status < 500 ? err.message : null);
        }
    }

    async function ask(question, jobId) {
        const turn = createTurn(question);
        controller = new AbortController();
        const signal = controller.signal;
        let res;
        try {
            res = await request('/api/ask/stream', { method: 'POST', json: { question, job_id: jobId }, signal, accept: 'text/event-stream' });
        } catch (err) {
            if (err.name === 'AbortError') return turn.error('Stopped.');
            if (isQuiet(err)) return;
            return fallback(turn, question, jobId, signal);
        }
        if (!res.ok) {
            const payload = await readJson(res);
            const missingRoute = (res.status === 404 && payload && payload.error === 'Not found') || res.status === 405 || res.status >= 500;
            if (missingRoute) return fallback(turn, question, jobId, signal);
            return turn.error(messageFor(res.status, payload)); // validation error, sent before the stream
        }
        if (!(res.headers.get('content-type') || '').includes('text/event-stream') || !res.body) {
            return fallback(turn, question, jobId, signal);
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let terminal = false;
        let sawEvent = false;
        const parser = createSSEParser((type, data) => {
            if (terminal) return;
            let p;
            try { p = JSON.parse(data); } catch (e) { return; }
            sawEvent = true;
            if (type === 'token') turn.token(p.text);
            else if (type === 'citation') turn.citation(p);
            else if (type === 'done') { terminal = true; turn.done(p); }
            else if (type === 'error') { terminal = true; turn.error(null); } // generic message only
        });
        try {
            while (!terminal) {
                const { value, done } = await reader.read();
                if (done) break;
                parser.push(decoder.decode(value, { stream: true }));
            }
            if (!terminal) { parser.push(decoder.decode()); parser.end(); }
        } catch (err) {
            if (err && err.name === 'AbortError') { if (!terminal) turn.error('Stopped.'); return; }
            if (!terminal && !sawEvent) return fallback(turn, question, jobId, signal);
        } finally {
            if (terminal) reader.cancel().catch(() => {});
        }
        if (!terminal) turn.error(null); // stream ended without done/error
    }

    function setBusy(busy) {
        $('ask-send').disabled = busy;
        $('ask-send').textContent = busy ? 'Asking…' : 'Ask';
        $('ask-stop').classList.toggle('hidden', !busy);
    }

    async function submit(event) {
        event.preventDefault();
        if (controller) return;
        const question = $('ask-question').value.trim();
        hideAlert($('ask-error'));
        if (!question) { showAlert($('ask-error'), 'Type a question first.'); return; }
        const jobValue = $('ask-job').value;
        setBusy(true);
        try {
            await ask(question, jobValue ? parseInt(jobValue, 10) : null);
            $('ask-question').value = '';
        } finally {
            controller = null;
            setBusy(false);
        }
    }

    async function load() {
        try { fillJobSelect($('ask-job'), await HireAI.fetchJobs(), 'All jobs'); } catch (e) { /* keep "All jobs" */ }
    }

    document.addEventListener('DOMContentLoaded', () => {
        $('ask-form').addEventListener('submit', submit);
        $('ask-stop').addEventListener('click', () => { if (controller) controller.abort(); });
        $('ask-clear').addEventListener('click', () => clear($('ask-log')));
        $('ask-question').addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); $('ask-form').requestSubmit(); }
        });
        $('ask-suggestions').addEventListener('click', (e) => {
            const b = e.target.closest('[data-question]');
            if (b) { $('ask-question').value = b.getAttribute('data-question'); $('ask-question').focus(); }
        });
    });

    HireAI.createSSEParser = createSSEParser;
    HireAI.views.ask = { title: 'Ask the pool', render: load };
})();
