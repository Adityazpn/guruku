# Daftar yang harus Anda lakukan sebelum peluncuran

Urutan disarankan. Yang bertanda **[BLOKIR]** menghalangi peluncuran. Tidak ada kunci/kredensial di repositori; semua Anda yang menyediakan.

## A. Akun dan biaya yang harus Anda buat sendiri
- [ ] **[BLOKIR] OpenAI developer account + billing + API key** (platform.openai.com; terpisah dari langganan ChatGPT). Isi saldo kecil dulu dan set batas pengeluaran di OpenAI.
- [ ] **[BLOKIR] Midtrans atau Xendit**: daftar merchant, selesaikan verifikasi bisnis (KYB) untuk produksi, ambil kunci **sandbox** untuk uji dulu. Persetujuan produksi biasanya paling lama: mulai sekarang.
- [ ] **[BLOKIR] Server**: paket Hostinger Premium (shared) **tidak bisa** menjalankan aplikasi ini. Butuh VPS dengan akses root dan Docker (minimal 2 vCPU / 4 GB RAM untuk beta; lihat docs/SPEC_03 §27). Bisa Hostinger VPS atau penyedia lain.
- [ ] **[BLOKIR] Domain/subdomain**: mis. `guruku.peluangruang.id`, record DNS **A** ke IP VPS (bukan folder hosting lama). Cek merek "Nalar Edu"/"Guruku" di PDKI dan ketersediaan domain sebelum mencetak materi.
- [ ] **[BLOKIR] Email pengirim (SMTP)**: Brevo/Resend/Mailgun/SMTP Hostinger. Dipakai untuk verifikasi email, reset password, kuitansi, pengingat perpanjangan.
- [ ] (Opsional) Bucket S3-compatible (Cloudflare R2, AWS S3) untuk file pustaka; tanpa itu file disimpan di disk VPS.
- [ ] (Opsional) Akun Sentry untuk pemantauan error; layanan uptime (UptimeRobot dll.) memantau `https://DOMAIN/api/v1/ready`.

## B. Pemasangan di server (ikuti docs/DEPLOYMENT.md)
1. [ ] Pasang Docker + Compose; buka port 80/443 saja; aktifkan firewall dan login SSH dengan key.
2. [ ] `git clone` repositori; salin `.env.production.example` ke `.env.production`; isi **semua** nilai (buat rahasia dengan `openssl rand -base64 48`). Simpan `PROVIDER_KEY_MASTER` dan `BACKUP_PASSPHRASE` juga di tempat aman **di luar server** (hilang = kunci terenkripsi tidak bisa dibuka).
3. [ ] `docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build`, lalu `scripts/init-letsencrypt.sh` untuk sertifikat HTTPS.
4. [ ] Buat admin pertama: `python ../scripts/create_admin.py email@anda.com super_admin`, login, **aktifkan MFA** di menu Keamanan, login ulang dengan kode.
5. [ ] Jalankan seed: `seed_tools.py`, `seed_commerce.py` (harga contoh!), `seed_library.py` (materi contoh).
6. [ ] Di Panel admin → Provider AI: isi kurs, tambah `openai`, tempel API key, tambah **ID model persis dari dokumentasi OpenAI**, isi harga dari halaman harga resmi OpenAI, **Tes koneksi**, aktifkan. Lalu Alat & Prompt: tugaskan model ke setiap alat. (docs/ADMIN_SETUP.md)
7. [ ] Daftarkan URL webhook di dashboard gateway: `https://DOMAIN/api/v1/webhooks/midtrans` (atau `/xendit`). (docs/PAYMENTS_SETUP.md)
8. [ ] **Uji sandbox pembayaran** (bayar, gagal, kedaluwarsa, kirim ulang webhook); baru setelah itu kunci produksi + 1 transaksi nyata kecil, cocokkan di dashboard gateway.
9. [ ] **Latihan pemulihan backup**: `infrastructure/backup/verify_backup.sh <file>` harus mencetak `BACKUP VERIFIED`. Salin backup ke luar server (`BACKUP_S3_URI`).
10. [ ] Pasang uptime monitor + notifikasi; cek halaman Admin → ringkasan/sistem berkala.

## C. Keputusan dan konten dari Anda
- [ ] **[BLOKIR] Teks hukum**: Syarat & Ketentuan, Kebijakan Privasi, kebijakan pengembalian dana dan kedaluwarsa kredit. **Halaman ini belum ada di aplikasi** dan tidak boleh saya karang; minta konsultan hukum (termasuk kepatuhan UU PDP untuk data siswa), lalu saya pasang di situs dan di alur pendaftaran.
- [ ] **[BLOKIR] Harga final**: paket langganan, paket kredit, biaya kredit per alat, margin. Seed hanya contoh. Pantau biaya OpenAI nyata selama beta, lalu sesuaikan aturan harga (mode dinamis/hybrid tersedia).
- [ ] Putuskan kebijakan: perpanjangan lewat tautan (bukan auto-debit), tanpa rollover kredit langganan, kredit beli berlaku 12 bulan?, ganti paket tanpa proration, **belum ada refund**. Setiap butir ini harus tertulis jelas di halaman harga dan S&K.
- [ ] **Akuntan**: perlakuan PPN dan format faktur resmi (faktur di aplikasi hanya catatan, bukan faktur pajak).
- [ ] **Ahli kurikulum / guru senior**: tinjau semua prompt dan istilah (Modul Ajar, RPP, ATP, dll.) dan coba tiap alat dengan model asli. Prompt saat ini draf dan belum pernah diuji dengan model sungguhan. Perbarui di Admin → Alat & Prompt (versi baru, bisa rollback).
- [ ] **Materi pustaka asli** yang Anda miliki hak ciptanya/berlisensi; arsipkan materi "[CONTOH]".
- [ ] Putuskan alat mana yang khusus pelanggan (toggle "requires_subscription" per alat via Admin API; belum ada tombol di UI).
- [ ] Finalisasi nama merek, logo, dan teks landing page.

## D. Verifikasi sebelum membuka untuk umum
- [ ] Beta tertutup (10–30 guru) dengan batas pengeluaran OpenAI rendah; kumpulkan umpan balik kualitas.
- [ ] Jalankan `pip-audit` dan `npm audit`; perbaiki temuan serius.
- [ ] Uji penetrasi/ulasan keamanan oleh pihak independen; uji beban (belum dilakukan).
- [ ] Uji ulang di perangkat HP nyata (Android murah, jaringan lambat).
- [ ] Pastikan email transaksional tidak masuk spam (SPF, DKIM, DMARC untuk domain pengirim).

## E. Belum dibangun (saya bisa lanjutkan; sebagian butuh keputusan Anda)
Halaman S&K/Privasi + persetujuan saat daftar (menunggu teks hukum) · refund (API gateway + penarikan kredit) · akun institusi/sekolah · adapter Claude dan Gemini · analisis nilai siswa/hasil ujian dari unggahan (statistik) · bank soal · administrasi presensi/wali kelas · template PMM/PKG · UI form profil guru (API sudah ada) · Pusat Bantuan, notifikasi dalam aplikasi, tiket dukungan, pengumuman, feature flags · dasbor keuangan lengkap (biaya vs pendapatan) · dataset evaluasi kualitas AI per jenjang · tes E2E otomatis di CI (saat ini diuji manual dengan Playwright, tidak di repositori) · kode pemulihan MFA · pembatas laju berbasis Redis (untuk >1 server) · perpanjangan otomatis kartu · e-faktur.
