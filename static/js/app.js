// Finance Tracker - Main JavaScript

// Toggle mobile navigation
function toggleNav() {
    document.getElementById('navLinks').classList.toggle('active');
}

// Dismiss notification banner
function dismissNotification() {
    const banner = document.getElementById('notificationBanner');
    if (banner) {
        banner.style.animation = 'slideUp 0.3s ease forwards';
        setTimeout(() => banner.remove(), 300);
    }
    // Also clear server-side
    fetch('/dismiss-notification/', { method: 'POST', headers: {'X-CSRFToken': getCookie('csrftoken')} });
}

// Auto-dismiss notifications after 8 seconds
document.addEventListener('DOMContentLoaded', function() {
    const banners = document.querySelectorAll('.notification-banner');
    banners.forEach((banner, i) => {
        setTimeout(() => {
            if (banner.parentElement) {
                banner.style.animation = 'slideUp 0.3s ease forwards';
                setTimeout(() => banner.remove(), 300);
            }
        }, 8000 + (i * 500));
    });
});

// Close modal on overlay click
document.querySelectorAll('.modal-overlay').forEach(overlay => {
    overlay.addEventListener('click', function(e) {
        if (e.target === this) this.classList.remove('active');
    });
});

// Close modal on Escape key
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        document.querySelectorAll('.modal-overlay.active').forEach(m => m.classList.remove('active'));
    }
});

// Get CSRF token from cookies
function getCookie(name) {
    let value = null;
    document.cookie.split(';').forEach(c => {
        c = c.trim();
        if (c.startsWith(name + '=')) value = c.substring(name.length + 1);
    });
    return value;
}

// CSS animation for slide up
const style = document.createElement('style');
style.textContent = '@keyframes slideUp { from { transform: translateY(0); opacity: 1; } to { transform: translateY(-20px); opacity: 0; } }';
document.head.appendChild(style);
