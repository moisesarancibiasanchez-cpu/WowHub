"""
HU_01 — Inventario de funciones `window.*` del prototipo V134.1.

Analiza un archivo HTML del prototipo y extrae todas las asignaciones
`window.NOMBRE = function() { ... }`, agrupándolas por módulo según los
comentarios `// MÓDULO:`.

Uso programático:
    from app.f0_baseline.inventory import WindowInventory
    inv = WindowInventory.from_html(Path("prototypes/.../foo.html"))
    rows = inv.extract()
    md = inv.to_markdown()

Uso CLI:
    python -m app.f0_baseline.inventory <html_path>
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional


# Patrones
# Acepta tanto el header en una línea:
#   "// ============== // MÓDULO: DASHBOARD (20 funciones) // =============="
# como en múltiples líneas (versión clásica).
# También acepta la sección de localStorage:  "// MÓDULO: LOCALSTORAGE (demo)"
RE_MODULE_HEADER = re.compile(
    r"//\s*(?:=+\s*)?//?\s*MÓDULO:\s*(\w+)\s*\([^)]*\)",
    re.MULTILINE,
)
RE_WINDOW_FN = re.compile(
    r"window\.(?P<name>[A-Za-z_]\w*)\s*=\s*function\s*\([^)]*\)\s*\{\s*"
    r"/\*\s*(?P<desc>[^*]+?)\s*\*/\s*\};",
    re.MULTILINE,
)
RE_ANY_FN = re.compile(r"window\.(?P<name>[A-Za-z_]\w*)\s*=\s*function")


@dataclass
class FunctionRow:
    n: int
    name: str
    module: str
    line: int
    description: str


class WindowInventory:
    """Inventario de funciones `window.*` extraídas de un HTML."""

    def __init__(self, html_path: Path):
        self.html_path = Path(html_path)
        self.text: str = ""
        self.lines: list[str] = []
        self._module_ranges: dict[str, tuple[int, int]] = {}

    @classmethod
    def from_html(cls, html_path: Path) -> "WindowInventory":
        inv = cls(html_path)
        if not inv.html_path.is_file():
            raise FileNotFoundError(f"No se encuentra {inv.html_path}")
        inv.text = inv.html_path.read_text(encoding="utf-8")
        inv.lines = inv.text.splitlines()
        inv._compute_module_ranges()
        return inv

    def _compute_module_ranges(self) -> None:
        """Encuentra los rangos de líneas de cada módulo."""
        self._module_ranges = {}
        for m in RE_MODULE_HEADER.finditer(self.text):
            name = m.group(1)
            start = self.text[: m.start()].count("\n") + 1
            self._module_ranges[name] = (start, None)

        sorted_mods = sorted(self._module_ranges.items(), key=lambda kv: kv[1][0])
        for i, (name, (start, _)) in enumerate(sorted_mods):
            if i + 1 < len(sorted_mods):
                end = sorted_mods[i + 1][1][0] - 1
            else:
                end = len(self.lines)
            self._module_ranges[name] = (start, end)

    def extract(self) -> list[FunctionRow]:
        """Devuelve la lista de funciones detectadas."""
        rows: list[FunctionRow] = []
        seen: set[str] = set()

        for m in RE_WINDOW_FN.finditer(self.text):
            name = m.group("name").strip()
            desc = m.group("desc").strip()
            line_no = self.text[: m.start()].count("\n") + 1
            module = self._module_for_line(line_no)
            rows.append(FunctionRow(
                n=len(rows) + 1, name=name, module=module,
                line=line_no, description=desc,
            ))
            seen.add(name)

        # Detección de funciones huérfanas (sin /* */)
        for m in RE_ANY_FN.finditer(self.text):
            name = m.group("name")
            if name in seen:
                continue
            line_no = self.text[: m.start()].count("\n") + 1
            module = self._module_for_line(line_no)
            rows.append(FunctionRow(
                n=len(rows) + 1, name=name, module=module,
                line=line_no, description="(sin descripción)",
            ))
            seen.add(name)

        return rows

    def _module_for_line(self, line_no: int) -> str:
        for mod, (s, e) in self._module_ranges.items():
            if s <= line_no <= e:
                return mod
        return "unknown"

    def to_markdown(self, rows: list[FunctionRow], elapsed_ms: int) -> str:
        total = len(rows)
        by_module: dict[str, int] = {}
        for r in rows:
            by_module[r.module] = by_module.get(r.module, 0) + 1

        out: list[str] = []
        out.append(f"# Inventario de funciones `window.*` — WowHub V134.1")
        out.append("")
        out.append(f"- **Archivo analizado:** `{self.html_path.name}`")
        out.append(f"- **Total funciones detectadas:** **{total}**")
        out.append(f"- **Módulos:** {len(by_module)}")
        out.append(f"- **Tiempo de análisis:** {elapsed_ms} ms")
        out.append("")
        out.append("## Resumen por módulo")
        out.append("")
        out.append("| Módulo | Funciones | % |")
        out.append("|---|---:|---:|")
        for mod, n in sorted(by_module.items(), key=lambda kv: -kv[1]):
            pct = (n / total) * 100 if total else 0
            out.append(f"| `{mod}` | {n} | {pct:.1f}% |")
        out.append(f"| **Total** | **{total}** | **100.0%** |")
        out.append("")
        out.append("## Detalle por función")
        out.append("")
        out.append("| # | Función | Módulo | Línea | Descripción |")
        out.append("|---:|---|---|---:|---|")
        for r in rows:
            desc = r.description.replace("|", "\\|")
            out.append(f"| {r.n} | `{r.name}` | `{r.module}` | {r.line} | {desc} |")
        out.append("")
        out.append("---")
        out.append(f"_Generado por `app.f0_baseline.inventory` · {time.strftime('%Y-%m-%d %H:%M:%S')}_")
        return "\n".join(out)

    def run(self) -> dict:
        """Ejecuta el inventario completo y devuelve un dict con rows + md + elapsed."""
        t0 = time.perf_counter()
        rows = self.extract()
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        return {
            "html": str(self.html_path),
            "total": len(rows),
            "elapsed_ms": elapsed_ms,
            "rows": [asdict(r) for r in rows],
            "markdown": self.to_markdown(rows, elapsed_ms),
        }
