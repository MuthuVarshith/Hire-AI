/* Router, signed-in user and logout. Loaded last: every view has registered itself in
   HireAI.views by now as {title, render}. */
(function () {
    'use strict';

    const { api, $, isQuiet, toast, errorMessage } = HireAI;
    let current = null;

    function routeFromHash() {
        const name = location.hash.replace(/^#/, '');
        return Object.prototype.hasOwnProperty.call(HireAI.views, name) ? name : 'dashboard';
    }

    function show(name) {
        const view = HireAI.views[name];
        current = name;
        document.querySelectorAll('.view').forEach((v) => v.classList.toggle('active', v.id === `view-${name}`));
        document.querySelectorAll('.nav-link').forEach((link) => {
            const active = link.dataset.view === name;
            link.classList.toggle('active', active);
            if (active) link.setAttribute('aria-current', 'page');
            else link.removeAttribute('aria-current');
        });
        $('page-title').textContent = view.title;
        document.title = `${view.title} · HireAI`;
        $('main').scrollTop = 0;
        Promise.resolve()
            .then(() => view.render())
            .catch((err) => { if (!isQuiet(err)) console.error(`Rendering ${name} failed:`, err); });
    }

    /** Navigate to a view (re-renders it when it is already showing). */
    HireAI.go = function (name) {
        if (location.hash === `#${name}`) show(name);
        else location.hash = name;
    };

    HireAI.currentView = () => current;

    /** After a change, re-render the current view if it shows affected data. */
    HireAI.refreshViews = function (names) {
        if (current && names.includes(current)) show(current);
    };

    async function loadUser() {
        const user = await api('/api/auth/me');
        HireAI.user = user;
        $('user-name').textContent = user && user.name ? user.name : 'Signed in';
        const role = $('user-role');
        role.textContent = user && user.role ? user.role : '';
        role.classList.toggle('hidden', !(user && user.role));
    }

    async function logout() {
        const button = $('logout-btn');
        button.disabled = true;
        button.textContent = 'Logging out…';
        try {
            await api('/api/auth/logout', { method: 'POST', noAuthRedirect: true });
        } catch (err) {
            // 401: the session had already ended, which is what logging out wants.
            if (err.status !== 401) {
                toast(errorMessage(err, 'Could not log out. Please try again.'), true);
                button.disabled = false;
                button.textContent = 'Log out';
                return;
            }
        }
        location.replace('/login');
    }

    document.addEventListener('DOMContentLoaded', async () => {
        $('logout-btn').addEventListener('click', logout);
        $('hdr-new-job').addEventListener('click', () => HireAI.openJobForm());
        $('hdr-upload').addEventListener('click', () => HireAI.openUpload());
        window.addEventListener('hashchange', () => show(routeFromHash()));

        try {
            await loadUser();
        } catch (err) {
            if (isQuiet(err)) return; // redirecting to /login
            $('user-name').textContent = 'Unknown user';
            toast(errorMessage(err, 'Could not load your account.'), true);
        }
        show(routeFromHash());
    });
})();
