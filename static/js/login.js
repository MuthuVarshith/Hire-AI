/* Login page: POST /api/auth/login, then go to the dashboard. Standalone (no core.js), because
   the dashboard's 401 handling redirects here and must not loop. */
(function () {
    'use strict';

    const RETURN_KEY = 'hireai.returnTo';

    function returnTarget() {
        // Only a known-safe hash on our own dashboard: never an absolute or caller-supplied URL.
        let hash = '';
        try {
            hash = sessionStorage.getItem(RETURN_KEY) || '';
            sessionStorage.removeItem(RETURN_KEY);
        } catch (e) { /* storage unavailable */ }
        return /^#[a-z-]+$/.test(hash) ? '/' + hash : '/';
    }

    function showError(message) {
        const box = document.getElementById('login-error');
        box.textContent = message;
        box.classList.toggle('hidden', !message);
    }

    function setBusy(busy) {
        const button = document.getElementById('login-submit');
        button.disabled = busy;
        button.textContent = busy ? 'Signing in…' : 'Sign in';
        document.getElementById('login-username').disabled = busy;
        document.getElementById('login-password').disabled = busy;
    }

    async function signIn(event) {
        event.preventDefault();
        showError('');
        const userEl = document.getElementById('login-username');
        const passEl = document.getElementById('login-password');
        const username = userEl.value.trim();
        const password = passEl.value;
        userEl.classList.toggle('invalid', !username);
        passEl.classList.toggle('invalid', !password);
        if (!username || !password) {
            showError('Enter your username and password.');
            (username ? passEl : userEl).focus();
            return;
        }

        setBusy(true);
        let res;
        try {
            res = await fetch('/api/auth/login', {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
                body: JSON.stringify({ username, password }),
            });
        } catch (err) {
            setBusy(false);
            showError('Could not reach the server. Check that it is running and try again.');
            return;
        }

        if (res.ok) {
            passEl.value = '';
            location.replace(returnTarget());
            return;
        }

        const payload = await res.json().catch(() => null);
        setBusy(false);
        passEl.value = '';
        if (res.status === 401) {
            showError((payload && payload.error) || 'Invalid username or password');
        } else if (res.status === 429) {
            showError((payload && payload.error) || 'Too many attempts. Wait a moment and try again.');
        } else if (res.status >= 500) {
            showError('Something went wrong on the server. Please try again.');
        } else {
            showError((payload && payload.error) || `Sign-in failed (status ${res.status}).`);
        }
        passEl.focus();
    }

    /** Already signed in (valid cookie)? Skip the form. */
    async function checkSession() {
        try {
            const res = await fetch('/api/auth/me', { credentials: 'same-origin', headers: { Accept: 'application/json' } });
            if (res.ok) location.replace(returnTarget());
        } catch (e) { /* stay on the form */ }
    }

    document.addEventListener('DOMContentLoaded', () => {
        document.getElementById('login-form').addEventListener('submit', signIn);
        checkSession();
    });
})();
