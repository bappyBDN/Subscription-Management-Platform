"""Mail settings (Gmail shortcut) and the admin test-email endpoint."""

import smtplib

from app.core.config import Settings, get_settings
from app.services import mailer


def _settings(**env) -> Settings:
    # the test run sets MAIL_ENABLED=false in the environment; these settings start from mail switched on
    return Settings(_env_file=None, **{"mail_enabled": True, **env})


def test_gmail_shortcut_fills_smtp_settings():
    s = _settings(gmail_user="me@gmail.com", gmail_app_password="abcd efgh ijkl mnop")
    assert (s.smtp_host, s.smtp_port, s.smtp_tls) == ("smtp.gmail.com", 587, True)
    assert s.smtp_user == "me@gmail.com" and s.smtp_password == "abcdefghijklmnop"
    assert s.smtp_from == "me@gmail.com" and s.mail_on


def test_mail_off_without_host_or_when_disabled():
    assert not _settings().mail_on
    assert not _settings(smtp_host="smtp.x.org", mail_enabled=False).mail_on
    assert _settings(smtp_host="smtp.x.org").mail_on


def test_explain_bad_gmail_password(monkeypatch):
    monkeypatch.setattr(mailer, "get_settings", lambda: _settings(gmail_user="me@gmail.com", gmail_app_password="x"))
    text = mailer.explain(smtplib.SMTPAuthenticationError(535, b"Username and Password not accepted"))
    assert "app password" in text


def test_mail_test_endpoint(client, auth, monkeypatch):
    headers = auth("dmd")
    # tests run with MAIL_ENABLED=false
    r = client.post("/api/mail/test", headers=headers)
    assert r.status_code == 400 and "Email is off" in r.json()["detail"]
    assert client.get("/api/mail/status", headers=headers).json()["enabled"] is False
    assert client.post("/api/mail/test", headers=auth("staff")).status_code == 403

    on = _settings(gmail_user="me@gmail.com", gmail_app_password="wrong")
    monkeypatch.setattr("app.api.routers.system.get_settings", lambda: on)
    monkeypatch.setattr(mailer, "get_settings", lambda: on)

    def refuse(*_):
        raise smtplib.SMTPAuthenticationError(535, b"Username and Password not accepted")

    monkeypatch.setattr(mailer, "_deliver", refuse)
    r = client.post("/api/mail/test", headers=headers)
    assert r.status_code == 400 and "rejected the user name or password" in r.json()["detail"]

    sent = []
    monkeypatch.setattr(mailer, "_deliver", lambda to, subject, body: sent.append(to))
    r = client.post("/api/mail/test", headers=headers)
    assert r.status_code == 200 and sent == ["dmd1@test.local"]
    get_settings.cache_clear()
