import type { JsonSchema } from "@/types/api";

export const LABELS: Record<string, string> = {
  education_level: "Jenjang", curriculum: "Kurikulum", subject: "Mata pelajaran", grade: "Kelas / Fase", semester: "Semester",
  topic: "Topik / materi", learning_objectives: "Tujuan pembelajaran (opsional)", extra_instructions: "Instruksi tambahan (opsional)",
  count: "Jumlah", student_names: "Nama siswa (opsional; akan disamarkan sebelum diproses AI)", observations: "Catatan pengamatan guru",
  text: "Teks materi", slide_count: "Jumlah slide", jumlah_pertemuan: "Jumlah pertemuan", difficulty: "Tingkat kesulitan", option_count: "Jumlah opsi",
  cognitive_levels: "Level kognitif (opsional)", assessment_type: "Jenis penilaian", level_count: "Jumlah level", alokasi_waktu: "Alokasi waktu (opsional)",
  model_pembelajaran: "Model pembelajaran (opsional)", metode: "Metode (opsional)", duration: "Durasi (opsional)", jenis_surat: "Jenis surat", tujuan_surat: "Tujuan surat",
  ringkasan_isi: "Ringkasan isi surat", nama_sekolah: "Nama sekolah (opsional)", kota: "Kota (opsional)", penandatangan: "Penandatangan (opsional)",
  nama_kegiatan: "Nama kegiatan", ringkasan: "Ringkasan kegiatan", tanggal: "Tanggal (opsional)", peserta: "Peserta (opsional)",
};
export const LONG_TEXT = new Set(["learning_objectives", "extra_instructions", "observations", "text", "ringkasan_isi", "ringkasan", "student_names"]);

/** Validates against the tool's JSON schema subset (required, enum, string/number bounds). Returns field -> message. */
export function validateForm(schema: JsonSchema, values: Record<string, string>): Record<string, string> {
  const errs: Record<string, string> = {};
  for (const [k, def] of Object.entries(schema.properties)) {
    const v = (values[k] ?? "").trim();
    const required = schema.required?.includes(k);
    if (!v) { if (required) errs[k] = "Wajib diisi"; continue; }
    if (def.enum && !def.enum.includes(v)) errs[k] = "Pilihan tidak valid";
    else if (def.type === "integer") {
      const n = Number(v);
      if (!Number.isInteger(n)) errs[k] = "Harus bilangan bulat";
      else if (def.minimum !== undefined && n < def.minimum) errs[k] = `Minimal ${def.minimum}`;
      else if (def.maximum !== undefined && n > def.maximum) errs[k] = `Maksimal ${def.maximum}`;
    } else {
      if (def.minLength && v.length < def.minLength) errs[k] = `Minimal ${def.minLength} karakter`;
      if (def.maxLength && v.length > def.maxLength) errs[k] = `Maksimal ${def.maxLength} karakter`;
    }
  }
  return errs;
}

/** Form strings -> typed payload; empty optional fields are omitted. */
export function toPayload(schema: JsonSchema, values: Record<string, string>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [k, def] of Object.entries(schema.properties)) {
    const v = (values[k] ?? "").trim();
    if (v) out[k] = def.type === "integer" ? Number(v) : v;
  }
  return out;
}
