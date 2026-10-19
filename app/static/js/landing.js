/* ═══════════════════════════════════════════════════════════════════════
   WowHub · Landing Page JS (V2.01)
   Mínimo, accesible, sin dependencias externas.
   Funciones: theme toggle, mobile menu, modal demo, pricing toggle.
   ═══════════════════════════════════════════════════════════════════════ */

(function () {
  'use strict';

  var THEME_KEY = 'wowhub.theme';
  var PERIOD_KEY = 'wowhub.pricing.period';

  /* ── Theme toggle ─────────────────────────────────────────────── */
  function applyTheme(theme) {
    var t = theme === 'dark' ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', t);
    try { localStorage.setItem(THEME_KEY, t); } catch (_) {}
    var btn = document.getElementById('theme-toggle');
    if (btn) btn.setAttribute('aria-pressed', t === 'dark' ? 'true' : 'false');
  }

  function initTheme() {
    var stored = null;
    try { stored = localStorage.getItem(THEME_KEY); } catch (_) {}
    var theme = stored ||
      (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches
        ? 'dark' : 'light');
    applyTheme(theme);

    var btn = document.getElementById('theme-toggle');
    if (btn) {
      btn.addEventListener('click', function () {
        var current = document.documentElement.getAttribute('data-theme') || 'light';
        applyTheme(current === 'dark' ? 'light' : 'dark');
      });
    }
  }

  /* ── Mobile menu ──────────────────────────────────────────────── */
  function initMobileMenu() {
    var btn = document.querySelector('.mobile-menu-btn');
    var nav = document.querySelector('.topbar__nav');
    if (!btn || !nav) return;
    btn.addEventListener('click', function () {
      var open = nav.getAttribute('data-open') === 'true';
      nav.setAttribute('data-open', open ? 'false' : 'true');
      btn.setAttribute('aria-expanded', open ? 'false' : 'true');
    });
  }

  /* ── Demo modal (accesible: focus trap, ESC, aria-hidden) ────── */
  var activeModal = null;
  function trapFocus(modal) {
    var focusable = modal.querySelectorAll(
      'a, button, input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    if (!focusable.length) return;
    var first = focusable[0];
    var last = focusable[focusable.length - 1];
    first.focus();

    function keyHandler(e) {
      if (e.key === 'Escape') { closeModal(); return; }
      if (e.key !== 'Tab') return;
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault(); last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault(); first.focus();
      }
    }
    modal.addEventListener('keydown', keyHandler);
    modal._keyHandler = keyHandler;
  }

  function openModal(id) {
    var modal = document.getElementById(id);
    if (!modal) return;
    modal.setAttribute('aria-hidden', 'false');
    activeModal = modal;
    trapFocus(modal);
    document.body.style.overflow = 'hidden';
  }

  function closeModal() {
    if (!activeModal) return;
    activeModal.setAttribute('aria-hidden', 'true');
    if (activeModal._keyHandler) {
      activeModal.removeEventListener('keydown', activeModal._keyHandler);
    }
    document.body.style.overflow = '';
    activeModal = null;
  }

  function initDemoModals() {
    document.querySelectorAll('[data-demo-target]').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.preventDefault();
        var target = btn.getAttribute('data-demo-target');
        openModal(target);
      });
    });
    document.querySelectorAll('.demo-modal__close').forEach(function (btn) {
      btn.addEventListener('click', closeModal);
    });
    document.querySelectorAll('.demo-modal').forEach(function (modal) {
      modal.addEventListener('click', function (e) {
        if (e.target === modal) closeModal();
      });
    });
  }

  /* ── Pricing toggle (monthly / yearly) ──────────────────────── */
  function applyPricingPeriod(period) {
    var p = period === 'yearly' ? 'yearly' : 'monthly';
    try { localStorage.setItem(PERIOD_KEY, p); } catch (_) {}
    document.querySelectorAll('[data-price]').forEach(function (el) {
      var monthly = el.getAttribute('data-price');
      var yearly = el.getAttribute('data-price-yearly');
      el.textContent = p === 'yearly' && yearly ? yearly : monthly;
    });
    document.querySelectorAll('[data-price-period]').forEach(function (el) {
      el.textContent = p === 'yearly' ? '/ mes (facturado anual)' : '/ mes';
    });
    document.querySelectorAll('.pricing-toggle__btn').forEach(function (btn) {
      btn.setAttribute('aria-pressed', btn.getAttribute('data-period') === p ? 'true' : 'false');
    });
  }

  function initPricing() {
    var stored = null;
    try { stored = localStorage.getItem(PERIOD_KEY); } catch (_) {}
    applyPricingPeriod(stored || 'monthly');
    document.querySelectorAll('.pricing-toggle__btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        applyPricingPeriod(btn.getAttribute('data-period'));
      });
    });
  }

  /* ── Smooth scroll for anchor links ──────────────────────────── */
  function initSmoothScroll() {
    document.querySelectorAll('a[href^="#"]').forEach(function (a) {
      a.addEventListener('click', function (e) {
        var id = a.getAttribute('href');
        if (id.length < 2) return;
        var el = document.querySelector(id);
        if (el) {
          e.preventDefault();
          el.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      });
    });
  }

  /* ── Init ─────────────────────────────────────────────────────── */
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      initTheme();
      initMobileMenu();
      initDemoModals();
      initPricing();
      initSmoothScroll();
    });
  } else {
    initTheme();
    initMobileMenu();
    initDemoModals();
    initPricing();
    initSmoothScroll();
  }
})();