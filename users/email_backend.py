"""Enviar el correo transaccional de Django mediante la API de Brevo."""

from email.utils import parseaddr

import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend


class BrevoEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        sent = 0
        for message in email_messages or ():
            if not message.to:
                continue

            sender_name, sender_email = parseaddr(message.from_email)
            sender = {"email": sender_email}
            if sender_name:
                sender["name"] = sender_name

            payload = {
                "sender": sender,
                "to": [{"email": address} for address in message.to],
                "subject": message.subject,
                "textContent": message.body,
            }
            try:
                response = requests.post(
                    "https://api.brevo.com/v3/smtp/email",
                    headers={"api-key": settings.BREVO_API_KEY},
                    json=payload,
                    timeout=10,
                    allow_redirects=False,
                )
            except requests.RequestException:
                if not self.fail_silently:
                    raise RuntimeError("No se pudo conectar con la API de Brevo.") from None
                continue

            if response.status_code != 201:
                if not self.fail_silently:
                    raise RuntimeError(f"Brevo rechazó el envío (HTTP {response.status_code}).")
                continue
            sent += 1
        return sent
