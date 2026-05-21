import os
import smtplib
from email.message import EmailMessage
from urllib.parse import urlencode


PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://127.0.0.1:8010").rstrip("/")
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.environ.get("SMTP_FROM_EMAIL", "support@chargebackcopilot.local")
SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "true").lower() in {"1", "true", "yes"}


def email_delivery_configured() -> bool:
    return bool(SMTP_HOST and SMTP_FROM_EMAIL)


def email_health() -> dict[str, object]:
    return {
        "ok": True,
        "configured": email_delivery_configured(),
        "host": SMTP_HOST or "not_configured",
        "from_email": SMTP_FROM_EMAIL if email_delivery_configured() else "not_configured",
    }


def auth_link(path: str, token: str) -> str:
    return f"{PUBLIC_BASE_URL}/?{urlencode({path: token})}#authPanel"


def send_email(to_email: str, subject: str, body: str) -> bool:
    if not email_delivery_configured():
        return False
    message = EmailMessage()
    message["From"] = SMTP_FROM_EMAIL
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as smtp:
        if SMTP_USE_TLS:
            smtp.starttls()
        if SMTP_USERNAME:
            smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
        smtp.send_message(message)
    return True


def send_verification_email(to_email: str, token: str) -> bool:
    link = auth_link("verify_email_token", token)
    return send_email(
        to_email,
        "Verify your Chargeback Copilot email",
        f"Open this link to verify your Chargeback Copilot email:\n\n{link}\n\nIf you did not create an account, ignore this email.",
    )


def send_password_reset_email(to_email: str, token: str) -> bool:
    link = auth_link("reset_password_token", token)
    return send_email(
        to_email,
        "Reset your Chargeback Copilot password",
        f"Open this link to reset your Chargeback Copilot password:\n\n{link}\n\nIf you did not request this, ignore this email.",
    )


def send_test_email(to_email: str) -> bool:
    return send_email(
        to_email,
        "Chargeback Copilot email test",
        "This is a test email from Chargeback Copilot. If you received it, SMTP delivery is configured correctly.",
    )
