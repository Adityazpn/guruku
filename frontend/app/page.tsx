import Link from "next/link";

const MODULES = [
  ["Perencanaan Pembelajaran", "RPP, Modul Ajar, ATP, PROTA, PROMES, LKPD"],
  ["Asesmen & Evaluasi", "Soal PG, esai, HOTS, kisi-kisi, rubrik"],
  ["Administrasi Guru", "Jurnal, agenda, surat, laporan, portofolio"],
  ["Analisis Siswa", "Rekomendasi pembelajaran (bersifat saran)"],
  ["Media Pembelajaran", "Slide, ringkasan, peta pikiran, naskah video"],
  ["Pustaka Digital", "Template dan panduan untuk guru"],
];

export default function Landing() {
  return (
    <>
      <header className="border-b border-slate-200">
        <nav className="max-w-6xl mx-auto flex items-center justify-between px-4 h-16">
          <span className="font-bold text-navy text-lg">Guruku</span>
          <div className="flex gap-3 text-sm">
            <Link href="/login" className="px-3 py-2 text-navy">Masuk</Link>
            <Link href="/register" className="px-4 py-2 rounded-lg bg-navy text-white">Daftar</Link>
          </div>
        </nav>
      </header>
      <main>
        <section className="max-w-6xl mx-auto px-4 py-16 sm:py-24">
          <h1 className="text-3xl sm:text-5xl font-bold text-navy max-w-3xl">Mengajar lebih cerdas, administrasi lebih ringan.</h1>
          <p className="mt-4 text-slate-600 max-w-2xl">Satu akun, banyak alat AI untuk guru: dari modul ajar hingga soal ujian. Hasil berupa draf yang dapat Anda tinjau, sunting, dan unduh.</p>
          <Link href="/register" className="inline-block mt-8 rounded-lg bg-navy text-white px-6 py-3 font-medium">Coba sekarang</Link>
        </section>
        <section className="bg-navy-50">
          <div className="max-w-6xl mx-auto px-4 py-14 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {MODULES.map(([t, d]) => (
              <div key={t} className="bg-white rounded-xl border border-slate-200 p-5">
                <h2 className="font-semibold text-navy">{t}</h2>
                <p className="text-sm text-slate-600 mt-1">{d}</p>
              </div>
            ))}
          </div>
        </section>
        <p className="max-w-6xl mx-auto px-4 py-8 text-xs text-slate-500">Seluruh keluaran AI adalah draf dan perlu ditinjau guru; bukan dokumen resmi.</p>
      </main>
    </>
  );
}
