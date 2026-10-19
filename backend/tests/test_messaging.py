"""
Task 4.2 tests: text messaging (FR-E1) between a Guardian and a linked Dependent.
"""

import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import func, select

from app.models import Message, Notification
from app.services import push_service
from tests.test_linkage import assert_error, auth
from tests.test_location import team
from tests.test_notifications import inbox
from tests.test_permissions import put

TOKEN_D = "d" * 40 + "-dependent-phone-token"


@pytest.fixture(autouse=True)
def push():
    p = push_service.get_provider()
    p.sent.clear()
    p.fail = False
    yield p


def uid(client, token):
    r = client.get("/auth/me", headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()["user_id"]


def msgteam(client):
    t = team(client)
    t["pid"] = uid(client, t["pt"])
    return t


def send(client, token, to, body="Hello", **extra):
    return client.post("/messages", json={"receiver_id": to, "body": body, **extra}, headers=auth(token))


def history(client, token, other, **params):
    r = client.get("/messages", params={"with_user_id": other, **params}, headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()


def allow(client, t, granted=True):
    assert put(client, t["pt"], t["dep"], "communication", t["sid"], granted).status_code == 200


# ------------------------------------------------------------ sending

def test_guardian_sends_to_dependent_and_dependent_replies(client):
    t = msgteam(client)
    r = send(client, t["pt"], t["dep"], "  Did you eat?  ")
    assert r.status_code == 201, r.text
    m = r.json()
    assert m["body"] == "Did you eat?" and m["type"] == "text" and m["priority"] == "standard"
    assert m["from_me"] is True and m["read_at"] is None and m["already_sent"] is False
    r2 = send(client, t["dt"], t["pid"], "Yes, thanks")
    assert r2.status_code == 201 and r2.json()["from_me"] is True
    h = history(client, t["pt"], t["dep"])
    assert [i["body"] for i in h["items"]] == ["Yes, thanks", "Did you eat?"]
    assert [i["from_me"] for i in h["items"]] == [False, True]


def test_empty_blank_and_too_long_are_rejected(client):
    t = msgteam(client)
    for body in ("", "   ", "x" * 2001):
        assert_error(send(client, t["pt"], t["dep"], body), 422, "VALIDATION_ERROR")
    assert send(client, t["pt"], t["dep"], "x" * 2000).status_code == 201


def test_needs_login(client):
    t = msgteam(client)
    r = client.post("/messages", json={"receiver_id": t["dep"], "body": "hi"})
    assert_error(r, 401, "NOT_AUTHENTICATED")
    assert_error(client.get("/messages", params={"with_user_id": t["dep"]}), 401, "NOT_AUTHENTICATED")
    assert_error(client.get("/messages/conversations"), 401, "NOT_AUTHENTICATED")


def test_same_role_unknown_and_self_are_refused(client):
    t = msgteam(client)
    assert_error(send(client, t["pt"], t["sid"]), 403, "NOT_LINKED_TO_DEPENDENT")  # guardian to guardian
    assert_error(send(client, t["pt"], t["pid"]), 403, "NOT_LINKED_TO_DEPENDENT")  # to myself
    assert_error(send(client, t["pt"], str(uuid.uuid4())), 403, "NOT_LINKED_TO_DEPENDENT")
    assert_error(send(client, t["dt"], str(uuid.uuid4())), 403, "NOT_LINKED_TO_DEPENDENT")


def test_unlinked_guardian_cannot_message_or_read(client):
    t = msgteam(client)
    from tests.test_linkage import make_guardian
    from tests.test_location import verify  # noqa: F401

    ot, _, _ = make_guardian(client, 9)
    assert_error(send(client, ot, t["dep"]), 403, "NOT_LINKED_TO_DEPENDENT")
    assert_error(client.get("/messages", params={"with_user_id": t["dep"]}, headers=auth(ot)), 403, "NOT_LINKED_TO_DEPENDENT")
    assert_error(client.post("/messages/read", json={"with_user_id": t["dep"]}, headers=auth(ot)), 403, "NOT_LINKED_TO_DEPENDENT")


# ------------------------------------------------------------ permission (Secondary)

def test_secondary_needs_communication_grant_both_ways(client):
    t = msgteam(client)
    assert_error(send(client, t["st"], t["dep"]), 403, "MODULE_ACCESS_DENIED")
    assert_error(send(client, t["dt"], t["sid"]), 403, "MODULE_ACCESS_DENIED")  # dependent to a Secondary without grant
    assert_error(client.get("/messages", params={"with_user_id": t["dep"]}, headers=auth(t["st"])), 403, "MODULE_ACCESS_DENIED")
    allow(client, t)
    assert send(client, t["st"], t["dep"], "Hi from secondary").status_code == 201
    assert send(client, t["dt"], t["sid"], "Hi back").status_code == 201
    assert len(history(client, t["st"], t["dep"])["items"]) == 2


def test_losing_the_grant_stops_sending_reading_and_hides_the_conversation(client):
    t = msgteam(client)
    allow(client, t)
    assert send(client, t["st"], t["dep"]).status_code == 201
    allow(client, t, False)
    assert_error(send(client, t["st"], t["dep"]), 403, "MODULE_ACCESS_DENIED")
    assert_error(client.get("/messages", params={"with_user_id": t["dep"]}, headers=auth(t["st"])), 403, "MODULE_ACCESS_DENIED")
    assert client.get("/messages/conversations", headers=auth(t["st"])).json()["items"] == []
    # The Primary still sees the Dependent's side; the Secondary's earlier message is not in the Primary's thread.
    assert history(client, t["pt"], t["dep"])["items"] == []


def test_two_guardians_have_separate_threads(client):
    t = msgteam(client)
    allow(client, t)
    send(client, t["pt"], t["dep"], "from primary")
    send(client, t["st"], t["dep"], "from secondary")
    assert [i["body"] for i in history(client, t["pt"], t["dep"])["items"]] == ["from primary"]
    assert [i["body"] for i in history(client, t["st"], t["dep"])["items"]] == ["from secondary"]
    assert len(history(client, t["dt"], t["pid"])["items"]) == 1
    assert len(history(client, t["dt"], t["sid"])["items"]) == 1


def test_unverified_secondary_is_refused_even_with_grant(client, db):
    t = msgteam(client)
    allow(client, t)
    from app.models import GuardianProfile

    p = db.get(GuardianProfile, uuid.UUID(t["sid"]))
    p.phone_verified = False
    p.cnic_verified = False
    db.commit()
    assert_error(send(client, t["st"], t["dep"]), 403, "GUARDIAN_NOT_VERIFIED")
    assert_error(send(client, t["dt"], t["sid"]), 403, "GUARDIAN_NOT_VERIFIED")


# ------------------------------------------------------------ safe retry (client_id)

def test_same_client_id_sends_once(client, db):
    t = msgteam(client)
    cid = str(uuid.uuid4())
    a = send(client, t["pt"], t["dep"], "once", client_id=cid)
    b = send(client, t["pt"], t["dep"], "once", client_id=cid)
    assert a.status_code == 201 and b.status_code == 200
    assert b.json()["message_id"] == a.json()["message_id"] and b.json()["already_sent"] is True
    assert db.scalar(select(func.count()).select_from(Message)) == 1
    assert len(inbox(client, t["dt"])["items"]) == 1  # one notification, not two


def test_client_id_reused_for_different_text_is_a_conflict(client):
    t = msgteam(client)
    cid = str(uuid.uuid4())
    assert send(client, t["pt"], t["dep"], "one", client_id=cid).status_code == 201
    assert_error(send(client, t["pt"], t["dep"], "two", client_id=cid), 409, "CLIENT_ID_REUSED")


def test_two_people_may_use_the_same_client_id(client):
    t = msgteam(client)
    cid = str(uuid.uuid4())
    assert send(client, t["pt"], t["dep"], "a", client_id=cid).status_code == 201
    assert send(client, t["dt"], t["pid"], "b", client_id=cid).status_code == 201


def test_parallel_retries_send_exactly_one(client, db):
    t = msgteam(client)
    cid = str(uuid.uuid4())
    n = 6
    gate = Barrier(n)

    def go(_):
        gate.wait()
        return send(client, t["pt"], t["dep"], "race", client_id=cid)

    with ThreadPoolExecutor(n) as pool:
        rs = list(pool.map(go, range(n)))
    assert sorted(r.status_code for r in rs) == [200] * (n - 1) + [201]
    assert len({r.json()["message_id"] for r in rs}) == 1
    assert db.scalar(select(func.count()).select_from(Message)) == 1
    assert db.scalar(select(func.count()).select_from(Notification)) == 1


# ------------------------------------------------------------ notification and push

def test_receiver_gets_a_standard_notification_and_push(client, push):
    t = msgteam(client)
    assert client.put("/devices/push-token", json={"token": TOKEN_D}, headers=auth(t["dt"])).status_code == 200
    r = send(client, t["pt"], t["dep"], "y" * 200)
    items = inbox(client, t["dt"])["items"]
    assert len(items) == 1 and items[0]["type"] == "message" and items[0]["priority"] == "standard"
    assert items[0]["data"]["message_id"] == r.json()["message_id"]
    assert items[0]["body"].endswith("…") and len(items[0]["body"]) == 80
    assert len(push.sent) == 1 and push.sent[0].tokens == [TOKEN_D] and push.sent[0].priority == "standard"
    assert inbox(client, t["pt"])["items"] == []  # the sender gets nothing


def test_push_failure_never_loses_the_message(client, push):
    t = msgteam(client)
    client.put("/devices/push-token", json={"token": TOKEN_D}, headers=auth(t["dt"]))
    push.fail = True
    assert send(client, t["pt"], t["dep"], "still saved").status_code == 201
    assert len(history(client, t["dt"], t["pid"])["items"]) == 1


# ------------------------------------------------------------ history paging

def test_history_pages_without_gaps_or_repeats(client):
    t = msgteam(client)
    for i in range(7):
        assert send(client, t["pt"], t["dep"], f"m{i}").status_code == 201
    seen, before = [], None
    for _ in range(5):
        params = {"limit": 3, **({"before": before} if before else {})}
        h = history(client, t["pt"], t["dep"], **params)
        seen += [i["body"] for i in h["items"]]
        before = h["next_before"]
        if before is None:
            break
    assert seen == [f"m{i}" for i in range(6, -1, -1)]


def test_history_limit_is_checked(client):
    t = msgteam(client)
    for limit in (0, 101):
        r = client.get("/messages", params={"with_user_id": t["dep"], "limit": limit}, headers=auth(t["pt"]))
        assert_error(r, 422, "VALIDATION_ERROR")


# ------------------------------------------------------------ read receipts and conversations

def test_mark_read_only_marks_their_messages_and_is_safe_to_repeat(client):
    t = msgteam(client)
    send(client, t["pt"], t["dep"], "a")
    send(client, t["pt"], t["dep"], "b")
    send(client, t["dt"], t["pid"], "mine")
    r = client.post("/messages/read", json={"with_user_id": t["pid"]}, headers=auth(t["dt"]))
    assert r.status_code == 200 and r.json() == {"marked_read": 2}
    assert client.post("/messages/read", json={"with_user_id": t["pid"]}, headers=auth(t["dt"])).json() == {"marked_read": 0}
    h = history(client, t["pt"], t["dep"])["items"]
    by = {i["body"]: i for i in h}
    assert by["a"]["read_at"] and by["b"]["read_at"]  # the sender sees the read time
    assert by["mine"]["read_at"] is None  # my own message to them is untouched


def test_conversations_show_last_message_and_unread(client):
    t = msgteam(client)
    allow(client, t)
    send(client, t["pt"], t["dep"], "p1")
    send(client, t["st"], t["dep"], "s1")
    send(client, t["st"], t["dep"], "s2")
    c = client.get("/messages/conversations", headers=auth(t["dt"])).json()
    assert c["total_unread"] == 3
    assert [i["name"] for i in c["items"]] and c["items"][0]["last_message"]["body"] == "s2"  # most recent first
    assert {i["user_id"]: i["unread_count"] for i in c["items"]} == {t["pid"]: 1, t["sid"]: 2}
    client.post("/messages/read", json={"with_user_id": t["sid"]}, headers=auth(t["dt"]))
    c = client.get("/messages/conversations", headers=auth(t["dt"])).json()
    assert c["total_unread"] == 1
    mine = client.get("/messages/conversations", headers=auth(t["pt"])).json()
    assert len(mine["items"]) == 1 and mine["items"][0]["role"] == "dependent" and mine["items"][0]["unread_count"] == 0
    assert mine["items"][0]["last_message"]["from_me"] is True


def test_conversations_empty_for_new_user(client):
    t = msgteam(client)
    assert client.get("/messages/conversations", headers=auth(t["dt"])).json() == {"items": [], "total_unread": 0}


# ------------------------------------------------------------ database rules

def test_database_refuses_a_text_message_without_body(db):
    from sqlalchemy.exc import IntegrityError

    from app.models import User

    users = list(db.scalars(select(User)))
    assert users == []  # nothing yet; create two quickly
    a = User(email="a@x.com", phone="03001110001", password_hash="x", role="guardian", full_name="A")
    b = User(email="b@x.com", phone="03001110002", password_hash="x", role="dependent", full_name="B")
    db.add_all([a, b])
    db.commit()
    db.add(Message(sender_id=a.user_id, receiver_id=b.user_id, type="text"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.add(Message(sender_id=a.user_id, receiver_id=b.user_id, type="text", body=""))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.add(Message(sender_id=a.user_id, receiver_id=b.user_id, type="priority_voice", content_url="x", duration_s=3))
    db.commit()  # voice messages need no body


def test_dependent_to_dependent_is_refused(client):
    from tests.test_linkage import make_dependent

    t = msgteam(client)
    other = make_dependent(client, 2)
    assert_error(send(client, t["dt"], other), 403, "NOT_LINKED_TO_DEPENDENT")


# ============================================================ Task 4.3: priority voice messages (FR-E4)

from app.core.config import get_settings  # noqa: E402

M4A = b"\x00\x00\x00\x18ftypM4A \x00\x00\x00\x00M4A mp42isom" + b"\x01" * 400
TOKEN_G = "g" * 40 + "-guardian-phone-token"


@pytest.fixture(autouse=True)
def voice_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "VOICE_STORAGE_DIR", str(tmp_path / "voice"))
    return tmp_path / "voice"


def voice(client, token, to, data=M4A, dur=5, **extra):
    form = {"receiver_id": to, "duration_s": str(dur), **{k: str(v) for k, v in extra.items()}}
    return client.post("/messages/voice", data=form, files={"audio": ("note.m4a", data, "audio/mp4")}, headers=auth(token))


def test_guardian_sends_voice_as_critical_and_dependent_downloads_it(client, push, voice_dir):
    t = msgteam(client)
    client.put("/devices/push-token", json={"token": TOKEN_D}, headers=auth(t["dt"]))
    r = voice(client, t["pt"], t["dep"], dur=7)
    assert r.status_code == 201, r.text
    m = r.json()
    assert m["type"] == "priority_voice" and m["priority"] == "critical" and m["duration_s"] == 7 and m["body"] is None
    assert m["content_url"] == f"/messages/{m['message_id']}/audio"
    n = inbox(client, t["dt"])["items"][0]
    assert n["type"] == "voice_message" and n["priority"] == "critical" and n["data"]["message_id"] == m["message_id"]
    assert push.sent[-1].priority == "critical"
    for who in ("dt", "pt"):  # receiver and sender can both fetch it
        a = client.get(m["content_url"], headers=auth(t[who]))
        assert a.status_code == 200 and a.content == M4A
    assert len(list(voice_dir.iterdir())) == 1


def test_voice_appears_in_history_and_conversations_and_can_be_read(client):
    t = msgteam(client)
    send(client, t["pt"], t["dep"], "text first")
    m = voice(client, t["pt"], t["dep"]).json()
    h = history(client, t["dt"], t["pid"])["items"]
    assert [i["type"] for i in h] == ["priority_voice", "text"]
    c = client.get("/messages/conversations", headers=auth(t["dt"])).json()
    assert c["items"][0]["last_message"]["message_id"] == m["message_id"] and c["items"][0]["unread_count"] == 2
    assert client.post("/messages/read", json={"with_user_id": t["pid"]}, headers=auth(t["dt"])).json() == {"marked_read": 2}


def test_dependent_cannot_send_voice(client):
    t = msgteam(client)
    assert_error(voice(client, t["dt"], t["pid"]), 403, "FORBIDDEN")


def test_voice_follows_the_communication_permission(client):
    t = msgteam(client)
    assert_error(voice(client, t["st"], t["dep"]), 403, "MODULE_ACCESS_DENIED")
    allow(client, t)
    m = voice(client, t["st"], t["dep"]).json()
    assert client.get(m["content_url"], headers=auth(t["st"])).status_code == 200
    allow(client, t, False)
    assert_error(client.get(m["content_url"], headers=auth(t["st"])), 403, "MODULE_ACCESS_DENIED")
    assert_error(client.get(m["content_url"], headers=auth(t["dt"])), 403, "MODULE_ACCESS_DENIED")


def test_only_sender_and_receiver_can_download(client):
    t = msgteam(client)
    allow(client, t)
    m = voice(client, t["pt"], t["dep"]).json()
    assert_error(client.get(m["content_url"], headers=auth(t["st"])), 404, "MESSAGE_NOT_FOUND")
    assert_error(client.get(m["content_url"]), 401, "NOT_AUTHENTICATED")
    assert_error(client.get(f"/messages/{uuid.uuid4()}/audio", headers=auth(t["pt"])), 404, "MESSAGE_NOT_FOUND")
    text = send(client, t["pt"], t["dep"], "hello").json()
    assert_error(client.get(f"/messages/{text['message_id']}/audio", headers=auth(t["pt"])), 404, "MESSAGE_NOT_FOUND")


def test_bad_audio_is_refused_and_nothing_is_saved(client, voice_dir):
    t = msgteam(client)
    assert_error(voice(client, t["pt"], t["dep"], data=b"this is not audio at all" * 20), 415, "UNSUPPORTED_AUDIO")
    assert_error(voice(client, t["pt"], t["dep"], data=b""), 422, "VALIDATION_ERROR")
    assert_error(voice(client, t["pt"], t["dep"], data=M4A + b"x" * 2_000_000), 413, "AUDIO_TOO_LARGE")
    for d in (0, 121, -3):
        assert_error(voice(client, t["pt"], t["dep"], dur=d), 422, "VALIDATION_ERROR")
    assert_error(client.post("/messages/voice", data={"receiver_id": t["dep"], "duration_s": "5"}, headers=auth(t["pt"])), 422, "VALIDATION_ERROR")
    assert not voice_dir.exists() or list(voice_dir.iterdir()) == []


def test_other_audio_types_are_accepted(client):
    t = msgteam(client)
    samples = [b"ID3\x03\x00" + b"\x00" * 50, b"OggS" + b"\x00" * 50, b"RIFF\x00\x00\x00\x00WAVE" + b"\x00" * 50, b"#!AMR\n" + b"\x00" * 50]
    for s in samples:
        assert voice(client, t["pt"], t["dep"], data=s).status_code == 201


def test_voice_retry_with_client_id_sends_once(client, db, voice_dir):
    t = msgteam(client)
    cid = str(uuid.uuid4())
    a = voice(client, t["pt"], t["dep"], client_id=cid)
    b = voice(client, t["pt"], t["dep"], client_id=cid)
    assert (a.status_code, b.status_code) == (201, 200) and b.json()["already_sent"] is True
    assert a.json()["message_id"] == b.json()["message_id"]
    assert len(list(voice_dir.iterdir())) == 1 and len(inbox(client, t["dt"])["items"]) == 1
    assert_error(voice(client, t["pt"], t["dep"], dur=9, client_id=cid), 409, "CLIENT_ID_REUSED")


def test_parallel_voice_retries_leave_one_message_and_one_file(client, db, voice_dir):
    t = msgteam(client)
    cid = str(uuid.uuid4())
    n = 6
    gate = Barrier(n)

    def go(_):
        gate.wait()
        return voice(client, t["pt"], t["dep"], client_id=cid)

    with ThreadPoolExecutor(n) as pool:
        rs = list(pool.map(go, range(n)))
    assert sorted(r.status_code for r in rs) == [200] * (n - 1) + [201]
    assert db.scalar(select(func.count()).select_from(Message)) == 1
    assert len(list(voice_dir.iterdir())) == 1
    assert db.scalar(select(func.count()).select_from(Notification)) == 1


def test_missing_file_on_disk_is_a_clean_404(client, voice_dir):
    t = msgteam(client)
    m = voice(client, t["pt"], t["dep"]).json()
    for f in voice_dir.iterdir():
        f.unlink()
    assert_error(client.get(m["content_url"], headers=auth(t["dt"])), 404, "AUDIO_NOT_FOUND")


def test_database_refuses_voice_without_audio_or_length(db):
    from sqlalchemy.exc import IntegrityError

    from app.models import User

    a = User(email="a@x.com", phone="03001110001", password_hash="x", role="guardian", full_name="A")
    b = User(email="b@x.com", phone="03001110002", password_hash="x", role="dependent", full_name="B")
    db.add_all([a, b])
    db.commit()
    for kw in ({}, {"content_url": "k"}, {"duration_s": 5}, {"content_url": "k", "duration_s": 0}):
        db.add(Message(sender_id=a.user_id, receiver_id=b.user_id, type="priority_voice", **kw))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
