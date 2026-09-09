from __future__ import annotations

from email.message import EmailMessage
import smtplib


class MailDeliveryError(RuntimeError):
    """Raised when Cloud cannot hand a message to the mail server."""


def _send_message(*, host: str, port: int, username: str | None, password: str | None, sender: str, recipient: str, subject: str, body: str, starttls: bool, timeout: float = 10.0) -> None:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    try:
        with smtplib.SMTP(host, port, timeout=timeout) as server:
            server.ehlo()
            if starttls:
                server.starttls()
                server.ehlo()
            if username:
                server.login(username, password or "")
            server.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise MailDeliveryError("email delivery failed") from exc


def send_verification_code(*, host: str, port: int, username: str | None, password: str | None, sender: str, recipient: str, code: str, purpose: str, starttls: bool, timeout: float = 10.0) -> None:
    reason = {"login": "登录", "password_reset": "重置密码", "access_request": "申请访问"}.get(purpose, "验证")
    _send_message(host=host, port=port, username=username, password=password, sender=sender, recipient=recipient, subject="NoteMeld Cloud 验证码", body=f"你的 NoteMeld Cloud {reason}验证码是：{code}\n验证码 10 分钟内有效。请勿将验证码转发给他人。", starttls=starttls, timeout=timeout)


def send_invitation(*, host: str, port: int, username: str | None, password: str | None, sender: str, recipient: str, invite_url: str, starttls: bool, timeout: float = 10.0) -> None:
    _send_message(host=host, port=port, username=username, password=password, sender=sender, recipient=recipient, subject="你被邀请加入 NoteMeld Cloud", body=f"你已被邀请加入 NoteMeld Cloud。请打开以下链接完成注册：\n{invite_url}\n\n此邀请 7 天内有效。请勿将链接转发给他人。", starttls=starttls, timeout=timeout)
