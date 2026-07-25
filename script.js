// Interactive behavior for the How-To Guides accordion and the Directory
// filter is added in later steps of this build.

function initGuides() {
  const guides = document.querySelectorAll('[data-guide]');
  guides.forEach((guide) => {
    const toggle = guide.querySelector('.guide-toggle');
    toggle.addEventListener('click', () => {
      guide.classList.toggle('is-open');
      const label = toggle.querySelector('.guide-toggle-label');
      label.textContent = guide.classList.contains('is-open') ? 'Hide steps' : 'Show steps';
    });
  });
}

document.addEventListener('DOMContentLoaded', initGuides);

function initDirectoryFilter() {
  const buttons = document.querySelectorAll('.filter-btn');
  const cards = document.querySelectorAll('[data-org]');

  buttons.forEach((button) => {
    button.addEventListener('click', () => {
      buttons.forEach((b) => b.classList.remove('is-active'));
      button.classList.add('is-active');

      const filter = button.dataset.filter;
      cards.forEach((card) => {
        const show = filter === 'All' || card.dataset.category === filter;
        card.classList.toggle('is-hidden', !show);
      });
    });
  });
}

document.addEventListener('DOMContentLoaded', initDirectoryFilter);

function initThemeToggle() {
  const toggle = document.getElementById('theme-toggle');
  const root = document.documentElement;

  function syncLabel() {
    const isDark = root.getAttribute('data-theme') === 'dark';
    toggle.textContent = isDark ? 'Light mode' : 'Dark mode';
    toggle.setAttribute('aria-pressed', String(isDark));
  }

  syncLabel();

  toggle.addEventListener('click', () => {
    const isDark = root.getAttribute('data-theme') === 'dark';
    if (isDark) {
      root.removeAttribute('data-theme');
      localStorage.setItem('theme', 'light');
    } else {
      root.setAttribute('data-theme', 'dark');
      localStorage.setItem('theme', 'dark');
    }
    syncLabel();
  });
}

document.addEventListener('DOMContentLoaded', initThemeToggle);
