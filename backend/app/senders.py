"""Delivery channels behind the notification outbox (S6-B-3). Each sender is a small class so tests can inject a fake.
Without configuration both channels are console/log senders (the default in development and tests)."""
import logging
import smtplib
from collections.abc import Callable
from email.message import EmailMessage
from typing import Any, Protocol

import httpx

from app.config import PRODUCTION_ENVS, settings

log = logging.getLogger("app.senders")
FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"


class PermanentFailure(Exception):
    """The message can never be delivered (unregistered device, malformed address): do not retry."""


class PushSender(Protocol):
    def send(self, token: str, title: str, body: str, data: dict[str, str]) -> None: ...


class EmailSender(Protocol):
    def send(self, to: str, subject: str, body: str) -> None: ...


class ConsolePushSender:
    def send(self, token: str, title: str, body: str, data: dict[str, str]) -> None:
        log.info("push to %s...: %s | %s", token[:8], title, body)


class ConsoleEmailSender:
    def send(self, to: str, subject: str, body: str) -> None:
        # the body can hold a reset token: only development logs it
        if settings.env.lower() in PRODUCTION_ENVS:
            log.info("email to %s: %s", to, subject)
        else:
            log.info("email to %s: %s\n%s", to, subject, body)


class FcmPushSender:
    """FCM HTTP v1. `token_provider` returns a short-lived OAuth2 access token."""

    def __init__(self, project_id: str, token_provider: Callable[[], str], client: httpx.Client | None = None):
        self.url = f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
        self.token_provider = token_provider
        self.client = client or httpx.Client(timeout=10)

    def send(self, token: str, title: str, body: str, data: dict[str, str]) -> None:
        message: dict[str, Any] = {"token": token, "notification": {"title": title, "body": body},
                                   "data": {k: str(v) for k, v in data.items()}}
        resp = self.client.post(self.url, json={"message": message},
                                headers={"Authorization": f"Bearer {self.token_provider()}"})
        if resp.status_code == 200:
            return
        if resp.status_code in (400, 404):  # INVALID_ARGUMENT / UNREGISTERED: the device token is dead
            raise PermanentFailure(f"FCM rejected the token ({resp.status_code})")
        raise RuntimeError(f"FCM error {resp.status_code}")


class SmtpEmailSender:
    def __init__(self, host: str, port: int, username: str, password: str, starttls: bool, sender: str):
        self.host, self.port, self.username, self.password = host, port, username, password
        self.starttls, self.sender = starttls, sender

    def send(self, to: str, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self.sender, to, subject
        msg.set_content(body)
        try:
            with smtplib.SMTP(self.host, self.port, timeout=15) as smtp:
                if self.starttls:
                    smtp.starttls()
                if self.username:
                    smtp.login(self.username, self.password)
                smtp.send_message(msg)
        except smtplib.SMTPRecipientsRefused as exc:
            raise PermanentFailure("recipient refused") from exc


def _fcm_token_provider() -> Callable[[], str]:
    if settings.fcm_access_token:
        return lambda: settings.fcm_access_token
    if settings.fcm_credentials_file:
        from google.auth.transport.requests import Request  # optional dependency, only with a credentials file
        from google.oauth2 import service_account
        creds = service_account.Credentials.from_service_account_file(settings.fcm_credentials_file,
                                                                      scopes=[FCM_SCOPE])

        def refresh() -> str:
            if not creds.valid:
                creds.refresh(Request())
            return creds.token
        return refresh
    raise RuntimeError("FCM is enabled but neither FCM_ACCESS_TOKEN nor FCM_CREDENTIALS_FILE is set")


def get_push_sender() -> PushSender:
    if settings.fcm_project_id:
        return FcmPushSender(settings.fcm_project_id, _fcm_token_provider())
    return ConsolePushSender()


def get_email_sender() -> EmailSender:
    if settings.smtp_host:
        return SmtpEmailSender(settings.smtp_host, settings.smtp_port, settings.smtp_username, settings.smtp_password,
                               settings.smtp_starttls, settings.email_from)
    return ConsoleEmailSender()
