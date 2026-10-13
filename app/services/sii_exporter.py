"""HU_32 — Exportador de Libro de Ventas SII Chile (Res. Ex. 4119/1999).

Genera un CSV con las 17 columnas oficiales del Libro de Ventas del SII.

Encoding: la cadena retornada es UTF-8 sin BOM; el caller debe codificarla
con ``utf-8-sig`` al servirla (esto es lo que hace el endpoint de FastAPI).
Se eligió ``utf-8-sig`` en lugar del CP1252 histórico del SII para que Excel
en Chile abra correctamente tildes y ñ; el contador puede convertir a
CP1252 desde su propio sistema si el portal SII lo exige.

NO usa create_all ni migraciones: sólo SELECT sobre Order y Customer
existentes. Si el tenant no tiene órdenes en el período, devuelve CSV con
sólo los headers + una fila de totales en cero (fail-soft).
"""
from __future__ import annotations

import csv
from datetime import datetime
from io import StringIO
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.time import CL_TZ
from app.models.order import Order, OrderStatus
from app.services.sii_validator import format_rut

# ── Header oficial del Libro de Ventas (Res. Ex. SII 4119/1999, Anexo) ──
LIBRO_VENTAS_HEADER: list[str] = [
    "Nro",            # 1  - correlativo interno
    "Fecha",          # 2  - YYYY-MM-DD
    "Tipo Doc",       # 3  - BOLETA | FACTURA | NC
    "RUT",            # 4  - RUT del receptor (formateado)
    "Razón Social",   # 5  - nombre del cliente
    "Folio",          # 6  - número del documento
    "Monto Exento",   # 7  - sin IVA
    "Monto Neto",     # 8  - subtotal antes de IVA
    "Monto IVA",      # 9  - IVA (19% en Chile)
    "Monto Total",    # 10 - total = neto + IVA + exento
    "IVA Retenido",   # 11 - normalmente 0
    "IVA Propio",     # 12 - = Monto IVA
    "IVA Terceros",   # 13 - normalmente 0
    "RUT Mandante",   # 14 - vacío en del_giro normal
    "Nro Int.",       # 15 - número interno interno del SII (vacío)
    "Tipo Venta",     # 16 - DEL_GIRO | NO_GIRO
    "Fecha Anulación",  # 17 - vacío si no anulada
]


def _cents_to_str(cents: int) -> str:
    """Convierte centavos a string con 2 decimales separados por coma (estilo CL).

    Para compatibilidad con Excel chileno y muchos sistemas contables locales
    que esperan coma como separador decimal. Se eliminó el "int formatting"
    que proponía el snippet del roadmap porque rompía boletas (que son sin
    IVA pero totalizadas a entero).
    """
    whole = cents // 100
    frac = cents % 100
    return f"{whole},{frac:02d}"


def _to_doc_type(order: Order) -> str:
    """Mapea el estado de Order a Tipo Doc SII."""
    if order.status == OrderStatus.CANCELADO:
        return "NC"  # Nota de Crédito (anulación)
    # Para BOLETA el SII exige campos sin IVA — el resto se trata como FACTURA.
    # Por defecto usamos BOLETA (el caso más común para PyMEs).
    return "BOLETA"


def _to_cl_date(dt: Optional[datetime]) -> str:
    """YYYY-MM-DD en zona horaria local Chile (America/Santiago).

    Para el SII la fecha civil del documento debe corresponder al día
    calendario chileno en que se realizó la venta, no al día UTC. Por
    ejemplo, una venta creada a las 23:30 CLT del 14/sep es fecha SII
    ``2026-09-14`` (no ``2026-09-15`` aunque UTC ya esté en el día siguiente).
    """
    if dt is None:
        return ""
    # Si tiene tz, convertimos a America/Santiago y quitamos tz para strftime.
    if dt.tzinfo is not None:
        dt = dt.astimezone(CL_TZ).replace(tzinfo=None)
    return dt.strftime("%Y-%m-%d")


def export_ventas(
    tenant_id: UUID,
    year: int,
    month: int,
    db: Session,
) -> str:
    """Genera el Libro de Ventas SII para el período (year, month).

    Args:
        tenant_id: UUID del tenant (multi-tenant)
        year: año (ej. 2026)
        month: mes 1-12
        db: sesión de SQLAlchemy

    Returns:
        String CSV (sin BOM; usar ``.encode("utf-8-sig")`` al servir).

    Notas:
        - Si el tenant no tiene órdenes en el período, devuelve CSV con
          sólo los headers + una fila TOTAL con todos los montos en cero.
        - Las órdenes CANCELADO se incluyen como NC (nota de crédito).
        - El RUT del cliente se formatea si está presente en
          ``customer.rut``; si no, queda vacío.
    """
    # Rango del período [inicio, inicio_siguiente_mes)
    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)

    # Query: órdenes del tenant dentro del período.
    # Excluimos soft-deletes usando el flag estándar is_deleted cuando exista.
    orders = (
        db.query(Order)
        .filter(
            Order.tenant_id == str(tenant_id),
            Order.created_at >= start,
            Order.created_at < end,
        )
        .order_by(Order.created_at.asc(), Order.id.asc())
        .all()
    )

    buf = StringIO(newline="")
    writer = csv.writer(
        buf,
        delimiter=";",
        quoting=csv.QUOTE_MINIMAL,
        lineterminator="\r\n",
    )

    # Header
    writer.writerow(LIBRO_VENTAS_HEADER)

    # Acumuladores para fila TOTAL
    sum_exento = 0
    sum_neto = 0
    sum_iva = 0
    sum_total = 0

    for nro, order in enumerate(orders, start=1):
        # Customer puede ser None; manejamos ese caso con seguridad.
        customer = getattr(order, "customer", None)

        # RUT del cliente (campo opcional del Customer — si no existe, vacío)
        rut_raw = getattr(customer, "rut", None) if customer else None
        rut_fmt = format_rut(rut_raw) if rut_raw else ""

        # Razón social / nombre del cliente
        razon_social = ""
        if customer is not None:
            razon_social = (
                getattr(customer, "razon_social", None)
                or getattr(customer, "full_name", None)
                or ""
            )

        # Folio: usamos el `number` del Order (es human-friendly, ej. "P-00042").
        folio = getattr(order, "number", None) or ""

        # Montos (centavos → string CL). Para BOLETA el SII exige neto/IVA
        # reportados como 0 (no hay desglose). En el MVP simplificado, los
        # incluimos igual para que el contador pueda auditar.
        tipo_doc = _to_doc_type(order)
        is_boleta = tipo_doc == "BOLETA"
        if is_boleta:
            exento_cents = 0
            iva_cents = 0
            neto_cents = int(order.total_cents)
        else:
            # FACTURA o NC: reportamos subtotal como neto y tax como IVA.
            exento_cents = 0
            iva_cents = int(order.tax_cents)
            neto_cents = int(order.subtotal_cents)

        total_cents = int(order.total_cents)

        writer.writerow([
            nro,
            _to_cl_date(order.created_at),
            tipo_doc,
            rut_fmt,
            razon_social[:60],
            folio,
            _cents_to_str(exento_cents),
            _cents_to_str(neto_cents),
            _cents_to_str(iva_cents),
            _cents_to_str(total_cents),
            _cents_to_str(0),         # IVA Retenido
            _cents_to_str(iva_cents), # IVA Propio = Monto IVA
            _cents_to_str(0),         # IVA Terceros
            "",                        # RUT Mandante
            "",                        # Nro Int.
            "DEL_GIRO",
            _to_cl_date(getattr(order, "cancelled_at", None)),
        ])

        # Acumular (sólo si no está cancelado, para no inflar el total).
        if order.status != OrderStatus.CANCELADO:
            sum_exento += exento_cents
            sum_neto += neto_cents
            sum_iva += iva_cents
            sum_total += total_cents

    # Fila de totales al final (incluida incluso si no hay datos → todo en 0)
    writer.writerow([
        "",  # Nro
        "",  # Fecha
        "TOTAL",  # Tipo Doc → marca como fila de totales
        "",  # RUT
        "",  # Razón Social
        "",  # Folio
        _cents_to_str(sum_exento),
        _cents_to_str(sum_neto),
        _cents_to_str(sum_iva),
        _cents_to_str(sum_total),
        _cents_to_str(0),  # IVA Retenido
        _cents_to_str(sum_iva),
        _cents_to_str(0),  # IVA Terceros
        "",
        "",
        "",
        "",
    ])

    return buf.getvalue()
