import pytest

from fxauto.config import Config, load_config, load_dotenv


def test_load_config_yaml(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("instrument: EUR_USD\nrisk:\n  max_positions: 2\n", encoding="utf-8")
    cfg = load_config(p)
    assert cfg["instrument"] == "EUR_USD"
    assert cfg["risk"]["max_positions"] == 2
    assert isinstance(cfg["risk"], Config)


def test_repo_config_is_valid():
    cfg = load_config("config.yaml")
    for key in ("instrument", "granularity", "strategy", "backtest", "risk",
                "walkforward", "execution", "notify", "data"):
        assert key in cfg, f"config.yaml に {key} がありません"
    assert 0 < cfg["risk"]["risk_per_trade"] <= 0.02
    assert cfg["risk"]["max_positions"] >= 1


def test_load_dotenv_does_not_override(tmp_path, monkeypatch):
    envfile = tmp_path / ".env"
    envfile.write_text("MY_TEST_KEY=from_file\n# comment\nOTHER=x\n", encoding="utf-8")
    monkeypatch.setenv("MY_TEST_KEY", "from_env")
    monkeypatch.delenv("OTHER", raising=False)
    load_dotenv(envfile)
    import os
    assert os.environ["MY_TEST_KEY"] == "from_env"
    assert os.environ["OTHER"] == "x"


def test_missing_credentials_raise(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # .env が無いディレクトリ
    monkeypatch.delenv("OANDA_API_TOKEN", raising=False)
    monkeypatch.delenv("OANDA_ACCOUNT_ID", raising=False)
    from fxauto.config import get_oanda_credentials
    with pytest.raises(RuntimeError, match="OANDA"):
        get_oanda_credentials()
