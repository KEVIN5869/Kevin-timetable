"""build.py 的测试（不会真的联网）。"""

import pytest

import build


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def read(self):
        return self.data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_load_url_from_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("ICS_URL", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("# 注释\nOTHER=1\nICS_URL=https://example.com/a.ics\n", encoding="utf-8")
    assert build.load_ics_url(env_file) == "https://example.com/a.ics"


def test_load_url_strips_quotes(tmp_path, monkeypatch):
    monkeypatch.delenv("ICS_URL", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text('ICS_URL="https://example.com/a.ics"\n', encoding="utf-8")
    assert build.load_ics_url(env_file) == "https://example.com/a.ics"


def test_environment_variable_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("ICS_URL", "https://example.com/from-env.ics")
    env_file = tmp_path / ".env"
    env_file.write_text("ICS_URL=https://example.com/from-file.ics\n", encoding="utf-8")
    assert build.load_ics_url(env_file) == "https://example.com/from-env.ics"


def test_missing_url_stops_build(tmp_path, monkeypatch):
    monkeypatch.delenv("ICS_URL", raising=False)
    with pytest.raises(SystemExit):
        build.load_ics_url(tmp_path / "no-such-file")


def test_fetch_returns_ics(monkeypatch):
    monkeypatch.setattr(build.urllib.request, "urlopen",
                        lambda request, timeout: FakeResponse(b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n"))
    assert build.fetch_ics("https://example.com/a.ics").startswith(b"BEGIN:VCALENDAR")


def test_fetch_rejects_non_ics(monkeypatch):
    monkeypatch.setattr(build.urllib.request, "urlopen",
                        lambda request, timeout: FakeResponse(b"<html>Login required</html>"))
    with pytest.raises(ValueError):
        build.fetch_ics("https://example.com/a.ics")
