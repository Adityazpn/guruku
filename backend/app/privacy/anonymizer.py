"""Removes personal identifiers BEFORE any text is sent to an AI provider.
Names the teacher lists become reversible tokens ([SISWA_1]) restored only in what the owner sees; identifiers matched by pattern
(NIK, NISN, phone, email) are replaced irreversibly. This is a safety net, not a guarantee: free text can still contain identifying details
(the UI tells teachers to use aliases or first names only)."""
import json
import re

from app.core.crypto import decrypt_secret, encrypt_secret

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"(?<!\d)(?:\+?62|0)[\s.-]?8\d{1,2}(?:[\s.-]?\d{3,4}){2,3}(?!\d)")  # 0812-3456-7890, +62 812 3456 7890, 081234567890
NIK = re.compile(r"(?<!\d)\d{16}(?!\d)")
NISN = re.compile(r"(?<!\d)\d{10}(?!\d)")


def parse_names(raw: str | None) -> list[str]:
    seen, out = set(), []
    for n in re.split(r"[,\n;]", raw or ""):
        n = " ".join(n.split())
        if len(n) >= 2 and n.lower() not in seen:
            seen.add(n.lower())
            out.append(n)
    return sorted(out, key=len, reverse=True)  # longest first so "Siti Aminah" is replaced before "Siti"


def _name_forms(names: list[str]) -> list[tuple[str, int]]:
    """(text, student index) for the full name and each name part of 3+ letters."""
    forms = []
    for idx, full in enumerate(names, 1):
        forms.append((full, idx))
        forms += [(p, idx) for p in full.split() if len(p) >= 3 and p.lower() != full.lower()]
    return sorted(forms, key=lambda f: len(f[0]), reverse=True)


def anonymize(value, names: list[str], skip_keys: frozenset[str] = frozenset()):
    """Returns (anonymized value, {token: name}). Works recursively on dict/list/str. `skip_keys` are server-generated fields
    (ids) that must never be touched: a UUID can contain a run of digits that looks like a NISN."""
    forms = _name_forms(names)
    mapping: dict[str, str] = {}

    def scrub(s: str) -> str:
        for pat, tok in ((EMAIL, "[EMAIL]"), (PHONE, "[TELEPON]"), (NIK, "[NIK]"), (NISN, "[NISN]")):
            s = pat.sub(tok, s)
        for text, idx in forms:
            token = f"[SISWA_{idx}]"
            s, n = re.subn(rf"(?<!\w){re.escape(text)}(?!\w)", token, s, flags=re.IGNORECASE)
            if n:
                mapping[token] = names[idx - 1]
        return s

    def walk(v):
        if isinstance(v, str):
            return scrub(v)
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, dict):
            return {k: (x if k in skip_keys else walk(x)) for k, x in v.items()}
        return v

    return walk(value), mapping


def restore(value, mapping: dict[str, str]):
    if not mapping:
        return value
    if isinstance(value, str):
        for tok, name in mapping.items():
            value = value.replace(tok, name)
        return value
    if isinstance(value, list):
        return [restore(x, mapping) for x in value]
    if isinstance(value, dict):
        return {k: restore(x, mapping) for k, x in value.items()}
    return value


def seal(mapping: dict[str, str]) -> str | None:
    return encrypt_secret(json.dumps(mapping, ensure_ascii=False)) if mapping else None


def unseal(blob: str | None) -> dict[str, str]:
    return json.loads(decrypt_secret(blob)) if blob else {}


CRISIS = re.compile(r"bunuh diri|mengakhiri hidup|menyakiti diri|melukai diri|self[- ]?harm|ingin mati|dipukul|kekerasan|dilecehkan|pelecehan|dicabuli|diperkosa|ditelantarkan", re.I)
CRISIS_NOTICE = ("PENTING: Catatan guru menyinggung kemungkinan keselamatan atau kekerasan. Jangan mengandalkan saran AI. Segera hubungi guru BK/konselor sekolah, "
                 "kepala sekolah, dan pihak berwenang atau layanan perlindungan anak yang relevan. Dokumen ini bukan pengganti penanganan profesional.")
FORBIDDEN = re.compile(r"autis|adhd|disleksia|diskalkulia|depresi klinis|gangguan jiwa|gangguan mental|skizofrenia|bipolar|retardasi|keterbelakangan|idiot|psikopat|gangguan kepribadian|gangguan kecemasan", re.I)


def has_crisis(*texts) -> bool:
    return any(CRISIS.search(str(t)) for t in texts if t)


def diagnostic_terms(obj) -> list[str]:
    return sorted({m.group(0).lower() for m in FORBIDDEN.finditer(json.dumps(obj, ensure_ascii=False))})
