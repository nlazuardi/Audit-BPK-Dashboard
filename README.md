# Audit-BPK-Dashboard

Dashboard Streamlit untuk memantau permintaan data BPK dan data audit lainnya. Data ditarik langsung dari file Excel di SharePoint lewat link tipe "Anyone".

## Menjalankan di laptop
```
git clone https://github.com/nlazuardi/Audit-BPK-Dashboard.git
cd Audit-BPK-Dashboard
pip install -r requirements.txt
```
Salin `.streamlit/secrets.toml.example` jadi `.streamlit/secrets.toml`, isi password dan link-nya (minta ke pemilik repo lewat jalur pribadi), lalu:
```
streamlit run app.py
```

## Struktur
| Lokasi | Isi |
|---|---|
| `app.py` | pintu masuk: password, menu, merangkai halaman |
| `core/sumber.py` | narik Excel dari link + cache |
| `core/auth.py` | gerbang password |
| `parsers/` | **satu file per sheet**: aturan baca, status, issue. Nggak boleh mengimpor streamlit |
| `tampilan/ui.py` | kartu, grafik, tabel, filter |
| `tampilan/style.css` | CSS |
| `.streamlit/config.toml` | tema warna |
| `notebooks/` | eksplor dan tes parser |

## Kolom standar (hasil `parse()` untuk halaman dashboard)
`No`, `Permintaan Data`, `Jenis Data`, `Divisi` (list), `Issue`, `Status` (`Done` / `Pending` / `N/A`).
Opsional: `PIC (Nama)`, `Tanggal penyerahan ke BPK`, `Konfirmasi dari BPK`.

## Menambah sheet baru
1. Salin salah satu file di `parsers/`, ganti `NAMA`, `KUNCI`, dan isi `parse()`.
2. Tambahkan link-nya di `secrets.toml` bagian `[link]` dengan nama yang sama dengan `KUNCI`.
3. Daftarkan modulnya di `parsers/__init__.py`.
4. Selama `SIAP = False`, halamannya cuma menampilkan isi sheet apa adanya.

## Aturan kerja bareng
- Satu orang satu file parser, supaya nggak bentrok.
- Kerja di branch sendiri, kirim lewat Pull Request, pemilik repo yang merge ke `main`.
- Jangan pernah commit `secrets.toml` atau file Excel.
- Kalau ada secret yang terlanjur ter-commit, ganti link dan password-nya. Menghapus file saja nggak cukup.
