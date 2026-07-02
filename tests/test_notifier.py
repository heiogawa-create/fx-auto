from fxauto.notify.notifier import Notifier


def test_disabled_without_token(monkeypatch):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("LINE_NOTIFY_TOKEN", raising=False)
    n = Notifier(channel="discord")
    assert not n.enabled
    assert n.send("hello") is False


def test_channel_none_disabled():
    n = Notifier(channel="none")
    assert not n.enabled


def test_send_failure_does_not_raise(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://invalid.localhost/webhook")
    n = Notifier(channel="discord", timeout_sec=0.5)
    assert n.enabled
    # 接続不能でも例外を投げない(取引ループを止めない)
    assert n.send("test") is False
    n.notify_entry("USD_JPY", 1, 1000, 150.0, 149.5)
    n.notify_exit("USD_JPY", -100.0, "stop_loss")
    n.notify_error("boom")
