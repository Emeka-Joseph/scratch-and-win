"""SMTP mailer. Sends in a background thread so customers never wait on the mail server."""
import logging
import smtplib
import ssl
import threading
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from flask import current_app, render_template

log = logging.getLogger(__name__)


def _deliver(cfg, msg):
    try:
        if cfg["MAIL_USE_SSL"]:
            server = smtplib.SMTP_SSL(cfg["MAIL_SERVER"], cfg["MAIL_PORT"], context=ssl.create_default_context(), timeout=20)
        else:
            server = smtplib.SMTP(cfg["MAIL_SERVER"], cfg["MAIL_PORT"], timeout=20)
            if cfg["MAIL_USE_TLS"]:
                server.starttls(context=ssl.create_default_context())
        with server:
            if cfg["MAIL_USERNAME"]:
                server.login(cfg["MAIL_USERNAME"], cfg["MAIL_PASSWORD"])
            server.send_message(msg)
        log.info("Mail sent to %s: %s", msg["To"], msg["Subject"])
        return True
    except Exception:  # noqa: BLE001 - mail failures must never break the request
        log.exception("Mail delivery to %s failed", msg["To"])
        return False


def send_email(to, subject, template, from_name=None, sync=False, inline_images=None, **context):
    """Render emails/<template>.html (+ optional .txt) and send it.

    inline_images: {"cid-name": png_bytes} referenced in HTML as <img src="cid:cid-name">.
    """
    app = current_app._get_current_object()
    cfg = {k: app.config[k] for k in (
        "MAIL_SERVER", "MAIL_PORT", "MAIL_USE_TLS", "MAIL_USE_SSL",
        "MAIL_USERNAME", "MAIL_PASSWORD", "MAIL_FROM", "MAIL_FROM_NAME", "MAIL_SUPPRESS_SEND")}

    html = render_template(f"emails/{template}.html", **context)
    try:
        text = render_template(f"emails/{template}.txt", **context)
    except Exception:  # noqa: BLE001 - text part is optional
        text = None

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((from_name or cfg["MAIL_FROM_NAME"], cfg["MAIL_FROM"]))
    msg["To"] = to
    msg["Message-ID"] = make_msgid()
    msg.set_content(text or "Please view this email in an HTML-capable client.")
    msg.add_alternative(html, subtype="html")
    if inline_images:
        html_part = msg.get_payload()[1]
        for cid, data in inline_images.items():
            html_part.add_related(data, maintype="image", subtype="png", cid=f"<{cid}>",
                                  filename=f"{cid}.png", disposition="inline")

    if cfg["MAIL_SUPPRESS_SEND"] or not cfg["MAIL_SERVER"]:
        log.warning("MAIL_SUPPRESS_SEND: email to %s | %s\n%s", to, subject, text or "")
        app.extensions.setdefault("outbox", []).append(msg)
        return True

    if sync:
        return _deliver(cfg, msg)
    threading.Thread(target=_deliver, args=(cfg, msg), daemon=True).start()
    return True
