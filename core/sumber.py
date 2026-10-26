"""Narik file Excel dari link di secrets.toml (tabel [link]). Nama kunci = nama di tabel itu."""
import io
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests
import streamlit as st

TTL_DETIK = 30   # data dianggap segar selama ini; lewat itu, tarikan berikutnya ambil ulang dari SharePoint


def _url_unduh(url: str) -> str:
    url = url.strip()
    if "download=1" in url:
        return url
    return url + ("&" if "?" in url else "?") + "download=1"


def _unduh(kunci: str) -> bytes:
    # mode tes lokal: tambahkan [lokal] auditkepatuhan = "path/ke/file.xlsx" di secrets.toml
    lokal = st.secrets.get("lokal", {})
    if kunci in lokal:
        with open(lokal[kunci], "rb") as f:
            return f.read()

    try:
        url = st.secrets["link"][kunci]
    except Exception:
        raise RuntimeError(f"Link '{kunci}' belum diisi di secrets.toml bagian [link].") from None

    try:
        r = requests.get(_url_unduh(url), headers={"User-Agent": "Mozilla/5.0"}, timeout=30, allow_redirects=True)
        r.raise_for_status()
    except Exception:
        # sengaja tanpa detail error asli: pesan bawaan requests bisa memuat URL lengkap
        raise RuntimeError(f"Gagal narik data '{kunci}'. Cek link masih aktif (tipe Anyone) dan belum kedaluwarsa.") from None

    if r.content[:2] != b"PK":
        raise RuntimeError(f"Link '{kunci}' tidak mengembalikan file Excel. Kemungkinan bukan link tipe Anyone atau sudah kedaluwarsa.")
    return r.content


@st.cache_data(ttl=TTL_DETIK, show_spinner="Narik data...")
def ambil_raw(kunci: str, sheet=None):
    """Return (tabel mentah tanpa header, waktu tarik, nama sheet yang dipakai)."""
    data = _unduh(kunci)
    waktu = datetime.now(timezone(timedelta(hours=7))).strftime("%d %b %Y, %H:%M:%S WIB")
    xl = pd.ExcelFile(io.BytesIO(data))
    nama = sheet if sheet in xl.sheet_names else xl.sheet_names[0]
    # keep_default_na=False: biar teks "N/A" di Excel nggak dianggap kosong oleh pandas
    raw = xl.parse(nama, header=None, keep_default_na=False, na_values=[""])
    raw.attrs["sheets"] = {s: xl.parse(s, header=None, keep_default_na=False, na_values=[""]) for s in xl.sheet_names}
    raw.attrs["sheet_names"] = list(xl.sheet_names)
    raw.attrs["excel_bytes"] = data
    return raw, waktu, nama
