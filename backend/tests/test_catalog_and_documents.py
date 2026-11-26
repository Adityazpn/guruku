import io
import json

import jsonschema
import pytest
from docx import Document as DocxDocument
from jinja2 import StrictUndefined
from jinja2.sandbox import SandboxedEnvironment
from pypdf import PdfReader
from sqlalchemy import select

from app.ai_engine import engine as eng
from app.ai_engine.catalog import POST_CHECKS, TOOLS, seed_all, tmpl
from app.ai_engine.models import AiTool
from app.ai_providers.adapters.fake import FakeProvider
from app.documents.builders import build
from app.documents.render_docx import render_docx
from app.documents.render_pdf import render_pdf
from tests.aihelpers import reset_fake, setup_ai
from tests.test_admin import login

BASE = {"education_level": "SMP/MTs", "curriculum": "Kurikulum Merdeka", "subject": "IPA", "grade": "8", "topic": "Getaran dan Gelombang"}
EXTRA = {"soal-pilihan-ganda": {"count": 3, "option_count": "4"}, "soal-esai": {"count": 2}, "rubrik-penilaian": {"assessment_type": "Presentasi", "level_count": "3"}}


def instance(sc):
    t = sc.get("type")
    if "enum" in sc:
        return sc["enum"][0]
    if t == "object":
        return {k: instance(v) for k, v in sc["properties"].items()}
    if t == "array":
        return [instance(sc["items"]) for _ in range(max(sc.get("minItems", 1), 1))]
    return max(sc.get("minimum", 1), 1) if t == "integer" else "Teks contoh bahasa Indonesia"


def sample(slug):
    o = next(t["output"] for t in TOOLS if t["slug"] == slug)
    out = instance(o)
    if slug == "soal-pilihan-ganda":
        out["soal"] = [{**out["soal"][0], "nomor": i, "opsi": {k: f"Opsi {k}" for k in "ABCD"}, "kunci": "B"} for i in (1, 2, 3)]
    if slug == "soal-esai":
        out["soal"] = [{**out["soal"][0], "nomor": i} for i in (1, 2)]
    if slug == "rubrik-penilaian":
        out["kriteria"] = [{"kriteria": "Isi", "level": [{"nama": n, "skor": s, "deskripsi": f"Deskripsi {n}"} for n, s in (("Baik", 3), ("Cukup", 2), ("Kurang", 1))]}]
    if slug == "atp":
        out["alur"] = [{**out["alur"][0], "urutan": i} for i in (1, 2)]
    return out


@pytest.mark.parametrize("t", TOOLS, ids=[t["slug"] for t in TOOLS])
def test_every_tool_is_coherent_and_exports_complete_documents(t):
    slug = t["slug"]
    # schemas are valid, prompt compiles and renders for a typical teacher input
    jsonschema.Draft202012Validator.check_schema(t["input"])
    jsonschema.Draft202012Validator.check_schema(t["output"])
    inp = {**BASE, **EXTRA.get(slug, {})}
    jsonschema.validate(inp, t["input"])
    env = SandboxedEnvironment(undefined=StrictUndefined)
    prompt = env.from_string(tmpl(t["task"], t["output"], t["rules"])).render(input=inp, input_json=json.dumps(inp))
    assert "Getaran dan Gelombang" in prompt and "JSON" in prompt
    # a valid output passes schema + completeness check, and both exports contain its content
    out = sample(slug)
    jsonschema.validate(out, t["output"])
    if slug in POST_CHECKS:
        POST_CHECKS[slug](inp, out)
    doc = build(slug, t["name"], inp, out)
    txt = "\n".join(p.text for p in DocxDocument(io.BytesIO(render_docx(doc))).paragraphs)
    txt += "\n".join(c.text for tb in DocxDocument(io.BytesIO(render_docx(doc))).tables for r in tb.rows for c in r.cells)
    assert "Teks contoh bahasa Indonesia" in txt or slug in ("soal-pilihan-ganda", "rubrik-penilaian") or "Opsi" in txt
    pdf = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(render_pdf(doc))).pages)
    assert len(pdf) > 100


def test_completeness_checks_reject_wrong_outputs():
    pg_in = {"count": 3, "option_count": "4"}
    good = sample("soal-pilihan-ganda")
    POST_CHECKS["soal-pilihan-ganda"](pg_in, good)
    for mutate in (lambda o: o["soal"].pop(), lambda o: o["soal"][0].update(kunci="E"), lambda o: o["soal"][1].update(nomor=7),
                   lambda o: o["soal"][0]["opsi"].update(E="x")):
        bad = json.loads(json.dumps(good))
        mutate(bad)
        with pytest.raises((ValueError, KeyError)):
            POST_CHECKS["soal-pilihan-ganda"](pg_in, bad)
    with pytest.raises(ValueError):
        POST_CHECKS["atp"]({}, {"alur": [{"urutan": 2}]})
    with pytest.raises(ValueError):
        POST_CHECKS["rubrik-penilaian"]({"level_count": "5"}, sample("rubrik-penilaian"))


def test_seed_all_is_idempotent_and_never_overwrites_admin_edits(pg):
    with pg() as db:
        assert len(seed_all(db)) == len(TOOLS)
        db.commit()
        db.scalar(select(AiTool).where(AiTool.slug == "rpp")).name = "Nama kustom admin"
        db.commit()
        assert seed_all(db) == []
        db.commit()
        assert db.scalar(select(AiTool).where(AiTool.slug == "rpp")).name == "Nama kustom admin"


# ---------------------------------------------------------------- generation with count enforcement
PW = "correct-horse-battery"


@pytest.fixture
def env(pg_client, pg, monkeypatch):
    reset_fake()
    monkeypatch.setattr(eng, "RETRY_BACKOFF", (0, 0))
    with pg() as db:
        setup_ai(db)  # tp-generator + fake provider/model/prices
        seed_all(db)  # every other tool
        from app.ai_providers.models import AiModel, AiToolModelAssignment
        m = db.scalar(select(AiModel))
        for t in db.scalars(select(AiTool)):
            if t.slug != "tp-generator":
                db.add(AiToolModelAssignment(tool_id=t.id, model_id=m.id, priority=0))
        db.commit()
    c = pg_client
    return c, login(c, pg, "t@x.id"), login(c, pg, "other@x.id")


def gen(c, h, slug, body, key):
    return c.post(f"/api/v1/tools/{slug}/generate", json={"input": body}, headers={**h, "Idempotency-Key": key}).json()


def test_mcq_with_wrong_question_count_is_repaired_or_refunded(env):
    c, h, _ = env
    inp = {**BASE, **EXTRA["soal-pilihan-ganda"]}
    short = json.loads(json.dumps(sample("soal-pilihan-ganda")))
    short["soal"].pop()
    FakeProvider.script = [json.dumps(short), json.dumps(sample("soal-pilihan-ganda"))]  # wrong count, then fixed by the repair call
    r = gen(c, h, "soal-pilihan-ganda", inp, "mcq-key-0001")
    assert c.get(f"/api/v1/ai/requests/{r['id']}", headers=h).json()["status"] == "succeeded"
    FakeProvider.script = [json.dumps(short), json.dumps(short)]  # never fixed
    bal = float(c.get("/api/v1/credits/summary", headers=h).json()["total"])
    r2 = gen(c, h, "soal-pilihan-ganda", inp, "mcq-key-0002")
    got = c.get(f"/api/v1/ai/requests/{r2['id']}", headers=h).json()
    assert got["status"] == "failed" and got["error_code"] == "malformed_output"
    assert float(c.get("/api/v1/credits/summary", headers=h).json()["total"]) == bal  # not charged for an incomplete exam


# ---------------------------------------------------------------- documents API
def make_doc(c, h, key="doc-gen-0001", slug="rpp"):
    FakeProvider.script = [json.dumps(sample(slug))]
    r = gen(c, h, slug, BASE, key)
    got = c.get(f"/api/v1/ai/requests/{r['id']}", headers=h).json()
    assert got["status"] == "succeeded" and got["document_id"]
    return got["document_id"]


def test_generation_creates_a_document_with_version_1(env):
    c, h, _ = env
    d = c.get(f"/api/v1/documents/{make_doc(c, h)}", headers=h).json()
    assert d["version"] == 1 and d["tool_slug"] == "rpp" and d["content"]["materi_pokok"] and d["output_schema"]["required"]
    assert c.get("/api/v1/documents", headers=h).json()["total"] == 1


def test_edit_creates_versions_with_conflict_detection(env):
    c, h, _ = env
    did = make_doc(c, h)
    d = c.get(f"/api/v1/documents/{did}", headers=h).json()
    content = d["content"]
    content["materi_pokok"] = "Materi yang saya sunting sendiri"
    ok = c.patch(f"/api/v1/documents/{did}", json={"content": content, "base_version": 1, "note": "revisi"}, headers=h)
    assert ok.status_code == 200 and ok.json()["version"] == 2
    stale = c.patch(f"/api/v1/documents/{did}", json={"content": content, "base_version": 1}, headers=h)  # editor from another tab
    assert stale.status_code == 409 and stale.json()["detail"] == "version_conflict"
    vs = c.get(f"/api/v1/documents/{did}/versions", headers=h).json()
    assert [(v["version"], v["source"]) for v in vs] == [(2, "edit"), (1, "ai")]
    assert c.patch(f"/api/v1/documents/{did}", json={"title": "Judul baru", "base_version": 2}, headers=h).json()["title"] == "Judul baru"
    assert c.patch(f"/api/v1/documents/{did}", json={"base_version": 2}, headers=h).status_code == 422


def test_invalid_edit_is_rejected_so_export_cannot_break(env):
    c, h, _ = env
    did = make_doc(c, h)
    content = c.get(f"/api/v1/documents/{did}", headers=h).json()["content"]
    del content["materi_pokok"]
    assert c.patch(f"/api/v1/documents/{did}", json={"content": content, "base_version": 1}, headers=h).status_code == 422
    content["materi_pokok"] = "ok"
    content["kegiatan"]["inti"] = []  # minItems violated
    assert c.patch(f"/api/v1/documents/{did}", json={"content": content, "base_version": 1}, headers=h).status_code == 422
    assert c.get(f"/api/v1/documents/{did}", headers=h).json()["version"] == 1


def test_restore_duplicate_delete_and_isolation(env):
    c, h, other = env
    did = make_doc(c, h)
    d = c.get(f"/api/v1/documents/{did}", headers=h).json()
    d["content"]["materi_pokok"] = "Versi dua"
    c.patch(f"/api/v1/documents/{did}", json={"content": d["content"], "base_version": 1}, headers=h)
    r = c.post(f"/api/v1/documents/{did}/restore", json={"version": 1}, headers=h).json()
    assert r["version"] == 3 and r["content"]["materi_pokok"] != "Versi dua"  # restored as a NEW version, history intact
    assert len(c.get(f"/api/v1/documents/{did}/versions", headers=h).json()) == 3
    assert c.post(f"/api/v1/documents/{did}/restore", json={"version": 99}, headers=h).status_code == 404
    dup = c.post(f"/api/v1/documents/{did}/duplicate", headers=h).json()
    assert dup["id"] != did and dup["title"].endswith("(salinan)") and dup["version"] == 1
    # another teacher sees nothing and can change nothing
    for method, path, body in (("get", f"/{did}", None), ("patch", f"/{did}", {"title": "x", "base_version": 1}), ("delete", f"/{did}", None),
                               ("post", f"/{did}/duplicate", None), ("get", f"/{did}/versions", None), ("get", f"/{did}/export", None)):
        assert getattr(c, method)(f"/api/v1/documents{path}", headers=other, **({"json": body} if body else {})).status_code == 404, path
    assert c.get("/api/v1/documents", headers=other).json()["total"] == 0
    assert c.delete(f"/api/v1/documents/{did}", headers=h).status_code == 204
    assert c.get(f"/api/v1/documents/{did}", headers=h).status_code == 404
    assert c.get("/api/v1/documents", headers=h).json()["total"] == 1  # the duplicate remains


def test_export_uses_edited_content_and_logs_download(env, pg):
    c, h, _ = env
    did = make_doc(c, h)
    d = c.get(f"/api/v1/documents/{did}", headers=h).json()
    d["content"]["materi_pokok"] = "MATERI-HASIL-EDIT-GURU"
    c.patch(f"/api/v1/documents/{did}", json={"content": d["content"], "base_version": 1}, headers=h)
    new = c.get(f"/api/v1/documents/{did}/export?format=docx", headers=h)
    old = c.get(f"/api/v1/documents/{did}/export?format=docx&version=1", headers=h)
    text = lambda b: "\n".join(p.text for p in DocxDocument(io.BytesIO(b)).paragraphs)  # noqa: E731
    assert "MATERI-HASIL-EDIT-GURU" in text(new.content) and "MATERI-HASIL-EDIT-GURU" not in text(old.content)
    assert c.get(f"/api/v1/documents/{did}/export?format=pdf", headers=h).content[:4] == b"%PDF"
    with pg() as db:
        assert sorted((x.version_no, x.format) for x in db.query(__import__("app.documents.models", fromlist=["x"]).DocumentDownload)) == [(1, "docx"), (2, "docx"), (2, "pdf")]


def test_regenerate_adds_a_version_and_charges_like_a_generation(env):
    c, h, _ = env
    did = make_doc(c, h)
    before = float(c.get("/api/v1/credits/summary", headers=h).json()["total"])
    new_out = sample("rpp")
    new_out["materi_pokok"] = "Materi hasil regenerasi"
    FakeProvider.script = [json.dumps(new_out)]
    assert c.post(f"/api/v1/documents/{did}/regenerate", headers=h).status_code == 400  # needs Idempotency-Key
    r = c.post(f"/api/v1/documents/{did}/regenerate", headers={**h, "Idempotency-Key": "regen-key-0001"})
    assert r.status_code == 202
    d = c.get(f"/api/v1/documents/{did}", headers=h).json()
    assert d["version"] == 2 and d["content"]["materi_pokok"] == "Materi hasil regenerasi"
    assert float(c.get("/api/v1/credits/summary", headers=h).json()["total"]) == before - 3  # rpp default fixed cost 3
    assert c.get("/api/v1/documents", headers=h).json()["total"] == 1  # still one document
    assert c.post(f"/api/v1/documents/{did}/regenerate", headers={**h, "Idempotency-Key": "regen-key-0001"}).status_code == 202  # retry is harmless
    assert float(c.get("/api/v1/credits/summary", headers=h).json()["total"]) == before - 3


def test_documents_pagination_and_search(env):
    c, h, _ = env
    for i in range(3):
        make_doc(c, h, key=f"many-docs-{i:04d}")
    assert c.get("/api/v1/documents?page_size=2", headers=h).json()["total"] == 3
    assert len(c.get("/api/v1/documents?page_size=2&page=2", headers=h).json()["items"]) == 1
    assert c.get("/api/v1/documents?q=zzz", headers=h).json()["total"] == 0
    assert c.get("/api/v1/documents?page_size=500", headers=h).status_code == 422
