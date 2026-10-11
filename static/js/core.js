/* HireAI dashboard: shared helpers (API client, DOM builder, formatting, modals, toasts).
 *
 * XSS rule for every file in static/js: user and resume text only ever reaches the page through
 * textContent or text nodes (h() below never touches innerHTML), attribute values go through
 * setAttribute, and event handlers are functions attached with addEventListener.
 */
(function () {
    'use strict';

    const HireAI = (window.HireAI = window.HireAI || {});
    HireAI.views = {};

    // ---- API client --------------------------------------------------------------------------

    class ApiError extends Error {
        constructor(status, message, payload) {
            super(message);
            this.name = 'ApiError';
            this.status = status;
            this.payload = payload || null;
            this.redirecting = false;
            this.network = false;
        }
    }

    const RETURN_KEY = 'hireai.returnTo';
    let redirecting = false;

    /** Any 401 sends the browser to the login page, remembering the current view. */
    function redirectToLogin() {
        if (redirecting) return;
        redirecting = true;
        try {
            if (/^#[a-z-]+$/.test(location.hash)) sessionStorage.setItem(RETURN_KEY, location.hash);
        } catch (e) { /* storage may be unavailable; the return view is only a convenience */ }
        location.assign('/login');
    }

    const DEFAULT_MESSAGES = {
        400: 'The request was not valid.',
        403: 'You do not have permission to do that.',
        404: 'Not found.',
        405: 'That action is not supported.',
        409: 'That conflicts with existing data.',
        410: 'That item no longer exists.',
        413: 'The file or request is too large.',
        415: 'The request format was not accepted.',
        429: 'Too many requests. Wait a moment and try again.',
    };

    function messageFor(status, payload) {
        if (payload && typeof payload.error === 'string' && payload.error.trim()) {
            return status >= 500 ? 'Something went wrong on the server. Please try again.' : payload.error;
        }
        if (status >= 500) return 'Something went wrong on the server. Please try again.';
        return DEFAULT_MESSAGES[status] || `The request failed (status ${status}).`;
    }

    /**
     * fetch() with the dashboard's rules: same-origin credentials, JSON bodies, and a redirect to
     * /login on 401. Resolves to the Response; rejects with ApiError (network failure, 401) or
     * the AbortError of a cancelled request.
     */
    async function request(path, opts) {
        const options = opts || {};
        const headers = { Accept: options.accept || 'application/json' };
        const init = { method: options.method || 'GET', credentials: 'same-origin', headers, signal: options.signal };
        if (options.json !== undefined) {
            headers['Content-Type'] = 'application/json';
            init.body = JSON.stringify(options.json);
        } else if (options.body !== undefined) {
            init.body = options.body; // FormData: the browser sets the multipart boundary
        }
        let res;
        try {
            res = await fetch(path, init);
        } catch (err) {
            if (err && err.name === 'AbortError') throw err;
            const netErr = new ApiError(0, 'Could not reach the server. Check that it is running and try again.');
            netErr.network = true;
            throw netErr;
        }
        if (res.status === 401 && !options.noAuthRedirect) {
            redirectToLogin();
            const authErr = new ApiError(401, 'Your session has ended. Redirecting to sign in…');
            authErr.redirecting = true;
            throw authErr;
        }
        return res;
    }

    async function readJson(res) {
        const type = res.headers.get('content-type') || '';
        if (!type.includes('json')) {
            await res.text().catch(() => '');
            return null;
        }
        return res.json().catch(() => null);
    }

    /** request() for JSON endpoints: resolves to the parsed body (null for 204), rejects with ApiError. */
    async function api(path, opts) {
        const res = await request(path, opts);
        if (res.status === 204) return null;
        const payload = await readJson(res);
        if (!res.ok) throw new ApiError(res.status, messageFor(res.status, payload), payload);
        return payload;
    }

    /** True for errors that need no message: a cancelled request or a redirect to /login. */
    function isQuiet(err) {
        return Boolean(err && (err.name === 'AbortError' || err.redirecting));
    }

    function errorMessage(err, fallback) {
        if (err instanceof ApiError) return err.message;
        return fallback || 'Something went wrong. Please try again.';
    }

    /** Path segment for an id from the API (always a number; encoded anyway). */
    function seg(value) {
        return encodeURIComponent(String(value));
    }

    // ---- DOM builder -------------------------------------------------------------------------

    function append(node, children) {
        for (const child of children.flat(Infinity)) {
            if (child === null || child === undefined || child === false) continue;
            node.appendChild(child instanceof Node ? child : document.createTextNode(String(child)));
        }
        return node;
    }

    function safeHref(value) {
        const s = String(value);
        return s.startsWith('/') || s.startsWith('#') || s.startsWith('blob:') ? s : null;
    }

    /**
     * h('div', {class: 'x', text: 'y', onclick: fn}, child, ...) builds an element.
     * Strings become text nodes; nothing is parsed as HTML.
     */
    function h(tag, props, ...children) {
        const node = document.createElement(tag);
        if (props) {
            for (const [key, value] of Object.entries(props)) {
                if (value === null || value === undefined || value === false) continue;
                if (key === 'class') node.className = value;
                else if (key === 'text') node.textContent = String(value);
                else if (key === 'dataset') Object.assign(node.dataset, value);
                else if (key === 'style') Object.assign(node.style, value);
                else if (key.startsWith('on') && typeof value === 'function') {
                    node.addEventListener(key.slice(2).toLowerCase(), value);
                } else if (key === 'href') {
                    const href = safeHref(value);
                    if (href) node.setAttribute('href', href);
                } else if (key === 'value' && 'value' in node) node.value = String(value);
                else if (key === 'checked' || key === 'selected' || key === 'disabled') node[key] = Boolean(value);
                else node.setAttribute(key, value === true ? '' : String(value));
            }
        }
        return append(node, children);
    }

    function clear(node) {
        while (node.firstChild) node.removeChild(node.firstChild);
        return node;
    }

    /** Replace a node's children. */
    function render(node, ...children) {
        clear(node);
        return append(node, children);
    }

    function $(id) {
        return document.getElementById(id);
    }

    function loadingRow(colspan, text) {
        return h('tr', null, h('td', { colspan, class: 'loading', text: text || 'Loading…' }));
    }

    function messageRow(colspan, text, isError) {
        return h('tr', null, h('td', { colspan, class: isError ? 'alert alert-error' : 'empty-state', text }));
    }

    // ---- Formatting --------------------------------------------------------------------------

    function isNum(value) {
        return typeof value === 'number' && Number.isFinite(value);
    }

    function fmt(value, digits) {
        return isNum(value) ? value.toFixed(digits === undefined ? 1 : digits) : '—';
    }

    function scorePill(score) {
        if (!isNum(score)) return h('span', { class: 'text-muted', text: '—', title: 'Not scored yet' });
        const cls = score >= 75 ? ' high' : (score < 50 ? ' low' : '');
        return h('span', { class: 'score-pill' + cls, text: score.toFixed(1) });
    }

    /** Skill tags; `limit` shows the first n and a "+k" count. */
    function skillTags(skills, options) {
        const opts = options || {};
        const list = Array.isArray(skills) ? skills : [];
        if (!list.length) return h('span', { class: 'text-muted', text: opts.empty || '—' });
        const limit = opts.limit || list.length;
        const cls = 'skill-tag' + (opts.variant ? ' ' + opts.variant : '');
        const wrap = h('span', null, list.slice(0, limit).map((s) => h('span', { class: cls, text: s })));
        if (list.length > limit) {
            wrap.appendChild(h('span', { class: 'text-muted small', text: ` +${list.length - limit}`,
                title: list.slice(limit).join(', ') }));
        }
        return wrap;
    }

    const STATUS_VARIANT = { Shortlisted: '', Interview: '', Offer: 'good', Hired: 'good', Rejected: 'bad' };

    function statusBadge(status) {
        const text = status || 'Screened';
        const variant = STATUS_VARIANT[text];
        return h('span', { class: 'badge' + (variant ? ' ' + variant : ''), text });
    }

    function formatDate(iso) {
        if (!iso) return '—';
        const d = new Date(iso);
        return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString();
    }

    function formatDateTime(iso) {
        if (!iso) return '—';
        // The API sends naive UTC timestamps; read them as UTC.
        const text = /[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : iso + 'Z';
        const d = new Date(text);
        return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString();
    }

    function truncate(text, max) {
        const s = String(text || '').replace(/\s+/g, ' ').trim();
        return s.length > max ? s.slice(0, max - 1) + '…' : s;
    }

    /** The candidate's latest screening. The contract names it `screening`; Flask sent `latest_screening`. */
    function screeningOf(candidate) {
        if (!candidate) return null;
        if (candidate.screening !== undefined) return candidate.screening || null;
        return candidate.latest_screening || null;
    }

    function candidateScore(candidate) {
        const s = screeningOf(candidate);
        return s && isNum(s.composite_score) ? s.composite_score : null;
    }

    /** Horizontal bars for a {label: count} object: one series, one hue, labelled values. */
    function barChart(data, emptyMessage) {
        const entries = Object.entries(data || {}).filter(([, v]) => isNum(v));
        if (!entries.length || entries.every(([, v]) => v === 0)) {
            return h('div', { class: 'empty-state', text: emptyMessage });
        }
        const max = Math.max(...entries.map(([, v]) => v)) || 1;
        return h('div', { role: 'list' }, entries.map(([label, value]) => {
            const fill = h('div', { class: 'bar-fill' });
            fill.style.width = `${Math.max(0, (value / max) * 100)}%`;
            return h('div', { class: 'bar-row', role: 'listitem', title: `${label}: ${value}` },
                h('div', { class: 'bar-label' }, h('span', { text: label }), h('strong', { text: String(value) })),
                h('div', { class: 'bar-track' }, fill));
        }));
    }

    /** A 0-100 value as a small labelled bar. */
    function miniBar(value) {
        const fill = h('div', { class: 'bar-fill' });
        fill.style.width = `${isNum(value) ? Math.min(100, Math.max(0, value)) : 0}%`;
        return h('div', { class: 'mini-bar' }, h('div', { class: 'bar-track' }, fill),
            h('span', { class: 'num', text: fmt(value) }));
    }

    function metricTiles(container, tiles) {
        render(container, tiles.map(([label, value]) => h('div', { class: 'metric' },
            h('div', { class: 'metric-label', text: label }),
            h('div', { class: 'metric-value', text: String(value) }))));
    }

    // ---- Jobs (used by several views) ---------------------------------------------------------

    function fetchJobs() {
        return api('/api/jobs');
    }

    /** Fill a <select> with jobs, keeping the current choice when it still exists. */
    function fillJobSelect(select, jobs, placeholder) {
        const previous = select.value;
        clear(select);
        if (placeholder !== null) select.appendChild(new Option(placeholder || 'All jobs', ''));
        for (const job of jobs) select.appendChild(new Option(job.title, String(job.id)));
        if ([...select.options].some((o) => o.value === previous)) select.value = previous;
    }

    // ---- Modals and toasts -------------------------------------------------------------------

    const openers = new Map();

    function openModal(id) {
        const modal = $(id);
        openers.set(id, document.activeElement);
        modal.classList.add('active');
        const focusable = modal.querySelector('[autofocus], input, select, textarea, button');
        if (focusable) setTimeout(() => focusable.focus(), 0);
    }

    function closeModal(id) {
        const modal = $(id);
        if (!modal.classList.contains('active')) return;
        if (modal.dataset.busy === 'true') return; // a request is in flight
        modal.classList.remove('active');
        const opener = openers.get(id);
        if (opener && typeof opener.focus === 'function' && document.contains(opener)) opener.focus();
        modal.dispatchEvent(new CustomEvent('modal-closed'));
    }

    function setModalBusy(id, busy) {
        $(id).dataset.busy = busy ? 'true' : 'false';
    }

    function toast(message, isError) {
        const box = $('toasts');
        if (!box) return;
        const item = h('div', { class: isError ? 'alert alert-error' : 'alert alert-success', role: 'status', text: message });
        box.appendChild(item);
        setTimeout(() => item.remove(), isError ? 8000 : 4000);
    }

    function showAlert(node, message, kind) {
        node.className = `alert alert-${kind || 'error'}`;
        node.textContent = message;
        node.classList.toggle('hidden', !message);
    }

    function hideAlert(node) {
        node.textContent = '';
        node.classList.add('hidden');
    }

    document.addEventListener('click', (event) => {
        const closer = event.target.closest('[data-close-modal]');
        if (closer) {
            closeModal(closer.getAttribute('data-close-modal'));
            return;
        }
        if (event.target.classList && event.target.classList.contains('modal')) closeModal(event.target.id);
    });

    document.addEventListener('keydown', (event) => {
        if (event.key !== 'Escape') return;
        const open = [...document.querySelectorAll('.modal.active')];
        if (open.length) closeModal(open[open.length - 1].id);
    });

    // ---- Resume passages (chat and agent citations) ------------------------------------------

    /** Open the passage viewer: the exact resume text, candidate name and section. */
    function showPassage(citation, label) {
        const body = $('passage-detail');
        if (!body) return;
        const c = citation || {};
        const range = isNum(c.char_start) && isNum(c.char_end)
            ? `Characters ${c.char_start}–${c.char_end} of the resume` : null;
        const profileButton = isNum(c.candidate_id) && typeof HireAI.openCandidate === 'function'
            ? h('button', { type: 'button', class: 'btn btn-secondary btn-sm', text: 'Open candidate profile',
                onclick: () => { closeModal('passage-modal'); HireAI.openCandidate(c.candidate_id); } })
            : null;
        render(body,
            h('dl', { class: 'detail-grid' },
                h('dt', { text: 'Candidate' }), h('dd', null, h('strong', { text: c.candidate_name || `Candidate ${c.candidate_id}` })),
                h('dt', { text: 'Section' }), h('dd', { text: c.section || '—' }),
                range ? [h('dt', { text: 'Location' }), h('dd', { text: range })] : null,
                isNum(c.similarity) ? [h('dt', { text: 'Similarity' }), h('dd', { text: c.similarity.toFixed(3) })] : null),
            h('div', { class: 'card-subtitle', text: 'Exact passage from the resume' }),
            h('div', { class: 'passage-text', text: c.text || '' }),
            profileButton ? h('div', { class: 'mt' }, profileButton) : null);
        $('passage-title').textContent = label ? `Passage ${label}` : 'Resume passage';
        openModal('passage-modal');
    }

    /** A clickable [n] marker that opens the passage. */
    function citationButton(number, citation) {
        const who = citation.candidate_name || `candidate ${citation.candidate_id}`;
        return h('button', {
            type: 'button', class: 'cite', text: `[${number}]`,
            title: `${who}, ${citation.section || 'resume'}`,
            'aria-label': `Show passage ${number}: ${who}, ${citation.section || 'resume'}`,
            onclick: () => showPassage(citation, `[${number}]`),
        });
    }

    /** One passage as a list item: number, candidate, section and a short snippet. */
    function passageItem(citation, number) {
        const label = number !== undefined && number !== null ? number : null;
        return h('li', { class: 'passage-item' },
            h('div', { class: 'meta' },
                label !== null ? citationButton(label, citation) : null,
                h('button', { type: 'button', class: 'btn-link', text: citation.candidate_name || `Candidate ${citation.candidate_id}`,
                    onclick: () => showPassage(citation, label !== null ? `[${label}]` : null) }),
                h('span', { class: 'badge muted', text: citation.section || 'resume' }),
                isNum(citation.similarity) ? h('span', { class: 'text-muted small', text: `similarity ${citation.similarity.toFixed(2)}` }) : null),
            h('div', { class: 'passage-snippet', text: truncate(citation.text, 260) }));
    }

    Object.assign(HireAI, {
        ApiError, api, request, readJson, messageFor, isQuiet, errorMessage, seg, redirectToLogin, RETURN_KEY,
        h, append, clear, render, $, loadingRow, messageRow,
        isNum, fmt, scorePill, skillTags, statusBadge, formatDate, formatDateTime, truncate,
        screeningOf, candidateScore, barChart, miniBar, metricTiles,
        fetchJobs, fillJobSelect,
        openModal, closeModal, setModalBusy, toast, showAlert, hideAlert,
        showPassage, citationButton, passageItem,
        PIPELINE_STATUSES: ['Screened', 'Shortlisted', 'Interview', 'Offer', 'Hired', 'Rejected'],
    });
})();
