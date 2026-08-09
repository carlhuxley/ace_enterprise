"""Regression guard for ace_enterprise-1f7: src.main (and the standalone
audit services) must be importable from pyproject.toml's declared
dependencies alone. fastapi, uvicorn, prometheus_client, and scipy were all
imported by core src/ code but missing from pyproject.toml -- they happened
to already be installed in dev environments, so nothing caught this until a
clean `pip install -e .` was tried.
"""


def test_main_app_imports():
    import src.main
    assert src.main.app is not None


def test_audit_api_imports():
    import src.audit.api
    assert src.audit.api.create_api_app is not None


def test_audit_collector_imports():
    import src.audit.collector
    assert src.audit.collector.create_collector_app is not None


def test_bayesian_broker_imports():
    """Exercises the scipy dependency (src/broker/bayesian.py)."""
    from src.broker.bayesian import estimate_success_rate
    assert estimate_success_rate is not None
