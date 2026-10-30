"""Sheet daftar permintaan data BPK (Audit Kepatuhan).

Aturan yang berlaku di sini:
- tiap baris = 1 permintaan (induk "17", rincian "17.1", "17.2", ...)
- Status dari kolom "Tanggal penyerahan ke BPK": kosong = Pending, "N/A" = N/A, isi apa pun = Done
- Issue ditebak dari kata kunci (ISSUE_RULES), berlaku untuk seluruh baris dalam satu nomor
- file ini TIDAK boleh mengimpor streamlit, supaya bisa dites dari notebook
"""
import re

import pandas as pd

NAMA = "Audit Kepatuhan"
KUNCI = "auditkepatuhan"   # nama di [link] secrets.toml
SHEET = "Sheet1"           # kalau nggak ada, dipakai sheet pertama
SIAP = True                # True = punya parse() lengkap, tampil sebagai dashboard
URUT_ISSUE = ["Pengadaan", "Streamlining/Astagina", "CITOS", "Inhealth", "TJSL/Mitra Binaan", "Lain-lain"]

SLA = True                 # True = halaman ini punya tab SLA
SLA_TARGET_HARI = 5        # SEMENTARA: ganti dengan target SLA yang sebenarnya (bisa juga diubah dari sidebar dashboard)
SLA_HARI_KERJA = True      # True = hari kerja (Sen-Jum), False = hari kalender
LIBUR = []                 # hari libur nasional yang tidak dihitung, mis. ["2026-10-20", "2026-12-25"]
CATATAN = ("Nomor yang punya rincian (a, b, c ... atau 1), 2) ...) cuma dianggap judul utama dan tidak dihitung di statistik. "
           "Yang dihitung adalah rinciannya.")

SECTIONS = ["Dokumen Umum", "Permintaan Pendapatan", "Permintaan Data Tambahan"]

# urutan penting: yang pertama cocok menang
ISSUE_RULES = [
    ("Streamlining/Astagina", r"streamlining|astagina"),
    ("CITOS", r"citos|cilandak|graha megaria"),
    ("Inhealth", r"inhealth|istanbul"),
    ("TJSL/Mitra Binaan", r"tjsl|mitra binaan|pumk|pendanaan usaha mikro|kemitraan|bina lingkungan|pkbl"),
    ("Pengadaan", r"pengadaan|capex|opex|tender|vendor|rekanan|konsultan"),
]
ISSUE_LAIN = "Lain-lain"


DIVISI_ALIAS = {
    # kiri = cara orang menuliskannya (huruf kecil), kanan = nama yang ditampilkan. Nama mengikuti bagan struktur organisasi.
    "sekper": "Sekper", "sekretaris perusahaan": "Sekper", "sekdekom": "Sekdekom",
    "keuangan": "Keuangan", "perencanaan keuangan": "Keuangan",
    "akp": "AKP", "mpiap": "MPIAP", "mpi ap": "MPIAP",
    "ppa": "PPA", "pengadaan": "PPA", "tjsl": "PPA",
    "ti": "Teknologi Informasi", "it": "Teknologi Informasi", "teknologi informasi": "Teknologi Informasi",
    "strategi perusahaan": "Strategi Perusahaan", "corporate strategy": "Strategi Perusahaan",
    "mrkk": "MRKK", "manajemen risiko": "MRKK",
    "m&a": "M&A", "slim": "SLIM", "ooa": "OOA", "aktuaria": "Aktuaria", "skai": "SKAI",
    "penjaminan": "Bisnis Asuransi Umum & Penjaminan",
    "divisi bisnis asuransi umum & penjaminan": "Bisnis Asuransi Umum & Penjaminan",
    "mitrasraya": "PT Mitrasraya",
    "?": "Belum ada PIC", "": "Belum ada PIC", "nan": "Belum ada PIC",
}


def _divisi(pic):
    s = str(pic).strip()
    if re.fullmatch(r"n\s*[/.]?\s*a\.?", s, re.I):   # PIC diisi "N/A"
        return ["Belum ada PIC"]
    out = []
    for p in re.split(r"\s*(?:/|\n|,|\bdan\b)\s*", s):
        p = p.strip()
        if "-" in p and not p.upper().startswith("PT"):
            p = p.split("-")[0].strip()      # PPA-TJSL -> PPA, MRKK-Kebijakan -> MRKK
        p = DIVISI_ALIAS.get(p.lower(), p)
        if p and p not in out:
            out.append(p)
    return out or ["Belum ada PIC"]


def _status(tgl_bpk):
    """Hanya lihat kolom 'Tanggal penyerahan ke BPK': kosong = Pending, 'N/A' = N/A, isi apa pun = Done."""
    if pd.isna(tgl_bpk):
        return "Pending"
    t = str(tgl_bpk).strip()
    if t == "":
        return "Pending"
    if re.fullmatch(r"n\s*[/.]?\s*a\.?", t, re.I):
        return "N/A"
    return "Done"


def _issue(teks):
    for nama, pola in ISSUE_RULES:
        if re.search(pola, teks, re.I):
            return nama
    return ISSUE_LAIN


_BULAN = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "mei": 5, "may": 5, "jun": 6, "jul": 7, "agu": 8, "aug": 8,
          "sep": 9, "okt": 10, "oct": 10, "nov": 11, "des": 12, "dec": 12}


def _ke_tanggal(v):
    """Datetime Excel -> Timestamp. Teks diambil tanggal pertamanya ('9/15/2026 / 9/28/2026' -> 15 Sep 2026). Gagal baca -> NaT."""
    if not isinstance(v, str) and pd.isna(v):
        return pd.NaT
    if hasattr(v, "year"):
        return pd.Timestamp(v).normalize()
    t = str(v)
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", t)
    if m:
        a, b, y = int(m[1]), int(m[2]), int(m[3])
        bulan, hari = (b, a) if a > 12 else (a, b)      # default format AS: bulan/tanggal/tahun
        try:
            return pd.Timestamp(y, bulan, hari)
        except ValueError:
            return pd.NaT
    m = re.search(r"(\d{1,2})[ \-]+([A-Za-z]{3,})[ \-,]*(\d{2,4})", t)
    if m and m[2][:3].lower() in _BULAN:
        y = int(m[3])
        y += 2000 if y < 100 else 0
        try:
            return pd.Timestamp(y, _BULAN[m[2][:3].lower()], int(m[1]))
        except ValueError:
            return pd.NaT
    return pd.NaT


def _kolom(d, kata):
    return next((c for c in d.columns if kata in str(c).lower()), None)


def parse(raw: pd.DataFrame) -> pd.DataFrame:
    r = raw.copy()
    r.columns = range(r.shape[1])
    hdr_mask = r[1].astype(str).str.strip().eq("Permintaan Data")
    if not hdr_mask.any():
        raise ValueError('Header "Permintaan Data" nggak ketemu di kolom ke-2. Cek sheet-nya.')
    hdr = hdr_mask.idxmax()
    names = [str(c).replace("\n", " ").replace('"', "").strip() for c in r.loc[hdr]]
    names = [n if n != "nan" else f"kol{i}" for i, n in enumerate(names)]
    names[3] = "PIC (Nama)"
    d = r.loc[hdr + 1:].copy()
    d.columns = names
    d["row"] = d.index

    no_col, txt, pic = names[0], names[1], names[2]
    no_num = pd.to_numeric(d[no_col], errors="coerce")
    teks = d[txt].astype(str).str.strip()

    # baris judul bagian: header "No" yang berulang, atau judul tanpa nomor & tanpa PIC
    is_sec = d[no_col].astype(str).str.strip().eq("No") | (
        no_num.isna() & d[pic].isna() & (teks.str.len() < 90)
        & teks.str.lower().str.startswith(tuple(s.lower() for s in SECTIONS))
    )
    d["Jenis Data"] = teks.where(is_sec).ffill().fillna("Tanpa Bagian")
    d = d[~is_sec & d[txt].notna()].copy()
    no_num = pd.to_numeric(d[no_col], errors="coerce")

    # satu kelompok = satu nomor induk beserta rincian di bawahnya
    d["_grp"] = no_num.notna().cumsum()
    d = d[d["_grp"] > 0].copy()
    no_num = pd.to_numeric(d[no_col], errors="coerce")
    d["_urut"] = d.groupby("_grp").cumcount()          # 0 = baris induk
    induk = no_num.ffill().astype(int).astype(str)
    huruf = d[no_col].astype(str).str.strip().str.extract(r"^([A-Za-z])[.)]?$")[0]   # rincian bernomor huruf: "a.", "b."
    rincian = huruf.fillna(d["_urut"].astype(str))                                     # selain itu: urutan 1, 2, 3
    d["No"] = induk.where(d["_urut"] == 0, induk + "." + rincian)

    # teks induk dipakai buat konteks (kolom Judul Induk) dan buat nentuin issue
    teks_induk = d[txt].where(d["_urut"] == 0).groupby(d["_grp"]).transform("first").astype(str)
    ringkas = teks_induk.str.replace(r"\s+", " ", regex=True).str.strip().str.slice(0, 80)
    d["Judul Induk"] = (induk + ". " + ringkas).where(d["_urut"] > 0, "")
    d["Teks lengkap"] = d.groupby("_grp")[txt].transform(lambda s: " ".join(s.astype(str)))
    # PIC kosong di baris rincian -> pakai PIC baris induknya (kalau induk juga kosong: Belum ada PIC)
    d[pic] = d[pic].fillna(d[pic].where(d["_urut"] == 0).groupby(d["_grp"]).transform("first"))

    # nomor induk yang punya rincian cuma judul utama: nggak dihitung di statistik
    ukuran = d.groupby("_grp")[txt].transform("size")
    d = d[~((d["_urut"] == 0) & (ukuran > 1))].copy()

    tgl = "Tanggal penyerahan ke BPK"
    d["Status"] = d[tgl].map(_status)
    d["Issue"] = d["Teks lengkap"].map(_issue)
    d["Divisi"] = d[pic].map(_divisi)

    # tanggal versi datetime, dipakai buat hitung SLA
    for nama, kata in (("Tgl Permintaan", "tanggal permintaan"), ("Tgl ke Auditi", "ke auditi"),
                       ("Tgl dari Auditi", "dari auditi"), ("Tgl Selesai", "penyerahan ke bpk")):
        c = _kolom(d, kata)
        d[nama] = pd.to_datetime(d[c].map(_ke_tanggal)) if c else pd.NaT
    return d.reset_index(drop=True)
