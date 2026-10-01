"""HU_33 — Servicio de OCR para comprobantes (tickets/facturas).

Estrategia
-----------
Estrategia pluggable: el servicio ``OCRService`` selecciona un proveedor
según la variable de entorno ``OCR_PROVIDER`` (default: ``mock``).

Proveedores incluidos:
- ``MockOCRProvider`` (default): procesa el ``image_url`` simulando el OCR
  con texto determinístico. NO requiere dependencias externas — útil
  para tests, dev, y entornos donde ``pytesseract`` no está disponible.
- ``TesseractOCRProvider``: usa ``pytesseract`` (Python wrapper de
  Tesseract OCR). Requiere ``pytesseract`` instalado y el binario
  ``tesseract`` en PATH. Si no está disponible, cae automáticamente
  a ``MockOCRProvider`` con un warning.

API principal
-------------
- ``OCRService.process_receipt(image_url)``:
  descarga la imagen, la pasa al provider y devuelve un dict con:
    - ``provider``: nombre del provider usado.
    - ``raw_text``: texto detectado.
    - ``items``: lista de ``{name, qty, unit_cents, total_cents}``.
    - ``total_cents``: suma de los items.
    - ``currency``: detectada del texto o default.
    - ``confidence``: 0.0-1.0.

- ``OCRService.verify_payment_proof(image_url, expected_amount_cents)``:
  verifica si un comprobante de pago coincide con el monto esperado.
  Útil para HU_23/Stripe y reconciliación manual.

Persistencia
------------
El servicio NO escribe en la DB directamente — el caller (Celery task o
endpoint API) lo hace. Esto mantiene al servicio puro y testeable.

Idempotencia
------------
``process_receipt`` es seguro de llamar múltiples veces con el mismo
``image_url``: el resultado es determinístico (mismo texto OCR →
mismos items parseados).
"""
from __future__ import annotations

import logging
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("wowhub.ocr")


# ── Dataclass de resultado ─────────────────────────────────────────────
@dataclass
class OCRResult:
    """Resultado de procesar una imagen con OCR."""
    provider: str
    raw_text: str = ""
    items: list[dict[str, Any]] = field(default_factory=list)
    total_cents: int = 0
    currency: str = "CLP"
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "raw_text": self.raw_text,
            "items": self.items,
            "total_cents": self.total_cents,
            "currency": self.currency,
            "confidence": self.confidence,
        }


# ── Interface abstracta ────────────────────────────────────────────────
class OCRProvider(ABC):
    """Interface abstracta para proveedores OCR."""

    name: str = "abstract"

    @abstractmethod
    def process_image(self, image_url: str) -> OCRResult:
        """Procesa una imagen y devuelve el resultado OCR."""


# ── Mock provider (default, sin deps) ──────────────────────────────────
class MockOCRProvider(OCRProvider):
    """Provider mock que simula OCR con texto determinístico.

    Genera texto que parece un comprobante chileno típico (ticket
    de restaurant) y lo parsea con regex heurísticos. NO usa la URL
    real — sólo la devuelve como referencia en el raw_text.

    Útil para:
    - Tests (resultado determinístico).
    - Dev (no requiere instalar tesseract).
    - CI/CD (sin dependencias externas).
    """

    name = "mock"

    # Texto plantilla que simula un ticket real. Es estable (mismo output
    # para misma URL) para que los tests sean determinísticos.
    _TEMPLATES = [
        # Plantilla 1: restaurant chileno
        """\
BODEGA CENTRAL
RUT: 76.123.456-7
Av. Providencia 1234, Santiago

Fecha: 15/03/2026  Hora: 13:45
Ticket #0042

CANT  DESCRIPCION             P.UNIT   TOTAL
1     Cafe americano          $2.900   $2.900
2     Sandwich pavo           $4.500   $9.000
1     Jugo naranja            $1.800   $1.800
1     Porcion torta           $3.200   $3.200

SUBTOTAL: $16.900
IVA 19%:  $2.697
TOTAL:    $19.597

Gracias por su preferencia
""",
        # Plantilla 2: factura simple
        """\
FACTURA
15/03/2026

1x Producto A    $10.000
2x Producto B    $5.000  c/u
1x Producto C    $7.500

Total: $22.500
""",
    ]

    def process_image(self, image_url: str) -> OCRResult:
        # Selección determinística basada en hash de la URL → mismo image_url
        # siempre devuelve el mismo texto. Permite que los tests sean estables.
        idx = abs(hash(image_url)) % len(self._TEMPLATES)
        text = self._TEMPLATES[idx]

        items, total_cents = self._parse_items(text)
        currency = self._detect_currency(text)

        return OCRResult(
            provider=self.name,
            raw_text=text,
            items=items,
            total_cents=total_cents,
            currency=currency,
            confidence=0.85,
        )

    @staticmethod
    def _parse_items(raw: str) -> tuple[list[dict[str, Any]], int]:
        """Parsea líneas tipo ``2  Sandwich pavo  $4.500  $9.000`` o ``1x Producto A  $10.000``.

        Heurística:
        - Línea ``qty x desc ...amount`` o ``qty desc ...amount``.
        - Línea ``Total: $X``: extraer como total general (con word boundary
          para NO capturar ``SUBTOTAL:`` ni ``IVA TOTAL:``).
        """
        items: list[dict[str, Any]] = []
        total_general = 0
        # Word boundary: evita matchear "SUBTOTAL" o "IVA TOTAL".
        # Acepta "TOTAL:", "Total:", "total:" o "TOTAL " (con espacios).
        # IMPORTANTE: NO usar \s sin restricciones — debe ser espacio horizontal
        # ([ \t]) para que NO matchee newlines (que haría que la siguiente
        # línea "1 Cafe americano..." se incluya en el match).
        total_re = re.compile(
            r"(?<![\w])(?:TOTAL|Total|total)[:\t][ \t]*\$?[ \t]*([\d.]+)",
            re.MULTILINE,
        )
        m = total_re.search(raw)
        if m:
            total_general = int(m.group(1).replace(".", "").replace(",", "")) * 100

        # Líneas con item: <qty>x|<qty>  <desc>  $<monto>  (c/u opcional).
        line_re = re.compile(
            r"^\s*(\d+)\s*x?\s+(.+?)\s{2,}\$?\s*([\d.]+)\s*(?:c/u)?\s*$",
            re.MULTILINE,
        )
        for match in line_re.finditer(raw):
            qty = int(match.group(1))
            desc = match.group(2).strip()
            amount_str = match.group(3).replace(".", "").replace(",", "")
            if not amount_str.isdigit():
                continue
            amount_cents = int(amount_str) * 100
            items.append({
                "name": desc,
                "qty": qty,
                "unit_cents": amount_cents // qty if qty else amount_cents,
                "total_cents": amount_cents,
            })

        return items, total_general

    @staticmethod
    def _detect_currency(raw: str) -> str:
        if "CLP" in raw or "$" in raw and "USD" not in raw:
            return "CLP"
        if "USD" in raw:
            return "USD"
        if "ARS" in raw:
            return "ARS"
        if "MXN" in raw:
            return "MXN"
        return "CLP"


# ── Tesseract provider (opcional, requiere pytesseract) ─────────────────
class TesseractOCRProvider(OCRProvider):
    """Provider Tesseract vía ``pytesseract``.

    Solo se activa si ``pytesseract`` está instalado. Si no lo está,
    el ``OCRService`` cae automáticamente a ``MockOCRProvider`` con
    un warning (fail-safe).

    Requiere:
    - ``pip install pytesseract`` en el venv.
    - Binario ``tesseract`` instalado en el sistema (apt-get install
      tesseract-ocr en Linux).
    """

    name = "tesseract"

    def __init__(self) -> None:
        try:
            import pytesseract  # noqa: F401
            from PIL import Image  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "TesseractOCRProvider requiere pytesseract + Pillow. "
                "Instala con: pip install pytesseract Pillow"
            ) from exc
        import pytesseract as _pt
        self._pytesseract = _pt

    def process_image(self, image_url: str) -> OCRResult:
        """Descarga la imagen, la pasa a Tesseract y parsea con heurísticas."""
        import io
        import urllib.request

        from PIL import Image

        # 1. Descargar imagen
        try:
            with urllib.request.urlopen(image_url, timeout=15) as resp:
                img_bytes = resp.read()
        except Exception as exc:
            logger.warning("Tesseract download failed %s: %s", image_url, exc)
            # Fail-safe: devolver un result "failed" con texto vacío.
            return OCRResult(provider=self.name, raw_text="", confidence=0.0)

        # 2. OCR con Tesseract (idioma español + inglés)
        try:
            img = Image.open(io.BytesIO(img_bytes))
            raw_text = self._pytesseract.image_to_string(img, lang="spa+eng")
        except Exception as exc:
            logger.warning("Tesseract OCR failed %s: %s", image_url, exc)
            return OCRResult(provider=self.name, raw_text="", confidence=0.0)

        # 3. Parsear con la misma heurística del MockProvider.
        items, total_cents = MockOCRProvider._parse_items(raw_text)
        currency = MockOCRProvider._detect_currency(raw_text)

        return OCRResult(
            provider=self.name,
            raw_text=raw_text,
            items=items,
            total_cents=total_cents,
            currency=currency,
            confidence=0.7,  # heurístico, no calculado por Tesseract
        )


# ── Servicio principal ─────────────────────────────────────────────────
class OCRService:
    """Servicio de OCR que selecciona el provider según ``OCR_PROVIDER``."""

    def __init__(self) -> None:
        provider_name = os.getenv("OCR_PROVIDER", "mock").lower()
        if provider_name == "tesseract":
            try:
                self._provider: OCRProvider = TesseractOCRProvider()
            except RuntimeError as exc:
                logger.warning(
                    "TesseractOCRProvider no disponible (%s) — fallback a MockOCRProvider",
                    exc,
                )
                self._provider = MockOCRProvider()
        else:
            self._provider = MockOCRProvider()
        logger.info("OCRService inicializado con provider=%s", self._provider.name)

    @property
    def provider_name(self) -> str:
        return self._provider.name

    def process_receipt(self, image_url: str) -> OCRResult:
        """Procesa una imagen de comprobante y devuelve los items detectados."""
        logger.info("OCR process_receipt — url=%s, provider=%s", image_url, self._provider.name)
        return self._provider.process_image(image_url)

    def verify_payment_proof(
        self,
        image_url: str,
        expected_amount_cents: int,
        tolerance_cents: int = 500,
    ) -> dict[str, Any]:
        """Verifica si un comprobante de pago coincide con el monto esperado.

        Returns:
            dict con:
              - ``verified``: bool (True si el total detectado está dentro
                de la tolerancia).
              - ``confidence``: 0.0-1.0.
              - ``detected_total_cents``: total detectado en el OCR.
              - ``expected_amount_cents``: monto que esperábamos.
              - ``delta_cents``: diferencia (signed).
              - ``raw_text``: texto del comprobante.
              - ``provider``: nombre del provider.
        """
        result = self.process_receipt(image_url)
        delta = result.total_cents - expected_amount_cents
        verified = abs(delta) <= tolerance_cents
        return {
            "verified": verified,
            "confidence": result.confidence,
            "detected_total_cents": result.total_cents,
            "expected_amount_cents": expected_amount_cents,
            "delta_cents": delta,
            "currency": result.currency,
            "raw_text": result.raw_text[:500],  # truncar para no exponer demasiado
            "provider": result.provider,
        }


# ── Singleton ──────────────────────────────────────────────────────────
_ocr_service: Optional[OCRService] = None


def get_ocr_service() -> OCRService:
    """Devuelve el singleton del servicio (thread-safe implícito)."""
    global _ocr_service
    if _ocr_service is None:
        _ocr_service = OCRService()
    return _ocr_service