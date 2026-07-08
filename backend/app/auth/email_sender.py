"""Aliyun DirectMail adapter for verification-code emails."""

from datetime import UTC, datetime
import base64
import hmac
import hashlib
import uuid
from urllib.parse import quote

import httpx

from app.auth.exceptions import AuthError
from app.config import Settings


class AliyunMailSender:
    """Send auth emails through Aliyun DirectMail SingleSendMail."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def send_register_code(self, *, email: str, code: str) -> None:
        """Send a registration verification code."""
        await self._send_code_email(
            email=email,
            code=code,
            subject="WolfArena AI 注册验证码",
            heading="WolfArena AI 注册验证码",
        )

    async def send_password_reset_code(self, *, email: str, code: str) -> None:
        """Send a password reset verification code."""
        await self._send_code_email(
            email=email,
            code=code,
            subject="WolfArena AI 重置密码验证码",
            heading="WolfArena AI 重置密码验证码",
        )

    def ensure_configured(self) -> None:
        """Ensure the Aliyun DirectMail settings needed for sending exist."""
        if not self.settings.resolved_aliyun_mail_access_key_id:
            raise AuthError("阿里云邮件 AccessKey 未配置", status_code=503)
        if not self.settings.resolved_aliyun_mail_access_key_secret:
            raise AuthError("阿里云邮件 AccessKey Secret 未配置", status_code=503)
        if not self.settings.resolved_aliyun_mail_account_name:
            raise AuthError("阿里云邮件发信地址未配置", status_code=503)

    async def _single_send_mail(
        self,
        *,
        to_address: str,
        subject: str,
        html_body: str,
    ) -> None:
        params = {
            "Action": "SingleSendMail",
            "Version": "2015-11-23",
            "Format": "JSON",
            "AccessKeyId": self.settings.resolved_aliyun_mail_access_key_id,
            "SignatureMethod": "HMAC-SHA1",
            "SignatureVersion": "1.0",
            "SignatureNonce": str(uuid.uuid4()),
            "Timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "AccountName": self.settings.resolved_aliyun_mail_account_name,
            "AddressType": "1",
            "ReplyToAddress": "false",
            "ToAddress": to_address,
            "Subject": subject,
            "HtmlBody": html_body,
            "ClickTrace": "0",
        }
        if self.settings.aliyun_mail_from_alias.strip():
            params["FromAlias"] = self.settings.aliyun_mail_from_alias.strip()

        signed_params = {
            **params,
            "Signature": self._sign(params),
        }
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(self.settings.aliyun_mail_endpoint, params=signed_params)
        if response.status_code >= 400:
            raise AuthError("邮件发送失败，请稍后重试", status_code=503)
        try:
            payload = response.json()
        except ValueError as exc:
            raise AuthError("邮件发送失败，请稍后重试", status_code=503) from exc
        if "Code" in payload and payload["Code"] != "OK":
            raise AuthError("邮件发送失败，请检查阿里云邮件配置", status_code=503)

    def _sign(self, params: dict[str, str]) -> str:
        canonical_query = "&".join(
            f"{self._percent_encode(key)}={self._percent_encode(value)}"
            for key, value in sorted(params.items())
        )
        string_to_sign = f"GET&%2F&{self._percent_encode(canonical_query)}"
        key = f"{self.settings.resolved_aliyun_mail_access_key_secret}&".encode("utf-8")
        digest = hmac.new(key, string_to_sign.encode("utf-8"), hashlib.sha1).digest()
        return base64.b64encode(digest).decode("utf-8")

    @staticmethod
    def _percent_encode(value: str) -> str:
        return quote(str(value), safe="~")

    async def _send_code_email(
        self,
        *,
        email: str,
        code: str,
        subject: str,
        heading: str,
    ) -> None:
        self.ensure_configured()
        html_body = (
            "<div style=\"font-family:Arial,sans-serif;line-height:1.7;color:#172033\">"
            f"<h2>{heading}</h2>"
            f"<p>你的验证码是：<strong style=\"font-size:24px\">{code}</strong></p>"
            "<p>验证码 5 分钟内有效。如果不是你本人操作，请忽略这封邮件。</p>"
            "</div>"
        )
        await self._single_send_mail(
            to_address=email,
            subject=subject,
            html_body=html_body,
        )
