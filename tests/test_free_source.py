from fxauto.data.free_source import to_yahoo_symbol


def test_usd_jpy_maps_to_jpy_x():
    assert to_yahoo_symbol("USD_JPY") == "JPY=X"


def test_eur_usd_maps_to_eurusd_x():
    assert to_yahoo_symbol("EUR_USD") == "EURUSD=X"


def test_gbp_usd_maps_to_gbpusd_x():
    assert to_yahoo_symbol("GBP_USD") == "GBPUSD=X"


def test_usd_chf_uses_override():
    assert to_yahoo_symbol("USD_CHF") == "CHF=X"
