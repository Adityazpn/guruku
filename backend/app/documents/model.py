"""Format-independent document model. AI output (JSON) -> Doc -> DOCX / PDF renderers."""
from dataclasses import dataclass, field

DISCLAIMER = ("Dokumen ini adalah draf yang dihasilkan AI dan wajib ditinjau serta disesuaikan oleh guru. "
              "Bukan dokumen resmi dan belum diverifikasi terhadap regulasi.")


@dataclass
class Block:
    kind: str  # heading | paragraph | bullets | numbered | table
    text: str = ""
    items: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)  # table: first row = header
    level: int = 1


@dataclass
class Doc:
    title: str
    meta: list[tuple[str, str]] = field(default_factory=list)  # shown as a small key/value table under the title
    blocks: list[Block] = field(default_factory=list)
    footer: str = DISCLAIMER
