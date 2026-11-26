"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Notice } from "@/components/ui/AuthCard";
import { OutputView } from "@/components/ui/OutputView";
import { ToolForm } from "@/components/ui/ToolForm";
import { toPayload, validateForm } from "@/lib/form";
import { api, errorMessage, messageFor } from "@/services/api";
import type { AiRequest, Estimate, ToolDetail } from "@/types/api";

export default function ToolPage() {
  const { slug } = useParams<{ slug: string }>();
  const [tool, setTool] = useState<ToolDetail | null>(null);
  const [est, setEst] = useState<Estimate | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [err, setErr] = useState<string | null>(null);
  const [req, setReq] = useState<AiRequest | null>(null);
  const [busy, setBusy] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout>>();
  // one key per "attempt"; reused on network retries of the same click, renewed for each new generation
  const keyRef = useRef<string>(crypto.randomUUID());

  const loadEstimate = useCallback(() => api.estimate(slug).then(setEst).catch((e) => setErr(errorMessage(e))), [slug]);
  useEffect(() => {
    api.tool(slug).then(setTool).catch((e) => setErr(errorMessage(e)));
    void loadEstimate();
    return () => clearTimeout(timer.current);
  }, [slug, loadEstimate]);

  function poll(id: string) {
    api.request(id).then((r) => {
      setReq(r);
      if (r.status === "queued" || r.status === "running") timer.current = setTimeout(() => poll(id), 1500);
      else { setBusy(false); void loadEstimate(); }
    }).catch((e) => { setBusy(false); setErr(errorMessage(e)); });
  }

  async function onGenerate(e: React.FormEvent) {
    e.preventDefault();
    if (!tool) return;
    const fe = validateForm(tool.input_schema, values);
    setErrors(fe);
    if (Object.keys(fe).length) return;
    setBusy(true); setErr(null); setReq(null);
    try {
      const r = await api.generate(slug, toPayload(tool.input_schema, values), keyRef.current);
      keyRef.current = crypto.randomUUID();
      setReq(r);
      poll(r.id);
    } catch (x) { setBusy(false); setErr(errorMessage(x)); }
  }

  async function download(format: "docx" | "pdf") {
    if (!req) return;
    try {
      const { blob, filename } = await api.exportDoc(req.id, format);
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob); a.download = filename; a.click();
      URL.revokeObjectURL(a.href);
    } catch (x) { setErr(errorMessage(x)); }
  }

  if (!tool) return err ? <Notice kind="error">{err}</Notice> : <p className="text-sm text-slate-600">Memuat…</p>;
  const failed = req?.status === "failed";
  return (
    <div className="max-w-4xl">
      <h1 className="text-2xl font-semibold text-navy">{tool.name}</h1>
      <p className="text-sm text-slate-600 mt-1">{tool.description}</p>
      <form onSubmit={onGenerate} noValidate className="mt-6">
        <ToolForm schema={tool.input_schema} values={values} errors={errors} onChange={(k, v) => setValues((s) => ({ ...s, [k]: v }))} />
        <div className="mt-6 flex flex-wrap items-center gap-4">
          <button type="submit" disabled={busy || (est ? !est.sufficient : false)}
            className="rounded-lg bg-navy text-white px-5 py-2.5 text-sm font-medium hover:bg-navy-700 disabled:opacity-60">
            {busy ? "Memproses…" : "Generate"}
          </button>
          {est && (
            <p className="text-sm text-slate-600" data-testid="estimate">
              Perkiraan: <b>{est.expected}</b> kredit{est.min !== est.max && <> (maks. {est.max})</>} · Saldo: <b>{est.balance}</b>
              {!est.sufficient && <span className="text-red-600"> · Kredit tidak cukup</span>}
            </p>
          )}
        </div>
      </form>
      {err && <div className="mt-4"><Notice kind="error">{err}</Notice></div>}
      {busy && !failed && <p className="mt-6 text-sm text-slate-600" role="status">AI sedang menyusun dokumen… biasanya kurang dari satu menit.</p>}
      {failed && <div className="mt-6"><Notice kind="error">{messageFor(req?.error_code ?? null)}</Notice></div>}
      {req?.status === "succeeded" && req.output && (
        <section className="mt-8 rounded-xl border border-slate-200 p-5" aria-label="Hasil">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-semibold text-navy">Hasil (draf)</h2>
            <div className="flex gap-2">
              {req.document_id && <Link href={`/app/documents/${req.document_id}`} className="rounded-lg bg-navy text-white px-3 py-1.5 text-sm">Sunting & simpan</Link>}
              <button onClick={() => download("docx")} className="rounded-lg border border-navy text-navy px-3 py-1.5 text-sm">Unduh DOCX</button>
              <button onClick={() => download("pdf")} className="rounded-lg border border-navy text-navy px-3 py-1.5 text-sm">Unduh PDF</button>
            </div>
          </div>
          <p className="text-xs text-slate-500 mt-1">Kredit terpakai: {req.credits_charged}. Tinjau dan sesuaikan sebelum digunakan; ini bukan dokumen resmi.</p>
          <div className="mt-3"><OutputView slug={slug} output={req.output} /></div>
        </section>
      )}
    </div>
  );
}
