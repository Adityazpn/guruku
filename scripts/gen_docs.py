"""Regenerates docs/DATABASE.md and docs/API_DOCUMENTATION.md from the code (so they cannot drift). Run from backend/:  python ../scripts/gen_docs.py"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import app.models  # noqa: E402,F401
from app.core.db import Base  # noqa: E402
from main import app  # noqa: E402

out = ["# Database schema (generated)\n", "Generated from the SQLAlchemy models by `scripts/gen_docs.py`. See docs/SPEC_02 for design intent.\n",
       "Conventions: UUID primary keys, `timestamptz` UTC, append-only tables (`credit_transactions`, `audit_logs`) are protected by PostgreSQL triggers (migrations 0003, 0005).\n"]
for t in Base.metadata.sorted_tables:
    out.append(f"\n## `{t.name}`\n\n| column | type | null | key / constraint |\n|---|---|---|---|")
    for c in t.columns:
        keys = []
        if c.primary_key:
            keys.append("PK")
        keys += [f"FK → {fk.column.table.name}.{fk.column.name}" for fk in c.foreign_keys]
        if c.unique:
            keys.append("unique")
        out.append(f"| {c.name} | {c.type} | {'yes' if c.nullable else 'no'} | {', '.join(keys)} |")
    extra = [f"unique({', '.join(c.name for c in k.columns)})" for k in t.constraints if k.__class__.__name__ == "UniqueConstraint"]
    extra += [f"index `{i.name}` ({', '.join(c.name for c in i.columns)}){' unique' if i.unique else ''}" for i in t.indexes if not (len(i.columns) == 1 and i.name.startswith('ix_'))]
    if extra:
        out.append("\nConstraints/indexes: " + "; ".join(extra))
(ROOT / "docs" / "DATABASE.md").write_text("\n".join(out) + "\n")

spec = app.openapi()
api = ["# API reference (generated)\n", "Base path `/api/v1`. Bearer access token (15 min) unless noted; refresh token is an HttpOnly cookie. Errors: `{\"detail\": \"<code>\"}`.\n",
       "Money/credit/AI-generation endpoints require an `Idempotency-Key` header (8–100 chars). Interactive docs at `/docs` when running.\n"]
groups: dict[str, list] = {}
for path, ops in sorted(spec["paths"].items()):
    for method, op in ops.items():
        groups.setdefault((op.get("tags") or ["other"])[0], []).append((path, method.upper(), op))
for tag, items in sorted(groups.items()):
    api.append(f"\n## {tag}\n\n| method | path | summary | auth |\n|---|---|---|---|")
    for path, m, op in items:
        auth = "bearer" if any("HTTPBearer" in s for s in op.get("security", [{}]) for s in s) else "—"
        api.append(f"| {m} | `{path}` | {op.get('summary', '')} | {auth} |")
(ROOT / "docs" / "API_DOCUMENTATION.md").write_text("\n".join(api) + "\n")
print("tables:", len(Base.metadata.sorted_tables), "endpoints:", sum(len(v) for v in groups.values()))
