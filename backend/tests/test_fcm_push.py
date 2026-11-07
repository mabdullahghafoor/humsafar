"""Real Firebase push provider (F-16). Firebase itself is replaced by a stand-in; no network, no key needed."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services import push_service
from app.services.push_service import FcmPushProvider, PushMessage


@pytest.fixture()
def provider():
    p = FcmPushProvider.__new__(FcmPushProvider)  # skip real credential loading
    p._app = object()
    return p


def _result(ok, fail):
    return SimpleNamespace(
        success_count=ok, failure_count=fail,
        responses=[SimpleNamespace(success=True, exception=None)] * ok + [SimpleNamespace(success=False, exception="dead")] * fail,
    )


def test_critical_uses_high_priority_channel(provider):
    with patch("firebase_admin.messaging.send_each_for_multicast", return_value=_result(1, 0)) as send:
        provider.send(PushMessage(tokens=["t1"], title="Panic", body="help", priority="critical", data={"event_id": 7}))
    m = send.call_args.args[0]
    assert m.android.priority == "high"
    assert m.android.notification.channel_id == "humsafar_critical"
    assert m.data == {"event_id": "7", "priority": "critical"}


def test_standard_uses_normal_channel(provider):
    with patch("firebase_admin.messaging.send_each_for_multicast", return_value=_result(1, 0)) as send:
        provider.send(PushMessage(tokens=["t1"], title="Hi", body="x", priority="standard"))
    assert send.call_args.args[0].android.priority == "normal"
    assert send.call_args.args[0].android.notification.channel_id == "humsafar_standard"


def test_more_than_500_tokens_are_split(provider):
    with patch("firebase_admin.messaging.send_each_for_multicast", return_value=_result(1, 0)) as send:
        provider.send(PushMessage(tokens=[f"t{i}" for i in range(1001)], title="a", body="b", priority="standard"))
    assert send.call_count == 3


def test_all_tokens_rejected_counts_as_failure(provider):
    with patch("firebase_admin.messaging.send_each_for_multicast", return_value=_result(0, 2)):
        with pytest.raises(RuntimeError):
            provider.send(PushMessage(tokens=["a", "b"], title="a", body="b", priority="standard"))


def test_deliver_never_raises_when_fcm_fails(provider, monkeypatch):
    monkeypatch.setattr(push_service, "_provider", provider)
    with patch("firebase_admin.messaging.send_each_for_multicast", side_effect=RuntimeError("down")):
        assert push_service.deliver(PushMessage(tokens=["a"], title="a", body="b", priority="critical")) is False
    monkeypatch.setattr(push_service, "_provider", None)


def test_fcm_without_credentials_is_refused(monkeypatch):
    monkeypatch.setattr(push_service, "_provider", None)
    monkeypatch.setattr(push_service.get_settings(), "PUSH_PROVIDER", "fcm", raising=False)
    monkeypatch.setattr(push_service.get_settings(), "FIREBASE_CREDENTIALS_JSON", "", raising=False)
    with pytest.raises(RuntimeError):
        push_service.get_provider()
    monkeypatch.setattr(push_service, "_provider", None)
