"""SMTP mailer.

Sends inside the request by default (MAIL_ASYNC=0). Shared hosts such as cPanel/LiteSpeed may pause or
recycle the worker as soon as the response is sent, which silently kills background-thread sends.
Every failure is written to the audit log as `email_failed` with the SMTP error.
"""
import logging
import smtplib
import ssl
import threading
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

from flask import current_app, g, has_request_context, render_template

log = logging.getLogger(__name__)


def _deliver(cfg, msg):
    """Send one message. Returns None on success, otherwise a short description of the SMTP error."""
    try:
        if cfg["MAIL_USE_SSL"]:
            server = smtplib.SMTP_SSL(cfg["MAIL_SERVER"], cfg["MAIL_PORT"], context=ssl.create_default_context(), timeout=15)
        else:
            server = smtplib.SMTP(cfg["MAIL_SERVER"], cfg["MAIL_PORT"], timeout=15)
            if cfg["MAIL_USE_TLS"]:
                server.starttls(context=ssl.create_default_context())
        with server:
            if cfg["MAIL_USERNAME"]:
                server.login(cfg["MAIL_USERNAME"], cfg["MAIL_PASSWORD"])
            server.send_message(msg)
        log.info("Mail sent to %s: %s", msg["To"], msg["Subject"])
        return None
    except Exception as exc:  # noqa: BLE001 - mail failures must never break the request
        log.exception("Mail delivery to %s failed", msg["To"])
        return f"{type(exc).__name__}: {exc}"[:300]


def _record_failure(to, subject, error):
    """Keep the error for the current request (g.mail_error) and in the audit log (caller commits)."""
    if not has_request_context():
        return
    g.mail_error = error
    from .audit import audit
    cfg = current_app.config
    audit("email_failed", to=to, subject=subject, error=error, server=f"{cfg['MAIL_SERVER']}:{cfg['MAIL_PORT']}")


def send_email(to, subject, template, from_name=None, sync=None, inline_images=None, reply_to=None, **context):
    """Render emails/<template>.html (+ optional .txt) and send it.

    inline_images: {"cid-name": png_bytes} referenced in HTML as <img src="cid:cid-name">.
    sync: None follows MAIL_ASYNC. Returns True when the mail server accepted the message.
    """
    app = current_app._get_current_object()
    cfg = {k: app.config[k] for k in (
        "MAIL_SERVER", "MAIL_PORT", "MAIL_USE_TLS", "MAIL_USE_SSL",
        "MAIL_USERNAME", "MAIL_PASSWORD", "MAIL_FROM", "MAIL_FROM_NAME", "MAIL_SUPPRESS_SEND", "MAIL_ASYNC")}

    html = render_template(f"emails/{template}.html", **context)
    try:
        text = render_template(f"emails/{template}.txt", **context)
    except Exception:  # noqa: BLE001 - text part is optional
        text = None

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((from_name or cfg["MAIL_FROM_NAME"], cfg["MAIL_FROM"]))
    msg["To"] = to
    if reply_to:
        msg["Reply-To"] = reply_to
    # Date and a Message-ID on the sender's own domain: missing/mismatched ones count against spam scores.
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=cfg["MAIL_FROM"].rsplit("@", 1)[-1] or None)
    msg["Auto-Submitted"] = "auto-generated"
    msg.set_content(text or "Please view this email in an HTML-capable client.")
    msg.add_alternative(html, subtype="html")
    if inline_images:
        html_part = msg.get_payload()[1]
        for cid, data in inline_images.items():
            html_part.add_related(data, maintype="image", subtype="png", cid=f"<{cid}>",
                                  filename=f"{cid}.png", disposition="inline")

    if not cfg["MAIL_SUPPRESS_SEND"] and not cfg["MAIL_SERVER"]:
        _record_failure(to, subject, "MAIL_SERVER is not set in .env")
        return False
    if cfg["MAIL_SUPPRESS_SEND"]:
        log.warning("MAIL_SUPPRESS_SEND: email to %s | %s\n%s", to, subject, text or "")
        app.extensions.setdefault("outbox", []).append(msg)
        return True

    if sync is None:
        sync = not cfg["MAIL_ASYNC"]
    if not sync:
        threading.Thread(target=_deliver, args=(cfg, msg), daemon=True).start()
        return True
    error = _deliver(cfg, msg)
    if error:
        _record_failure(to, subject, error)
        return False
    return True
