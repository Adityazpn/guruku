"""Tool output -> Doc. One builder per tool slug; unknown tools fall back to a generic JSON walk so that an export
never silently drops content."""
from collections.abc import Callable

from app.documents.model import Block, Doc

LABELS = {"education_level": "Jenjang", "curriculum": "Kurikulum", "subject": "Mata Pelajaran", "grade": "Kelas/Fase",
          "semester": "Semester", "topic": "Topik"}


def _meta(inp: dict) -> list[tuple[str, str]]:
    return [(LABELS[k], str(inp[k])) for k in LABELS if inp.get(k)]


def build_tp(inp: dict, out: dict) -> Doc:
    blocks = [Block("heading", "Tujuan Pembelajaran", level=1)]
    for i, tp in enumerate(out.get("tujuan_pembelajaran", []), 1):
        head = f"TP {i}" + (f" ({tp['level_kognitif']})" if tp.get("level_kognitif") else "")
        blocks += [Block("heading", head, level=2), Block("paragraph", tp["tujuan"]),
                   Block("paragraph", "Indikator pencapaian:"), Block("bullets", items=list(tp.get("indikator", [])))]
    if out.get("catatan"):
        blocks += [Block("heading", "Catatan untuk guru", level=2), Block("paragraph", out["catatan"])]
    return Doc("Tujuan Pembelajaran", _meta(inp), blocks)


def _generic(title: str, value, level: int = 1) -> list[Block]:
    out: list[Block] = []
    if isinstance(value, dict):
        for k, v in value.items():
            out.append(Block("heading", str(k).replace("_", " ").title(), level=min(level + 1, 3)))
            out += _generic(title, v, level + 1)
    elif isinstance(value, list):
        if all(not isinstance(x, (dict, list)) for x in value):
            out.append(Block("bullets", items=[str(x) for x in value]))
        else:
            for x in value:
                out += _generic(title, x, level + 1)
    elif value is not None:
        out.append(Block("paragraph", str(value)))
    return out


def build_generic(title: str, inp: dict, out: dict) -> Doc:
    return Doc(title, _meta(inp), _generic(title, out))


def _h(t, lvl=2):
    return Block("heading", t, level=lvl)


def _p(t):
    return Block("paragraph", t)


def _ul(items):
    return Block("bullets", items=[str(i) for i in items])


def _kegiatan(k):
    return [_h("Kegiatan Pembelajaran", 1), _h("Pendahuluan"), _ul(k["pendahuluan"]), _h("Kegiatan Inti"), _ul(k["inti"]), _h("Penutup"), _ul(k["penutup"])]


def build_modul(inp, o):
    i = o["identitas"]
    b = [_h("Identitas Modul", 1), Block("table", rows=[["Mata pelajaran", i["mata_pelajaran"]], ["Kelas", i["kelas"]], ["Alokasi waktu", i["alokasi_waktu"]]]),
         _h("Kompetensi Awal"), _p(o["kompetensi_awal"]), _h("Dimensi Profil yang Dikembangkan"), _ul(o["dimensi_profil"]),
         _h("Sarana dan Prasarana"), _ul(o["sarana_prasarana"]), _h("Target Peserta Didik"), _p(o["target_peserta_didik"]),
         _h("Model Pembelajaran"), _p(o["model_pembelajaran"]), _h("Tujuan Pembelajaran", 1), _ul(o["tujuan_pembelajaran"]),
         _h("Pemahaman Bermakna"), _ul(o["pemahaman_bermakna"]), _h("Pertanyaan Pemantik"), _ul(o["pertanyaan_pemantik"]), *_kegiatan(o["kegiatan"]),
         _h("Asesmen", 1), _h("Diagnostik"), _p(o["asesmen"]["diagnostik"]), _h("Formatif"), _p(o["asesmen"]["formatif"]), _h("Sumatif"), _p(o["asesmen"]["sumatif"]),
         _h("Pengayaan dan Remedial", 1), _h("Pengayaan"), _p(o["pengayaan_remedial"]["pengayaan"]), _h("Remedial"), _p(o["pengayaan_remedial"]["remedial"]),
         _h("Refleksi", 1), _h("Refleksi Guru"), _ul(o["refleksi"]["guru"]), _h("Refleksi Peserta Didik"), _ul(o["refleksi"]["peserta_didik"])]
    return Doc("Modul Ajar", _meta(inp), b)


def build_rpp(inp, o):
    i, p = o["identitas"], o["penilaian"]
    b = [_h("Identitas", 1), Block("table", rows=[["Mata pelajaran", i["mata_pelajaran"]], ["Kelas", i["kelas"]], ["Alokasi waktu", i["alokasi_waktu"]]]),
         _h("Tujuan Pembelajaran", 1), _ul(o["tujuan_pembelajaran"]), _h("Materi Pokok"), _p(o["materi_pokok"]), _h("Metode"), _ul(o["metode"]),
         _h("Media dan Alat"), _ul(o["media_alat"]), *_kegiatan(o["kegiatan"]), _h("Penilaian", 1),
         Block("table", rows=[["Aspek", "Teknik/Instrumen"], ["Sikap", p["sikap"]], ["Pengetahuan", p["pengetahuan"]], ["Keterampilan", p["keterampilan"]]]),
         _h("Refleksi", 1), _ul(o["refleksi"])]
    return Doc("Rencana Pelaksanaan Pembelajaran (RPP)", _meta(inp), b)


def build_atp(inp, o):
    rows = [["No", "Tujuan Pembelajaran", "Materi", "Alokasi Waktu", "Asesmen"]] + [[str(a["urutan"]), a["tujuan"], a["materi"], a["alokasi_waktu"], a["asesmen"]] for a in o["alur"]]
    b = [_h("Alur Tujuan Pembelajaran", 1), Block("table", rows=rows)]
    if o.get("catatan"):
        b += [_h("Catatan"), _p(o["catatan"])]
    return Doc("Alur Tujuan Pembelajaran (ATP)", _meta(inp), b)


def build_lkpd(inp, o):
    b = [_h(o["judul"], 1), _h("Tujuan"), _ul(o["tujuan"]), _h("Petunjuk"), _ul(o["petunjuk"]), _h("Alat dan Bahan"), _ul(o["alat_bahan"])]
    for n, k in enumerate(o["kegiatan"], 1):
        b += [_h(f"Kegiatan {n}: {k['judul']}"), _p("Langkah-langkah:"), Block("numbered", items=k["langkah"]), _p("Pertanyaan:"), Block("numbered", items=k["pertanyaan"])]
    b += [_h("Refleksi", 1), _ul(o["refleksi"])]
    return Doc("Lembar Kerja Peserta Didik (LKPD)", _meta(inp), b)


def build_pg(inp, o):
    b = [_h("Soal Pilihan Ganda", 1)]
    for q in o["soal"]:
        b += [_p(f"{q['nomor']}. {q['pertanyaan']}"), _p("\n".join(f"{k}. {v}" for k, v in q["opsi"].items()))]
    rows = [["No", "Kunci", "Level", "Pembahasan"]] + [[str(q["nomor"]), q["kunci"], q["level_kognitif"], q["pembahasan"]] for q in o["soal"]]
    return Doc("Soal Pilihan Ganda", _meta(inp), b + [_h("Kunci Jawaban dan Pembahasan", 1), Block("table", rows=rows)])


def build_esai(inp, o):
    b = [_h("Soal Esai", 1)] + [_p(f"{q['nomor']}. {q['pertanyaan']} (skor maksimal {q['skor_maks']})") for q in o["soal"]] + [_h("Kunci Jawaban dan Rubrik", 1)]
    for q in o["soal"]:
        b += [_h(f"Soal {q['nomor']} ({q['level_kognitif']})"), _p(q["kunci_jawaban"]),
              Block("table", rows=[["Skor", "Deskripsi"]] + [[str(r["skor"]), r["deskripsi"]] for r in q["rubrik"]])]
    return Doc("Soal Esai", _meta(inp), b)


def build_rubrik(inp, o):
    names = [lv["nama"] for lv in o["kriteria"][0]["level"]]
    rows = [["Kriteria"] + [f"{lv['nama']} ({lv['skor']})" for lv in o["kriteria"][0]["level"]]]
    rows += [[k["kriteria"]] + [lv["deskripsi"] for lv in k["level"]] for k in o["kriteria"]]
    return Doc("Rubrik Penilaian", _meta(inp) + [("Jenis penilaian", str(inp.get("assessment_type", "")))], [_h("Rubrik Analitik", 1), Block("table", rows=rows)] if names else [])


BUILDERS: dict[str, Callable[[dict, dict], Doc]] = {
    "tp-generator": build_tp, "modul-ajar": build_modul, "rpp": build_rpp, "atp": build_atp, "lkpd": build_lkpd,
    "soal-pilihan-ganda": build_pg, "soal-esai": build_esai, "rubrik-penilaian": build_rubrik}


SENSITIVE_SLUGS = {"analisis-kesulitan-belajar", "rekomendasi-pembelajaran", "laporan-perkembangan-siswa"}
ADVISORY = ("Dokumen ini adalah SARAN yang dihasilkan AI untuk membantu pertimbangan guru. Bukan diagnosis medis atau psikologis dan bukan dokumen resmi. "
            "Berisi data siswa: simpan dengan aman dan jangan dibagikan tanpa dasar yang sah.")


def build_surat(inp, o):
    b = [_p(f"Nomor\t: {o['nomor']}"), _p(f"Lampiran\t: {o['lampiran']}"), _p(f"Perihal\t: {o['perihal']}"), _p(f"Kepada Yth.\n{o['tujuan']}"),
         _p(o["pembuka"]), *[_p(x) for x in o["isi"]], _p(o["penutup"]), _p(f"Hormat kami,\n\n\n{o['penandatangan']}")]
    return Doc(f"Surat: {o['perihal']}", [], b)


def build_jurnal(inp, o):
    rows = [["Pertemuan", "Materi", "Kegiatan", "Capaian", "Catatan"]] + [[str(e["pertemuan"]), e["materi"], e["kegiatan"], e["capaian"], e["catatan"]] for e in o["entri"]]
    return Doc("Jurnal Mengajar", _meta(inp), [_h("Jurnal Mengajar", 1), Block("table", rows=rows)])


def build_slides(inp, o):
    blocks = [_h(o["judul"], 1)]
    for n, sl in enumerate(o["slide"], 1):
        blocks += [_h(f"Slide {n}: {sl['judul']}", 2), _ul(sl["poin"]), _p(f"Catatan pembicara: {sl['catatan_pembicara']}")]
    return Doc(o["judul"], _meta(inp), blocks)


BUILDERS.update({"surat-resmi-sekolah": build_surat, "jurnal-mengajar": build_jurnal, "konten-presentasi": build_slides})


def build(slug: str, title: str, inp: dict, out: dict) -> Doc:
    fn = BUILDERS.get(slug)
    doc = fn(inp, {k: v for k, v in out.items() if k != "_safety"}) if fn else build_generic(title, inp, {k: v for k, v in out.items() if k != "_safety"})
    if slug in SENSITIVE_SLUGS:
        doc.footer = ADVISORY
        doc.blocks.insert(0, _p("SARAN, BUKAN DIAGNOSIS. Gunakan sebagai bahan pertimbangan guru."))
    if out.get("_safety"):
        doc.blocks.insert(0, _p(out["_safety"]))
    return doc
