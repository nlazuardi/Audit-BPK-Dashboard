"""Pintu masuk dashboard. Isinya cuma merangkai: password, pilih halaman, tarik data, gambar.

Jalankan:  streamlit run app.py
"""
import streamlit as st

st.set_page_config(page_title="Monitoring Audit BPK", page_icon="📊", layout="wide")

from core.auth import cek_password          # noqa: E402
from core.sumber import ambil_raw           # noqa: E402
from parsers import HALAMAN                 # noqa: E402
from tampilan import ui                     # noqa: E402

ui.pasang_css(presentasi=bool(st.session_state.get("present")))

if not cek_password():
    st.stop()

# muat ulang otomatis (detik). Atur lewat AUTO_REFRESH_DETIK di secrets.toml, isi 0 untuk mematikan.
detik = int(st.secrets.get("AUTO_REFRESH_DETIK", 60))
if detik > 0:
    try:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=detik * 1000, key="auto_refresh")
    except ImportError:
        pass

with st.sidebar:
    nama = st.radio("Data", [h.NAMA for h in HALAMAN])
    if st.button("Refresh data", type="primary"):
        st.cache_data.clear()
        st.rerun()

halaman = next(h for h in HALAMAN if h.NAMA == nama)

try:
    raw, waktu, nama_sheet = ambil_raw(halaman.KUNCI, halaman.SHEET)
except RuntimeError as e:
    st.error(str(e))
    st.stop()

ui.header("Monitoring Audit BPK", halaman.NAMA, waktu)

if hasattr(halaman, "render"):
    halaman.render(raw)
elif halaman.SIAP:
    try:
        items = halaman.parse(raw)
    except Exception as e:
        st.error(f"Format sheet '{halaman.NAMA}' tidak sesuai dengan aturan bacanya: {e}")
        st.stop()
    sla = None
    if getattr(halaman, "SLA", False):
        sla = {"target": halaman.SLA_TARGET_HARI, "kerja": halaman.SLA_HARI_KERJA, "libur": halaman.LIBUR}
        ui.dashboard(items, halaman.KUNCI, halaman.URUT_ISSUE, sla=sla, catatan=getattr(halaman, "CATATAN", ""),
                 label_jenis=getattr(halaman, "LABEL_JENIS", "Jenis Data"))
else:
    ui.mentah(raw, halaman.KUNCI, nama_sheet)
