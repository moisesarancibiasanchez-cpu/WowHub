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
          // Latte — taza humeante sobre gradiente cálido
          '  <div class="mock-product">',
          '    <div class="mock-product__img mock-product__img--latte">',
          '      <svg viewBox="0 0 48 48" width="40" height="40" aria-hidden="true">',
          '        <defs><linearGradient id="cupGrad" x1="0%" y1="0%" x2="0%" y2="100%">',
          '          <stop offset="0%" stop-color="#f4f1ec"/><stop offset="100%" stop-color="#d4c5b3"/>',
          '        </linearGradient></defs>',
          '        <!-- Vapor -->',
          '        <path d="M16 8 Q18 4 16 0" stroke="#ffffff" stroke-width="1.8" fill="none" stroke-linecap="round" opacity="0.85"/>',
          '        <path d="M22 10 Q24 6 22 2" stroke="#ffffff" stroke-width="1.8" fill="none" stroke-linecap="round" opacity="0.7"/>',
          '        <path d="M28 8 Q30 4 28 0" stroke="#ffffff" stroke-width="1.8" fill="none" stroke-linecap="round" opacity="0.85"/>',
          '        <!-- Asa -->',
          '        <path d="M36 18 Q42 18 42 24 Q42 30 36 30" stroke="#a08570" stroke-width="2" fill="none"/>',
          '        <!-- Taza -->',
          '        <path d="M10 16 L36 16 L34 36 Q34 40 30 40 L16 40 Q12 40 12 36 Z" fill="url(#cupGrad)" stroke="#8b6f5a" stroke-width="1.2"/>',
          '        <!-- Café líquido -->',
          '        <ellipse cx="23" cy="16" rx="13" ry="2.5" fill="#3e2723"/>',
          '        <!-- Plato -->',
          '        <ellipse cx="23" cy="42" rx="18" ry="2" fill="#a08570" opacity="0.5"/>',
          '      </svg>',
          '    </div>',
          '    <div class="mock-product__info"><strong>Latte</strong><span>$3.500</span></div>',
          '  </div>',
          // Torta — cupcake con frosting sobre gradiente magenta
          '  <div class="mock-product">',
          '    <div class="mock-product__img mock-product__img--cake">',
          '      <svg viewBox="0 0 48 48" width="40" height="40" aria-hidden="true">',
          '        <!-- Wrapper inferior -->',
          '        <path d="M12 24 L36 24 L33 38 Q33 41 30 41 L18 41 Q15 41 15 38 Z" fill="#d4a574" stroke="#8b6f4a" stroke-width="1.2"/>',
          '        <!-- Lineas wrapper -->',
          '        <line x1="14" y1="28" x2="14" y2="38" stroke="#8b6f4a" stroke-width="0.8"/>',
          '        <line x1="19" y1="28" x2="19" y2="38" stroke="#8b6f4a" stroke-width="0.8"/>',
          '        <line x1="24" y1="28" x2="24" y2="38" stroke="#8b6f4a" stroke-width="0.8"/>',
          '        <line x1="29" y1="28" x2="29" y2="38" stroke="#8b6f4a" stroke-width="0.8"/>',
          '        <line x1="34" y1="28" x2="34" y2="38" stroke="#8b6f4a" stroke-width="0.8"/>',
          '        <!-- Frosting swirl -->',
          '        <path d="M12 24 Q12 18 18 18 Q18 12 24 12 Q30 12 30 18 Q36 18 36 24 Z" fill="#f472b6" stroke="#be185d" stroke-width="1.2"/>',
          '        <!-- Highlights swirl -->',
          '        <ellipse cx="20" cy="15" rx="2" ry="1" fill="#ffffff" opacity="0.6"/>',
          '        <!-- Cherry -->',
          '        <circle cx="24" cy="10" r="2.5" fill="#dc2626"/>',
          '        <line x1="24" y1="7" x2="25" y2="4" stroke="#16a34a" stroke-width="1" stroke-linecap="round"/>',
          '      </svg>',
          '    </div>',
          '    <div class="mock-product__info"><strong>Torta</strong><span>$5.200</span></div>',
          '  </div>',
          // Ensalada — bowl con hojas verdes sobre gradiente turquesa
          '  <div class="mock-product">',
          '    <div class="mock-product__img mock-product__img--salad">',
          '      <svg viewBox="0 0 48 48" width="40" height="40" aria-hidden="true">',
          '        <!-- Bowl -->',
          '        <path d="M8 24 Q8 38 24 38 Q40 38 40 24 Z" fill="#74b9ff" stroke="#0984e3" stroke-width="1.5"/>',
          '        <ellipse cx="24" cy="24" rx="16" ry="3" fill="#0984e3" opacity="0.4"/>',
          '        <!-- Hojas -->',
          '        <ellipse cx="18" cy="20" rx="6" ry="4" fill="#16a34a" transform="rotate(-20 18 20)"/>',
          '        <ellipse cx="24" cy="17" rx="6" ry="4" fill="#22c55e" transform="rotate(5 24 17)"/>',
          '        <ellipse cx="30" cy="20" rx="6" ry="4" fill="#16a34a" transform="rotate(25 30 20)"/>',
          '        <!-- Tomate cherry -->',
          '        <circle cx="20" cy="18" r="2" fill="#ef4444"/>',
          '        <circle cx="28" cy="16" r="2" fill="#ef4444"/>',
          '        <!-- Highlights -->',
          '        <path d="M12 26 L36 26" stroke="#ffffff" stroke-width="1" opacity="0.4"/>',
          '      </svg>',
          '    </div>',
          '    <div class="mock-product__info"><strong>Ensalada</strong><span>$7.800</span></div>',
          '  </div>',
          '</div>'
        ].join('');

      case 'qr':
        return [
          '<div class="mock-qr">',
          '  <div class="mock-qr__label">Mesa 1</div>',
          '  <div class="mock-qr__svg-wrap">',
          '    <svg viewBox="0 0 25 25" class="mock-qr__svg" aria-hidden="true">',
          '      <!-- Esquinas superiores (finder patterns) -->',
          '      <rect x="0" y="0" width="7" height="7" fill="#172033"/>',
          '      <rect x="1" y="1" width="5" height="5" fill="#ffffff"/>',
          '      <rect x="2" y="2" width="3" height="3" fill="#172033"/>',
          '      <rect x="18" y="0" width="7" height="7" fill="#172033"/>',
          '      <rect x="19" y="1" width="5" height="5" fill="#ffffff"/>',
          '      <rect x="20" y="2" width="3" height="3" fill="#172033"/>',
          '      <rect x="0" y="18" width="7" height="7" fill="#172033"/>',
          '      <rect x="1" y="19" width="5" height="5" fill="#ffffff"/>',
          '      <rect x="2" y="20" width="3" height="3" fill="#172033"/>',
          '      <!-- Modulos del medio (simulando datos) -->',
          '      <rect x="9" y="0" width="1" height="1" fill="#172033"/>',
          '      <rect x="11" y="0" width="1" height="1" fill="#172033"/>',
          '      <rect x="14" y="0" width="1" height="1" fill="#172033"/>',
          '      <rect x="9" y="2" width="1" height="1" fill="#172033"/>',
          '      <rect x="12" y="2" width="1" height="1" fill="#172033"/>',
          '      <rect x="15" y="2" width="1" height="1" fill="#172033"/>',
          '      <rect x="9" y="4" width="1" height="1" fill="#172033"/>',
          '      <rect x="13" y="4" width="1" height="1" fill="#172033"/>',
          '      <rect x="16" y="4" width="1" height="1" fill="#172033"/>',
          '      <rect x="8" y="6" width="1" height="1" fill="#172033"/>',
          '      <rect x="11" y="6" width="1" height="1" fill="#172033"/>',
          '      <rect x="14" y="6" width="1" height="1" fill="#172033"/>',
          '      <rect x="17" y="6" width="1" height="1" fill="#172033"/>',
          '      <rect x="9" y="8" width="1" height="1" fill="#172033"/>',
          '      <rect x="12" y="8" width="1" height="1" fill="#172033"/>',
          '      <rect x="15" y="8" width="1" height="1" fill="#172033"/>',
          '      <rect x="0" y="9" width="1" height="1" fill="#172033"/>',
          '      <rect x="3" y="9" width="1" height="1" fill="#172033"/>',
          '      <rect x="6" y="9" width="1" height="1" fill="#172033"/>',
          '      <rect x="10" y="9" width="1" height="1" fill="#172033"/>',
          '      <rect x="13" y="9" width="1" height="1" fill="#172033"/>',
          '      <rect x="16" y="9" width="1" height="1" fill="#172033"/>',
          '      <rect x="19" y="9" width="1" height="1" fill="#172033"/>',
          '      <rect x="22" y="9" width="1" height="1" fill="#172033"/>',
          '      <rect x="8" y="10" width="1" height="1" fill="#172033"/>',
          '      <rect x="11" y="10" width="1" height="1" fill="#172033"/>',
          '      <rect x="14" y="10" width="1" height="1" fill="#172033"/>',
          '      <rect x="17" y="10" width="1" height="1" fill="#172033"/>',
          '      <rect x="20" y="10" width="1" height="1" fill="#172033"/>',
          '      <rect x="9" y="11" width="1" height="1" fill="#172033"/>',
          '      <rect x="12" y="11" width="1" height="1" fill="#172033"/>',
          '      <rect x="15" y="11" width="1" height="1" fill="#172033"/>',
          '      <rect x="18" y="11" width="1" height="1" fill="#172033"/>',
          '      <rect x="21" y="11" width="1" height="1" fill="#172033"/>',
          '      <rect x="0" y="12" width="1" height="1" fill="#172033"/>',
          '      <rect x="3" y="12" width="1" height="1" fill="#172033"/>',
          '      <rect x="6" y="12" width="1" height="1" fill="#172033"/>',
          '      <rect x="9" y="12" width="1" height="1" fill="#172033"/>',
          '      <rect x="13" y="12" width="1" height="1" fill="#172033"/>',
          '      <rect x="16" y="12" width="1" height="1" fill="#172033"/>',
          '      <rect x="19" y="12" width="1" height="1" fill="#172033"/>',
          '      <rect x="22" y="12" width="1" height="1" fill="#172033"/>',
          '      <rect x="8" y="13" width="1" height="1" fill="#172033"/>',
          '      <rect x="11" y="13" width="1" height="1" fill="#172033"/>',
          '      <rect x="14" y="13" width="1" height="1" fill="#172033"/>',
          '      <rect x="17" y="13" width="1" height="1" fill="#172033"/>',
          '      <rect x="20" y="13" width="1" height="1" fill="#172033"/>',
          '      <rect x="9" y="14" width="1" height="1" fill="#172033"/>',
          '      <rect x="12" y="14" width="1" height="1" fill="#172033"/>',
          '      <rect x="15" y="14" width="1" height="1" fill="#172033"/>',
          '      <rect x="18" y="14" width="1" height="1" fill="#172033"/>',
          '      <rect x="21" y="14" width="1" height="1" fill="#172033"/>',
          '      <rect x="0" y="15" width="1" height="1" fill="#172033"/>',
          '      <rect x="3" y="15" width="1" height="1" fill="#172033"/>',
          '      <rect x="6" y="15" width="1" height="1" fill="#172033"/>',
          '      <rect x="10" y="15" width="1" height="1" fill="#172033"/>',
          '      <rect x="13" y="15" width="1" height="1" fill="#172033"/>',
          '      <rect x="16" y="15" width="1" height="1" fill="#172033"/>',
          '      <rect x="19" y="15" width="1" height="1" fill="#172033"/>',
          '      <rect x="22" y="15" width="1" height="1" fill="#172033"/>',
          '      <rect x="9" y="16" width="1" height="1" fill="#172033"/>',
          '      <rect x="11" y="16" width="1" height="1" fill="#172033"/>',
          '      <rect x="14" y="16" width="1" height="1" fill="#172033"/>',
          '      <rect x="17" y="16" width="1" height="1" fill="#172033"/>',
          '      <rect x="20" y="16" width="1" height="1" fill="#172033"/>',
          '      <rect x="8" y="18" width="1" height="1" fill="#172033"/>',
          '      <rect x="11" y="18" width="1" height="1" fill="#172033"/>',
          '      <rect x="14" y="18" width="1" height="1" fill="#172033"/>',
          '      <rect x="17" y="18" width="1" height="1" fill="#172033"/>',
          '      <rect x="9" y="20" width="1" height="1" fill="#172033"/>',
          '      <rect x="13" y="20" width="1" height="1" fill="#172033"/>',
          '      <rect x="16" y="20" width="1" height="1" fill="#172033"/>',
          '      <rect x="9" y="22" width="1" height="1" fill="#172033"/>',
          '      <rect x="11" y="22" width="1" height="1" fill="#172033"/>',
          '      <rect x="14" y="22" width="1" height="1" fill="#172033"/>',
          '      <rect x="18" y="22" width="1" height="1" fill="#172033"/>',
          '      <rect x="21" y="22" width="1" height="1" fill="#172033"/>',
          '      <rect x="8" y="23" width="1" height="1" fill="#172033"/>',
          '      <rect x="11" y="23" width="1" height="1" fill="#172033"/>',
          '      <rect x="14" y="23" width="1" height="1" fill="#172033"/>',
          '      <rect x="17" y="23" width="1" height="1" fill="#172033"/>',
          '      <rect x="20" y="23" width="1" height="1" fill="#172033"/>',
          '    </svg>',
          '    <div class="mock-qr__scan"></div>',
          '  </div>',
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