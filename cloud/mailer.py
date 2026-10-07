from __future__ import annotations

from email.message import EmailMessage
import smtplib


class MailDeliveryError(RuntimeError):
    """Raised when Cloud cannot hand a message to the mail server."""


def _send_message(*, host: str, port: int, username: str | None, password: str | None, sender: str, recipient: str, subject: str, body: str, starttls: bool, html: str | None = None, timeout: float = 10.0) -> None:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    # 附带 HTML 版本：支持的客户端展示品牌排版，不支持时自动回退到上面的纯文本。
    if html:
        message.add_alternative(html, subtype="html")
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


# 品牌色与 NoteMeld Cloud Web 端保持一致。
_BRAND = "#6366f1"


def _code_email_html(*, reason: str, code: str) -> str:
    return f"""\
<!doctype html>
<html lang="zh-CN">
  <body style="margin:0;padding:24px;background:#f4f5f7;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:440px;margin:0 auto;">
      <tr>
        <td style="border-radius:16px;background:#ffffff;padding:32px;box-shadow:0 8px 24px rgba(15,23,42,.06);">
          <div style="font-size:18px;font-weight:700;color:{_BRAND};margin-bottom:4px;">NoteMeld Cloud</div>
          <div style="font-size:13px;color:#94a3b8;margin-bottom:24px;">智能云端工作台</div>
          <h1 style="margin:0 0 8px;font-size:18px;color:#0f172a;">你的{reason}验证码</h1>
          <p style="margin:0 0 20px;font-size:13px;line-height:1.7;color:#64748b;">请在登录页面输入以下验证码完成{reason}：</p>
          <div style="text-align:center;background:#eef0fe;border:1px solid #d6dafe;border-radius:12px;padding:18px 0;margin-bottom:20px;">
            <span style="font-size:30px;font-weight:700;letter-spacing:10px;color:{_BRAND};padding-left:10px;">{code}</span>
          </div>
          <p style="margin:0;font-size:12px;line-height:1.7;color:#94a3b8;">验证码 10 分钟内有效。为保障账号安全，<strong style="color:#ef4444;">请勿将验证码转发给他人</strong>。</p>
          <hr style="border:0;border-top:1px solid #eef0f3;margin:24px 0;" />
          <p style="margin:0;font-size:11px;color:#cbd5e1;text-align:center;">此邮件由系统自动发送，请勿直接回复 · NoteMeld</p>
        </td>
      </tr>
    </table>
  </body>
</html>"""


def send_verification_code(*, host: str, port: int, username: str | None, password: str | None, sender: str, recipient: str, code: str, purpose: str, starttls: bool, timeout: float = 10.0) -> None:
    reason = {"login": "登录", "password_reset": "重置密码", "access_request": "申请访问"}.get(purpose, "验证")
    body = f"你的 NoteMeld Cloud {reason}验证码是：{code}\n验证码 10 分钟内有效。请勿将验证码转发给他人。"
    html = _code_email_html(reason=reason, code=code)
    _send_message(host=host, port=port, username=username, password=password, sender=sender, recipient=recipient, subject="NoteMeld Cloud 验证码", body=body, starttls=starttls, html=html, timeout=timeout)


def send_invitation(*, host: str, port: int, username: str | None, password: str | None, sender: str, recipient: str, invite_url: str, starttls: bool, timeout: float = 10.0) -> None:
    _send_message(host=host, port=port, username=username, password=password, sender=sender, recipient=recipient, subject="你被邀请加入 NoteMeld Cloud", body=f"你已被邀请加入 NoteMeld Cloud。请打开以下链接完成注册：\n{invite_url}\n\n此邀请 7 天内有效。请勿将链接转发给他人。", starttls=starttls, timeout=timeout)
