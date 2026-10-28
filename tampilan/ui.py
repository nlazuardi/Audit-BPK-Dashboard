"""Semua yang berhubungan dengan tampilan: kartu, grafik, tabel, filter, header.
Nggak ada logika baca data di sini. Terima tabel dengan kolom standar dan gambar.
"""
import html as _html
import io
from datetime import datetime, timedelta, timezone
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from core.sla import KATEGORI, hitung_sla

DIR = Path(__file__).resolve().parent
LOGO = DIR.parent / "assets" / "logo.svg"

MERAH = "#E40428"          # merah IFG
HITAM = "#111111"
STATUS_URUT = ["Done", "Pending", "N/A"]
WARNA_STATUS = {"Done": "#2E9E5B", "Pending": "#F2A33A", "N/A": "#9AA0A6"}
WARNA = alt.Scale(domain=STATUS_URUT, range=[WARNA_STATUS[s] for s in STATUS_URUT])


alt.theme.enable("default")


def pasang_css(presentasi: bool = False):
    css = (DIR / "style.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    if presentasi:
        css2 = (DIR / "presentasi.css").read_text(encoding="utf-8")
        st.markdown(f"<style>{css2}</style>", unsafe_allow_html=True)


def header(judul: str, subjudul: str, waktu: str):
    c_logo, c_judul, c_mode = st.columns([0.5, 3.3, 1], vertical_alignment="center")
    with c_logo:
        if LOGO.exists():
            st.image(str(LOGO), width=180)
    with c_judul:
        st.markdown(
            f'<h2 style="margin:0;padding:0;font-weight:800;line-height:1.15">{_html.escape(judul)}</h2>'
            f'<div style="color:#5B6470;margin-top:2px;padding:0;line-height:1.2">{_html.escape(subjudul)} &nbsp;&middot;&nbsp; '
            f'Data diperbarui: <b>{_html.escape(waktu)}</b></div>',
            unsafe_allow_html=True,
        )
    with c_mode:
        st.toggle("Mode presentasi", key="present")
    st.markdown('<div class="garis"></div>', unsafe_allow_html=True)


def kartu(label, angka, sub, warna):
    return (f'<div class="kartu" style="--c:{warna}"><div class="lbl">{label}</div>'
            f'<div class="num">{angka}</div><div class="sub">{sub}</div></div>')


def bar_per_jenis(df):
    out = ""
    for jenis, g in df.groupby("Jenis Data", sort=False):
        n = len(g)
        c = g["Status"].value_counts()
        d, p, a = (int(c.get(k, 0)) for k in STATUS_URUT)
        lebar = [x / n * 100 for x in (d, p, a)]
        out += (
            f'<div class="jenis-row"><div class="jt"><span>{_html.escape(str(jenis))}</span>'
            f'<span>{d}/{n} Done &middot; {d / n:.0%}</span></div><div class="bar">'
            f'<span style="width:{lebar[0]:.1f}%;background:{WARNA_STATUS["Done"]}"></span>'
            f'<span style="width:{lebar[1]:.1f}%;background:{WARNA_STATUS["Pending"]}"></span>'
            f'<span style="width:{lebar[2]:.1f}%;background:{WARNA_STATUS["N/A"]}"></span></div></div>'
        )
    out += '<div class="legend">' + "".join(
        f'<i style="background:{WARNA_STATUS[s]}"></i>{s}' for s in STATUS_URUT) + "</div>"
    return out


# ====== GRAFIK ======
def _legend():
    return alt.Legend(orient="bottom", title=None)


def chart_donut(data):
    agg = data.groupby("Status").size().reindex(STATUS_URUT, fill_value=0).reset_index(name="Jumlah")
    agg = agg[agg["Jumlah"] > 0]
    total = int(agg["Jumlah"].sum())
    done = int(agg.loc[agg["Status"] == "Done", "Jumlah"].sum())
    pilih = alt.selection_point(name="pilih_status", fields=["Status"])
    arc = (
        alt.Chart(agg)
        .mark_arc(innerRadius=72, outerRadius=125)
        .encode(
            theta=alt.Theta("Jumlah:Q", stack=True),
            color=alt.Color("Status:N", scale=WARNA, legend=_legend()),
            opacity=alt.condition(pilih, alt.value(1), alt.value(0.35)),
            tooltip=["Status", "Jumlah"],
        )
        .add_params(pilih)
    )
    angka = (
        alt.Chart(agg)
        .mark_text(radius=98, size=14, fontWeight="bold", color="white")
        .encode(theta=alt.Theta("Jumlah:Q", stack=True), text="Jumlah:Q")
        .transform_filter(f"datum.Jumlah >= {max(2, round(total * 0.04))}")
    )
    info = pd.DataFrame({"t": [f"{done / total:.0%}" if total else "-"], "s": ["Done"]})
    tengah = alt.Chart(info).mark_text(size=32, fontWeight="bold", color=HITAM, dy=-8).encode(text="t:N")
    tengah2 = alt.Chart(info).mark_text(size=13, color="#5B6470", dy=18).encode(text="s:N")
    return alt.layer(arc, angka, tengah, tengah2).properties(height=330)


def chart_stacked(data, kolom, urut, nama_pilih, tinggi=320):
    agg = data.groupby([kolom, "Status"]).size().reset_index(name="Jumlah")
    agg["urut"] = agg["Status"].map({s: i for i, s in enumerate(STATUS_URUT)})
    pilih = alt.selection_point(name=nama_pilih, fields=[kolom])
    minimal = max(2, round(agg.groupby(kolom)["Jumlah"].sum().max() * 0.035))  # sembunyikan label di segmen kecil
    base = (
        alt.Chart(agg)
        .transform_stack(stack="Jumlah", groupby=[kolom], sort=[alt.SortField("urut", order="ascending")], as_=["lo", "hi"])
        .transform_calculate(mid="(datum.lo + datum.hi) / 2")
    )
    sumbu_y = alt.Y(f"{kolom}:N", sort=urut, title=None)
    bars = (
        base.mark_bar()
        .encode(
            y=sumbu_y,
            x=alt.X("lo:Q", title="Jumlah baris permintaan"),
            x2="hi:Q",
            color=alt.Color("Status:N", scale=WARNA, legend=_legend()),
            opacity=alt.condition(pilih, alt.value(1), alt.value(0.35)),
            tooltip=[kolom, "Status", "Jumlah"],
        )
        .add_params(pilih)
    )
    angka = (
        base.mark_text(color="white", fontWeight="bold", size=12)
        .encode(y=alt.Y(f"{kolom}:N", sort=urut), x="mid:Q", text="Jumlah:Q")
        .transform_filter(f"datum.Jumlah >= {minimal}")
    )
    return alt.layer(bars, angka).properties(height=tinggi)


def tampil_chart(chart, key=None, klik=False):
    """Klik di grafik = filter (Streamlit baru). Versi lama otomatis jadi grafik biasa."""
    if klik:
        for kw in ({"width": "stretch"}, {"use_container_width": True}):
            try:
                st.altair_chart(chart, on_select="rerun", key=key, **kw)
                return
            except TypeError:
                continue
    try:
        st.altair_chart(chart, width="stretch")
    except TypeError:
        st.altair_chart(chart, use_container_width=True)


def _tanpa_attrs(obj):
    """Kosongkan metadata (attrs) pandas pada tabel sebelum dikirim ke st.dataframe."""
    data = getattr(obj, "data", None)                     # Styler -> DataFrame di dalamnya
    target = data if isinstance(data, pd.DataFrame) else obj
    if isinstance(target, pd.DataFrame) and target.attrs:
        target.attrs = {}
    return obj


def tampil_df(obj, **kw):
    obj = _tanpa_attrs(obj)
    try:
        st.dataframe(obj, hide_index=True, width="stretch", **kw)
    except TypeError:
        st.dataframe(obj, hide_index=True, use_container_width=True, **kw)


# ====== TABEL ======
KOLOM_TABEL = ["Jenis Data", "No", "Permintaan Data", "Judul Induk", "Divisi", "PIC (Nama)", "Issue", "Status",
               "Status SLA", "Lama total", "Tanggal penyerahan ke BPK", "Konfirmasi dari BPK"]


def _fmt(v):
    if pd.isna(v):
        return ""
    if hasattr(v, "strftime"):
        return v.strftime("%d-%b-%y")
    return str(v).replace("\n", " / ").strip()


def siapkan_tabel(df, pending_dulu=True, kolom=None):
    t = df
    if pending_dulu:
        t = t.assign(_r=t["Status"].map({"Pending": 0, "N/A": 1, "Done": 2})).sort_values("_r", kind="stable")
    kolom = [c for c in (kolom or KOLOM_TABEL) if c in t.columns]
    t = t[kolom].copy()
    t["Divisi"] = t["Divisi"].map(", ".join)
    for c in ("Tanggal penyerahan ke BPK", "Konfirmasi dari BPK", "PIC (Nama)"):
        if c in t.columns:
            t[c] = t[c].map(_fmt)
    t["Permintaan Data"] = t["Permintaan Data"].astype(str)
    return t.rename(columns={"Lama total": "Lama total (hari)"}).reset_index(drop=True)


WARNA_SEL = {
    "Done": "background-color:#DFF3E6;color:#14683A;font-weight:600",
    "Pending": "background-color:#FDEBD0;color:#9A5B00;font-weight:600",
    "N/A": "background-color:#ECEEF0;color:#555555;font-weight:600",
}


WARNA_SLA = {"Sesuai SLA": "#2E9E5B", "Terlambat": "#E40428", "Pending (dalam SLA)": "#F2A33A",
             "Pending (lewat SLA)": "#B45F06", "Tidak dihitung": "#9AA0A6"}
WARNA_SEL_SLA = {
    "Sesuai SLA": "background-color:#DFF3E6;color:#14683A;font-weight:600",
    "Terlambat": "background-color:#FADADF;color:#A0001B;font-weight:600",
    "Pending (dalam SLA)": "background-color:#FDEBD0;color:#9A5B00;font-weight:600",
    "Pending (lewat SLA)": "background-color:#F8D9B8;color:#7A4100;font-weight:600",
    "Tidak dihitung": "background-color:#ECEEF0;color:#555555;font-weight:600",
}


def berwarna(t):
    sty = t.style
    for kolom, peta in (("Status", WARNA_SEL), ("Status SLA", WARNA_SEL_SLA)):
        if kolom in t.columns:
            fn = sty.map if hasattr(sty, "map") else sty.applymap
            sty = fn(lambda v, peta=peta: peta.get(v, ""), subset=[kolom])
    return sty


def cfg_tabel(t):
    """Pengaturan kolom tabel: teks panjang lebar, angka hari tanpa desimal."""
    cfg = {}
    if "Permintaan Data" in t.columns:
        cfg["Permintaan Data"] = st.column_config.TextColumn(width="large")
    for c in ("Lama total (hari)", "Hari berjalan", "Lama / berjalan (hari)"):
        if c in t.columns:
            cfg[c] = st.column_config.NumberColumn(c, format="%d")
    return cfg


def rekap(df, kolom, urut=None):
    pv = df.groupby([kolom, "Status"]).size().unstack(fill_value=0).reindex(columns=STATUS_URUT, fill_value=0)
    pv["Total"] = pv.sum(axis=1)
    pv["% Done"] = (pv["Done"] / pv["Total"] * 100).round(0)
    pv = pv.sort_values("Total", ascending=False)
    if urut:
        pv = pv.reindex([u for u in urut if u in pv.index])
    return pv.reset_index()


def ke_excel(df):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="Data")
    return buf.getvalue()


# ====== FILTER ======
def filt(df, status=None, divisi=None, issue=None):
    if status:
        df = df[df["Status"].isin(status)]
    if divisi:
        df = df[df["Divisi"].map(lambda l: any(x in divisi for x in l))]
    if issue:
        df = df[df["Issue"].isin(issue)]
    return df


def baca_klik(key, nama, kolom):
    st_ = st.session_state.get(key)
    if not st_:
        return []
    sel = (st_.get("selection") or {}).get(nama) or []
    return [s[kolom] for s in sel if isinstance(s, dict) and kolom in s]


def reset_klik():
    st.session_state["ver"] = st.session_state.get("ver", 0) + 1


# ====== DOWNLOAD GRAFIK (PNG) ======
@st.cache_data(show_spinner=False)
def _png(spec_json: str, skala: int = 3) -> bytes:
    import vl_convert as vlc
    return vlc.vegalite_to_png(spec_json, scale=skala)


def tombol_png(chart, nama_file, key, judul=None, lebar=760):
    """Tombol download grafik sebagai PNG resolusi tinggi. Nggak muncul kalau vl-convert-python belum terpasang."""
    try:
        import vl_convert  # noqa: F401
    except ImportError:
        return
    props = {"width": lebar, "background": "white"}
    if judul:
        props["title"] = alt.TitleParams(judul, anchor="start", fontSize=16, color=HITAM)
    try:
        data = _png(chart.properties(**props).to_json())
    except Exception:
        return
    st.download_button("Download PNG", data, file_name=f"{nama_file}.png", mime="image/png", key=key)


# ====== GRAFIK SLA ======
def chart_sla_status(data):
    agg = data.groupby("Status SLA").size().reindex(KATEGORI, fill_value=0).reset_index(name="Jumlah")
    skala = alt.Scale(domain=KATEGORI, range=[WARNA_SLA[k] for k in KATEGORI])
    y = alt.Y("Status SLA:N", sort=KATEGORI, title=None)
    bars = alt.Chart(agg).mark_bar().encode(
        y=y, x=alt.X("Jumlah:Q", title="Jumlah baris permintaan"),
        color=alt.Color("Status SLA:N", scale=skala, legend=None), tooltip=["Status SLA", "Jumlah"],
    )
    angka = alt.Chart(agg).mark_text(align="left", dx=5, fontWeight="bold").encode(y=y, x="Jumlah:Q", text="Jumlah:Q")
    return alt.layer(bars, angka).properties(height=240)


TAHAP = {"Lama ke auditi": "Diteruskan ke divisi", "Lama auditi": "Dikerjakan divisi", "Lama finalisasi": "Finalisasi & serah ke BPK"}


def chart_tahap(data):
    agg = pd.DataFrame({
        "Tahap": list(TAHAP.values()),
        "Rata-rata": [round(float(data[c].mean()), 1) if data[c].notna().any() else 0.0 for c in TAHAP],
    })
    x = alt.X("Tahap:N", sort=list(TAHAP.values()), title=None, axis=alt.Axis(labelAngle=0, labelLimit=170))
    y = alt.Y("Rata-rata:Q", title="Rata-rata lama (hari)", scale=alt.Scale(domainMax=max(1.0, float(agg["Rata-rata"].max()) * 1.25)))
    bars = alt.Chart(agg).mark_bar(color=MERAH).encode(x=x, y=y, tooltip=["Tahap", "Rata-rata"])
    angka = alt.Chart(agg).mark_text(dy=-8, fontWeight="bold", size=13).encode(x=x, y=alt.Y("Rata-rata:Q"), text="Rata-rata:Q")
    return alt.layer(bars, angka).properties(height=240)


# ====== HALAMAN DASHBOARD (data sudah berkolom standar) ======
def dashboard(items: pd.DataFrame, kunci: str, urut_issue: list, sla=None, catatan: str = "", hari_ini=None,
              label_jenis: str = "Jenis Data"):
    p = kunci   # awalan key widget, supaya tiap halaman punya state sendiri
    satuan = ""

    if sla:
        with st.sidebar:
            st.header("SLA")
            target = int(st.number_input("Target SLA (hari)", min_value=1, max_value=365, value=int(sla.get("target", 5)),
                                         step=1, key=f"{p}_sla_target"))
            kerja = st.radio("Satuan hari", ["Hari kerja", "Hari kalender"], index=0 if sla.get("kerja", True) else 1,
                             key=f"{p}_sla_satuan") == "Hari kerja"
        satuan = "hari kerja" if kerja else "hari kalender"
        hari_ini = hari_ini or datetime.now(timezone(timedelta(hours=7))).date()
        items = hitung_sla(items, target, kerja, sla.get("libur"), hari_ini)

    with st.sidebar:
        st.header("Filter")
        f_jenis = st.multiselect(label_jenis, list(items["Jenis Data"].unique()), key=f"{p}_f_jenis")
        f_div = st.multiselect("Divisi", sorted({d for l in items["Divisi"] for d in l}), key=f"{p}_f_div")
        f_issue = st.multiselect("Issue", urut_issue, key=f"{p}_f_issue")
        f_status = st.multiselect("Status", STATUS_URUT, key=f"{p}_f_status")
        f_sla = st.multiselect("Status SLA", KATEGORI, key=f"{p}_f_sla") if sla else []
        st.button("Reset klik grafik", on_click=reset_klik, key=f"{p}_reset_side")

    dasar = items if not f_jenis else items[items["Jenis Data"].isin(f_jenis)]
    dasar = filt(dasar, f_status, f_div, f_issue)
    if f_sla:
        dasar = dasar[dasar["Status SLA"].isin(f_sla)]

    # filter dari klik grafik (tiap grafik nyaring grafik lain, bukan dirinya sendiri)
    ver = st.session_state.get("ver", 0)
    K_STATUS, K_DIV, K_ISSUE = f"{p}_c_status_{ver}", f"{p}_c_div_{ver}", f"{p}_c_issue_{ver}"
    k_status = baca_klik(K_STATUS, "pilih_status", "Status")
    k_div = baca_klik(K_DIV, "pilih_divisi", "Divisi")
    k_issue = baca_klik(K_ISSUE, "pilih_issue", "Issue")
    view = filt(dasar, k_status, k_div, k_issue)

    # kartu ringkasan
    total = len(view)
    n = view["Status"].value_counts()
    done, pending, na = (int(n.get(s, 0)) for s in STATUS_URUT)

    def pct(x):
        return f"{x / total:.0%}" if total else "-"

    st.markdown(
        '<div class="kartu-wrap">'
        + kartu("Total permintaan", total, "baris permintaan data", HITAM)
        + kartu("Done", done, f"{pct(done)} dari total", WARNA_STATUS["Done"])
        + kartu("Pending", pending, f"{pct(pending)} dari total", WARNA_STATUS["Pending"])
        + kartu("N/A", na, f"{pct(na)} dari total", WARNA_STATUS["N/A"])
        + "</div>",
        unsafe_allow_html=True,
    )
    if catatan:
        st.caption(catatan)

    if k_status or k_div or k_issue:
        aktif = " · ".join(
            f"{nama}: {', '.join(map(str, v))}"
            for nama, v in (("Status", k_status), ("Divisi", k_div), ("Issue", k_issue)) if v
        )
        st.info(f"Filter dari klik grafik aktif: {aktif}")
        st.button("Reset klik", on_click=reset_klik, key=f"{p}_reset_atas")

    if view.empty:
        st.warning("Tidak ada data untuk filter ini.")
        return

    nama_tab = ["Ringkasan", "Per Divisi", "Per Issue"] + (["SLA"] if sla else []) + ["Pending", "Detail"]
    tabs = dict(zip(nama_tab, st.tabs(nama_tab)))

    # ---- Ringkasan ----
    with tabs["Ringkasan"]:
        st.caption("Klik bagian grafik untuk menyaring seluruh dashboard. Klik di area kosong atau tombol Reset untuk membatalkan.")
        g1, g2 = st.columns([1, 1.4])
        with g1:
            st.markdown("#### Pemenuhan Data")
            c_status = chart_donut(filt(dasar, None, k_div, k_issue))
            tampil_chart(c_status, key=K_STATUS, klik=True)
            tombol_png(c_status, f"{p}_pemenuhan_data", f"{p}_png_status", "Pemenuhan Data", lebar=480)
        with g2:
            st.markdown("#### Berdasarkan Issue")
            c_issue = chart_stacked(filt(dasar, k_status, k_div, None), "Issue", urut_issue, "pilih_issue", 330)
            tampil_chart(c_issue, key=K_ISSUE, klik=True)
            tombol_png(c_issue, f"{p}_per_issue", f"{p}_png_issue", "Distribusi berdasarkan Issue")

        st.markdown(f"#### Progres per {label_jenis}")
        st.markdown(bar_per_jenis(view), unsafe_allow_html=True)

        st.markdown("#### Distribusi per Divisi")
        d_div = filt(dasar, k_status, None, k_issue).explode("Divisi")
        urut_div = d_div.groupby("Divisi").size().sort_values(ascending=False).index.tolist()
        c_div = chart_stacked(d_div, "Divisi", urut_div, "pilih_divisi", max(300, 30 * len(urut_div)))
        tampil_chart(c_div, key=K_DIV, klik=True)
        tombol_png(c_div, f"{p}_per_divisi", f"{p}_png_div", "Distribusi data per divisi", lebar=820)
        st.caption("Baris dengan lebih dari satu PIC dihitung di tiap divisinya.")

    # ---- Per Divisi ----
    with tabs["Per Divisi"]:
        rk = rekap(view.explode("Divisi"), "Divisi")
        tampil_df(rk, column_config={"% Done": st.column_config.ProgressColumn("% Done", min_value=0, max_value=100, format="%d%%")})
        pilih_div = st.selectbox("Lihat permintaan milik divisi", rk["Divisi"].tolist(), key=f"{p}_pilih_div")
        sub = siapkan_tabel(filt(view, divisi=[pilih_div]))
        st.caption(f"{len(sub)} baris permintaan · Pending ditaruh paling atas")
        tampil_df(berwarna(sub), column_config=cfg_tabel(sub))

    # ---- Per Issue ----
    with tabs["Per Issue"]:
        rk = rekap(view, "Issue", urut_issue)
        tampil_df(rk, column_config={"% Done": st.column_config.ProgressColumn("% Done", min_value=0, max_value=100, format="%d%%")})
        pilih_issue = st.selectbox("Lihat permintaan untuk issue", rk["Issue"].tolist(), key=f"{p}_pilih_issue")
        sub = siapkan_tabel(filt(view, issue=[pilih_issue]))
        st.caption(f"{len(sub)} baris permintaan · Pending ditaruh paling atas")
        tampil_df(berwarna(sub), column_config=cfg_tabel(sub))

    # ---- SLA ----
    if sla:
        with tabs["SLA"]:
            st.caption(
                f"Target SLA: {target} {satuan}. Permintaan yang sudah Done dihitung dari Tanggal Permintaan BPK sampai "
                f"Tanggal penyerahan ke BPK. Yang masih Pending dihitung dari tanggal permintaan sampai hari ini. "
                f"Baris N/A, atau yang tanggalnya tidak terbaca, tidak dihitung."
            )
            selesai = view[view["Status SLA"].isin(["Sesuai SLA", "Terlambat"])]
            n_ok = int((view["Status SLA"] == "Sesuai SLA").sum())
            n_telat = int((view["Status SLA"] == "Terlambat").sum())
            n_lewat = int((view["Status SLA"] == "Pending (lewat SLA)").sum())
            rata = selesai["Lama total"].mean()
            med = selesai["Lama total"].median()
            persen_ok = f"{n_ok / len(selesai):.0%} dari yang selesai" if len(selesai) else "-"
            st.markdown(
                '<div class="kartu-wrap">'
                + kartu("Sesuai SLA", n_ok, persen_ok, WARNA_SLA["Sesuai SLA"])
                + kartu("Terlambat", n_telat, "selesai tapi melewati target", WARNA_SLA["Terlambat"])
                + kartu("Pending lewat SLA", n_lewat, "belum selesai dan sudah lewat target", WARNA_SLA["Pending (lewat SLA)"])
                + kartu("Rata-rata lama", "-" if pd.isna(rata) else f"{rata:.1f}",
                        "-" if pd.isna(med) else f"median {med:.0f} {satuan}", HITAM)
                + "</div>",
                unsafe_allow_html=True,
            )
            s1, s2 = st.columns(2)
            with s1:
                st.markdown("#### Status SLA")
                c1 = chart_sla_status(view)
                tampil_chart(c1)
                tombol_png(c1, f"{p}_status_sla", f"{p}_png_sla1", f"Status SLA (target {target} {satuan})", lebar=620)
            with s2:
                st.markdown(f"#### Rata-Rata Lama per Tahap ({satuan})")
                c2 = chart_tahap(view)
                tampil_chart(c2)
                tombol_png(c2, f"{p}_lama_per_tahap", f"{p}_png_sla2", f"Rata-rata lama per tahap ({satuan})", lebar=620)
            st.caption("Tahap 1: dari permintaan BPK sampai diteruskan ke divisi. Tahap 2: dikerjakan divisi. "
                       "Tahap 3: dari divisi sampai diserahkan ke BPK. Dipakai buat melihat di tahap mana waktu paling banyak habis.")

            st.markdown("#### SLA per Divisi")
            baris = []
            for dv, g in view.explode("Divisi").groupby("Divisi"):
                sel = g["Status SLA"].isin(["Sesuai SLA", "Terlambat"])
                ok = int((g["Status SLA"] == "Sesuai SLA").sum())
                baris.append({
                    "Divisi": dv,
                    "Selesai": int(sel.sum()),
                    "Sesuai SLA": ok,
                    "Terlambat": int((g["Status SLA"] == "Terlambat").sum()),
                    "% Sesuai SLA": round(ok / sel.sum() * 100) if sel.sum() else None,
                    "Rata-rata lama (hari)": round(float(g.loc[sel, "Lama total"].mean()), 1) if sel.any() else None,
                    "Pending lewat SLA": int((g["Status SLA"] == "Pending (lewat SLA)").sum()),
                })
            per_div = pd.DataFrame(baris).sort_values("Selesai", ascending=False)
            tampil_df(per_div, column_config={"% Sesuai SLA": st.column_config.ProgressColumn("% Sesuai SLA", min_value=0, max_value=100, format="%d%%")})

            st.markdown("#### Perlu Perhatian")
            perlu = view[view["Status SLA"].isin(["Terlambat", "Pending (lewat SLA)"])].copy()
            if perlu.empty:
                st.success("Tidak ada permintaan yang terlambat atau lewat SLA.")
            else:
                perlu["Lama / berjalan (hari)"] = perlu["Lama total"].fillna(perlu["Hari berjalan"])
                perlu = perlu.sort_values("Lama / berjalan (hari)", ascending=False)
                st.caption(f"{len(perlu)} baris, diurutkan dari yang paling lama")
                t = siapkan_tabel(perlu, pending_dulu=False,
                                  kolom=["Jenis Data", "No", "Permintaan Data", "Divisi", "Status SLA", "Lama / berjalan (hari)"])
                tampil_df(berwarna(t), column_config=cfg_tabel(t))

    # ---- Pending ----
    with tabs["Pending"]:
        pend = view[view["Status"] == "Pending"]
        if pend.empty:
            st.success("Tidak ada permintaan yang masih Pending.")
        else:
            st.markdown(f"**{len(pend)} permintaan belum diserahkan ke BPK**")
            per_d = pend.explode("Divisi")["Divisi"].value_counts()
            st.markdown(
                "".join(f'<span class="chip">{_html.escape(str(d))}: <b>{c}</b></span>' for d, c in per_d.items()),
                unsafe_allow_html=True,
            )
            kolom_pend = ["Jenis Data", "No", "Permintaan Data", "Judul Induk", "Divisi", "PIC (Nama)", "Issue", "Hari berjalan", "Status SLA"]
            t = siapkan_tabel(pend, pending_dulu=False, kolom=kolom_pend)
            tampil_df(berwarna(t), column_config=cfg_tabel(t))

    # ---- Detail ----
    with tabs["Detail"]:
        cari = st.text_input("Cari di teks permintaan", placeholder="mis. TJSL, kontrak, laporan keuangan", key=f"{p}_cari")
        pending_dulu = st.checkbox("Pending paling atas", value=True, key=f"{p}_pending_dulu")
        sub = view
        if cari.strip():
            sub = view[view["Permintaan Data"].astype(str).str.contains(cari.strip(), case=False, regex=False)]
        tabel = siapkan_tabel(sub, pending_dulu=pending_dulu)
        st.caption(f"{len(tabel)} baris")
        tampil_df(berwarna(tabel), column_config=cfg_tabel(tabel))
        d1, d2, _ = st.columns([1, 1, 4])
        d1.download_button("Download CSV", tabel.to_csv(index=False).encode("utf-8-sig"),
                           file_name=f"{p}.csv", mime="text/csv", key=f"{p}_dl_csv")
        d2.download_button("Download Excel", ke_excel(tabel), file_name=f"{p}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key=f"{p}_dl_xlsx")


# ====== HALAMAN PRATINJAU (parser belum dibuat) ======
def _unik(nama):
    hasil, dipakai = [], {}
    for i, n in enumerate(nama):
        n = str(n).strip()
        if n in ("", "nan", "None"):
            n = f"kolom_{i + 1}"
        dipakai[n] = dipakai.get(n, 0) + 1
        hasil.append(n if dipakai[n] == 1 else f"{n}_{dipakai[n]}")
    return hasil


def mentah(raw: pd.DataFrame, kunci: str, nama_sheet: str):
    st.info("Aturan baca untuk data ini belum dibuat, jadi yang tampil isi sheet apa adanya. "
            "Setelah aturannya ditentukan, tulis `parse()` di folder `parsers/` lalu ubah `SIAP = True`.")
    st.caption(f"Sheet: {nama_sheet} · {raw.shape[0]} baris × {raw.shape[1]} kolom")

    terisi = raw.apply(lambda c: c.map(lambda v: not pd.isna(v) and str(v).strip() != "")).sum(axis=1)
    tebak = int(terisi[terisi >= 3].index[0]) + 1 if (terisi >= 3).any() else 1
    h = st.number_input("Baris header (nomor baris di Excel)", min_value=1, max_value=max(1, len(raw)), value=tebak, step=1,
                        key=f"{kunci}_baris_header")
    h = int(h)

    t = raw.iloc[h:].copy()
    t.columns = _unik(raw.iloc[h - 1])
    t = t.dropna(how="all").dropna(axis=1, how="all")
    fn = t.map if hasattr(t, "map") else t.applymap
    t = fn(_fmt).reset_index(drop=True)
    tampil_df(t)

    d1, d2, _ = st.columns([1, 1, 4])
    d1.download_button("Download CSV", t.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"{kunci}.csv", mime="text/csv", key=f"{kunci}_dl_csv")
    d2.download_button("Download Excel", ke_excel(t), file_name=f"{kunci}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key=f"{kunci}_dl_xlsx")
