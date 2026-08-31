"""Unit tests for server/auth/email.py: email message construction and the
SMTP / logging delivery backends (design doc §7.1.1, §7.1.11, §3, Phase 3)."""

import logging
from unittest.mock import AsyncMock, patch

import pytest

from server.auth.email import (
    EmailMessage,
    LoggingEmailSender,
    SmtpEmailSender,
    build_account_locked_email,
    build_password_reset_email,
    build_verification_email,
    build_welcome_email,
)


class TestEmailTemplates:
    def test_verification_email_contains_the_token_and_base_url(self):
        message = build_verification_email(to="a@example.com", token="tok123", base_url="https://app.example.com")
        assert message.to == "a@example.com"
        assert "tok123" in message.text_body
        assert "https://app.example.com" in message.text_body

    def test_password_reset_email_contains_the_token_and_base_url(self):
        message = build_password_reset_email(to="a@example.com", token="tok456", base_url="https://app.example.com")
        assert "tok456" in message.text_body
        assert "https://app.example.com" in message.text_body

    def test_welcome_email_contains_the_temporary_password(self):
        message = build_welcome_email(
            to="a@example.com", display_name="Alice", temporary_password="Sup3rSecr3t!",
            base_url="https://app.example.com",
        )
        assert "Sup3rSecr3t!" in message.text_body
        assert "Alice" in message.text_body

    def test_account_locked_email_mentions_the_lockout_window(self):
        message = build_account_locked_email(to="a@example.com", lockout_minutes=15)
        assert message.to == "a@example.com"
        assert "15" in message.text_body
        assert "locked" in message.subject.lower()


class TestLoggingEmailSender:
    async def test_logs_a_warning_instead_of_sending(self, caplog):
        sender = LoggingEmailSender()
        message = EmailMessage(to="a@example.com", subject="Subject", text_body="Body with a link")
        with caplog.at_level(logging.WARNING):
            await sender.send(message)
        assert any("a@example.com" in record.message for record in caplog.records)


class TestSmtpEmailSender:
    async def test_send_calls_aiosmtplib_with_the_right_envelope(self):
        sender = SmtpEmailSender(
            host="smtp.example.com", port=587, username="user", password="pass",
            use_tls=True, from_address="no-reply@example.com",
        )
        message = EmailMessage(to="a@example.com", subject="Hi", text_body="Body")

        with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
            await sender.send(message)

        assert mock_send.await_count == 1
        _, kwargs = mock_send.call_args
        assert kwargs["hostname"] == "smtp.example.com"
        assert kwargs["port"] == 587
        assert kwargs["username"] == "user"
        assert kwargs["password"] == "pass"
        sent_mime = mock_send.call_args.args[0]
        assert sent_mime["To"] == "a@example.com"
        assert sent_mime["From"] == "no-reply@example.com"
        assert sent_mime["Subject"] == "Hi"

    async def test_send_propagates_smtp_errors(self):
        sender = SmtpEmailSender(
            host="smtp.example.com", port=587, username=None, password=None,
            use_tls=True, from_address="no-reply@example.com",
        )
        message = EmailMessage(to="a@example.com", subject="Hi", text_body="Body")

        with patch("aiosmtplib.send", new_callable=AsyncMock, side_effect=RuntimeError("smtp down")):
            with pytest.raises(RuntimeError):
                await sender.send(message)
