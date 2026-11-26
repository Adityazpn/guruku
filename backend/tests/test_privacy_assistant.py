import io
import json
from decimal import Decimal as D

import pytest
from pptx import Presentation
from sqlalchemy import select

from app.ai_engine import engine as eng
from app.ai_engine.catalog import seed_all
from app.ai_engine.models import AiRequest, AiTool
from app.ai_providers.adapters.fake import FakeProvider
from app.ai_providers.models import AiModel, AiToolModelAssignment
from app.documents.models import Document, DocumentVersion
from app.privacy import anonymizer as an
from app.users.models import User
from tests.aihelpers import reset_fake, setup_ai
from tests.test_admin import login

A = "/api/v1"
OBS = "Rina sulit memahami pecahan, sering terlambat. Ibunya (0812-3456-7890 / ibu.rina@mail.com) khawatir. NISN 1234567890."


# ---------------------------------------------------------------- anonymizer (pure)
def test_names_and_identifiers_are_replaced_and_names_are_restorable():
    data = {"observations": "Siti Aminah dan Budi bertengkar. Siti Aminah NIK 3171234567890001, hubungi 081234567890 atau a.b@sekolah.id.", "n": 3}
    out, mapping = an.anonymize(data, an.parse_names("Siti Aminah, Budi"))
    flat = json.dumps(out)
    for secret in ("Siti", "Aminah", "Budi", "3171234567890001", "081234567890", "a.b@sekolah.id"):
        assert secret not in flat, secret
    assert "[SISWA_1]" in flat and "[SISWA_2]" in flat and "[NIK]" in flat and "[TELEPON]" in flat and "[EMAIL]" in flat and out["n"] == 3
    assert mapping == {"[SISWA_1]": "Siti Aminah", "[SISWA_2]": "Budi"}
    assert an.restore(out["observations"], mapping).startswith("Siti Aminah dan Budi bertengkar")


def test_name_matching_is_whole_word_and_case_insensitive():
    out, m = an.anonymize("rina dan Marina; RINA!", an.parse_names("Rina"))
    assert out == "[SISWA_1] dan Marina; [SISWA_1]!" and m == {"[SISWA_1]": "Rina"}  # 'Marina' is left alone
    assert an.parse_names("A, , Budi;Budi\nCi ") == ["Budi", "Ci"]


def test_forbidden_terms_and_crisis_detection():
    assert an.diagnostic_terms({"x": "Siswa tampak ADHD dan depresi klinis"}) == ["adhd", "depresi klinis"]
    assert an.diagnostic_terms({"x": "Siswa tampak kurang fokus"}) == []
    assert an.has_crisis("anak ini sering dipukul di rumah") and not an.has_crisis("anak ini suka menggambar")


# ---------------------------------------------------------------- sensitive tools end to end
@pytest.fixture
def env(pg_client, pg, monkeypatch):
    from app.core import config

    monkeypatch.setenv("PROVIDER_KEY_MASTER", "test-master")
    config.get_settings.cache_clear()
    reset_fake()
    monkeypatch.setattr(eng, "RETRY_BACKOFF", (0, 0))
    with pg() as db:
        setup_ai(db)
        seed_all(db)
        m = db.scalar(select(AiModel))
        for t in db.scalars(select(AiTool)):
            if t.slug != "tp-generator":
                db.add(AiToolModelAssignment(tool_id=t.id, model_id=m.id, priority=0))
        db.commit()
    return pg_client, pg, login(pg_client, pg, "t@x.id"), login(pg_client, pg, "o@x.id")


SENS_IN = {"education_level": "SD/MI", "curriculum": "Kurikulum Merdeka", "subject": "Matematika", "grade": "4", "topic": "Pecahan",
           "observations": OBS, "student_names": "Rina"}
GOOD = {"ringkasan": "[SISWA_1] membutuhkan pendampingan.", "pola_yang_teramati": ["Sering terlambat"], "faktor_pembelajaran": ["Materi abstrak"],
        "strategi_pendampingan": ["Gunakan alat peraga"], "tindak_lanjut_guru": ["Pantau [SISWA_1] mingguan"], "peringatan": "Ini saran, bukan diagnosis."}


def gen(c, h, slug, body, key="sens-key-0001"):
    return c.post(f"{A}/tools/{slug}/generate", json={"input": body}, headers={**h, "Idempotency-Key": key})


def test_consent_is_required_then_granted_and_revocable(env):
    c, pg, h, _ = env
    assert c.get(f"{A}/me/consents", headers=h).json()["student_data"] is False
    r = gen(c, h, "analisis-kesulitan-belajar", SENS_IN)
    assert r.status_code == 403 and r.json()["detail"] == "consent_required"
    assert D(c.get(f"{A}/credits/summary", headers=h).json()["total"]) == D("10.00")  # nothing was held
    assert c.post(f"{A}/me/consents", json={"type": "student_data"}, headers=h).status_code == 201
    FakeProvider.script = [json.dumps(GOOD)]
    assert gen(c, h, "analisis-kesulitan-belajar", SENS_IN).status_code == 202
    c.delete(f"{A}/me/consents/student_data", headers=h)
    assert gen(c, h, "analisis-kesulitan-belajar", SENS_IN, "sens-key-0002").status_code == 403


def test_provider_never_sees_names_or_identifiers_but_owner_does(env):
    c, pg, h, _ = env
    c.post(f"{A}/me/consents", json={"type": "student_data"}, headers=h)
    FakeProvider.script = [json.dumps(GOOD)]
    r = gen(c, h, "analisis-kesulitan-belajar", SENS_IN).json()
    sent = FakeProvider.calls[0].user
    for secret in ("Rina", "0812-3456-7890", "081234567890", "ibu.rina@mail.com", "1234567890"):
        assert secret not in sent, secret
    assert "[SISWA_1]" in sent and "[EMAIL]" in sent
    got = c.get(f"{A}/ai/requests/{r['id']}", headers=h).json()
    assert got["status"] == "succeeded" and "Rina membutuhkan pendampingan." in json.dumps(got["output"])  # owner sees real name
    with pg() as db:  # what is stored at rest is anonymized; the name map is encrypted
        req = db.scalar(select(AiRequest))
        assert "Rina" not in json.dumps(req.input) and "Rina" not in json.dumps(req.output) and req.anon_map_enc and "Rina" not in req.anon_map_enc
        assert "student_names" not in req.input
    d = c.get(f"{A}/documents/{got['document_id']}", headers=h).json()
    assert "Rina" in json.dumps(d["content"]) and d["input"]["student_names"] == "Rina"


def test_diagnostic_labels_are_blocked_and_refunded(env):
    c, pg, h, _ = env
    c.post(f"{A}/me/consents", json={"type": "student_data"}, headers=h)
    bad = {**GOOD, "ringkasan": "[SISWA_1] kemungkinan mengalami ADHD."}
    FakeProvider.script = [json.dumps(bad), json.dumps(bad)]
    r = gen(c, h, "analisis-kesulitan-belajar", SENS_IN).json()
    got = c.get(f"{A}/ai/requests/{r['id']}", headers=h).json()
    assert got["status"] == "failed" and got["error_code"] == "malformed_output" and got["output"] is None
    assert D(c.get(f"{A}/credits/summary", headers=h).json()["total"]) == D("10.00")
    FakeProvider.script = [json.dumps(bad), json.dumps(GOOD)]  # the repair attempt succeeds
    ok = gen(c, h, "analisis-kesulitan-belajar", SENS_IN, "sens-key-0003").json()
    assert c.get(f"{A}/ai/requests/{ok['id']}", headers=h).json()["status"] == "succeeded"


def test_crisis_notes_get_a_fixed_safety_notice_in_output_and_export(env):
    c, pg, h, _ = env
    c.post(f"{A}/me/consents", json={"type": "student_data"}, headers=h)
    FakeProvider.script = [json.dumps(GOOD)]
    body = {**SENS_IN, "observations": "Rina bercerita sering dipukul di rumah dan tampak takut. Perlu bantuan guru."}
    r = gen(c, h, "analisis-kesulitan-belajar", body).json()
    got = c.get(f"{A}/ai/requests/{r['id']}", headers=h).json()
    assert "BK" in got["output"]["_safety"]
    exp = c.get(f"{A}/documents/{got['document_id']}/export?format=docx", headers=h).content
    from docx import Document as D_
    text = "\n".join(p.text for p in D_(io.BytesIO(exp)).paragraphs) + "\n".join(p.text for p in D_(io.BytesIO(exp)).sections[0].footer.paragraphs)
    assert "guru BK" in text and "SARAN, BUKAN DIAGNOSIS" in text and "Bukan diagnosis medis" in text


def test_retention_purge_and_erasure(env):
    c, pg, h, other = env
    for who in (h, other):
        c.post(f"{A}/me/consents", json={"type": "student_data"}, headers=who)
    FakeProvider.script = [json.dumps(GOOD), json.dumps(GOOD)]
    r1 = gen(c, h, "analisis-kesulitan-belajar", SENS_IN).json()
    gen(c, other, "analisis-kesulitan-belajar", SENS_IN, "sens-other-001")
    from datetime import timedelta

    from app.core.db import utcnow
    from app.privacy import service as ps
    with pg() as db:
        assert ps.purge_request_data(db, older_than_days=30) == 0  # too recent
        db.query(AiRequest).update({"created_at": utcnow() - timedelta(days=45)})
        db.commit()
        assert ps.purge_request_data(db, older_than_days=30) == 2
        db.commit()
        assert all(r.input == {} and r.output is None and r.anon_map_enc is None for r in db.query(AiRequest))
        assert db.query(Document).count() == 2  # purge does not touch the users' own documents
    out = c.post(f"{A}/me/student-data/delete", headers=h).json()
    assert out["documents"] == 1
    with pg() as db:
        mine = db.scalar(select(Document).join(User, User.id == Document.user_id).where(User.email == "t@x.id"))
        assert mine.is_deleted and mine.input == {} and all(v.content == {} for v in db.query(DocumentVersion).filter_by(document_id=mine.id))
        theirs = db.scalar(select(Document).join(User, User.id == Document.user_id).where(User.email == "o@x.id"))
        assert not theirs.is_deleted and theirs.input  # other users untouched
    assert c.get(f"{A}/documents/{r1['id']}", headers=h).status_code in (404, 422)


# ---------------------------------------------------------------- subscription-gated tools
def test_tools_can_require_a_subscription(env):
    c, pg, h, _ = env
    with pg() as db:
        db.query(AiTool).filter_by(slug="rpp").update({"requires_subscription": True})
        db.commit()
    body = {"education_level": "SD/MI", "curriculum": "K13", "subject": "IPA", "grade": "4", "topic": "Cahaya"}
    r = c.post(f"{A}/tools/rpp/generate", json={"input": body}, headers={**h, "Idempotency-Key": "gate-key-0001"})
    assert r.status_code == 403 and r.json()["detail"] == "subscription_required"
    assert c.get(f"{A}/tools/rpp", headers=h).json()["requires_subscription"] is True
    assert D(c.get(f"{A}/credits/summary", headers=h).json()["total"]) == D("10.00")
    root = login(c, pg, "root@x.id", "super_admin")
    tid = next(t["id"] for t in c.get(f"{A}/admin/tools", headers=root).json() if t["slug"] == "rpp")
    assert c.patch(f"{A}/admin/tools/{tid}", json={"requires_subscription": False}, headers=root).json()["requires_subscription"] is False


# ---------------------------------------------------------------- assistant
def say(c, h, cid, text, key):
    return c.post(f"{A}/assistant/conversations/{cid}/messages", json={"content": text}, headers={**h, "Idempotency-Key": key})


def reply(answer="Gunakan metode think-pair-share.", tips=()):
    return json.dumps({"jawaban": answer, "saran_tindak_lanjut": list(tips)})


def test_conversation_flow_context_credits_and_privacy(env):
    c, pg, h, other = env
    cid = c.post(f"{A}/assistant/conversations", headers=h).json()["id"]
    FakeProvider.script = [reply(tips=["Coba di kelas 4A"])]
    r = say(c, h, cid, "Bagaimana membuat siswa aktif? Hubungi saya di 081234567890", "chat-key-0001")
    assert r.status_code == 202
    conv = c.get(f"{A}/assistant/conversations/{cid}", headers=h).json()
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant"] and "think-pair-share" in conv["messages"][1]["content"] and "Coba di kelas 4A" in conv["messages"][1]["content"]
    assert conv["title"].startswith("Bagaimana membuat siswa aktif")
    assert "081234567890" not in FakeProvider.calls[0].user and "[TELEPON]" in FakeProvider.calls[0].user  # identifiers scrubbed even in chat
    assert D(c.get(f"{A}/credits/summary", headers=h).json()["total"]) == D("9.00")  # 1 credit per message (default rule)
    FakeProvider.script = [reply("Jawaban kedua")]
    say(c, h, cid, "Lanjutkan dengan contoh", "chat-key-0002")
    assert "think-pair-share" in FakeProvider.calls[1].user  # earlier turns are sent as context
    assert say(c, h, cid, "Lanjutkan dengan contoh", "chat-key-0002").status_code == 202  # retry: no duplicate message/charge
    assert len(c.get(f"{A}/assistant/conversations/{cid}", headers=h).json()["messages"]) == 4
    assert D(c.get(f"{A}/credits/summary", headers=h).json()["total"]) == D("8.00")
    assert c.post(f"{A}/assistant/conversations/{cid}/messages", json={"content": "x"}, headers=h).status_code == 400  # key required
    assert c.post(f"{A}/assistant/conversations/{cid}/messages", json={"content": ""}, headers={**h, "Idempotency-Key": "chat-key-0009"}).status_code == 422


def test_assistant_is_private_deletable_and_hidden_from_the_tool_catalogue(env):
    c, pg, h, other = env
    cid = c.post(f"{A}/assistant/conversations", headers=h).json()["id"]
    FakeProvider.script = [reply()]
    say(c, h, cid, "Halo", "chat-key-0101")
    for method, path in (("get", ""), ("delete", ""), ("patch", "")):
        kw = {"json": {"title": "x"}} if method == "patch" else {}
        assert getattr(c, method)(f"{A}/assistant/conversations/{cid}{path}", headers=other, **kw).status_code == 404
    assert say(c, other, cid, "intip", "chat-key-0102").status_code == 404
    assert c.get(f"{A}/assistant/conversations", headers=other).json() == []
    assert "asisten-guru" not in [t["slug"] for t in c.get(f"{A}/tools", headers=h).json()]
    assert c.patch(f"{A}/assistant/conversations/{cid}", json={"title": "Judul saya"}, headers=h).json()["title"] == "Judul saya"
    assert c.delete(f"{A}/assistant/conversations/{cid}", headers=h).status_code == 204
    assert c.get(f"{A}/assistant/conversations/{cid}", headers=h).status_code == 404
    with pg() as db:
        from app.assistant.models import Message
        assert db.query(Message).count() == 0  # really deleted


def test_assistant_failure_costs_nothing_and_out_of_credits_is_402(env):
    c, pg, h, _ = env
    cid = c.post(f"{A}/assistant/conversations", headers=h).json()["id"]
    FakeProvider.script = ["bukan json", "tetap bukan json"]
    say(c, h, cid, "Halo", "chat-key-0201")
    assert D(c.get(f"{A}/credits/summary", headers=h).json()["total"]) == D("10.00")
    assert [m["role"] for m in c.get(f"{A}/assistant/conversations/{cid}", headers=h).json()["messages"]] == ["user"]  # no fake answer
    FakeProvider.script = [reply()] * 12
    codes = [say(c, h, cid, f"Pesan {i}", f"chat-many-{i:04d}").status_code for i in range(12)]
    assert codes.count(202) == 10 and codes[-1] == 402


# ---------------------------------------------------------------- PPTX export
def test_pptx_export_has_a_slide_per_slide_and_notes_and_nothing_is_cut(env):
    c, pg, h, _ = env
    slides = {"judul": "Fotosintesis", "slide": [{"judul": f"Bagian {i}", "poin": [f"Poin {i}-{j}" for j in range(9)], "catatan_pembicara": f"Catatan {i}"} for i in (1, 2, 3)]}
    FakeProvider.script = [json.dumps(slides)]
    body = {"education_level": "SMP/MTs", "curriculum": "K13", "subject": "IPA", "grade": "8", "topic": "Fotosintesis", "slide_count": 3}
    r = gen(c, h, "konten-presentasi", body, "ppt-key-00001").json()
    did = c.get(f"{A}/ai/requests/{r['id']}", headers=h).json()["document_id"]
    resp = c.get(f"{A}/documents/{did}/export?format=pptx", headers=h)
    assert resp.status_code == 200 and "presentationml" in resp.headers["content-type"]
    prs = Presentation(io.BytesIO(resp.content))
    text = "\n".join(sh.text_frame.text for sl in prs.slides for sh in sl.shapes if sh.has_text_frame)
    assert len(prs.slides) >= 4 and all(f"Poin {i}-8" in text for i in (1, 2, 3)) and "Catatan 3" in text and "(lanjutan)" in text  # long slides continue
    assert c.get(f"{A}/documents/{did}/export?format=exe", headers=h).status_code == 422


def test_server_generated_ids_are_never_scrubbed_even_if_they_look_like_a_nisn(env):
    """Regression: a conversation id containing 10 consecutive digits was rewritten to [NISN] and the reply could not be stored."""
    import uuid

    from app.assistant.models import Conversation

    c, pg, h, _ = env
    with pg() as db:
        uid = db.scalar(select(User.id).where(User.email == "t@x.id"))
        cid = uuid.UUID("a1b2c3d4-e5f6-4a8b-9c0d-1234567890ab")
        db.add(Conversation(id=cid, user_id=uid))
        db.commit()
    assert an.NISN.search(str(cid))  # the trap is real
    FakeProvider.script = [reply("Berhasil")]
    assert say(c, h, str(cid), "Halo", "chat-key-0301").status_code == 202
    msgs = c.get(f"{A}/assistant/conversations/{cid}", headers=h).json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant"]
