const H = ({ children }: { children: React.ReactNode }) => <h3 className="font-semibold text-navy mt-4 mb-1">{children}</h3>;

function Generic({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (Array.isArray(value)) {
    if (value.every((x) => typeof x !== "object" || x === null))
      return <ul className="list-disc pl-5 text-sm space-y-1">{value.map((x, i) => <li key={i}>{String(x)}</li>)}</ul>;
    return <>{value.map((x, i) => <div key={i} className="mt-2"><Generic value={x} depth={depth + 1} /></div>)}</>;
  }
  if (value && typeof value === "object")
    return <>{Object.entries(value).map(([k, v]) => (
      <div key={k}><H>{k.replace(/_/g, " ")}</H><Generic value={v} depth={depth + 1} /></div>
    ))}</>;
  return <p className="text-sm whitespace-pre-wrap">{String(value ?? "")}</p>;
}

interface TP { tujuan: string; indikator: string[]; level_kognitif?: string }

export function OutputView({ slug, output }: { slug: string; output: Record<string, unknown> }) {
  if (slug === "tp-generator") {
    const tps = (output.tujuan_pembelajaran as TP[]) ?? [];
    return (
      <div>
        {tps.map((tp, i) => (
          <section key={i} className="mb-4">
            <H>TP {i + 1}{tp.level_kognitif ? ` (${tp.level_kognitif})` : ""}</H>
            <p className="text-sm">{tp.tujuan}</p>
            <p className="text-sm mt-2 text-slate-600">Indikator pencapaian:</p>
            <ul className="list-disc pl-5 text-sm space-y-1">{tp.indikator.map((x, j) => <li key={j}>{x}</li>)}</ul>
          </section>
        ))}
        {typeof output.catatan === "string" && output.catatan && (
          <><H>Catatan untuk guru</H><p className="text-sm">{output.catatan}</p></>
        )}
      </div>
    );
  }
  return <Generic value={output} />;
}
