"""Shared pytest fixtures.

Redirects the global audit and compliance loggers to a per-test temporary
directory, so running the suite never writes into the real
``scope/logging/audit_logs`` or ``scope/logging/compliance_logs``.
"""

import pytest


@pytest.fixture(autouse=True)
def isolated_log_dirs(tmp_path, monkeypatch):
    """Point the shared loggers at tmp dirs; returns (audit_dir, compliance_dir)."""
    from scope.logging import get_audit_logger, get_compliance_logger

    audit_dir = tmp_path / "audit_logs"
    compliance_dir = tmp_path / "compliance_logs"
    audit_dir.mkdir()
    compliance_dir.mkdir()

    # Log files are resolved from log_dir on every write, so this redirects
    # modules that captured the logger instances at import time as well.
    monkeypatch.setattr(get_audit_logger(), "log_dir", audit_dir)
    monkeypatch.setattr(get_compliance_logger(), "log_dir", compliance_dir)
    return audit_dir, compliance_dir
