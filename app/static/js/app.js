(() => {
  document.documentElement.classList.add('js-enabled');

  const toggle = document.querySelector('.menu-toggle');
  const nav = document.querySelector('#site-nav');
  if (toggle && nav) {
    const closeMenu = () => {
      nav.classList.remove('is-open');
      toggle.setAttribute('aria-expanded', 'false');
      toggle.setAttribute('aria-label', 'Abrir navegación');
    };
    toggle.addEventListener('click', () => {
      const open = toggle.getAttribute('aria-expanded') !== 'true';
      toggle.setAttribute('aria-expanded', String(open));
      toggle.setAttribute('aria-label', open ? 'Cerrar navegación' : 'Abrir navegación');
      nav.classList.toggle('is-open', open);
    });
    nav.querySelectorAll('a').forEach((link) => link.addEventListener('click', closeMenu));
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') closeMenu();
    });
    window.addEventListener('resize', () => {
      if (window.innerWidth > 1200) closeMenu();
    });
  }

  document.querySelectorAll('.flash-close').forEach((button) => {
    button.addEventListener('click', () => button.closest('.flash')?.remove());
  });

  document.querySelectorAll('img[data-fallback]').forEach((image) => {
    image.addEventListener('error', () => {
      const fallback = image.dataset.fallback;
      if (fallback && image.src !== new URL(fallback, window.location.href).href) {
        image.src = fallback;
      }
    });
  });

  const revealItems = document.querySelectorAll('[data-reveal]');
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver((entries, currentObserver) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          currentObserver.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12, rootMargin: '0px 0px -28px 0px' });
    revealItems.forEach((item) => observer.observe(item));
  } else {
    revealItems.forEach((item) => item.classList.add('is-visible'));
  }

  const format = (value, decimals) => new Intl.NumberFormat('es-PE', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals
  }).format(value);
  const counters = document.querySelectorAll('[data-count]');
  const animateCounter = (element) => {
    const target = Number(element.dataset.count || 0);
    const decimals = Number(element.dataset.decimals || 0);
    if (!Number.isFinite(target)) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      element.textContent = format(target, decimals);
      return;
    }
    const start = performance.now();
    const duration = 850;
    element.textContent = format(0, decimals);
    const tick = (now) => {
      const progress = Math.min(1, (now - start) / duration);
      const eased = 1 - ((1 - progress) ** 3);
      element.textContent = format(target * eased, decimals);
      if (progress < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  };
  if ('IntersectionObserver' in window) {
    const counterObserver = new IntersectionObserver((entries, currentObserver) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          animateCounter(entry.target);
          currentObserver.unobserve(entry.target);
        }
      });
    }, { threshold: 0.35 });
    counters.forEach((counter) => counterObserver.observe(counter));
  } else {
    counters.forEach(animateCounter);
  }
})();
