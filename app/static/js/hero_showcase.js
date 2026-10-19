/* ═══════════════════════════════════════════════════════════════════════
   WowHub · Hero Showcase Controller (V2.01)
   Carrusel interactivo de 8 funcionalidades con autoplay + pause on hover.
   Implementa ARIA tabs (role="tablist", aria-selected, role="tabpanel").
   Sin dependencias externas. ~5KB.
   ═══════════════════════════════════════════════════════════════════════ */

(function () {
  'use strict';

  var AUTOPLAY_MS = 3000;  // V2.003 — bajado de 4500ms a 3000ms
                            //          por feedback del usuario (mas
                            //          dinamico, mejor engagement).
  var TRANSITION_MS = 350;

  /**
   * Definición de las 8 funcionalidades. Cada una renderiza contenido
   * distinto en el mockup del teléfono.
   *
   * Por orden del brief UX/UI senior:
   *  1. Página Web
   *  2. Catálogo Digital
   *  3. Códigos QR
   *  4. Pedidos
   *  5. Pagos
   *  6. Reservas
   *  7. Promociones
   *  8. Estadísticas
   */
  var TABS = [
    {
      id: 'page',
      label: 'Página',
      icon: '⚡',
      title: 'Tu negocio presente',
      subtitle: 'Landing con tu marca',
      visual: 'page'
    },
    {
      id: 'catalog',
      label: 'Catálogo',
      icon: '📦',
      title: 'Catálogo digital',
      subtitle: 'Productos en tiempo real',
      visual: 'catalog'
    },
    {
      id: 'qr',
      label: 'QR',
      icon: '📱',
      title: 'QR para mesas',
      subtitle: 'Genera y mide escaneos',
      visual: 'qr'
    },
    {
      id: 'orders',
      label: 'Pedidos',
      icon: '🧾',
      title: 'Panel en vivo',
      subtitle: 'Recepción al instante',
      visual: 'orders'
    },
    {
      id: 'payments',
      label: 'Pagos',
      icon: '💳',
      title: 'Cobra seguro',
      subtitle: 'MercadoPago integrado',
      visual: 'payments'
    },
    {
      id: 'bookings',
      label: 'Reservas',
      icon: '📅',
      title: 'Agenda online',
      subtitle: 'Tus clientes reservan',
      visual: 'bookings'
    },
    {
      id: 'promos',
      label: 'Promociones',
      icon: '🎉',
      title: 'Cupones y ofertas',
      subtitle: 'Atrae más clientes',
      visual: 'promos'
    },
    {
      id: 'stats',
      label: 'Estadísticas',
      icon: '📊',
      title: 'Métricas claras',
      subtitle: 'Ventas y visitas',
      visual: 'stats'
    }
  ];

  /* ── Visual factory (devuelve el HTML del mockup por tab) ────
     V2.002 — Las 8 variantes ahora muestran IMÁGENES REALISTAS
     generadas con connector__matrix__generate_image, servidas
     desde /static/img/hero/ (catalog, qr, orders, etc.). Las
     versiones previas con SVG inline / emojis / texto se
     reemplazaron para que el Hero contenga "imágenes que
     representen el contenido real de las funcionalidades"
     (feedback del usuario). */

  // Helper: <img> con lazy loading + alt contextual.
  function imgMock(name, alt) {
    return '<img class="mock-image" src="/static/img/hero/' + name +
           '" alt="' + alt + '" loading="lazy" decoding="async" />';
  }

  function visualHTML(tab) {
    switch (tab.visual) {
      case 'page':
        return '<div class="mock-image-wrap">' + imgMock('page.png', 'Página de presentación del negocio') + '</div>';
      case 'catalog':
        return '<div class="mock-image-wrap">' + imgMock('catalog.png', 'Catálogo digital con productos reales') + '</div>';
      case 'qr':
        return '<div class="mock-image-wrap">' + imgMock('qr.png', 'Código QR para mesa') + '</div>';
      case 'orders':
        return '<div class="mock-image-wrap">' + imgMock('orders.png', 'Panel de pedidos en vivo') + '</div>';
      case 'payments':
        return '<div class="mock-image-wrap">' + imgMock('payments.jpg', 'Confirmación de pago') + '</div>';
      case 'bookings':
        return '<div class="mock-image-wrap">' + imgMock('bookings.png', 'Agenda de reservas') + '</div>';
      case 'promos':
        return '<div class="mock-image-wrap">' + imgMock('promos.png', 'Promociones y cupones') + '</div>';
      case 'stats':
      default:
        return '<div class="mock-image-wrap">' + imgMock('stats.png', 'Dashboard de estadísticas') + '</div>';
    }
  }

  /* ── Init ─────────────────────────────────────────────────────── */
  function init() {
    var tabsRoot = document.querySelector('[data-hero-tabs]');
    var panel = document.querySelector('[data-hero-panel]');
    var mockup = document.querySelector('[data-hero-mockup]');
    if (!tabsRoot || !panel || !mockup) return;

    var tabs = Array.prototype.slice.call(tabsRoot.querySelectorAll('[role="tab"]'));
    if (!tabs.length) return;

    var active = 0;
    var timer = null;
    var isHovered = false;
    var isFocus = false;

    function activate(index, opts) {
      opts = opts || {};
      if (index < 0) index = tabs.length - 1;
      if (index >= tabs.length) index = 0;
      active = index;

      tabs.forEach(function (tab, i) {
        var isActive = i === index;
        tab.setAttribute('aria-selected', isActive ? 'true' : 'false');
        tab.setAttribute('tabindex', isActive ? '0' : '-1');
        tab.classList.toggle('is-active', isActive);
      });

      var tab = TABS[index];
      if (!tab) return;

      // Update panel accessible label
      panel.setAttribute('aria-labelledby', 'hero-tab-' + tab.id);

      // Render mockup content with fade transition.
      // V2.01 FIX: inyectamos DENTRO de .phone__screen (que tiene bg #fff)
      // en vez de reemplazar innerHTML del .phone (que tiene bg #1a1d28).
      // Antes el contenido dinámico quedaba sobre el frame oscuro del
      // teléfono → mockups invisibles.
      var screen = mockup.querySelector('.phone__screen');
      if (!screen) {
        // Fallback defensivo: si por algún motivo no existe phone__screen,
        // lo creamos para no romper la experiencia.
        screen = document.createElement('div');
        screen.className = 'phone__screen';
        mockup.appendChild(screen);
      }
      mockup.classList.add('is-switching');
      window.setTimeout(function () {
        screen.innerHTML = visualHTML(tab);
        mockup.setAttribute('data-visual', tab.visual);
        mockup.classList.remove('is-switching');
      }, TRANSITION_MS / 2);

      // Update tooltip near phone
      var tooltip = document.querySelector('[data-hero-tooltip]');
      if (tooltip) {
        tooltip.querySelector('.hero-tooltip__title').textContent = tab.title;
        tooltip.querySelector('.hero-tooltip__subtitle').textContent = tab.subtitle;
      }
    }

    function next() {
      if (!isHovered && !isFocus) activate(active + 1);
    }

    function startAutoplay() {
      stopAutoplay();
      timer = window.setInterval(next, AUTOPLAY_MS);
    }

    function stopAutoplay() {
      if (timer) { window.clearInterval(timer); timer = null; }
    }

    function pauseOnHover() { isHovered = true; stopAutoplay(); }
    function resumeOnLeave() { isHovered = false; if (!isFocus) startAutoplay(); }

    // Tab events
    tabs.forEach(function (tab, i) {
      tab.addEventListener('click', function () { activate(i); stopAutoplay(); startAutoplay(); });
      tab.addEventListener('keydown', function (e) {
        var key = e.key;
        if (key === 'ArrowRight' || key === 'ArrowDown') { e.preventDefault(); activate(active + 1); tabs[(active + 1) % tabs.length].focus(); }
        if (key === 'ArrowLeft' || key === 'ArrowUp') { e.preventDefault(); activate(active - 1); tabs[(active - 1 + tabs.length) % tabs.length].focus(); }
        if (key === 'Home') { e.preventDefault(); activate(0); tabs[0].focus(); }
        if (key === 'End') { e.preventDefault(); activate(tabs.length - 1); tabs[tabs.length - 1].focus(); }
      });
      tab.addEventListener('focus', function () { isFocus = true; stopAutoplay(); });
      tab.addEventListener('blur', function () { isFocus = false; if (!isHovered) startAutoplay(); });
    });

    // Hover sobre el showcase pausa el autoplay
    var showcase = mockup.closest('.hero-showcase') || mockup.parentElement;
    if (showcase) {
      showcase.addEventListener('mouseenter', pauseOnHover);
      showcase.addEventListener('mouseleave', resumeOnLeave);
    }

    // Swipe en mobile
    var touchStartX = 0;
    mockup.addEventListener('touchstart', function (e) {
      touchStartX = e.touches[0].clientX;
    }, { passive: true });
    mockup.addEventListener('touchend', function (e) {
      var dx = e.changedTouches[0].clientX - touchStartX;
      if (Math.abs(dx) > 50) {
        activate(dx < 0 ? active + 1 : active - 1);
      }
    }, { passive: true });

    // Click en tab pausa y reanuda
    tabsRoot.addEventListener('mouseenter', pauseOnHover);
    tabsRoot.addEventListener('mouseleave', resumeOnLeave);

    // Init
    activate(0);
    startAutoplay();

    // Visibilidad: pausa si tab no está visible
    document.addEventListener('visibilitychange', function () {
      if (document.hidden) stopAutoplay();
      else if (!isHovered && !isFocus) startAutoplay();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();