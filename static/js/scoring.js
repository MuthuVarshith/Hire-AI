/* Scoring templates: CRUD on /api/scoring-templates. Weights are edited as percentages. */
(function () {
    'use strict';

    const { api, h, $, seg, render, loadingRow, messageRow, openModal, closeModal, setModalBusy, toast,
        showAlert, hideAlert, isQuiet, errorMessage } = HireAI;

    const FIELDS = [['tpl-w-semantic', 'semantic_weight'], ['tpl-w-skill', 'skill_weight'],
        ['tpl-w-experience', 'experience_weight'], ['tpl-w-education', 'education_weight']];
    let editing = null;

    const pct = (w) => (typeof w === 'number' ? `${Math.round(w * 1000) / 10}%` : '—');

    async function load() {
        const tbody = $('tpl-list');
        render(tbody, loadingRow(7));
        try {
            const list = await api('/api/scoring-templates');
            render(tbody, list.length ? list.map((t) => h('tr', null,
                h('td', null, h('strong', { text: t.name }), t.is_default ? [' ', h('span', { class: 'badge', text: 'default' })] : null),
                h('td', { class: 'text-muted', text: t.description || '—' }),
                FIELDS.map(([, key]) => h('td', { text: pct(t[key]) })),
                h('td', { class: 'nowrap' },
                    h('button', { type: 'button', class: 'btn btn-sm btn-secondary', text: 'Edit', onclick: () => openForm(t) }), ' ',
                    h('button', { type: 'button', class: 'btn btn-sm btn-danger', text: 'Delete', disabled: Boolean(t.is_default),
                        title: t.is_default ? 'The default template cannot be deleted' : null,
                        onclick: (e) => remove(t, e.currentTarget) })))) : messageRow(7, 'No templates yet.'));
        } catch (err) {
            if (!isQuiet(err)) render(tbody, messageRow(7, errorMessage(err, 'Could not load templates.'), true));
        }
    }

    function sum() {
        return FIELDS.reduce((acc, [id]) => acc + (parseFloat($(id).value) || 0), 0);
    }

    function updateSum() {
        const total = sum();
        const ok = Math.abs(total - 100) < 0.001;
        $('tpl-sum').textContent = `Total: ${Math.round(total * 100) / 100}%${ok ? '' : ' (must be 100%)'}`;
        return ok;
    }

    function setBusy(busy) {
        $('tpl-submit-btn').disabled = busy;
        $('tpl-cancel-btn').disabled = busy;
        $('tpl-submit-btn').textContent = busy ? 'Saving…' : 'Save';
        setModalBusy('template-modal', busy);
    }

    function openForm(t) {
        editing = t || null;
        $('template-modal-title').textContent = editing ? 'Edit Scoring Template' : 'New Scoring Template';
        $('tpl-name').value = editing ? editing.name : '';
        $('tpl-desc').value = editing ? editing.description || '' : '';
        const defaults = { semantic_weight: 0.4, skill_weight: 0.3, experience_weight: 0.15, education_weight: 0.15 };
        FIELDS.forEach(([id, key]) => { $(id).value = String(Math.round(((editing || defaults)[key] || 0) * 10000) / 100); });
        hideAlert($('template-form-error'));
        setBusy(false);
        updateSum();
        openModal('template-modal');
    }

    async function submit(event) {
        event.preventDefault();
        const errorBox = $('template-form-error');
        hideAlert(errorBox);
        const name = $('tpl-name').value.trim();
        if (!name) { showAlert(errorBox, 'Enter a name.'); return; }
        if (!updateSum()) { showAlert(errorBox, 'The four weights must add up to 100%.'); return; }
        const payload = { name, description: $('tpl-desc').value.trim() };
        FIELDS.forEach(([id, key]) => { payload[key] = Math.round((parseFloat($(id).value) || 0) * 10000) / 1000000; });
        setBusy(true);
        try {
            if (editing) await api(`/api/scoring-templates/${seg(editing.id)}`, { method: 'PUT', json: payload });
            else await api('/api/scoring-templates', { method: 'POST', json: payload });
            setBusy(false);
            closeModal('template-modal');
            toast(`Template "${name}" saved.`);
            load();
        } catch (err) {
            setBusy(false);
            if (!isQuiet(err)) showAlert(errorBox, `Could not save the template. ${errorMessage(err)}`);
        }
    }

    async function remove(t, button) {
        if (!window.confirm(`Delete the scoring template "${t.name}"?`)) return;
        button.disabled = true;
        try {
            await api(`/api/scoring-templates/${seg(t.id)}`, { method: 'DELETE' });
            toast(`Template "${t.name}" deleted.`);
            load();
        } catch (err) {
            button.disabled = false;
            if (!isQuiet(err)) toast(`Could not delete the template. ${errorMessage(err)}`, true);
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        $('tpl-new-btn').addEventListener('click', () => openForm(null));
        $('template-form').addEventListener('submit', submit);
        FIELDS.forEach(([id]) => $(id).addEventListener('input', updateSum));
    });
    HireAI.views.scoring = { title: 'Scoring templates', render: load };
})();
