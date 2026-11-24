"""Save outreach as Gmail DRAFTS over IMAP. This module never sends mail."""
from __future__ import annotations

import imaplib
import time
from email.message import EmailMessage

GMAIL_IMAP = "imap.gmail.com"
DRAFTS_FOLDER = '"[Gmail]/Drafts"'


def build_message(sender: str, to: str, subject: str, body: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    return msg


class GmailDrafts:
    """Uses a Gmail app password (Google Account > Security > App passwords)."""

    def __init__(self, address: str, app_password: str):
        self.address = address
        self.app_password = app_password

    def save(self, messages: list[EmailMessage]) -> int:
        if not messages:
            return 0
        with imaplib.IMAP4_SSL(GMAIL_IMAP) as imap:
            imap.login(self.address, self.app_password)
            for m in messages:
                imap.append(DRAFTS_FOLDER, "\\Draft", imaplib.Time2Internaldate(time.time()), m.as_bytes())
        return len(messages)
