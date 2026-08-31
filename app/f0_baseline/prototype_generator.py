"""
Generador del prototipo HTML sintético V134.1 usado por HU_01.

Produce un HTML con N funciones `window.*` distribuidas en 11 módulos
para que el inventario (`WindowInventory`) tenga material con qué
trabajar y para que el módulo `mapping` pueda cruzarse contra
`localStorage.setItem(...)` en el mismo HTML.

Uso programático:
    from app.f0_baseline.prototype_generator import PrototypeGenerator
    g = PrototypeGenerator()
    out = g.build()
    Path("prototypes/f0_baseline/demo.html").write_text(out, encoding="utf-8")

Uso CLI:
    python -m app.f0_baseline.prototype_generator
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

# Catálogo de 11 módulos y 20 funciones cada uno = 220 funciones
# (alineado con el plan original F0).
MODULES: list[tuple[str, int]] = [
    ("DASHBOARD", 20),
    ("PRODUCTOS", 20),
    ("INSUMOS", 20),
    ("PEDIDOS", 20),
    ("CLIENTES", 20),
    ("COTIZACIONES", 20),
    ("FACTURACION", 20),
    ("INVENTARIO", 20),
    ("PROMOCIONES", 20),
    ("FIDELIZACION", 20),
    ("REPORTES", 20),
]

# Mapeo localStorage → modelo (subconjunto representativo).
LOCALSTORAGE_DEMO: list[tuple[str, str]] = [
    ("wowhub.tenant", '{"id":"t1","name":"Demo","plan":"pro"}'),
    ("wowhub.user", '{"id":"u1","email":"demo@wowhub.io","role":"admin"}'),
    ("wowhub.session", '{"token":"abc123","expires":"2026-12-31"}'),
    ("wowhub.branch", '[{"id":"b1","name":"Sucursal Centro"}]'),
    ("wowhub.category", '[{"id":"c1","name":"Bebidas"},{"id":"c2","name":"Snacks"}]'),
    ("wowhub.product", '[{"id":"p1","name":"Café","price":25},{"id":"p2","name":"Té","price":20}]'),
    ("wowhub.insumo", '[{"id":"i1","name":"Café grano","unit":"kg"}]'),
    ("wowhub.receta", '[{"id":"r1","product_id":"p1","insumo_id":"i1","qty":0.02}]'),
    ("wowhub.branchProduct", '[{"branch_id":"b1","product_id":"p1","stock":50}]'),
    ("wowhub.order", '[{"id":"o1","total":75,"status":"paid"}]'),
    ("wowhub.orderItem", '[{"order_id":"o1","product_id":"p1","qty":3}]'),
    ("wowhub.quote", '[{"id":"q1","total":150,"status":"sent"}]'),
    ("wowhub.quoteItem", '[{"quote_id":"q1","product_id":"p2","qty":5}]'),
    ("wowhub.invoice", '[{"id":"inv1","order_id":"o1","total":75}]'),
    ("wowhub.payment", '[{"id":"pay1","order_id":"o1","amount":75,"method":"card"}]'),
    ("wowhub.cart", '{"id":"cart1","items":[]}'),
    ("wowhub.cartItem", '[{"cart_id":"cart1","product_id":"p1","qty":1}]'),
    ("wowhub.customer", '[{"id":"cust1","name":"Juan","email":"j@x.com"}]'),
    ("wowhub.booking", '[{"id":"bk1","service":"corte","date":"2026-09-10"}]'),
    ("wowhub.loyaltyCampaign", '[{"id":"lc1","name":"Estampitas","stamps":10}]'),
    ("wowhub.customerPass", '[{"id":"cp1","customer_id":"cust1","campaign_id":"lc1"}]'),
    ("wowhub.passStamp", '[{"pass_id":"cp1","qty":3}]'),
    ("wowhub.qrToken", '[{"id":"qrt1","code":"WOW-001"}]'),
    ("wowhub.promotion", '[{"id":"pr1","name":"20% off","pct":20}]'),
    ("wowhub.qr", '[{"id":"qr1","target":"menu","url":"https://x.com"}]'),
    ("wowhub.landingConfig", '{"hero":"Bienvenido","cta":"Ordena ya"}'),
    ("wowhub.siteConfig", '{"theme":"dark","lang":"es"}'),
    ("wowhub.aiConversation", '[{"id":"ai1","user_id":"u1"}]'),
    ("wowhub.aiMessage", '[{"conversation_id":"ai1","role":"user","text":"hola"}]'),
    ("wowhub.aiLog", '[{"id":"ail1","agent":"growth","status":"ok"}]'),
    ("wowhub.aiTrace", '[{"id":"ait1","duration_ms":120}]'),
    ("wowhub.aiMetricDaily", '[{"day":"2026-08-31","tokens":4321}]'),
    ("wowhub.audit", '[{"id":"a1","action":"login","user_id":"u1"}]'),
    ("wowhub.webhook", '[{"id":"w1","url":"https://hook.example"}]'),
    ("wowhub.webhookEvent", '[{"id":"we1","type":"order.paid"}]'),
    ("wowhub.webhookDelivery", '[{"id":"wd1","status":"200"}]'),
    ("wowhub.automation", '[{"id":"au1","name":"Bienvenida","status":"ok"}]'),
    ("wowhub.upload", '[{"id":"up1","filename":"foto.jpg"}]'),
    ("wowhub.legalConsent", '[{"id":"lg1","version":"v1"}]'),
    ("wowhub.onboarding", '{"step":3,"completed":false}'),
]


@dataclass
class PrototypeGenerator:
    """Genera el HTML sintético V134.1."""
    output_path: Path = Path("prototypes/f0_baseline/demo.html")
    title: str = "WowHub V134.1 — Prototipo Demo (F0 Baseline)"
    n_modules: int = 11
    fns_per_module: int = 20

    def build(self) -> str:
        modules = MODULES[: self.n_modules]
        body: list[str] = []
        body.append(self._header())
        for mod_name, n in modules:
            body.append(self._module_section(mod_name, n))
        body.append(self._localstorage_section())
        body.append(self._footer())
        return "\n".join(body)

    def write(self, path: Path | None = None) -> Path:
        target = Path(path) if path else self.output_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.build(), encoding="utf-8")
        return target

    # ----------------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------------
    def _header(self) -> str:
        return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>{self.title}</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 1100px; margin: 24px auto; padding: 0 20px; color: #0f172a; }}
  h1 {{ font-size: 26px; margin-bottom: 4px; }}
  h2 {{ font-size: 18px; margin-top: 32px; color: #0369a1; border-bottom: 1px solid #e2e8f0; padding-bottom: 4px; }}
  .tag {{ background: #0f172a; color: #06b6d4; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-family: monospace; }}
  pre {{ background: #f1f5f9; padding: 10px; border-radius: 6px; overflow-x: auto; font-size: 12px; }}
  .muted {{ color: #64748b; font-size: 13px; }}
</style>
</head>
<body>
<span class="tag">WOWHUB V134.1 · F0 BASELINE</span>
<h1>{self.title}</h1>
<p class="muted">Prototipo sintético para auditoría. Genera {sum(n for _, n in MODULES[:self.n_modules])} funciones <code>window.*</code> en {self.n_modules} módulos, más escrituras <code>localStorage</code> para mapeo contra <code>app.models</code>.</p>
"""

    def _footer(self) -> str:
        t = time.strftime("%Y-%m-%d %H:%M:%S")
        return f"""
<hr>
<p class="muted">Generado por <code>app.f0_baseline.prototype_generator</code> · {t}</p>
</body>
</html>
"""

    def _module_section(self, mod_name: str, n: int) -> str:
        lines: list[str] = []
        lines.append(f"<h2>// ============== // MÓDULO: {mod_name} ({n} funciones) // ==============</h2>")
        for i in range(1, n + 1):
            fn = f"{mod_name.lower()}_func_{i:02d}"
            desc = f"Acción #{i} del módulo {mod_name}"
            lines.append(
                f"window.{fn} = function() {{\n"
                f"  /* {desc} */\n"
                f"  console.log('wowhub.{mod_name.lower()}.{i}');\n"
                f"}};\n"
            )
        return "\n".join(lines)

    def _localstorage_section(self) -> str:
        lines: list[str] = ["<h2>// ============== // MÓDULO: LOCALSTORAGE (demo) // ==============</h2>"]
        lines.append("<h2>localStorage seed (HU_02)</h2>")
        lines.append("<pre>")
        for key, value in LOCALSTORAGE_DEMO:
            lines.append(f"localStorage.setItem({key!r}, {value!r});")
        lines.append("</pre>")
        # Función no-op para mantener el conteo de 1 función de "demo".
        lines.append(
            "window.localStorage_seed = function() { /* siembra localStorage para HU_02 */ };"
        )
        return "\n".join(lines)


def main() -> None:
    g = PrototypeGenerator()
    target = g.write()
    n = sum(n for _, n in MODULES)
    print(f"✓ Prototipo escrito en {target}  ·  {n} funciones  ·  {len(LOCALSTORAGE_DEMO)} claves localStorage")


if __name__ == "__main__":
    main()
