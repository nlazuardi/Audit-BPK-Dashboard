"""Halaman Wawancara Kepatuhan: log book jadwal wawancara BPK, ditampilkan seperti slide progres.

Beda dengan sheet permintaan data, halaman ini punya fungsi render() sendiri (bukan dashboard
Done/Pending), jadi app.py memanggil render(raw) kalau sebuah modul punya fungsi itu.

Yang bisa kamu sesuaikan ada di bagian ATURAN: kata kunci kategori fokus diskusi dan pengelompokan divisi.
Catatan: file ini mengimpor streamlit dan tampilan.ui, jadi tidak bisa dites murni dari luar Streamlit.
"""
import html as _html
import re

import altair as alt
import pandas as pd
import streamlit as st

from tampilan import ui

NAMA = "Wawancara Kepatuhan"
KUNCI = "wawancarakepatuhan"   # nama di [link] secrets.toml
SHEET = None                   # None = sheet pertama
SIAP = True
URUT_ISSUE = []

# ============================== ATURAN ==============================
# Agenda yang melibatkan Direksi dikeluarkan dari statistik (sama seperti "Non-Direksi" di slide).
# Bisa dimasukkan lagi lewat centang di sidebar.
DIREKSI_POLA = r"direksi|direktur|radir"

# Kategori fokus diskusi, ditebak dari teks agenda. Yang cocok PERTAMA menang, jadi urutan penting.
FOKUS_RULES = [
    ("Pengadaan & Jasa Konsultansi", r"pengadaan|jasa konsultan|jasa professional|konsultan|\bhps\b|rekanan"),
    ("Streamlining & Organisasi", r"streamlining|astagina|fungsi dan peran|struktur organisasi"),
    ("TJSL & Komunikasi Korporasi", r"tjsl|sumbangan|komunikasi|kampanye|mitra binaan"),
    ("SDM & Remunerasi", r"belanja manajemen|pegawai|pelatihan|tantiem|purna jabatan|gaji|tunjangan|remunerasi"),
    ("Aset & Aksi Korporasi", r"akuisisi|inhealth|citos|cilandak|aksi korporasi|saham|apollo|divestasi|kjpp"),
    ("Kinerja Anak Perusahaan", r"kinerja anak|anak perusahaan"),
    ("Keuangan & Akuntansi", r"alokasi aset|\balm\b|portofolio|keuangan|akuntansi|\bcoa\b|\bsas\b|dividen|deviden|\bkas\b|arus kas"),
]
FOKUS_LAIN = "Lainnya"

# Pengelompokan divisi/fungsi dari kolom "Pihak yang diwawancara" (dicari di seluruh teksnya).
# Satu agenda bisa masuk ke lebih dari satu kelompok.
DIVISI_RULES = [
    ("PPA / Pengadaan / TJSL", r"\bPPA\b|PENGADAAN|TJSL"),
    ("Keuangan", r"KEUANGAN"),
    ("PMOP / PMOK", r"\bPMOP\b|\bPMOK\b"),
    ("M&A", r"M&A"),
    ("SDM", r"\bSDM\b"),
    ("AKP", r"\bAKP\b"),
    ("TI", r"\bTI\b"),
    ("IFG Life", r"IFG LIFE"),
    ("Hublem", r"HUBLEM"),
    ("Corcomm", r"CORCOMM"),
    ("Tata Kelola", r"TATA KELOLA"),
    ("Strategi Digital", r"STRATEGI DIGITAL"),
    ("MPI AP", r"MPI AP"),
    ("SLIM", r"\bSLIM\b"),
    ("OOA", r"\bOOA\b"),
    ("Aspen", r"BISNIS ASURANSI UMUM"),
    ("PT Mitrasraya", r"MITRASRAYA"),
    ("Tim Pengelola Aset Citos", r"PENGELOLA ASET"),
]
# Unit yang belum ada di daftar di atas otomatis memakai nama unit pertama yang tertulis di kolom Pihak
# (bagian sebelum tanda ":"), jadi tampil sebagai batang sendiri. "Fungsi lain" cuma dipakai kalau kolom Pihak kosong.
DIVISI_LAIN = "Fungsi lain"
DIREKSI_LABEL = "Direksi"   # batang khusus Direksi di grafik keterlibatan (dihitung terpisah dari unit lain)

WARNA_FOKUS = {
    "Pengadaan & Jasa Konsultansi": "#0B3D91", "Streamlining & Organisasi": "#1FB5A6",
    "Keuangan & Akuntansi": "#F2B233", "Aset & Aksi Korporasi": "#7B4FD6",
    "SDM & Remunerasi": "#E5484D", "TJSL & Komunikasi Korporasi": "#4CAF50",
    "Kinerja Anak Perusahaan": "#8A8F98", FOKUS_LAIN: "#C5CAD3",
}
WARNA_METODE = {"Hybrid": "#0B3D91", "Online": "#F2B233", "Tatap Muka (Offline)": "#1FB5A6", "Lainnya": "#C5CAD3"}
PALET_BULAN = ["#0B3D91", "#1FB5A6", "#F2B233", "#7B4FD6", "#E5484D", "#4CAF50"]
MINGGU_LABEL = {1: "Minggu 1 (1–7)", 2: "Minggu 2 (8–14)", 3: "Minggu 3 (15–21)", 4: "Minggu 4 (22–akhir)"}
# ====================================================================

_BULAN_ID = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
_HARI_ID = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]


# ============================== BACA DATA ==============================
def _bersih(v):
    return "" if pd.isna(v) else re.sub(r"\s+", " ", str(v)).strip()


def _topeng(t):
    """Sembunyikan link dan kode akses rapat online supaya nggak tampil di dashboard."""
    t = re.sub(r"https?://\S+", "[link]", t)
    return re.sub(r"(?i)\b(passcode|meeting id)\b\s*:?\s*\S+", r"\1 ***", t)


def _ruang(t):
    if not t:
        return ""
    return "Zoom" if "zoom" in t.lower() else t.title()


def _format(k):
    k = k.lower()
    if "hybrid" in k:
        return "Hybrid"
    if "online" in k or "zoom" in k:
        return "Online"
    if "offline" in k or "tatap muka" in k:
        return "Tatap Muka (Offline)"
    return "Lainnya"


def _fokus(teks):
    t = teks.lower()
    for nama, pola in FOKUS_RULES:
        if re.search(pola, t):
            return nama
    return FOKUS_LAIN


def _unit_pertama(pihak):
    t = re.sub(r"^\s*\d+[.)]\s*", "", pihak)           # buang nomor urut "1. "
    t = re.sub(r"(?i)^divisi\s+", "", t.split(":")[0].strip())
    return t[:40].strip(" .,-") or DIVISI_LAIN


def _divisi(pihak):
    up = pihak.upper()
    hasil = [nama for nama, pola in DIVISI_RULES if re.search(pola, up)]
    return hasil or [_unit_pertama(pihak)]


def _jam(m):
    return "" if pd.isna(m) else f"{int(m // 60):02d}:{int(m % 60):02d}"


def _tgl(d):
    return f"{d.day:02d} {_BULAN_ID[d.month - 1][:3]} {d.year}"


def parse(raw: pd.DataFrame) -> pd.DataFrame:
    """Tabel mentah (header=None) -> satu baris per wawancara, lengkap dengan kolom turunan."""
    r = raw.copy()
    r.columns = range(r.shape[1])
    mask = r[0].astype(str).str.strip().str.lower().eq("tanggal")
    if not mask.any():
        raise ValueError('Header "Tanggal" nggak ketemu di kolom pertama.')
    hdr = mask.idxmax()
    nama = [str(c).strip().lower() for c in r.loc[hdr]]

    def kol(kata):
        return next((i for i, n in enumerate(nama) if kata in n), None)

    idx = {k: kol(k) for k in ("tanggal", "kategori", "status", "pihak", "agenda", "tempat")}
    for wajib in ("tanggal", "kategori", "pihak", "agenda"):
        if idx[wajib] is None:
            raise ValueError(f'Kolom "{wajib}" nggak ketemu di baris header.')

    d = r.loc[hdr + 1:]

    def ambil(k):
        return d[idx[k]] if idx[k] is not None else pd.Series("", index=d.index)

    out = pd.DataFrame({
        "Tanggal": pd.to_datetime(ambil("tanggal"), errors="coerce"),
        "Kategori": ambil("kategori").map(_bersih),
        "Status": ambil("status").map(_bersih),
        "Pihak": ambil("pihak").map(_bersih),
        "Agenda": ambil("agenda").map(_bersih).map(_topeng),
        "Tempat": ambil("tempat").map(_bersih).map(_ruang),
    })
    out = out[out["Tanggal"].notna()].copy()

    out["Format"] = out["Kategori"].map(_format)
    out["Direksi"] = out["Kategori"].str.contains("radir", case=False) | out["Pihak"].str.contains(DIREKSI_POLA, case=False, regex=True)

    jam = out["Kategori"].str.extract(r"(\d{1,2})[.:](\d{2})\s*-\s*(\d{1,2})[.:](\d{2})").astype(float)
    mulai, selesai = jam[0] * 60 + jam[1], jam[2] * 60 + jam[3]
    out["Jam"] = [f"{_jam(a)}–{_jam(b)}" if not pd.isna(a) else "" for a, b in zip(mulai, selesai)]
    out["Durasi (menit)"] = (selesai - mulai).where(selesai > mulai)
    out["Jam tidak valid"] = mulai.notna() & ~(selesai > mulai)

    out["Bulan"] = out["Tanggal"].dt.strftime("%Y-%m")
    out["Bulan Label"] = [f"{_BULAN_ID[m - 1]} {y}" for y, m in zip(out["Tanggal"].dt.year, out["Tanggal"].dt.month)]
    out["Minggu"] = out["Tanggal"].dt.day.map(lambda x: 1 if x <= 7 else 2 if x <= 14 else 3 if x <= 21 else 4)
    out["Hari"] = out["Tanggal"].dt.weekday.map(lambda i: _HARI_ID[i])
    out["Fokus"] = out["Agenda"].map(_fokus)
    out["Divisi"] = out["Pihak"].map(_divisi)
    return out.sort_values("Tanggal", kind="stable").reset_index(drop=True)


# ============================== GRAFIK ==============================
def _pct(x):
    return f"{x:.1%}".replace(".", ",")


def _daftar(items):
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " dan " + items[-1]


def _donut(agg, warna, sub, layar=True):
    """agg berkolom Kategori dan Jumlah. Label angka di irisan, persen di legenda.

    layar=True: dipakai di dashboard. Streamlit memaksa seluruh grafik (termasuk legenda) muat di tinggi yang ditentukan,
    jadi tinggi ditambah sesuai jumlah baris legenda supaya donut nggak terhimpit dan terpotong.
    layar=False: untuk file PNG, tingginya cukup untuk donut saja (legenda ditambahkan di bawahnya).
    """
    agg = agg[agg["Jumlah"] > 0].reset_index(drop=True).copy()
    total = int(agg["Jumlah"].sum())
    agg["Urut"] = range(len(agg))
    agg["Label"] = [f"{k} · {j} ({_pct(j / total)})" for k, j in zip(agg["Kategori"], agg["Jumlah"])]
    skala = alt.Scale(domain=agg["Label"].tolist(), range=[warna.get(k, "#9AA0A6") for k in agg["Kategori"]])
    theta, urut = alt.Theta("Jumlah:Q", stack=True), alt.Order("Urut:Q")
    arc = alt.Chart(agg).mark_arc(innerRadius=60, outerRadius=112, stroke="white", strokeWidth=2).encode(
        theta=theta, order=urut,
        color=alt.Color("Label:N", scale=skala, legend=alt.Legend(orient="bottom", title=None, columns=1, labelLimit=320, symbolType="circle",
                          labelFontSize=12, symbolSize=90, rowPadding=6, offset=14)),
        tooltip=["Kategori", "Jumlah"],
    )
    angka = (
        alt.Chart(agg).mark_text(radius=86, size=13, fontWeight="bold", color="white")
        .encode(theta=theta, order=urut, text="Jumlah:Q")
        .transform_filter(f"datum.Jumlah >= {max(1, round(total * 0.05))}")
    )
    tengah = alt.Chart(pd.DataFrame({"t": [str(total)]})).mark_text(size=30, fontWeight="bold", color=ui.HITAM, dy=-6).encode(text="t:N")
    sub_t = alt.Chart(pd.DataFrame({"t": [sub]})).mark_text(size=11, color="#5B6470", dy=16).encode(text="t:N")
    tinggi = 270 + 30 * len(agg) + 30 if layar else 260
    return alt.layer(arc, angka, tengah, sub_t).properties(height=tinggi)


def _chart_trend(df, bulan_urut, layar=True):
    total_bln = df.groupby("Bulan Label").size()
    baris = []
    for b in bulan_urut:
        g = df[df["Bulan Label"] == b]
        for m in range(1, int(g["Minggu"].max()) + 1):     # sampai minggu terakhir yang ada datanya
            baris.append({"Seri": f"{b} ({int(total_bln[b])} agenda)", "Minggu": MINGGU_LABEL[m], "Jumlah": int((g["Minggu"] == m).sum())})
    agg = pd.DataFrame(baris)
    seri = agg["Seri"].drop_duplicates().tolist()
    x = alt.X("Minggu:N", sort=list(MINGGU_LABEL.values()), title=None, axis=alt.Axis(labelAngle=0, labelLimit=110))
    y = alt.Y("Jumlah:Q", title="Jumlah agenda", scale=alt.Scale(domainMin=0, domainMax=int(agg["Jumlah"].max()) + 2), axis=alt.Axis(tickMinStep=1))
    warna = alt.Scale(domain=seri, range=PALET_BULAN[:len(seri)])
    garis = alt.Chart(agg).mark_line(point=alt.OverlayMarkDef(size=80, filled=True), strokeWidth=3).encode(
        x=x, y=y, color=alt.Color("Seri:N", scale=warna, legend=alt.Legend(orient="top", title=None, columns=1, labelLimit=400)), tooltip=["Seri", "Minggu", "Jumlah"])
    angka = alt.Chart(agg).mark_text(dy=-13, fontWeight="bold", size=12).encode(
        x=x, y="Jumlah:Q", text="Jumlah:Q", color=alt.Color("Seri:N", scale=warna, legend=None))
    return alt.layer(garis, angka).properties(height=300 + (22 * len(seri) + 16 if layar else 0))


def _chart_divisi(df, n_direksi=0):
    """Batang per unit dari agenda di df. Top 5 divisi diberi warna utama (#0B3D91), sisanya abu-abu (#BAC2CB), Direksi merah (#E40428)."""
    ex = df.explode("Divisi")
    agg = ex[ex["Divisi"] != DIREKSI_LABEL].groupby("Divisi").size().reset_index(name="Jumlah")
    if n_direksi:
        agg = pd.concat([agg, pd.DataFrame([{"Divisi": DIREKSI_LABEL, "Jumlah": int(n_direksi)}])], ignore_index=True)
    agg["lain"] = agg["Divisi"].eq(DIVISI_LAIN)
    agg = agg.sort_values(["lain", "Jumlah"], ascending=[True, False]).reset_index(drop=True)

    warna_list = []
    top_n = 0
    for _, row in agg.iterrows():
        if row["Divisi"] == DIREKSI_LABEL:
            warna_list.append("#E40428")
        elif row["lain"]:
            warna_list.append("#BAC2CB")
        elif top_n < 5:
            warna_list.append("#0B3D91")
            top_n += 1
        else:
            warna_list.append("#BAC2CB")
    agg["Warna"] = warna_list

    urut = agg["Divisi"].tolist()
    y = alt.Y("Divisi:N", sort=urut, title=None, axis=alt.Axis(labelLimit=260))
    bars = alt.Chart(agg).mark_bar(cornerRadiusEnd=4).encode(
        y=y, x=alt.X("Jumlah:Q", title="Jumlah agenda", scale=alt.Scale(domainMax=int(agg["Jumlah"].max()) + 1), axis=alt.Axis(tickMinStep=1)),
        color=alt.Color("Warna:N", scale=None),
        tooltip=["Divisi", "Jumlah"])
    teks = alt.Chart(agg).mark_text(align="left", dx=5, fontWeight="bold", color=ui.HITAM).encode(y=y, x="Jumlah:Q", text="Jumlah:Q")
    return alt.layer(bars, teks).properties(height=max(240, 34 * len(agg)))


def _insight(no, judul, isi):
    return (
        '<div style="display:flex;gap:12px;align-items:flex-start;background:#EEF7F6;border-radius:12px;padding:12px 16px;margin:6px 0">'
        f'<div style="background:#1FB5A6;color:#fff;font-weight:800;border-radius:50%;width:28px;height:28px;display:flex;'
        f'align-items:center;justify-content:center;flex:none">{no}</div>'
        f'<div><div style="font-weight:700">{_html.escape(judul)}</div>'
        f'<div style="color:#5B6470;font-size:.9rem">{_html.escape(isi)}</div></div></div>'
    )


def _tabel_log(df):
    return pd.DataFrame({
        "Tanggal": df["Tanggal"].map(_tgl),
        "Hari": df["Hari"],
        "Format": df["Format"],
        "Jam": df["Jam"],
        "Durasi (menit)": df["Durasi (menit)"],
        "Divisi/Fungsi": df["Divisi"].map(", ".join),
        "Fokus Diskusi": df["Fokus"],
        "Agenda dari BPK": df["Agenda"],
        "Pihak yang diwawancara": df["Pihak"],
        "Tempat": df["Tempat"],
        "Direksi": df["Direksi"].map({True: "Ya", False: "Tidak"}),
    })


# ============================== HALAMAN ==============================
def render(raw: pd.DataFrame):
    try:
        semua = parse(raw)
    except Exception as e:
        st.error(f"Format sheet '{NAMA}' tidak sesuai dengan aturan bacanya: {e}")
        return
    p = KUNCI

    with st.sidebar:
        st.header("Filter")
        sertakan = st.checkbox("Sertakan agenda Direksi", value=False, key=f"{p}_direksi")
        bulan_semua = semua[["Bulan", "Bulan Label"]].drop_duplicates().sort_values("Bulan")["Bulan Label"].tolist()
        f_bulan = st.multiselect("Bulan", bulan_semua, key=f"{p}_f_bulan")
        f_format = st.multiselect("Metode", sorted(semua["Format"].unique()), key=f"{p}_f_format")
        _opsi_div = sorted({d for l in semua["Divisi"] for d in l} - (set() if sertakan else {DIREKSI_LABEL}))
        f_div = st.multiselect("Divisi / Fungsi", _opsi_div, key=f"{p}_f_div")
        f_fokus = st.multiselect("Fokus diskusi", sorted(semua["Fokus"].unique()), key=f"{p}_f_fokus")

    def terapkan(x):
        if f_bulan:
            x = x[x["Bulan Label"].isin(f_bulan)]
        if f_format:
            x = x[x["Format"].isin(f_format)]
        if f_div:
            x = x[x["Divisi"].map(lambda l: any(d in f_div for d in l))]
        if f_fokus:
            x = x[x["Fokus"].isin(f_fokus)]
        return x

    df = terapkan(semua if sertakan else semua[~semua["Direksi"]])
    n_direksi_batang = len(terapkan(semua[semua["Direksi"]]))   # untuk batang Direksi di grafik keterlibatan
    if df.empty:
        st.warning("Tidak ada agenda untuk filter ini.")
        return

    n = len(df)
    n_direksi = int(semua["Direksi"].sum())
    ket_direksi = "termasuk Direksi" if sertakan else "non-Direksi"
    bulan_urut = df[["Bulan", "Bulan Label"]].drop_duplicates().sort_values("Bulan")["Bulan Label"].tolist()
    per_bulan = df.groupby("Bulan Label").size()
    divisi_n = df.explode("Divisi")["Divisi"].value_counts()
    divisi_nama = [d for d in divisi_n.index if d not in (DIVISI_LAIN, DIREKSI_LABEL)]
    fokus_n = df["Fokus"].value_counts()
    fokus_nama = [f for f in fokus_n.index if f != FOKUS_LAIN]
    durasi = df["Durasi (menit)"].dropna()

    tab_ring, tab_log = st.tabs(["Ringkasan", "Log Wawancara"])

    # ---------------- Ringkasan ----------------
    with tab_ring:
        st.markdown("#### HOLDING – PROGRES WAWANCARA DENGAN DIVISI")

        kalimat = f"Dari total **{n} agenda wawancara** ({ket_direksi}), "
        if len(bulan_urut) > 1:
            top = per_bulan.idxmax()
            kalimat += f"aktivitas pemeriksaan paling terkonsentrasi pada **{top}**, yaitu sebesar **{_pct(per_bulan.max() / n)}**. "
        else:
            kalimat += f"seluruhnya berlangsung pada **{bulan_urut[0]}**. "
        if divisi_nama:
            kalimat += f"Fungsi yang paling banyak terlibat: **{_daftar(divisi_nama[:4])}**. "
        if fokus_nama:
            kalimat += f"Topik yang paling banyak dibahas: **{fokus_nama[0]}** ({_pct(fokus_n[fokus_nama[0]] / n)})."
        st.markdown(kalimat)

        st.markdown(
            '<div class="kartu-wrap">'
            + ui.kartu("Total agenda wawancara", n, ket_direksi, "#0B3D91")
            + ui.kartu("Divisi/fungsi terlibat", len(divisi_nama), "kelompok divisi/fungsi", "#1FB5A6")
            + ui.kartu("Kategori fokus diskusi", len(fokus_nama), "kategori topik", "#F2B233")
            + ui.kartu("Rata-rata durasi", f"{durasi.mean():.0f}" if len(durasi) else "-",
                       f"menit · median {durasi.median():.0f}" if len(durasi) else "jam belum terbaca", ui.HITAM)
            + "</div>",
            unsafe_allow_html=True,
        )
        if not sertakan and n_direksi:
            st.caption(f"{n_direksi} agenda Direksi tidak dihitung. Centang \"Sertakan agenda Direksi\" di sidebar untuk memasukkannya.")

        c1, c2, c3 = st.columns([1, 1, 1.35])
        with c1:
            st.markdown("#### Metode Pelaksanaan")
            metode = df.groupby("Format").size().reset_index(name="Jumlah").rename(columns={"Format": "Kategori"})
            ui.tampil_chart(_donut(metode, WARNA_METODE, "Agenda"))
            ui.tombol_png(_donut(metode, WARNA_METODE, "Agenda", layar=False), f"{p}_metode", f"{p}_png_metode", "Metode Pelaksanaan Wawancara", lebar=460)
        with c2:
            st.markdown("#### Distribusi Agenda per Bulan")
            bln = per_bulan.reindex(bulan_urut).reset_index()
            bln.columns = ["Kategori", "Jumlah"]
            warna_bln = {b: PALET_BULAN[i % len(PALET_BULAN)] for i, b in enumerate(bulan_urut)}
            ui.tampil_chart(_donut(bln, warna_bln, "Agenda"))
            ui.tombol_png(_donut(bln, warna_bln, "Agenda", layar=False), f"{p}_per_bulan", f"{p}_png_bulan", "Distribusi Agenda per Bulan", lebar=460)
            if len(bulan_urut) > 1:
                st.caption(f"Wawancara paling banyak pada {per_bulan.idxmax()}, {_pct(per_bulan.max() / n)} dari total agenda.")
        with c3:
            st.markdown("#### Trend Pelaksanaan per Minggu")
            ui.tampil_chart(_chart_trend(df, bulan_urut))
            ui.tombol_png(_chart_trend(df, bulan_urut, layar=False), f"{p}_trend_minggu", f"{p}_png_trend", "Trend Pelaksanaan per Minggu", lebar=640)

        e1, e2 = st.columns([1.8, 1])
        with e1:
            st.markdown("#### Keterlibatan Divisi / Fungsi / Anper")
            ch_div = _chart_divisi(df, n_direksi_batang if sertakan else 0)
            ui.tampil_chart(ch_div)
            ui.tombol_png(ch_div, f"{p}_divisi", f"{p}_png_divisi", "Keterlibatan Divisi / Fungsi / Anper", lebar=640)
            st.caption("Catatan: Jumlah agenda menunjukan keterlibatan divisi/fungsi/anper. Satu agenda dapat melibatkan lebih dari satu divisi.")
        with e2:
            st.markdown("##### Fokus diskusi per kategori")
            fokus = fokus_n.reset_index()
            fokus.columns = ["Kategori", "Jumlah"]
            ui.tampil_chart(_donut(fokus, WARNA_FOKUS, "Agenda"))
            ui.tombol_png(_donut(fokus, WARNA_FOKUS, "Agenda", layar=False), f"{p}_fokus", f"{p}_png_fokus", "Fokus Diskusi Berdasarkan Kategori", lebar=520)
            lain = int(fokus_n.get(FOKUS_LAIN, 0))
            if lain:
                st.caption(f"{lain} agenda belum masuk kategori mana pun (Lainnya). Lihat di tab Log Wawancara, lalu tambah kata kuncinya di FOKUS_RULES.")

        st.markdown("#### Insight Utama")
        isi = ""
        no = 1
        if divisi_nama:
            top3 = divisi_nama[:3]
            isi += _insight(no, f"Keterlibatan tertinggi: {_daftar(top3)}",
                            "Paling sering diwawancarai pada periode ini (" + ", ".join(str(int(divisi_n[d])) for d in top3) + " agenda).")
            no += 1
        if fokus_nama:
            isi += _insight(no, f"Fokus utama pada {fokus_nama[0]}", f"Menjadi topik paling banyak dibahas ({_pct(fokus_n[fokus_nama[0]] / n)} dari total agenda).")
        st.markdown(isi, unsafe_allow_html=True)

    # ---------------- Log ----------------
    with tab_log:
        cari = st.text_input("Cari di agenda, divisi, atau pihak", placeholder="mis. streamlining, keuangan, Citos", key=f"{p}_cari")
        sub = df
        if cari.strip():
            c = cari.strip()
            gabung = sub["Agenda"] + " " + sub["Pihak"] + " " + sub["Divisi"].map(" ".join) + " " + sub["Fokus"]
            sub = sub[gabung.str.contains(c, case=False, regex=False)]
        tabel = _tabel_log(sub)
        st.caption(f"{len(tabel)} agenda")
        tidak_valid = sub[sub["Jam tidak valid"]]
        if len(tidak_valid):
            st.caption("Jam selesai tidak setelah jam mulai (durasi tidak dihitung), perlu dicek di Excel: "
                       + ", ".join(f"{_tgl(t)} ({j})" for t, j in zip(tidak_valid["Tanggal"], tidak_valid["Jam"])))
        ui.tampil_df(tabel, column_config={
            "Agenda dari BPK": st.column_config.TextColumn(width="large"),
            "Pihak yang diwawancara": st.column_config.TextColumn(width="medium"),
            "Durasi (menit)": st.column_config.NumberColumn("Durasi (menit)", format="%d"),
        })
        x1, x2, _ = st.columns([1, 1, 4])
        x1.download_button("Download CSV", tabel.to_csv(index=False).encode("utf-8-sig"),
                           file_name=f"{p}.csv", mime="text/csv", key=f"{p}_dl_csv")
        x2.download_button("Download Excel", ui.ke_excel(tabel), file_name=f"{p}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key=f"{p}_dl_xlsx")
