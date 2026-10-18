"""
CP Index — Parser del documento TEST_CASES_V134_2.md e índice de casos de prueba
WowHub Multi-Agent System v1.1.0 — FASE 3

Convierte el documento markdown de CPs en un índice estructurado (JSON)
que se puede consultar por CP, épica, HU o endpoint.

Soporta dos formatos:
  A) SECCIÓN (formato legacy, V134.2 ideal):
        ## CP-01-01-F — Título
        - **Épica**: E01
        - **HU**: HU-01
        - **Tipo**: functional
        - **Método**: GET
        - **Endpoint**: /api/...
        - **Status esperado**: 200

  B) TABLA (formato real encontrado en TEST_CASES_V134_Completo.MD):
        ## HU_01 · Título (X SP)
        ### 🟢 Casos Funcionales
        | ID | Descripción | Pasos | Resultado esperado |
        |----|-------------|-------|---------------------|
        | CP-01-01-F | Descripción | Pasos | Resultado |
"""

import os
import re
import json
import hashlib
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


@dataclass
class TestCase:
    """Representacion estructurada de un Caso de Prueba."""
    id:               str
    epic:            str
    hu:              str
    hu_id:           str      # HU_XX (usado por el runner para resolver endpoint)
    title:           str
    type:            str      # functional | security | performance | negative
    method:          str      # GET | POST | PUT | DELETE | ...
    path:            str      # /api/products
    expected_status: int      # 200 | 201 | 400 | 401 | ...
    expected_body_contains: Optional[str] = None
    description:     Optional[str] = None
    steps:           Optional[List[str]] = None
    tags:            List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_http_test(self) -> Dict[str, Any]:
        """Convierte el CP a formato ejecutable por CPRunner."""
        return {
            "id":                   self.id,
            "method":               self.method,
            "path":                self.path,
            "expected_status":      self.expected_status,
            "expected_body_contains": self.expected_body_contains,
            "hu_id":               self.hu_id,   # para HU→endpoint mapping
            "type":                 self.type,
            "title":                self.title,
        }


class CPIndex:
    """
    Parser e índice del documento TEST_CASES_V134_2.md.

    Formato esperado del documento (BPMN-style):
        ## CP-01-01-F — Verificación de usuario existe
        - **Épica**: E01 — Autenticación
        - **HU**: HU-01 — Login de usuario
        - **Tipo**: functional
        - **Método**: GET
        - **Endpoint**: /api/users/{id}
        - **Status esperado**: 200
        - **Body contiene**: "email"
    """

    CP_HEADER_RE   = re.compile(
        r"^##\s+(CP-\d+-\d+-[A-Z])\s*[-—]\s*(.+)$",
        re.MULTILINE | re.IGNORECASE
    )
    FIELD_RE       = re.compile(
        r"^\s*-\s*\*\*([^*]+)\*\*:\s*(.+)$",
        re.MULTILINE
    )

    def __init__(self, doc_path: Optional[str] = None, cache_dir: Optional[str] = None):
        self.doc_path = Path(doc_path) if doc_path else None
        self.cache_dir = Path(cache_dir or os.getenv("CACHE_DIR", "./cache"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self._cps:      Dict[str, TestCase] = {}   # id -> TestCase
        self._by_epic:  Dict[str, List[TestCase]] = {}
        self._by_hu:    Dict[str, List[TestCase]] = {}
        self._by_type:  Dict[str, List[TestCase]] = {}
        self._by_method: Dict[str, List[TestCase]] = {}

    @property
    def cache_path(self) -> Path:
        h = hashlib.sha256(
            (str(self.doc_path) if self.doc_path else "no-doc").encode()
        ).hexdigest()[:16]
        return self.cache_dir / f"cp_index_{h}.json"

    def load(self, force_reparse: bool = False) -> "CPIndex":
        """Carga el índice desde caché o desde el documento."""
        if not force_reparse and self.cache_path.exists():
            logger.info(f"Cargando índice desde caché: {self.cache_path}")
            with open(self.cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._cps = {cp["id"]: TestCase(**cp) for cp in data["cps"]}
            self._rebuild_indexes()
            return self

        if self.doc_path and self.doc_path.exists():
            logger.info(f"Parseando documento: {self.doc_path}")
            self.parse(str(self.doc_path))
            self.save_index()
        else:
            logger.warning(f"Documento no encontrado: {self.doc_path}")

        return self

    def save_index(self) -> None:
        data = {
            "cps": [cp.to_dict() for cp in self._cps.values()],
            "meta": {
                "doc_path": str(self.doc_path) if self.doc_path else None,
                "total": len(self._cps),
            }
        }
        with open(self.cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"Índice guardado en {self.cache_path}")

    # ------------------------------------------------------------------
    # Parser
    # ------------------------------------------------------------------
    def parse(self, doc_path: str) -> "CPIndex":
        """Parsea el documento markdown y construye el índice.

        Detecta automáticamente el formato:
        - SECCIÓN: si encuentra headers `## CP-...` → usa _parse_section()
        - TABLA:  si encuentra headers `## HU_` y tablas markdown → usa _parse_table_format()
        """
        with open(doc_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Detectar formato
        if re.search(r"^##\s+CP-\d+-\d+-[A-Z]", content, re.MULTILINE):
            # Formato SECCIÓN
            logger.info("Detectado formato SECCIÓN (## CP-...)")
            sections = self._split_sections(content)
            for cp_id, section_text in sections.items():
                cp = self._parse_section(cp_id, section_text)
                if cp:
                    self._cps[cp.id] = cp
        elif re.search(r"^##\s+HU_\d+", content, re.MULTILINE):
            # Formato TABLA (HU_NN con tablas markdown)
            logger.info("Detectado formato TABLA (## HU_XX con tablas)")
            self._parse_table_format(content)
        else:
            logger.warning("Formato no detectado. Intentando parseo por sección...")
            sections = self._split_sections(content)
            for cp_id, section_text in sections.items():
                cp = self._parse_section(cp_id, section_text)
                if cp:
                    self._cps[cp.id] = cp

        self._rebuild_indexes()
        logger.info(f"Parseados {len(self._cps)} casos de prueba")
        return self

    def _parse_table_format(self, content: str) -> None:
        """
        Parsea formato TABLA:
          ## HU_NN · Título (X SP)
          ### 🟢 Casos Funcionales
          | ID | Descripción | Pasos | Resultado esperado |
          | CP-NN-XX-T | ... | ... | ... |
        """
        lines = content.split("\n")
        current_hu_id: Optional[str] = None
        current_hu_title: str = ""
        current_type: str = "functional"

        # Mapeo de emojis/secciones a tipo
        type_map = {
            "🟢": "functional",
            "🔒": "security",
            "⚡": "performance",
            "❌": "negative",
            "🟡": "functional",
            "🟠": "negative",
        }

        for raw in lines:
            line = raw.rstrip()

            # HU header: ## HU_01 · ...
            m_hu = re.match(r"^##\s+HU_(\d+)\s*·?\s*(.+)$", line)
            if m_hu:
                current_hu_id = m_hu.group(1)
                current_hu_title = m_hu.group(2).strip()
                continue

            # Type section header: ### 🟢 Casos Funcionales
            m_type = re.match(r"^###\s+(.)", line)
            if m_type and current_hu_id:
                emoji = m_type.group(1)
                current_type = type_map.get(emoji, "functional")
                continue

            # Fila de tabla: | CP-01-01-F | desc | pasos | resultado |
            if line.startswith("|") and current_hu_id:
                cols = [c.strip() for c in line.strip("|").split("|")]
                if len(cols) < 2:
                    continue
                first = cols[0]
                m_cp = re.match(r"^(CP-\d+-\d+-[A-Z])\s*$", first)
                if m_cp:
                    cp_id = m_cp.group(1)
                    description = cols[1] if len(cols) > 1 else ""
                    steps_raw   = cols[2] if len(cols) > 2 else ""
                    expected    = cols[3] if len(cols) > 3 else ""

                    # Mapear tipo desde sufijo
                    cp_type = {
                        "F": "functional",
                        "S": "security",
                        "N": "negative",
                        "R": "performance",
                    }.get(cp_id[-1], current_type)

                    # Extraer método y path heurísticamente de la descripción
                    method, path, status = self._extract_endpoint(description + " " + steps_raw)

                    tags = [cp_type]
                    if "security" in cp_type: tags.append("security")
                    if "negative" in cp_type: tags.append("negative")
                    if "performance" in cp_type: tags.append("performance")

                    self._cps[cp_id] = TestCase(
                        id                   = cp_id,
                        epic                 = "E" + current_hu_id[0:1] if len(current_hu_id) >= 1 else "E0",
                        hu                   = f"HU-{current_hu_id} — {current_hu_title[:60]}",
                        hu_id                = f"HU_{current_hu_id}",
                        title                = description[:140],
                        type                 = cp_type,
                        method               = method,
                        path                 = path,
                        expected_status      = status,
                        expected_body_contains = None,
                        description          = description,
                        steps                = [s.strip() for s in steps_raw.split(".") if s.strip()] or None,
                        tags                 = tags,
                    )

    @staticmethod
    def _extract_endpoint(text: str) -> tuple:
        """
        Heurística: extraer (método HTTP, path, status_code) del texto del CP.
        Default: GET, /health, 200.
        """
        method = "GET"
        path = "/health"
        status = 200

        # Buscar verbo HTTP explícito
        m = re.search(r"\b(GET|POST|PUT|DELETE|PATCH)\b", text, re.IGNORECASE)
        if m:
            method = m.group(1).upper()

        # Buscar path tipo /api/...
        m = re.search(r"(/api/[^\s'\"\)`,;}]*)", text)
        if m:
            path = m.group(1).rstrip(".,;:")

        # Buscar status code esperado
        m = re.search(r"(?:status|código|code)\s*(?:esperado)?\s*[:=]?\s*(200|201|204|400|401|403|404|409|422|429|500)", text, re.IGNORECASE)
        if m:
            status = int(m.group(1))
        else:
            # Heurística por tipo de error mencionado
            text_lower = text.lower()
            if "rechaz" in text_lower or "invalido" in text_lower or "no v" in text_lower:
                status = 400
            elif "no autoriz" in text_lower or "sin permiso" in text_lower:
                status = 401
            elif "no encontrado" in text_lower or "no existe" in text_lower:
                status = 404
            elif "servidor" in text_lower or "cae" in text_lower:
                status = 500

        return method, path, status

    def _split_sections(self, content: str) -> Dict[str, str]:
        """Divide el documento en secciones por CP."""
        sections: Dict[str, str] = {}
        last_cp_id: Optional[str] = None
        last_pos = 0

        for m in self.CP_HEADER_RE.finditer(content):
            if last_cp_id:
                sections[last_cp_id] = content[last_pos:m.start()]
            last_cp_id = m.group(1)
            last_pos   = m.start()

        if last_cp_id:
            sections[last_cp_id] = content[last_pos:]

        return sections

    def _parse_section(self, cp_id: str, text: str) -> Optional[TestCase]:
        """Parsea una seccion individual de CP."""
        # Titulo desde el regex (ya extraído)
        title = None
        header_m = re.search(
            r"^##\s+" + re.escape(cp_id) + r"\s*[-—]\s*(.+)$",
            text, re.MULTILINE | re.IGNORECASE
        )
        if header_m:
            title = header_m.group(1).strip()

        # Campos
        fields: Dict[str, str] = {}
        for fm in self.FIELD_RE.finditer(text):
            key   = fm.group(1).strip()
            value = fm.group(2).strip()
            fields[key.lower()] = value

        epic            = fields.get("épica", "Unknown")
        hu              = fields.get("hu", fields.get("historia de usuario", "Unknown"))
        type_           = fields.get("tipo", "functional")
        method          = fields.get("método", fields.get("method", "GET")).upper()
        path            = fields.get("endpoint", fields.get("path", "/"))
        status_str      = fields.get("status esperado", fields.get("status", "200"))
        body_contains   = fields.get("body contiene", None)
        description     = fields.get("descripción", fields.get("descripcion", None))

        # Extraer numero de status
        status_m = re.search(r"\d+", status_str)
        expected_status = int(status_m.group()) if status_m else 200

        # Tags
        tags = []
        if "security" in type_.lower(): tags.append("security")
        if "negative" in type_.lower(): tags.append("negative")
        if "performance" in type_.lower(): tags.append("performance")
        tags.append(type_.lower())

        # Extraer hu_id (HU-XX → HU_XX)
        hu_id = ""
        m_hu = re.search(r"HU-?(\d+)", hu)
        if m_hu:
            hu_id = f"HU_{m_hu.group(1)}"

        return TestCase(
            id                   = cp_id,
            epic                 = self._clean_epic(epic),
            hu                   = hu,
            hu_id                = hu_id,
            title                = title or cp_id,
            type                 = type_.lower(),
            method               = method,
            path                 = path,
            expected_status      = expected_status,
            expected_body_contains = body_contains,
            description          = description,
            tags                 = tags,
        )

    def _clean_epic(self, epic: str) -> str:
        """Limpia el nombre de épica (Ej: 'E01 — Autenticación' -> 'E01')."""
        m = re.match(r"^(E\d+)", epic.strip())
        return m.group(1) if m else epic.strip()

    def _rebuild_indexes(self) -> None:
        """Construye los índices secundarios."""
        self._by_epic   = {}
        self._by_hu     = {}
        self._by_hu_id  = {}   # índice adicional por HU_XX
        self._by_type   = {}
        self._by_method = {}

        for cp in self._cps.values():
            self._by_epic.setdefault(cp.epic, []).append(cp)
            self._by_hu.setdefault(cp.hu, []).append(cp)
            if cp.hu_id:
                self._by_hu_id.setdefault(cp.hu_id, []).append(cp)
            self._by_type.setdefault(cp.type, []).append(cp)
            self._by_method.setdefault(cp.method, []).append(cp)

    def by_hu_id(self, hu_id: str) -> List[TestCase]:
        """Devuelve los CPs de una HU específica por su ID (ej: 'HU_03')."""
        return self._by_hu_id.get(hu_id, [])

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    def get(self, cp_id: str) -> Optional[TestCase]:
        return self._cps.get(cp_id)

    def by_epic(self, epic: str) -> List[TestCase]:
        return self._by_epic.get(epic, [])

    def by_hu(self, hu: str) -> List[TestCase]:
        return self._by_hu.get(hu, [])

    def by_type(self, type_: str) -> List[TestCase]:
        return self._by_type.get(type_, [])

    def all(self) -> List[TestCase]:
        return list(self._cps.values())

    def to_http_tests(self) -> List[Dict[str, Any]]:
        return [cp.to_http_test() for cp in self._cps.values()]

    def stats(self) -> Dict[str, Any]:
        return {
            "total":         len(self._cps),
            "by_epic":       {k: len(v) for k, v in self._by_epic.items()},
            "by_type":       {k: len(v) for k, v in self._by_type.items()},
            "by_method":     {k: len(v) for k, v in self._by_method.items()},
        }
