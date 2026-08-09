"""EmailService — envío de emails transaccionales.

Soporta múltiples backends:
- "resend" (default en producción): vía API REST de Resend
- "smtp": servidor SMTP genérico (Gmail, SendGrid, Mailgun)
- "log": solo loguea a stdout (para dev/tests)
- "console": imprime el HTML del email (dev)
"""
import logging
import os
import smtplib
from abc import ABC, abstractmethod
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger("wowhub.email")


class EmailBackend(ABC):
    @abstractmethod
    def send(self, *, to: str, subject: str, html: str, text: Optional[str] = None,
             from_addr: Optional[str] = None, from_name: Optional[str] = None) -> bool: ...


class ResendBackend(EmailBackend):
    """Backend vía API REST de Resend (https://resend.com)."""
    def __init__(self, api_key: str, from_addr: str, from_name: str = "WowHub"):
        self.api_key = api_key
        self.from_addr = from_addr
        self.from_name = from_name

    def send(self, *, to: str, subject: str, html: str, text: Optional[str] = None,
             from_addr: Optional[str] = None, from_name: Optional[str] = None) -> bool:
        try:
            payload = {
                "from": f"{from_name or self.from_name} <{from_addr or self.from_addr}>",
                "to": [to],
                "subject": subject,
                "html": html,
            }
            if text:
                payload["text"] = text
            resp = httpx.post(
                "https://api.resend.com/emails",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10.0,
            )
            if resp.status_code in (200, 201, 202):
                logger.info("Email enviado a %s via Resend (status=%s)", to, resp.status_code)
                return True
            logger.error("Resend error %s: %s", resp.status_code, resp.text)
            return False
        except Exception as e:
            logger.exception("Error enviando email a %s via Resend: %s", to, e)
            return False


class SMTPBackend(EmailBackend):
    """Backend SMTP genérico (Gmail, SendGrid, Mailgun, etc)."""
    def __init__(self, host: str, port: int, username: str, password: str,
                 from_addr: str, from_name: str = "WowHub", use_tls: bool = True):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.from_addr = from_addr
        self.from_name = from_name
        self.use_tls = use_tls

    def send(self, *, to: str, subject: str, html: str, text: Optional[str] = None,
             from_addr: Optional[str] = None, from_name: Optional[str] = None) -> bool:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{from_name or self.from_name} <{from_addr or self.from_addr}>"
            msg["To"] = to
            if text:
                msg.attach(MIMEText(text, "plain"))
            msg.attach(MIMEText(html, "html"))

            with smtplib.SMTP(self.host, self.port, timeout=10) as server:
                if self.use_tls:
                    server.starttls()
                server.login(self.username, self.password)
                server.sendmail(self.from_addr, to, msg.as_string())
            logger.info("Email enviado a %s via SMTP", to)
            return True
        except Exception as e:
            logger.exception("Error SMTP a %s: %s", to, e)
            return False


class LogBackend(EmailBackend):
    """Backend que solo loguea (para dev y tests)."""
    def send(self, *, to: str, subject: str, html: str, text: Optional[str] = None,
             from_addr: Optional[str] = None, from_name: Optional[str] = None) -> bool:
        logger.info("[EMAIL-LOG] to=%s subject=%s body_len=%d", to, subject, len(html))
        return True


class ConsoleBackend(EmailBackend):
    """Backend que imprime el HTML completo (para desarrollo)."""
    def send(self, *, to: str, subject: str, html: str, text: Optional[str] = None,
             from_addr: Optional[str] = None, from_name: Optional[str] = None) -> bool:
        print(f"\n{'='*60}\nEMAIL → {to}\nSUBJECT: {subject}\n{'='*60}\n{html}\n{'='*60}\n")
        return True


class EmailService:
    """Facade para envío de emails. Selecciona backend según config."""

    def __init__(self):
        self.backend: EmailBackend = self._build_backend()
        self.from_addr: str = os.getenv("EMAIL_FROM", "no-reply@wowhub.app")
        self.from_name: str = os.getenv("EMAIL_FROM_NAME", "WowHub")

    def _build_backend(self) -> EmailBackend:
        backend_type = os.getenv("EMAIL_BACKEND", "log").lower()
        if backend_type == "resend":
            api_key = os.getenv("RESEND_API_KEY", "")
            if not api_key:
                logger.warning("RESEND_API_KEY no configurada — fallback a LogBackend")
                return LogBackend()
            return ResendBackend(api_key=api_key, from_addr=self.from_addr, from_name=self.from_name)
        if backend_type == "smtp":
            return SMTPBackend(
                host=os.getenv("SMTP_HOST", "smtp.gmail.com"),
                port=int(os.getenv("SMTP_PORT", "587")),
                username=os.getenv("SMTP_USERNAME", ""),
                password=os.getenv("SMTP_PASSWORD", ""),
                from_addr=self.from_addr,
                from_name=self.from_name,
                use_tls=os.getenv("SMTP_USE_TLS", "true").lower() == "true",
            )
        if backend_type == "console":
            return ConsoleBackend()
        return LogBackend()

    def send(self, *, to: str, subject: str, html: str, text: Optional[str] = None) -> bool:
        return self.backend.send(
            to=to, subject=subject, html=html, text=text,
            from_addr=self.from_addr, from_name=self.from_name,
        )

    # ── Templates pre-armados ────────────────────────────
    def send_welcome(self, to: str, full_name: str, verification_url: Optional[str] = None) -> bool:
        html = f"""
        <div style="font-family:sans-serif;max-width:600px;margin:auto;padding:20px">
            <h1 style="color:#7c5cff">¡Bienvenido a WowHub, {full_name}!</h1>
            <p>Tu cuenta está activa y lista para usar.</p>
            {"<p><a href='" + verification_url + "' style='background:#7c5cff;color:white;padding:12px 24px;border-radius:6px;text-decoration:none'>Verificar mi email</a></p>" if verification_url else ""}
            <p>Saludos,<br>El equipo de WowHub</p>
        </div>"""
        return self.send(to=to, subject="Bienvenido a WowHub", html=html)

    def send_password_reset(self, to: str, reset_url: str) -> bool:
        html = f"""
        <div style="font-family:sans-serif;max-width:600px;margin:auto;padding:20px">
            <h2 style="color:#7c5cff">Recuperación de contraseña</h2>
            <p>Recibimos una solicitud para restablecer tu contraseña.</p>
            <p>Si no fuiste tú, ignora este email.</p>
            <p><a href="{reset_url}" style="background:#7c5cff;color:white;padding:12px 24px;border-radius:6px;text-decoration:none">Restablecer contraseña</a></p>
            <p style="color:#888;font-size:12px">Este enlace expira en 1 hora.</p>
        </div>"""
        return self.send(to=to, subject="Recupera tu contraseña — WowHub", html=html)

    def send_order_confirmation(self, to: str, order_number: str, total: str, currency: str) -> bool:
        html = f"""
        <div style="font-family:sans-serif;max-width:600px;margin:auto;padding:20px">
            <h2 style="color:#7c5cff">¡Pedido confirmado!</h2>
            <p>Tu pedido <strong>{order_number}</strong> ha sido recibido.</p>
            <p>Total: <strong>{currency} {total}</strong></p>
            <p>Te notificaremos cuando esté en preparación.</p>
        </div>"""
        return self.send(to=to, subject=f"Pedido {order_number} confirmado", html=html)

    def send_order_paid(self, to: str, order_number: str, total: str, currency: str) -> bool:
        html = f"""
        <div style="font-family:sans-serif;max-width:600px;margin:auto;padding:20px">
            <h2 style="color:#00d4a8">Pago recibido</h2>
            <p>Recibimos el pago de tu pedido <strong>{order_number}</strong> por <strong>{currency} {total}</strong>.</p>
        </div>"""
        return self.send(to=to, subject=f"Pago confirmado — pedido {order_number}", html=html)

    def send_booking_confirmation(self, to: str, booking_id: str, when: str, where: str) -> bool:
        html = f"""
        <div style="font-family:sans-serif;max-width:600px;margin:auto;padding:20px">
            <h2 style="color:#7c5cff">Reserva confirmada</h2>
            <p>Tu reserva <strong>#{booking_id}</strong> está confirmada para:</p>
            <p><strong>{when}</strong> en {where}</p>
        </div>"""
        return self.send(to=to, subject=f"Reserva #{booking_id} confirmada", html=html)


# Singleton
email_service = EmailService()
