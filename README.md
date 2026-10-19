# Jadwal kuliah 2023 B (otomatis)

Website statis yang menampilkan jadwal kelas 2023 B, disinkronkan otomatis dari dokumen jadwal fakultas.

## Cara pasang (GitHub Pages)
1. Buat repository baru di GitHub, unggah semua isi folder ini.
2. Settings → Pages → Source: *Deploy from a branch* → `main` / root.
3. Settings → Actions → General → Workflow permissions → *Read and write*.
4. Tab Actions → "Sinkron jadwal" → *Run workflow* untuk uji pertama. Setelah itu berjalan tiap 30 menit.

## Cara kerja
- `scripts/sync_jadwal.py` mengunduh dokumen, membaca tabel (termasuk sel gabungan), mengambil kolom **2023 B** lewat judul kolom, lalu menulis `jadwal.json`.
- Jika unduhan/parsing gagal, `jadwal.json` lama tidak ditimpa dan job Actions berstatus gagal (GitHub mengirim email).
- Tahun pada judul hari di dokumen sering salah; tanggal dicocokkan lewat nama hari. Hari yang tidak cocok dilewati dan dicatat di `meta.peringatan`.
- Ganti kelas lain: ubah `KELAS` di `sync_jadwal.py`.

## Tes lokal
`pip install requests beautifulsoup4 && python scripts/sync_jadwal.py`
