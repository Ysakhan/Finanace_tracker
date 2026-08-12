// Finance Tracker / FinRoll - Main JavaScript

// Toggle mobile navigation
function toggleNav() {
    const navLinks = document.getElementById('navLinks');
    if (navLinks) {
        navLinks.classList.toggle('active');
    }
}

// Dismiss notification banner
function dismissNotification() {
    const banner = document.getElementById('notificationBanner');
    if (banner) {
        banner.style.animation = 'slideUp 0.3s ease forwards';
        setTimeout(() => banner.remove(), 300);
    }
    // Also clear server-side
    const token = getCookie('csrftoken');
    if (token) {
        fetch('/dismiss-notification/', { method: 'POST', headers: {'X-CSRFToken': token} }).catch(() => {});
    }
}

// Theme Management Logic (Default: Light Theme)
function setTheme(theme) {
    const targetTheme = (theme === 'dark') ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', targetTheme);
    localStorage.setItem('finroll_theme', targetTheme);
    
    // Sync all slide switch checkboxes
    document.querySelectorAll('.themeToggleCheckbox').forEach(cb => {
        cb.checked = (targetTheme === 'dark');
    });

    // Toggle icons inside slide knob
    document.querySelectorAll('.icon-sun').forEach(el => el.style.display = (targetTheme === 'dark') ? 'none' : 'block');
    document.querySelectorAll('.icon-moon').forEach(el => el.style.display = (targetTheme === 'dark') ? 'block' : 'none');

    const themeSelect = document.getElementById('themeSelect');
    if (themeSelect) themeSelect.value = targetTheme;
}

function toggleThemeFromCheckbox(isDark) {
    setTheme(isDark ? 'dark' : 'light');
}

function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
    setTheme(currentTheme === 'dark' ? 'light' : 'dark');
}

// Auto-dismiss notifications & sync light/dark theme
document.addEventListener('DOMContentLoaded', function() {
    const savedTheme = localStorage.getItem('finroll_theme') || 'light';
    setTheme(savedTheme);

    const banners = document.querySelectorAll('.notification-banner');
    banners.forEach((banner, i) => {
        setTimeout(() => {
            if (banner && banner.parentElement) {
                banner.style.animation = 'slideUp 0.3s ease forwards';
                setTimeout(() => banner.remove(), 300);
            }
        }, 8000 + (i * 500));
    });
});

// Close modal on overlay click (handles both class-based & inline display-based modals)
document.addEventListener('click', function(e) {
    if (e.target && e.target.classList && e.target.classList.contains('modal-overlay')) {
        e.target.classList.remove('active');
        if (e.target.style.display === 'flex' || e.target.style.display === 'block') {
            e.target.style.display = 'none';
        }
    }
});

// Close modal on Escape key
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        document.querySelectorAll('.modal-overlay').forEach(m => {
            m.classList.remove('active');
            if (m.style.display === 'flex' || m.style.display === 'block') {
                m.style.display = 'none';
            }
        });
    }
});

// Get CSRF token from cookies
function getCookie(name) {
    let value = null;
    if (document.cookie && document.cookie !== '') {
        document.cookie.split(';').forEach(c => {
            c = c.trim();
            if (c.startsWith(name + '=')) value = c.substring(name.length + 1);
        });
    }
    return value;
}

// CSS animation for slide up
const style = document.createElement('style');
style.textContent = '@keyframes slideUp { from { transform: translateY(0); opacity: 1; } to { transform: translateY(-20px); opacity: 0; } }';
document.head.appendChild(style);

