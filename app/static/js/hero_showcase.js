/* ═══════════════════════════════════════════════════════════════════════
   WowHub · Hero Showcase Controller (V2.01)
   Carrusel interactivo de 8 funcionalidades con autoplay + pause on hover.
   Implementa ARIA tabs (role="tablist", aria-selected, role="tabpanel").
   Sin dependencias externas. ~5KB.
   ═══════════════════════════════════════════════════════════════════════ */

(function () {
  'use strict';

  var AUTOPLAY_MS = 4500;
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

  /* ── Visual factory (devuelve el HTML del mockup por tab) ──── */
  function visualHTML(tab) {
    switch (tab.visual) {
      case 'page':
        return [
          '<div class="mock-page">',
          '  <div class="mock-page__hero">',
          '    <div class="mock-page__avatar">N</div>',
          '    <div>',
          '      <strong>Café Norte</strong>',
          '      <small>cafénorte.cl</small>',
          '    </div>',
          '  </div>',
          '  <div class="mock-page__lines">',
          '    <div class="mock-line w-80"></div>',
          '    <div class="mock-line w-60"></div>',
          '    <div class="mock-line w-90"></div>',
          '  </div>',
          '  <div class="mock-page__cta">¡Bienvenido!</div>',
          '</div>'
        ].join('');

      case 'catalog':
        return [
          '<div class="mock-catalog">',
          '  <div class="mock-product">',
          '    <div class="mock-product__img" style="background: linear-gradient(135deg, #f59e0b, #ef4444);">☕</div>',
          '    <div class="mock-product__info"><strong>Latte</strong><span>$3.500</span></div>',
          '  </div>',
          '  <div class="mock-product">',
          '    <div class="mock-product__img" style="background: linear-gradient(135deg, #6c5ce7, #ec4899);">🧁</div>',
          '    <div class="mock-product__info"><strong>Torta</strong><span>$5.200</span></div>',
          '  </div>',
          '  <div class="mock-product">',
          '    <div class="mock-product__img" style="background: linear-gradient(135deg, #00b894, #74b9ff);">🥗</div>',
          '    <div class="mock-product__info"><strong>Ensalada</strong><span>$7.800</span></div>',
          '  </div>',
          '</div>'
        ].join('');

      case 'qr':
        return [
          '<div class="mock-qr">',
          '  <div class="mock-qr__label">Mesa 1</div>',
          '  <div class="mock-qr__pattern" aria-hidden="true">',
          '    <div class="qr-cell c1"></div><div class="qr-cell c2"></div><div class="qr-cell c3"></div>',
          '    <div class="qr-cell c4"></div><div class="qr-cell c5"></div><div class="qr-cell c6"></div>',
          '    <div class="qr-cell c7"></div><div class="qr-cell c8"></div><div class="qr-cell c9"></div>',
          '  </div>',
          '  <div class="mock-qr__scan"></div>',
          '  <div class="mock-qr__footer">Escanea para ver el menú</div>',
          '</div>'
        ].join('');

      case 'orders':
        return [
          '<div class="mock-orders">',
          '  <div class="mock-order"><span class="dot ok"></span><div><strong>#124</strong><small>Hace 2 min</small></div><span class="amt">$3.500</span></div>',
          '  <div class="mock-order"><span class="dot proc"></span><div><strong>#123</strong><small>Hace 5 min</small></div><span class="amt">$5.200</span></div>',
          '  <div class="mock-order"><span class="dot ok"></span><div><strong>#122</strong><small>Hace 8 min</small></div><span class="amt">$7.800</span></div>',
          '  <div class="mock-order"><span class="dot proc"></span><div><strong>#121</strong><small>Hace 12 min</small></div><span class="amt">$3.500</span></div>',
          '</div>'
        ].join('');

      case 'payments':
        return [
          '<div class="mock-payment">',
          '  <div class="mock-payment__icon">',
          '    <svg viewBox="0 0 24 24" width="44" height="44" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">',
          '      <rect x="2" y="6" width="20" height="13" rx="2"/>',
          '      <line x1="2" y1="10" x2="22" y2="10"/>',
          '    </svg>',
          '  </div>',
          '  <div class="mock-payment__amount">$3.500 CLP</div>',
          '  <div class="mock-payment__status">✓ Pago confirmado</div>',
          '  <div class="mock-payment__method">MercadoPago · Visa ****4242</div>',
          '</div>'
        ].join('');

      case 'bookings':
        return [
          '<div class="mock-bookings">',
          '  <div class="mock-bookings__date">Miércoles 22 Oct</div>',
          '  <div class="mock-slots">',
          '    <span class="slot ok">10:00</span>',
          '    <span class="slot busy">11:00</span>',
          '    <span class="slot ok">12:00</span>',
          '    <span class="slot ok">15:00</span>',
          '    <span class="slot busy">16:00</span>',
          '    <span class="slot ok">17:00</span>',
          '    <span class="slot ok">18:00</span>',
          '    <span class="slot ok">19:00</span>',
          '  </div>',
          '  <div class="mock-bookings__hint">Reservas vía WhatsApp</div>',
          '</div>'
        ].join('');

      case 'promos':
        return [
          '<div class="mock-promos">',
          '  <div class="mock-promo-card">',
          '    <div class="mock-promo-card__badge">-30%</div>',
          '    <div class="mock-promo-card__emoji">🎉</div>',
          '    <strong>2x1 en Latte</strong>',
          '    <small>Todos los martes</small>',
          '    <div class="mock-promo-card__code">CUPON: CAFE2X1</div>',
          '  </div>',
          '  <div class="mock-promo-card">',
          '    <div class="mock-promo-card__badge" style="background:#fdcb6e;">15%</div>',
          '    <div class="mock-promo-card__emoji">🥐</div>',
            '<strong>15% Pastelería</strong>',
            '<small>De lunes a viernes</small>',
            '<div class="mock-promo-card__code">CUPON: DULCE15</div>',
          '</div>',
          '</div>'
        ].join('');

      case 'stats':
      default:
        return [
          '<div class="mock-stats">',
          '  <div class="mock-stat-bar"><span>Lun</span><div class="bar"><div class="fill" style="height:60%"></div></div><small>$42k</small></div>',
          '  <div class="mock-stat-bar"><span>Mar</span><div class="bar"><div class="fill" style="height:75%"></div></div><small>$58k</small></div>',
          '  <div class="mock-stat-bar"><span>Mié</span><div class="bar"><div class="fill" style="height:90%"></div></div><small>$72k</small></div>',
          '  <div class="mock-stat-bar"><span>Jue</span><div class="bar"><div class="fill" style="height:55%"></div></div><small>$38k</small></div>',
          '  <div class="mock-stat-bar"><span>Vie</span><div class="bar"><div class="fill" style="height:100%"></div></div><small>$85k</small></div>',
          '  <div class="mock-stat-bar"><span>Sáb</span><div class="bar"><div class="fill" style="height:85%"></div></div><small>$68k</small></div>',
          '  <div class="mock-stat-bar"><span>Dom</span><div class="bar"><div class="fill" style="height:40%"></div></div><small>$28k</small></div>',
          '</div>'
        ].join('');
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

      // Render mockup content with fade transition
      mockup.classList.add('is-switching');
      window.setTimeout(function () {
        mockup.innerHTML = visualHTML(tab);
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