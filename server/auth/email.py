"""Email delivery for auth flows: verification, password reset, and admin
welcome emails (design doc §7.1.1, §7.1.11, §3, Phase 3, §20 dependencies).

Raw tokens are only ever exposed here, inside an outbound email body -- the
HTTP layer (server/auth/routes.py) never returns them in a response, so a
compromised API client can't fish a live reset/verification token out of
its own request/response cycle.
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class EmailMessage:
    to: str
    subject: str
    text_body: str
    html_body: str | None = None


class EmailSender:
    """Base interface; server/main.py picks a concrete implementation based
    on whether SMTP is configured (design doc §5.2's SMTP_* env vars)."""

    async def send(self, message: EmailMessage) -> None:
        raise NotImplementedError


class LoggingEmailSender(EmailSender):
    """Fallback used when no SMTP server is configured. Logs the message
    instead of delivering it, so verification/reset links stay reachable
    during local development without a real mail provider. This is a
    deliberate dev-mode-only tradeoff: never used when SMTP_SERVER is set."""

    async def send(self, message: EmailMessage) -> None:
        logger.warning(
            "EMAIL NOT SENT (no SMTP server configured) -- to=%s subject=%r\n%s",
            message.to, message.subject, message.text_body,
        )


class SmtpEmailSender(EmailSender):
    def __init__(
        self, *, host: str, port: int, username: str | None, password: str | None,
        use_tls: bool, from_address: str,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._use_tls = use_tls
        self._from_address = from_address

    async def send(self, message: EmailMessage) -> None:
        import aiosmtplib
        from email.message import EmailMessage as MimeMessage

        mime = MimeMessage()
        mime["From"] = self._from_address
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime.set_content(message.text_body)
        if message.html_body:
            mime.add_alternative(message.html_body, subtype="html")

        await aiosmtplib.send(
            mime, hostname=self._host, port=self._port,
            username=self._username, password=self._password, start_tls=self._use_tls,
        )


def build_verification_email(*, to: str, token: str, base_url: str) -> EmailMessage:
    link = f"{base_url}/verify-email?token={token}"
    return EmailMessage(
        to=to,
        subject="Verify your OmniLaunge email address",
        text_body=(
            "Welcome to OmniLaunge!\n\n"
            f"Please verify your email address by visiting:\n{link}\n\n"
            "This link expires in 24 hours. If you didn't create this account, "
            "you can safely ignore this email."
        ),
    )


def build_password_reset_email(*, to: str, token: str, base_url: str) -> EmailMessage:
    link = f"{base_url}/reset-password?token={token}"
    return EmailMessage(
        to=to,
        subject="Reset your OmniLaunge password",
        text_body=(
            "We received a request to reset your OmniLaunge password.\n\n"
            f"Reset your password by visiting:\n{link}\n\n"
            "This link expires in 24 hours. If you didn't request this, you can "
            "safely ignore this email -- your password will not be changed."
        ),
    )


def build_welcome_email(*, to: str, display_name: str, temporary_password: str, base_url: str) -> EmailMessage:
    return EmailMessage(
        to=to,
        subject="Your OmniLaunge account has been created",
        text_body=(
            f"Hi {display_name},\n\n"
            "An administrator has created an OmniLaunge account for you.\n\n"
            f"Email: {to}\nTemporary password: {temporary_password}\n\n"
            f"Log in at {base_url} -- you will be asked to set a new password."
        ),
    )


def build_account_locked_email(*, to: str, lockout_minutes: int) -> EmailMessage:
    return EmailMessage(
        to=to,
        subject="Your OmniLaunge account was temporarily locked",
        text_body=(
            "We locked your OmniLaunge account after several failed sign-in "
            f"attempts. It will automatically unlock in about {lockout_minutes} "
            "minutes, or an administrator can unlock it sooner.\n\n"
            "If this wasn't you, consider changing your password once you're "
            "back in. If it was you and you just mistyped your password, "
            "you don't need to do anything else -- just try again shortly."
        ),
    )
