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


BUILDERS: dict[str, Callable[[dict, dict], Doc]] = {"tp-generator": build_tp}


def build(slug: str, title: str, inp: dict, out: dict) -> Doc:
    fn = BUILDERS.get(slug)
    return fn(inp, out) if fn else build_generic(title, inp, out)
