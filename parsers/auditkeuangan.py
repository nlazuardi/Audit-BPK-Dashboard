"""Sheet daftar permintaan data BPK (Audit Keuangan).

Aturan yang berlaku di sini:
- membaca seluruh sheet entitas: IFG Holding, Askrindo, Jamkrindo, Jasindo, Jasa Raharja, IFG Life
- tiap baris = 1 permintaan dokumen/data/informasi
- Status:
    * Done: bila tanggal pemenuhan terisi atau status mengandung kata dipenuhi/selesai/done
    * N/A: bila status/keterangan berisi "x", "n/a", dsb.
    * Pending: bila belum diserahkan
- Issue ditebak dari kata kunci (ISSUE_RULES)
- Divisi: list nama divisi (Holding) atau nama entitas (Anper bila kolom divisi kosong)
- parse() murni pandas. Tampilan khusus halaman ini ada di render() di bagian bawah; streamlit baru diimpor
  di dalam render(), jadi parse() tetap bisa dipakai/dites tanpa streamlit
"""
import re
from datetime import date, datetime
import altair as alt
import numpy as np
import pandas as pd

NAMA = "Audit Keuangan"
KUNCI = "auditkeuangan"   # nama di [link] secrets.toml
SHEET = "*"                # "*" = membaca SEMUA sheet entitas (IFG_Holding, Askrindo, Jamkrindo, Jasindo, JasaRaharja, IFGLife)
SIAP = True               # True = punya parse() lengkap, tampil sebagai dashboard
LABEL_JENIS = "Entitas"    # nama untuk kolom "Jenis Data" di judul, filter, dan grafik halaman ini

URUT_ISSUE = [
    "PSAK 117 & Aktuaria",
    "Audit KAP & Laporan Keuangan",
    "Konsolidasi & Interco",
    "Utang & Arus Kas",
    "Investasi & Portofolio",
    "Kebijakan & Prosedur",
    "Lain-lain",
]

SLA = True                 # True = halaman ini punya tab SLA
SLA_TARGET_HARI = 5        # target SLA default
SLA_HARI_KERJA = True      # True = hari kerja (Sen-Jum), False = hari kalender
LIBUR = []                 # hari libur nasional yang tidak dihitung

ENTITAS_MAP = {
    "ifg_holding": "IFG Holding",
    "ifg holding": "IFG Holding",
    "ifg": "IFG Holding",
    "holding": "IFG Holding",
    "askrindo": "Askrindo",
    "jamkrindo": "Jamkrindo",
    "jasindo": "Jasindo",
    "jasaraharja": "Jasa Raharja",
    "jasa raharja": "Jasa Raharja",
    "ifglife": "IFG Life",
    "ifg life": "IFG Life",
}

ISSUE_RULES = [
    ("PSAK 117 & Aktuaria", r"psak|tpp|mapping|transisi|sas|117|aktuari|prophet|cfgen|gmm|lrc|risk adjustment|contract screening|bootstrap|arp|mrp|premi|klaim|reasuransi|diskonto|pd lgd"),
    ("Audit KAP & Laporan Keuangan", r"kap|lha|management letter|audited|laporan keuangan|\blk\b|repack"),
    ("Konsolidasi & Interco", r"konsol|interco|eliminasi|reporting package|consolidation package|working paper|trial balance|komponen usaha|rekonsiliasi"),
    ("Utang & Arus Kas", r"mtn|utang|arus kas|kas\b"),
    ("Kebijakan & Prosedur", r"kebijakan|pedoman|sop|prosedur|struktur grup"),
    ("Investasi & Portofolio", r"investasi|reksadana|portofolio|efek|saham"),
]
ISSUE_LAIN = "Lain-lain"

NA_WORDS = {"n/a", "na", "n.a.", "n.a", "not applicable", "tidak berlaku", "x"}
DONE_WORDS = {"done", "selesai", "sudah", "sudah diserahkan", "diserahkan", "dipenuhi", "request telah dipenuhi"}


def _canonical_entity(name: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "", str(name).lower())
    for k in sorted(ENTITAS_MAP.keys(), key=len, reverse=True):
        if re.sub(r"[^a-z0-9]+", "", k) in key:
            return ENTITAS_MAP[k]
    return str(name).strip()


def _ke_tanggal(v):
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return pd.NaT
    if isinstance(v, (datetime, pd.Timestamp, date)):
        return pd.Timestamp(v).normalize()
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if 20000 < v < 80000:
            return pd.Timestamp("1899-12-30") + pd.to_timedelta(v, unit="D")
        return pd.NaT
    txt = str(v).strip()
    if not txt or txt in {"-", "—", "NaT", "nan"}:
        return pd.NaT
    return pd.to_datetime(txt, errors="coerce", dayfirst=True)


def _status(stat, tgl):
    s = str(stat).strip().lower() if pd.notna(stat) else ""
    if s in NA_WORDS:
        return "N/A"
    tgl_val = _ke_tanggal(tgl)
    if pd.notna(tgl_val):
        return "Done"
    if any(k in s for k in ("dipenuhi", "selesai", "done", "sudah")):
        return "Done"
    return "Pending"


def _tahap(stat):
    """Status pemenuhan dari sheet ("1. Request dari BPK" ... "6. Request telah dipenuhi"), apa adanya."""
    t = re.sub(r"\s+", " ", str(stat)).strip() if pd.notna(stat) else ""
    if not t:
        return "Tanpa status"
    return "N/A" if t.lower() in NA_WORDS else t


def _issue(teks):
    for nama, pola in ISSUE_RULES:
        if re.search(pola, str(teks), re.I):
            return nama
    return ISSUE_LAIN


def _divisi(div_val, entitas):
    if pd.isna(div_val) or str(div_val).strip() in ("", "-", "—", "nan", "x"):
        return [entitas] if entitas != "IFG Holding" else ["Belum ada PIC"]
    s = str(div_val).strip()
    parts = [p.strip() for p in re.split(r"[,;\n/]|(?:\bdan\b)", s) if p.strip() and p.strip().lower() != "nan"]
    return parts or [entitas]


def _parse_single_sheet(df: pd.DataFrame, sheet_name: str) -> list[dict]:
    ent = _canonical_entity(sheet_name)
    r = df.copy()
    r.columns = range(r.shape[1])

    hdr_idx = None
    for i in range(min(10, len(r))):
        row_str = " ".join(str(x) for x in r.iloc[i].dropna()).lower()
        if any(k in row_str for k in ("nama dokumen", "data yang diminta", "permintaan data", "uraian data")):
            hdr_idx = i
            break
    if hdr_idx is None:
        return []

    hdr = [str(c).replace("\n", " ").strip().lower() for c in r.loc[hdr_idx]]

    def find_col(words):
        return next((i for i, h in enumerate(hdr) if any(w in h for w in words)), None)

    c_no = find_col(["no", "nomor"])
    c_req = find_col(["nama dokumen", "permintaan", "data yang", "uraian"])
    c_req_tgl = find_col(["tanggal permintaan", "tgl permintaan", "tgl request"])
    c_div = find_col(["divisi", "unit terkait", "pic"])
    c_stat = find_col(["status"])
    c_pem_tgl = find_col(["tanggal pemenuhan", "penyerahan", "tgl pemenuhan"])
    c_ket = find_col(["keterangan", "catatan"])

    if c_req is None:
        return []

    body = r.loc[hdr_idx + 1:].dropna(how="all").copy()
    items = []
    for _, row in body.iterrows():
        req_text = str(row[c_req]).strip() if c_req is not None and pd.notna(row[c_req]) else ""
        if not req_text or req_text.lower() in ("nan", "x", "-", "—"):
            continue

        no_val = str(row[c_no]).strip() if c_no is not None and pd.notna(row[c_no]) else "-"
        if no_val.endswith(".0"):
            no_val = no_val[:-2]

        stat_cell = row[c_stat] if c_stat is not None else ""
        pem_cell = row[c_pem_tgl] if c_pem_tgl is not None else None
        req_tgl_cell = row[c_req_tgl] if c_req_tgl is not None else None
        div_cell = row[c_div] if c_div is not None else None
        ket_cell = row[c_ket] if c_ket is not None else ""

        tgl_req = _ke_tanggal(req_tgl_cell)
        tgl_pem = _ke_tanggal(pem_cell)
        stat = _status(stat_cell, pem_cell)
        div = _divisi(div_cell, ent)
        iss = _issue(req_text)
        ket = str(ket_cell).strip() if pd.notna(ket_cell) and str(ket_cell).strip() != "nan" else ""

        items.append({
            "No": no_val,
            "Permintaan Data": req_text,
            "Jenis Data": ent,
            "Divisi": div,
            "Issue": iss,
            "Status": stat,
            "Tahap": _tahap(stat_cell),
            "PIC (Nama)": div[0] if div else ent,
            "Tanggal penyerahan ke BPK": tgl_pem.strftime("%d/%m/%Y") if pd.notna(tgl_pem) else "",
            "Tgl Permintaan": tgl_req,
            "Tgl ke Auditi": pd.NaT,
            "Tgl dari Auditi": pd.NaT,
            "Tgl Selesai": tgl_pem,
            "Judul Induk": "",
            "Keterangan": ket,
        })
    return items


def parse(raw: pd.DataFrame) -> pd.DataFrame:
    # raw = dict {nama sheet: tabel} (SHEET = "*"), atau satu tabel kalau cuma satu sheet yang dibaca
    sheets = raw if isinstance(raw, dict) else {"IFG_Holding": raw}

    all_items = []
    for sheet_name, df_sheet in sheets.items():
        if df_sheet is not None and not df_sheet.empty:
            all_items.extend(_parse_single_sheet(df_sheet, sheet_name))

    if not all_items:
        raise ValueError("Tidak ada data permintaan valid yang ditemukan di sheet.")

    out = pd.DataFrame(all_items)
    return out.reset_index(drop=True)



# ====================================================================================================
# TAMPILAN HALAMAN: perbandingan progres antar entitas (untuk laporan)
# ====================================================================================================
STATUS = ["Done", "Pending", "N/A"]
WARNA_STATUS = {"Done": "#2E9E5B", "Pending": "#F2A33A", "N/A": "#9AA0A6"}
ENTITAS_URUT = ["IFG Holding", "Askrindo", "Jamkrindo", "Jasindo", "Jasa Raharja", "IFG Life"]
PALET_ENTITAS = {"IFG Holding": "#0B3D91", "Askrindo": "#1FB5A6", "Jamkrindo": "#F2B233",
                 "Jasindo": "#7B4FD6", "Jasa Raharja": "#E5484D", "IFG Life": "#4CAF50"}
WARNA_TAHAP = {1: "#9DB4D6", 2: "#7F9BC4", 3: "#5F82B4", 4: "#F2A33A", 5: "#E40428", 6: "#2E9E5B"}
TINDAK_LANJUT = (4, 5)   # status 4 "butuh konfirmasi ke BPK" dan 5 "data/dokumen belum sesuai"


def _kode_tahap(label):
    m = re.match(r"\s*(\d+)\.", str(label))
    return int(m.group(1)) if m else 99


def _stack_bar(agg, kat, seri, urut_kat, urut_seri, warna, persen=False, legend_vertikal=False):
    """Bar horizontal bertumpuk. agg berkolom [kat, seri, Jumlah]. persen=True: tiap batang jadi 100%."""
    d = agg.copy()
    total = d.groupby(kat)["Jumlah"].transform("sum")
    d["nilai"] = d["Jumlah"] / total * 100 if persen else d["Jumlah"].astype(float)
    d["_u"] = d[seri].map({x: i for i, x in enumerate(urut_seri)})
    d = d.sort_values([kat, "_u"])
    d["hi"] = d.groupby(kat)["nilai"].cumsum()
    d["lo"] = d["hi"] - d["nilai"]
    d["mid"] = (d["lo"] + d["hi"]) / 2
    if persen:
        d["teks"] = d["nilai"].round(0).astype(int).astype(str) + "%"
        minimal = 8
    else:
        d["teks"] = d["Jumlah"].astype(int).astype(str)
        minimal = max(1, round(d.groupby(kat)["nilai"].sum().max() * 0.035))
    skala = alt.Scale(domain=urut_seri, range=[warna.get(x, "#9AA0A6") for x in urut_seri])
    y = alt.Y(f"{kat}:N", sort=urut_kat, title=None, axis=alt.Axis(labelLimit=300))
    if persen:
        x = alt.X("lo:Q", title="Persentase", scale=alt.Scale(domain=[0, 100]), axis=alt.Axis(labelExpr="datum.value + '%'"))
    else:
        x = alt.X("lo:Q", title="Jumlah permintaan", axis=alt.Axis(tickMinStep=1))
    legend = alt.Legend(orient="bottom", title=None, columns=1 if legend_vertikal else 0, labelLimit=320)
    bars = alt.Chart(d).mark_bar().encode(
        y=y, x=x, x2="hi:Q", color=alt.Color(f"{seri}:N", scale=skala, legend=legend), tooltip=[kat, seri, "Jumlah"])
    teks = (
        alt.Chart(d).mark_text(color="white", fontWeight="bold", size=12)
        .encode(y=alt.Y(f"{kat}:N", sort=urut_kat), x="mid:Q", text="teks:N")
        .transform_filter(f"datum.nilai >= {minimal}")
    )
    # Streamlit memaksa grafik + legenda muat di tinggi ini, jadi tinggi legenda ikut ditambahkan
    tinggi = max(150, 38 * len(urut_kat) + 50) + (22 * len(urut_seri) if legend_vertikal else 30)
    return alt.layer(bars, teks).properties(height=tinggi)


def _bar_entitas(df, ent_urut, persen):
    g = df.groupby(["Jenis Data", "Status"]).size().unstack(fill_value=0).reindex(columns=STATUS, fill_value=0)
    g["Total"] = g.sum(axis=1)
    g["pct"] = g["Done"] / g["Total"]
    g = g.loc[[e for e in ent_urut if e in g.index]].sort_values(["pct", "Total"], ascending=[False, False])
    label = {e: f"{e} · {int(r.Done)}/{int(r.Total)} ({r.pct:.0%})" for e, r in g.iterrows()}
    agg = df.groupby(["Jenis Data", "Status"]).size().reset_index(name="Jumlah")
    agg["Entitas"] = agg["Jenis Data"].map(label)
    return _stack_bar(agg, "Entitas", "Status", [label[e] for e in g.index], STATUS, WARNA_STATUS, persen=persen)


def _bar_tahap(df, ent_urut):
    agg = df.groupby(["Jenis Data", "Tahap"]).size().reset_index(name="Jumlah")
    urut_tahap = sorted(agg["Tahap"].unique(), key=_kode_tahap)
    warna = {t: WARNA_TAHAP.get(_kode_tahap(t), "#9AA0A6") for t in urut_tahap}
    return _stack_bar(agg, "Jenis Data", "Tahap", [e for e in ent_urut if e in set(agg["Jenis Data"])], urut_tahap, warna,
                      legend_vertikal=True)


def _bar_minggu(df, ent_urut):
    d = df.dropna(subset=["Tgl Permintaan"]).copy()
    d["Minggu"] = d["Tgl Permintaan"].dt.to_period("W-SUN").dt.start_time
    agg = d.groupby(["Minggu", "Jenis Data"]).size().reset_index(name="Jumlah")
    ada = [e for e in ent_urut if e in set(agg["Jenis Data"])]
    skala = alt.Scale(domain=ada, range=[PALET_ENTITAS.get(e, "#9AA0A6") for e in ada])
    awal, akhir = agg["Minggu"].min() - pd.Timedelta(days=5), agg["Minggu"].max() + pd.Timedelta(days=11)   # ruang di tepi supaya batang tidak terpotong
    bars = alt.Chart(agg).mark_bar(size=26).encode(
        x=alt.X("Minggu:T", title="Minggu (mulai Senin)", scale=alt.Scale(domain=[awal.strftime("%Y-%m-%d"), akhir.strftime("%Y-%m-%d")]),
                axis=alt.Axis(format="%d %b", labelAngle=0, tickCount="week")),
        y=alt.Y("Jumlah:Q", title="Permintaan masuk", axis=alt.Axis(tickMinStep=1)),
        color=alt.Color("Jenis Data:N", scale=skala, legend=alt.Legend(orient="bottom", title=None, columns=3, labelLimit=200)),
        order=alt.Order("Jenis Data:N"),
        tooltip=[alt.Tooltip("Minggu:T", format="%d %b %Y"), "Jenis Data", "Jumlah"],
    )
    return bars.properties(height=300 + 60)


def _heatmap(df, ent_urut, urut_issue):
    g = df.groupby(["Jenis Data", "Issue"]).agg(Total=("Status", "size"), Pending=("Status", lambda s: int((s == "Pending").sum()))).reset_index()
    ada = [e for e in ent_urut if e in set(df["Jenis Data"])]
    full = pd.MultiIndex.from_product([ada, urut_issue], names=["Jenis Data", "Issue"]).to_frame(index=False)
    g = full.merge(g, how="left", on=["Jenis Data", "Issue"]).fillna({"Total": 0, "Pending": 0})
    g["Total"], g["Pending"] = g["Total"].astype(int), g["Pending"].astype(int)
    g["teks"] = np.where(g["Total"] > 0, g["Pending"].astype(str) + "/" + g["Total"].astype(str), "")
    batas = max(2, int(g["Pending"].max() * 0.6))
    base = alt.Chart(g).encode(
        x=alt.X("Issue:N", sort=urut_issue, title=None, axis=alt.Axis(labelAngle=-25, labelLimit=170)),
        y=alt.Y("Jenis Data:N", sort=ada, title=None),
    )
    rect = base.mark_rect(stroke="white", strokeWidth=2).encode(
        color=alt.Color("Pending:Q", scale=alt.Scale(domain=[0, max(1, int(g["Pending"].max()))], interpolate="rgb",
                                                    range=["#F1F3F5", "#F8CF8E", "#E0861B", "#9A4A00"]),
                        legend=alt.Legend(title="Pending", orient="right")),
        tooltip=["Jenis Data", "Issue", "Total", "Pending"],
    )
    teks = base.mark_text(fontSize=13, fontWeight="bold").encode(
        text="teks:N", color=alt.condition(alt.datum.Pending >= batas, alt.value("white"), alt.value("#111111")))
    return alt.layer(rect, teks).properties(height=44 * len(ada) + 130)


def _tabel(d, kolom):
    t = d[[c for c in kolom if c in d.columns]].copy()
    if "Divisi" in t:
        t["Divisi"] = t["Divisi"].map(", ".join)
    for c in [c for c in t.columns if c.startswith("Tgl ")]:
        t[c] = t[c].dt.strftime("%d-%b-%y").fillna("")
    return t.rename(columns={"Lama total": "Lama total (hari)"}).reset_index(drop=True)


def render(raw):
    import streamlit as st
    from datetime import datetime, timedelta, timezone
    from core.sla import KATEGORI, hitung_sla
    from tampilan import ui

    try:
        semua = parse(raw)
    except Exception as e:
        st.error(f"Format sheet '{NAMA}' tidak sesuai dengan aturan bacanya: {e}")
        return
    p = KUNCI

    # ---------- sidebar: SLA lalu filter ----------
    with st.sidebar:
        st.header("SLA")
        target = int(st.number_input("Target SLA (hari)", min_value=1, max_value=365, value=int(SLA_TARGET_HARI), step=1, key=f"{p}_sla_target"))
        kerja = st.radio("Satuan hari", ["Hari kerja", "Hari kalender"], index=0 if SLA_HARI_KERJA else 1, key=f"{p}_sla_satuan") == "Hari kerja"
    satuan = "hari kerja" if kerja else "hari kalender"
    semua = hitung_sla(semua, target, kerja, LIBUR, datetime.now(timezone(timedelta(hours=7))).date())

    ada_ent = set(semua["Jenis Data"])
    ent_urut = [e for e in ENTITAS_URUT if e in ada_ent] + sorted(ada_ent - set(ENTITAS_URUT))
    with st.sidebar:
        st.header("Filter")
        f_ent = st.multiselect("Entitas", ent_urut, key=f"{p}_f_ent")
        f_issue = st.multiselect("Issue", URUT_ISSUE, key=f"{p}_f_issue")
        f_status = st.multiselect("Status", STATUS, key=f"{p}_f_status")
        f_tahap = st.multiselect("Status pemenuhan", sorted(semua["Tahap"].unique(), key=_kode_tahap), key=f"{p}_f_tahap")

    df = semua
    if f_ent:
        df = df[df["Jenis Data"].isin(f_ent)]
    if f_issue:
        df = df[df["Issue"].isin(f_issue)]
    if f_status:
        df = df[df["Status"].isin(f_status)]
    if f_tahap:
        df = df[df["Tahap"].isin(f_tahap)]
    if df.empty:
        st.warning("Tidak ada data untuk filter ini.")
        return
    ent_urut = [e for e in ent_urut if e in set(df["Jenis Data"])]

    n = len(df)
    c = df["Status"].value_counts()
    done, pend, na = (int(c.get(s, 0)) for s in STATUS)
    tl = df["Tahap"].map(_kode_tahap).isin(TINDAK_LANJUT)
    n_tl = int(tl.sum())

    def pct(x):
        return f"{x / n:.0%}" if n else "-"

    per_ent = df.groupby("Jenis Data")["Status"].agg(total="size", done=lambda s: int((s == "Done").sum()))
    per_ent["pct"] = per_ent["done"] / per_ent["total"]
    tertinggi, terendah = per_ent["pct"].idxmax(), per_ent["pct"].idxmin()

    tab_ban, tab_det, tab_sla, tab_log = st.tabs(["Perbandingan Entitas", "Detail per Entitas", "SLA", "Log Permintaan"])

    # ================= Perbandingan Entitas =================
    with tab_ban:
        ringkas = f"Dari **{n} permintaan dokumen** di **{len(per_ent)} entitas**, **{done} ({pct(done)})** sudah terpenuhi dan **{pend}** masih pending. "
        if len(per_ent) > 1:
            ringkas += f"Progres tertinggi **{tertinggi} ({per_ent.loc[tertinggi, 'pct']:.0%})**, terendah **{terendah} ({per_ent.loc[terendah, 'pct']:.0%})**. "
        if n_tl:
            ringkas += f"**{n_tl} permintaan** perlu tindak lanjut (status 4 atau 5)."
        st.markdown(ringkas)
        st.markdown(
            '<div class="kartu-wrap">'
            + ui.kartu("Total permintaan", n, f"di {len(per_ent)} entitas", ui.HITAM)
            + ui.kartu("Done", done, f"{pct(done)} dari total", WARNA_STATUS["Done"])
            + ui.kartu("Pending", pend, f"{pct(pend)} dari total", WARNA_STATUS["Pending"])
            + ui.kartu("Perlu tindak lanjut", n_tl, "status 4 (butuh konfirmasi) atau 5 (belum sesuai)", "#E40428")
            + "</div>", unsafe_allow_html=True)
        st.caption("Done = tanggal pemenuhan terisi, atau status mengandung dipenuhi/selesai/done. Status pemenuhan 1–6 mengikuti kolom di sheet.")

        st.markdown("#### Progres per Entitas")
        mode = st.radio("Tampilan", ["Jumlah", "Persentase"], horizontal=True, key=f"{p}_mode")
        ch1 = _bar_entitas(df, ent_urut, persen=(mode == "Persentase"))
        ui.tampil_chart(ch1)
        ui.tombol_png(ch1, f"{p}_progres_entitas", f"{p}_png_ent", "Progres pemenuhan dokumen per entitas", lebar=760)

        g1, g2 = st.columns(2)
        with g1:
            st.markdown("#### Status Pemenuhan per Entitas")
            ch2 = _bar_tahap(df, ent_urut)
            ui.tampil_chart(ch2)
            ui.tombol_png(ch2, f"{p}_status_pemenuhan", f"{p}_png_tahap", "Status pemenuhan per entitas", lebar=620)
        with g2:
            st.markdown("#### Permintaan Masuk per Minggu")
            ch3 = _bar_minggu(df, ent_urut)
            ui.tampil_chart(ch3)
            ui.tombol_png(ch3, f"{p}_permintaan_per_minggu", f"{p}_png_minggu", "Permintaan masuk per minggu", lebar=620)

        st.markdown("#### Pending per Entitas dan Issue")
        ch4 = _heatmap(df, ent_urut, URUT_ISSUE)
        ui.tampil_chart(ch4)
        ui.tombol_png(ch4, f"{p}_heatmap_issue", f"{p}_png_heat", "Pending / total per entitas dan issue", lebar=760)
        st.caption("Angka di kotak = pending/total. Makin gelap makin banyak yang masih pending.")

    # ================= Detail per Entitas =================
    with tab_det:
        pilih = st.selectbox("Pilih entitas", ent_urut, key=f"{p}_pilih_ent")
        e = df[df["Jenis Data"] == pilih]
        ce = e["Status"].value_counts()
        tle = int(e["Tahap"].map(_kode_tahap).isin(TINDAK_LANJUT).sum())
        st.markdown(
            '<div class="kartu-wrap">'
            + ui.kartu("Total permintaan", len(e), pilih, ui.HITAM)
            + ui.kartu("Done", int(ce.get("Done", 0)), f"{ce.get('Done', 0) / len(e):.0%} dari total", WARNA_STATUS["Done"])
            + ui.kartu("Pending", int(ce.get("Pending", 0)), f"{ce.get('Pending', 0) / len(e):.0%} dari total", WARNA_STATUS["Pending"])
            + ui.kartu("Perlu tindak lanjut", tle, "status 4 atau 5", "#E40428")
            + "</div>", unsafe_allow_html=True)

        d1, d2 = st.columns(2)
        with d1:
            st.markdown("#### Berdasarkan Issue")
            ai = e.groupby(["Issue", "Status"]).size().reset_index(name="Jumlah")
            ci = _stack_bar(ai, "Issue", "Status", [i for i in URUT_ISSUE if i in set(ai["Issue"])], STATUS, WARNA_STATUS)
            ui.tampil_chart(ci)
            ui.tombol_png(ci, f"{p}_{pilih}_issue".replace(" ", "_"), f"{p}_png_det_issue", f"{pilih}: permintaan per issue", lebar=620)
        with d2:
            if pilih == "IFG Holding":
                st.markdown("#### Berdasarkan Divisi")
                ex = e.explode("Divisi")
                ad = ex.groupby(["Divisi", "Status"]).size().reset_index(name="Jumlah")
                urut_d = ad.groupby("Divisi")["Jumlah"].sum().sort_values(ascending=False).index.tolist()
                cd = _stack_bar(ad, "Divisi", "Status", urut_d, STATUS, WARNA_STATUS)
                ui.tampil_chart(cd)
                ui.tombol_png(cd, f"{p}_holding_divisi", f"{p}_png_det_div", "IFG Holding: permintaan per divisi", lebar=620)
            else:
                st.markdown("#### Status Pemenuhan")
                at = e.groupby(["Tahap", "Status"]).size().reset_index(name="Jumlah")
                at["Status pemenuhan"] = at["Tahap"]
                at2 = at.groupby("Status pemenuhan")["Jumlah"].sum().reset_index()
                at2["Seri"] = "Jumlah"
                urut_t = sorted(at2["Status pemenuhan"].unique(), key=_kode_tahap)
                ct = _stack_bar(at2, "Status pemenuhan", "Seri", urut_t, ["Jumlah"], {"Jumlah": "#0B3D91"})
                ui.tampil_chart(ct)
                st.caption("Kolom divisi/PIC tidak diisi untuk entitas ini, jadi rincian per divisi tidak ditampilkan.")

        tl_e = e[e["Tahap"].map(_kode_tahap).isin(TINDAK_LANJUT)]
        if len(tl_e):
            st.markdown("#### Perlu Tindak Lanjut")
            t = _tabel(tl_e, ["No", "Permintaan Data", "Divisi", "Tahap", "Tgl Permintaan", "Keterangan"])
            ui.tampil_df(t, column_config=ui.cfg_tabel(t))
        st.markdown("#### Pending (paling lama menunggu di atas)")
        pe = e[e["Status"] == "Pending"].sort_values("Hari berjalan", ascending=False)
        if pe.empty:
            st.success("Tidak ada permintaan pending untuk entitas ini.")
        else:
            t = _tabel(pe, ["No", "Permintaan Data", "Divisi", "Issue", "Tgl Permintaan", "Hari berjalan", "Tahap", "Status SLA"])
            ui.tampil_df(ui.berwarna(t), column_config=ui.cfg_tabel(t))

    # ================= SLA =================
    with tab_sla:
        st.caption(f"Target SLA: {target} {satuan}, dihitung dari tanggal permintaan sampai tanggal pemenuhan. "
                   "Yang masih Pending dihitung sampai hari ini. Baris N/A atau tanpa tanggal tidak dihitung.")
        selesai = df[df["Status SLA"].isin(["Sesuai SLA", "Terlambat"])]
        n_ok = int((df["Status SLA"] == "Sesuai SLA").sum())
        n_tel = int((df["Status SLA"] == "Terlambat").sum())
        n_lewat = int((df["Status SLA"] == "Pending (lewat SLA)").sum())
        rata, med = selesai["Lama total"].mean(), selesai["Lama total"].median()
        st.markdown(
            '<div class="kartu-wrap">'
            + ui.kartu("Sesuai SLA", n_ok, f"{n_ok / len(selesai):.0%} dari yang selesai" if len(selesai) else "-", ui.WARNA_SLA["Sesuai SLA"])
            + ui.kartu("Terlambat", n_tel, "selesai tapi melewati target", ui.WARNA_SLA["Terlambat"])
            + ui.kartu("Pending lewat SLA", n_lewat, "belum selesai dan sudah lewat target", ui.WARNA_SLA["Pending (lewat SLA)"])
            + ui.kartu("Rata-rata lama", "-" if pd.isna(rata) else f"{rata:.1f}", "-" if pd.isna(med) else f"median {med:.0f} {satuan}", ui.HITAM)
            + "</div>", unsafe_allow_html=True)
        st.markdown("#### Status SLA")
        cs = ui.chart_sla_status(df)
        ui.tampil_chart(cs)
        ui.tombol_png(cs, f"{p}_status_sla", f"{p}_png_sla", f"Status SLA (target {target} {satuan})", lebar=620)

        st.markdown("#### SLA per Entitas")
        baris = []
        for ent, g in df.groupby("Jenis Data"):
            sel = g["Status SLA"].isin(["Sesuai SLA", "Terlambat"])
            ok = int((g["Status SLA"] == "Sesuai SLA").sum())
            baris.append({"Entitas": ent, "Selesai": int(sel.sum()), "Sesuai SLA": ok,
                          "Terlambat": int((g["Status SLA"] == "Terlambat").sum()),
                          "% Sesuai SLA": round(ok / sel.sum() * 100) if sel.sum() else None,
                          "Rata-rata lama (hari)": round(float(g.loc[sel, "Lama total"].mean()), 1) if sel.any() else None,
                          "Pending lewat SLA": int((g["Status SLA"] == "Pending (lewat SLA)").sum())})
        tabel_sla = pd.DataFrame(baris)
        tabel_sla["_u"] = tabel_sla["Entitas"].map({e_: i for i, e_ in enumerate(ent_urut)})
        ui.tampil_df(tabel_sla.sort_values("_u").drop(columns="_u"),
                     column_config={"% Sesuai SLA": st.column_config.ProgressColumn("% Sesuai SLA", min_value=0, max_value=100, format="%d%%")})

        st.markdown("#### Perlu Perhatian")
        perlu = df[df["Status SLA"].isin(["Terlambat", "Pending (lewat SLA)"])].copy()
        if perlu.empty:
            st.success("Tidak ada permintaan yang terlambat atau lewat SLA.")
        else:
            perlu["Lama / berjalan (hari)"] = perlu["Lama total"].fillna(perlu["Hari berjalan"])
            perlu = perlu.sort_values("Lama / berjalan (hari)", ascending=False)
            st.caption(f"{len(perlu)} baris, diurutkan dari yang paling lama")
            t = _tabel(perlu, ["Jenis Data", "No", "Permintaan Data", "Divisi", "Status SLA", "Lama / berjalan (hari)"])
            ui.tampil_df(ui.berwarna(t), column_config=ui.cfg_tabel(t))

    # ================= Log =================
    with tab_log:
        cari = st.text_input("Cari di teks permintaan", placeholder="mis. PSAK, trial balance, laporan keuangan", key=f"{p}_cari")
        pending_dulu = st.checkbox("Pending paling atas", value=True, key=f"{p}_pending_dulu")
        sub = df
        if cari.strip():
            sub = df[df["Permintaan Data"].astype(str).str.contains(cari.strip(), case=False, regex=False)]
        if pending_dulu:
            sub = sub.assign(_r=sub["Status"].map({"Pending": 0, "N/A": 1, "Done": 2})).sort_values("_r", kind="stable")
        tabel = _tabel(sub, ["Jenis Data", "No", "Permintaan Data", "Divisi", "Issue", "Status", "Tahap", "Status SLA",
                             "Lama total", "Tgl Permintaan", "Tgl Selesai", "Keterangan"])
        st.caption(f"{len(tabel)} baris")
        ui.tampil_df(ui.berwarna(tabel), column_config=ui.cfg_tabel(tabel))
        x1, x2, _ = st.columns([1, 1, 4])
        x1.download_button("Download CSV", tabel.to_csv(index=False).encode("utf-8-sig"),
                           file_name=f"{p}.csv", mime="text/csv", key=f"{p}_dl_csv")
        x2.download_button("Download Excel", ui.ke_excel(tabel), file_name=f"{p}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key=f"{p}_dl_xlsx")
