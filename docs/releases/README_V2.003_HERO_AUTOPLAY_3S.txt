================================================================================
README_V2.003_HERO_AUTOPLAY_3S.txt
WowHub · Release Notes Atómicos · V2.003
================================================================================

FECHA          : 2026-10-22
BUILD          : post 176eae4 (V2.002 imágenes realistas)
ALCANCE        : Hero Showcase · Reducir tiempo de autoplay
ATOMICIDAD     : 1 commit único (e511ca1)
RIESGO         : Muy bajo · Solo cambia constante de timing.
                Sin cambios en assets, backend, DB.
REVERTIBLE     : Sí · `git revert e511ca1`.


--------------------------------------------------------------------------------
1. BASE (contexto)
--------------------------------------------------------------------------------

Tras el deploy de V2.002 (commit 176eae4) que mostró las 8 imágenes
realistas en el Hero Showcase, el usuario aprobó el resultado y
solicitó (09:17):

  "PERFECTO!. Ahora si está funcionando bien. Reduce el tiempo de
   transición del slide a 3 segundos."

Diagnóstico:
  · El autoplay estaba en 4.5s (AUTOPLAY_MS = 4500) desde el
    commit inicial V2.01 (24d3012). Era razonable para imágenes
    SVG/emojis que cargaban instantáneamente.
  · Con imágenes realistas (lazy loaded, ~1MB cada una), el usuario
    prefiere un ritmo más dinámico para ver más slides por minuto.


--------------------------------------------------------------------------------
2. CAMBIO ÚNICO
--------------------------------------------------------------------------------

ARCHIVO: app/static/js/hero_showcase.js

   ANTES (V2.002):
     var AUTOPLAY_MS = 4500;

   AHORA (V2.003):
     var AUTOPLAY_MS = 3000;  // V2.003 — bajado de 4500ms a 3000ms
                                 //          por feedback del usuario
                                 //          (más dinámico, mejor
                                 //          engagement).

EFECTO:
  · Antes: 8 tabs × 4.5s = 36s para ver el ciclo completo.
  · Ahora: 8 tabs × 3.0s = 24s para ver el ciclo completo.
  · Incremento de frecuencia: 50% más slides por minuto.

Lo que NO se modificó:
  · TRANSITION_MS = 350 (mantiene timing del fade).
  · La swap ocurre a TRANSITION_MS / 2 = 175ms (fade in/out).
  · Pausa en hover/focus: intacta.
  · Swipe mobile: intacta.
  · Keyboard ARIA: intacta.
  · Las 8 imágenes PNG/JPG: intactas (siguen con loading=lazy).
  · Cache busting HTML (?v=v2.01-hero-showcase): intacto.


--------------------------------------------------------------------------------
3. QUÉ NO SE MODIFICÓ
--------------------------------------------------------------------------------

· Imágenes en app/static/img/hero/: 0 cambios.
· CSS (.hero-tab, .mock-image-wrap, etc.): 0 cambios.
· HTML (home.html, base.html): 0 cambios.
· Backend, schemas, routers, DB: 0.
· Multi-agent tests: 0 cambios.


--------------------------------------------------------------------------------
4. REQUERIMIENTOS DE DESPLIEGUE
--------------------------------------------------------------------------------

· Worker: NO requiere cambio.
· Cache busting: el link JS usa `?v=v2.01-hero-showcase`. El cambio
  se sirve al siguiente hard refresh (Ctrl+Shift+R).
· Browser support: sin cambios.
· No requiere migraciones Alembic.
· No requiere cambio en variables de entorno.
· No requiere rebuild Docker.


--------------------------------------------------------------------------------
5. PROCEDIMIENTO DE PRUEBA RECOMENDADO
--------------------------------------------------------------------------------

5.1 Test manual (smoke)
  a) Hard refresh / (Ctrl+Shift+R).
  b) NO hacer hover sobre el showcase.
  c) Cronometrar: el tab debe cambiar cada 3 segundos (no 4.5s).
     · Click en cualquier tab → se queda 3s, luego cambia al
       siguiente automáticamente.
     · Verificar que el ciclo completo (8 tabs) toma ~24s.
  d) Hover sobre el showcase → autoplay pausa.
  e) Click en tab → autoplay se reinicia desde ese tab.

5.2 Test programático (reloj)
  ```python
  import time
  # Capturar dos cambios de tab consecutivos con timestamps.
  # El delta debe ser ~3000ms ±50ms.
  ```

5.3 Test de regresión UX
  · ¿El usuario aún tiene tiempo de leer el tooltip? SÍ (2s mínimo
    si está mirando + 175ms fade).
  · ¿Las imágenes tienen tiempo de cargar? SÍ (lazy loading +
    imagen ya cacheada después de primer load).

5.4 Rollback
  `git revert e511ca1` (1 commit) restaura 4500ms.
  Riesgo: cero (solo cambia constante).


--------------------------------------------------------------------------------
6. TRAZABILIDAD
--------------------------------------------------------------------------------

Commits relacionados a Hero Showcase:
  · 24d3012  feat(public): V2.01 Hero Showcase interactivo (AUTOPLAY_MS=4500)
  · 0f4b422  fix: phone invisible
  · 69d4334  fix: titulo + mockups iniciales
  · d6ffcba  fix: mockups visualmente mas ricos
  · 6b32f76  fix: SVG inline
  · 176eae4  feat: imagenes realistas (V2.002)
  · e511ca1  fix: autoplay 4500 -> 3000ms (commit actual, V2.003)

Feedback del usuario:
  "PERFECTO!. Ahora si está funcionando bien. Reduce el tiempo de
   transición del slide a 3 segundos."

Métricas:
  · Antes (V2.002): 8 tabs × 4.5s = 36s ciclo completo.
  · Ahora (V2.003): 8 tabs × 3.0s = 24s ciclo completo.
  · Incremento: 50% más slides por minuto.


================================================================================
FIN README_V2.003_HERO_AUTOPLAY_3S.txt
================================================================================