/**
 * Theme management for FlowGic.
 * Supports light & dark theme toggling with instant switching,
 * localStorage persistence, cookie sync, and server synchronization for all users.
 */
(function() {
    'use strict';

    function getCookie(name) {
        var value = '; ' + document.cookie;
        var parts = value.split('; ' + name + '=');
        if (parts.length === 2) {
            return parts.pop().split(';').shift();
        }
        return null;
    }

    function getCsrfToken() {
        var tokenInput = document.querySelector('input[name="csrfmiddlewaretoken"]');
        if (tokenInput && tokenInput.value) {
            return tokenInput.value;
        }
        var cookieToken = getCookie('csrftoken');
        if (cookieToken) {
            return cookieToken;
        }
        var metaToken = document.querySelector('meta[name="csrf-token"]');
        if (metaToken) {
            return metaToken.getAttribute('content');
        }
        return '';
    }

    function getCurrentTheme() {
        var attr = document.documentElement.getAttribute('data-theme');
        if (attr === 'dark' || attr === 'light') {
            return attr;
        }
        var saved = localStorage.getItem('flowgic_theme');
        if (saved === 'dark' || saved === 'light') {
            return saved;
        }
        var cookieTheme = getCookie('flowgic_theme');
        if (cookieTheme === 'dark' || cookieTheme === 'light') {
            return cookieTheme;
        }
        return 'light';
    }

    function updateThemeUI(theme) {
        var isDark = theme === 'dark';

        // Update all toggle buttons
        var buttons = document.querySelectorAll('.theme-toggle-btn, [data-theme-toggle]');
        buttons.forEach(function(btn) {
            btn.setAttribute('data-current-theme', theme);
            btn.setAttribute('aria-pressed', isDark ? 'true' : 'false');
            btn.setAttribute('title', isDark ? 'Переключить на светлую тему' : 'Переключить на тёмную тему');

            var label = btn.querySelector('.theme-toggle-label');
            if (label) {
                label.textContent = isDark ? 'Светлая тема' : 'Тёмная тема';
            }

            var iconSun = btn.querySelector('.theme-icon-sun');
            var iconMoon = btn.querySelector('.theme-icon-moon');
            if (iconSun && iconMoon) {
                iconSun.style.display = isDark ? 'inline-block' : 'none';
                iconMoon.style.display = isDark ? 'none' : 'inline-block';
            }
        });

        // Update dropdown menu items
        var menuBtn = document.getElementById('menu-theme-toggle');
        if (menuBtn) {
            var menuText = document.getElementById('menu-theme-text');
            var menuIcon = document.getElementById('menu-theme-icon');
            if (menuText) {
                menuText.textContent = isDark ? 'Светлая тема' : 'Тёмная тема';
            }
            if (menuIcon) {
                menuIcon.textContent = isDark ? '☀️' : '🌙';
            }
        }
    }

    function applyTheme(theme, syncServer) {
        if (theme !== 'dark' && theme !== 'light') {
            theme = 'light';
        }

        // Apply attribute to root and body
        document.documentElement.setAttribute('data-theme', theme);
        document.documentElement.setAttribute('data-bs-theme', theme);
        if (document.body) {
            document.body.setAttribute('data-theme', theme);
            document.body.setAttribute('data-bs-theme', theme);
        }

        // Persist to localStorage
        try {
            localStorage.setItem('flowgic_theme', theme);
        } catch (e) {
            console.warn('localStorage not accessible', e);
        }

        // Persist to cookie (365 days)
        document.cookie = 'flowgic_theme=' + theme + '; path=/; max-age=' + (365 * 24 * 60 * 60) + '; SameSite=Lax';

        // Update UI
        updateThemeUI(theme);

        // Notify fullcalendar if present
        if (window.dispatchEvent) {
            window.dispatchEvent(new CustomEvent('flowgic-theme-changed', { detail: { theme: theme } }));
        }

        // Sync with backend if requested
        if (syncServer) {
            var csrf = getCsrfToken();
            fetch('/toggle-theme/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrf,
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({ theme: theme })
            }).catch(function(err) {
                // Ignore network error; cookie and localStorage will handle offline/guest states
                console.debug('Theme sync failed:', err);
            });
        }
    }

    function toggleTheme() {
        var current = getCurrentTheme();
        var next = current === 'dark' ? 'light' : 'dark';
        applyTheme(next, true);
    }

    // Expose API globally
    window.FlowgicTheme = {
        getTheme: getCurrentTheme,
        setTheme: function(theme) { applyTheme(theme, true); },
        toggleTheme: toggleTheme
    };

    // Initialize on page load
    function init() {
        var initialTheme = getCurrentTheme();
        applyTheme(initialTheme, false);

        document.addEventListener('click', function(e) {
            var toggleTarget = e.target.closest('.theme-toggle-btn, #theme-toggle, #menu-theme-toggle, [data-theme-toggle]');
            if (toggleTarget) {
                e.preventDefault();
                toggleTheme();
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
