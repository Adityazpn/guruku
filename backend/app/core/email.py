import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

from app.core.config import get_settings


@dataclass
class Mail:
    to: str
    subject: str
    body: str


# Dev/test sink. In production SMTP is used when SMTP_HOST is set.
outbox: list[Mail] = []


def send_email(to: str, subject: str, body: str) -> None:
    s = get_settings()
    if not s.smtp_host:
        outbox.append(Mail(to, subject, body))
        return
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s.mail_from, to, subject
    msg.set_content(body)
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
        smtp.starttls()
        if s.smtp_user:
            smtp.login(s.smtp_user, s.smtp_password)
        smtp.send_message(msg)
