import io
import os
from datetime import timedelta

import pytest
from docx import Document as DocxDocument
from sqlalchemy import select

from app.core import config, storage
from app.core.db import utcnow
from app.library.models import LibraryAccessLog, LibraryFile
from app.subscriptions.models import Plan, Subscription
from app.users.models import User
from tests.test_admin import login

A = "/api/v1"


def real_docx(text="Isi dokumen contoh") -> bytes:
    b = io.BytesIO()
    d = DocxDocument()
    d.add_paragraph(text)
    d.save(b)
    return b.getvalue()


@pytest.fixture
def lib(pg_client, pg, tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "store"))
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    config.get_settings.cache_clear()
    c = pg_client
    editor = login(c, pg, "editor@x.id", "content_admin")
    assert c.post(f"{A}/admin/library/categories?slug=rpp&name=Template%20RPP", headers=editor).status_code == 201
    assert c.post(f"{A}/admin/library/categories?slug=ebook&name=E-book", headers=editor).status_code == 201
    return c, pg, editor, login(c, pg, "teacher@x.id"), tmp_path / "store"


def make_item(c, h, title="Template RPP Contoh", cat="rpp", **kw):
    r = c.post(f"{A}/admin/library/items", json={"category_slug": cat, "title": title, "description": "Deskripsi", "level": "SD/MI", "subject": "IPA",
                                                  "tags": ["rpp", "contoh"], "is_sample": True, **kw}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def upload(c, h, item, name="rpp.docx", data=None, expect=201):
    r = c.post(f"{A}/admin/library/items/{item}/files", files={"file": (name, data if data is not None else real_docx(), "application/octet-stream")}, headers=h)
    assert r.status_code == expect, r.text
    return r


def publish(c, h, item):
    return c.patch(f"{A}/admin/library/items/{item}", json={"status": "published"}, headers=h)


def test_roles_anonymous_and_teachers_cannot_manage(lib):
    c, pg, editor, teacher, _ = lib
    assert c.get(f"{A}/library/items").status_code == 401
    assert c.get(f"{A}/admin/library/items", headers=teacher).status_code == 403
    assert c.post(f"{A}/admin/library/items", json={"category_slug": "rpp", "title": "xx"}, headers=teacher).status_code == 403
    assert c.post(f"{A}/admin/library/items/{make_item(c, editor)}/files", files={"file": ("a.pdf", b"%PDF-1")}, headers=teacher).status_code == 403


def test_upload_validation(lib):
    c, pg, editor, teacher, store = lib
    item = make_item(c, editor)
    upload(c, editor, item, "malware.exe", b"MZ\x90", 422)
    upload(c, editor, item, "fake.pdf", b"this is not a pdf", 422)  # content must match the extension
    upload(c, editor, item, "fake.docx", b"not a zip", 422)
    upload(c, editor, item, "empty.pdf", b"", 422)
    upload(c, editor, item, "bin.txt", b"\xff\xfe\x00\x80", 422)
    upload(c, editor, item, "big.pdf", b"%PDF" + b"0" * (26 * 1024 * 1024), 422)
    upload(c, editor, item, "noext", b"hello", 422)
    assert c.post(f"{A}/admin/library/items/{item}/files", headers=editor).status_code == 422  # no file at all
    assert not store.exists() or not any(store.rglob("*.*"))  # nothing rejected was ever written


def test_filename_cannot_escape_storage_and_keys_are_random(lib):
    c, pg, editor, teacher, store = lib
    item = make_item(c, editor)
    upload(c, editor, item, "../../../etc/passwd.docx", real_docx())
    with pg() as db:
        f = db.scalar(select(LibraryFile))
        assert "passwd" not in f.storage_key and f.storage_key.startswith("library/") and "/" not in f.filename and ".." not in f.filename
    files = [p for p in store.rglob("*") if p.is_file()]
    assert len(files) == 1 and store.resolve() in files[0].resolve().parents
    with pytest.raises(ValueError):
        storage.LocalStorage(str(store))._path("../../etc/passwd")


def test_visibility_draft_publish_archive_and_search(lib):
    c, pg, editor, teacher, _ = lib
    a, b = make_item(c, editor, "Modul Ajar Fotosintesis", "rpp", subject="IPA"), make_item(c, editor, "Panduan AI untuk Guru", "ebook", subject="")
    assert publish(c, editor, a).status_code == 409  # cannot publish an empty item
    upload(c, editor, a)
    upload(c, editor, b, "panduan.pdf", b"%PDF-1.4 x")
    assert c.get(f"{A}/library/items", headers=teacher).json()["total"] == 0  # drafts are invisible
    assert c.get(f"{A}/library/items/{a}", headers=teacher).status_code == 404
    publish(c, editor, a)
    publish(c, editor, b)
    L = lambda qs="": c.get(f"{A}/library/items{qs}", headers=teacher).json()  # noqa: E731
    assert L()["total"] == 2
    assert [i["title"] for i in L("?q=fotosintesis")["items"]] == ["Modul Ajar Fotosintesis"]
    assert [i["title"] for i in L("?category=ebook")["items"]] == ["Panduan AI untuk Guru"]
    assert L("?tag=CONTOH")["total"] == 2 and L("?tag=zzz")["total"] == 0 and L("?level=SMA/MA")["total"] == 0
    assert L("?page_size=1")["items"].__len__() == 1 and L("?page_size=1&page=2")["items"].__len__() == 1
    assert c.get(f"{A}/library/items?page_size=500", headers=teacher).status_code == 422
    assert all(i["is_sample"] for i in L()["items"])  # sample content stays labelled
    c.patch(f"{A}/admin/library/items/{a}", json={"status": "archived"}, headers=editor)
    assert L()["total"] == 1 and c.post(f"{A}/library/items/{a}/download", headers=teacher).status_code == 404
    assert [c["slug"] for c in c.get(f"{A}/library/categories", headers=teacher).json()] == ["rpp", "ebook"]


def test_download_via_signed_link_logged_and_tamper_proof(lib):
    c, pg, editor, teacher, _ = lib
    item = make_item(c, editor)
    upload(c, editor, item, data=real_docx("ISI-RAHASIA-PUSTAKA"))
    publish(c, editor, item)
    r = c.post(f"{A}/library/items/{item}/download", headers=teacher).json()
    assert r["url"].startswith("/api/v1/library/files/") and r["expires_in"] == 300
    got = c.get(r["url"])  # no login needed: the signature is the credential
    assert got.status_code == 200 and "attachment" in got.headers["content-disposition"] and b"PK" == got.content[:2]
    token = r["url"].rsplit("/", 1)[1]
    assert c.get(f"{A}/library/files/{token[:-3]}abc").status_code == 403  # tampered signature
    assert c.get(f"{A}/library/files/garbage").status_code == 403
    expired = storage.get_storage().signed_url("library/x/y.docx", "a.docx", "application/octet-stream", ttl=-5)
    assert c.get(expired).status_code == 403
    forged = storage.get_storage().signed_url("../../etc/passwd", "p", "text/plain")  # signed by us, but traversal must still fail
    assert c.get(forged).status_code in (403, 404)
    with pg() as db:
        assert db.query(LibraryAccessLog).count() == 1
    assert [h["title"] for h in c.get(f"{A}/library/downloads", headers=teacher).json()] == ["Template RPP Contoh"]
    assert c.post(f"{A}/library/items/{item}/download").status_code == 401


def test_premium_is_enforced_by_the_server(lib):
    c, pg, editor, teacher, _ = lib
    free, prem = make_item(c, editor, "Gratis"), make_item(c, editor, "Premium", access="premium")
    for i in (free, prem):
        upload(c, editor, i)
        publish(c, editor, i)
    items = {i["title"]: i for i in c.get(f"{A}/library/items", headers=teacher).json()["items"]}
    assert items["Premium"]["locked"] is True and items["Gratis"]["locked"] is False
    assert c.post(f"{A}/library/items/{free}/download", headers=teacher).status_code == 200
    r = c.post(f"{A}/library/items/{prem}/download", headers=teacher)
    assert r.status_code == 403 and r.json()["detail"] == "premium_required"
    with pg() as db:  # an active subscription (created here directly; in production only a verified payment can do this)
        u = db.scalar(select(User).where(User.email == "teacher@x.id"))
        p = Plan(code="p", name="P", credits_monthly=1)
        db.add(p)
        db.flush()
        db.add(Subscription(user_id=u.id, plan_id=p.id, cycle="monthly", status="active", period_start=utcnow(), period_end=utcnow() + timedelta(days=30)))
        db.commit()
    assert c.post(f"{A}/library/items/{prem}/download", headers=teacher).status_code == 200
    assert {i["title"]: i["locked"] for i in c.get(f"{A}/library/items", headers=teacher).json()["items"]}["Premium"] is False


def test_new_upload_is_a_new_version_and_latest_is_served(lib):
    c, pg, editor, teacher, store = lib
    item = make_item(c, editor)
    assert upload(c, editor, item, data=real_docx("VERSI-SATU")).json()["version"] == 1
    assert upload(c, editor, item, data=real_docx("VERSI-DUA")).json()["version"] == 2
    publish(c, editor, item)
    url = c.post(f"{A}/library/items/{item}/download", headers=teacher).json()["url"]
    body = c.get(url).content
    assert DocxDocument(io.BytesIO(body)).paragraphs[0].text == "VERSI-DUA"
    assert len([p for p in store.rglob("*") if p.is_file()]) == 2  # the old version is kept
    log = c.get(f"{A}/admin/audit-logs?action=library.file.upload", headers=login(c, pg, "root@x.id", "super_admin")).json()
    assert log["total"] == 2


def test_s3_backend_issues_presigned_attachment_urls_without_network(monkeypatch):
    for k, v in {"STORAGE_BACKEND": "s3", "S3_BUCKET": "guruku-files", "S3_ENDPOINT": "https://s3.example.com", "S3_ACCESS_KEY": "AKIAEXAMPLE",
                 "S3_SECRET_KEY": "secret", "S3_REGION": "auto"}.items():
        monkeypatch.setenv(k, v)
    config.get_settings.cache_clear()
    url = storage.get_storage().signed_url("library/abc/file.pdf", 'na"me.pdf', "application/pdf", ttl=300)
    assert url.startswith("https://s3.example.com/") and "guruku-files" in url and "X-Amz-Expires=300" in url and "X-Amz-Signature=" in url
    assert "attachment" in url and "AKIAEXAMPLE" in url and "secret" not in url.replace("X-Amz-Signature", "")
    config.get_settings.cache_clear()
    assert os.environ["STORAGE_BACKEND"] == "s3"
