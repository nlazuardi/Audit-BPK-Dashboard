"""Hitung SLA. Murni pandas/numpy (nggak mengimpor streamlit), jadi bisa dites di mana saja.

Kolom yang dibutuhkan: Status (Done/Pending/N/A), Tgl Permintaan, Tgl ke Auditi, Tgl dari Auditi, Tgl Selesai.
Tambahan yang dihasilkan: Lama total, Lama ke auditi, Lama auditi, Lama finalisasi, Hari berjalan, Status SLA.
"""
import numpy as np
import pandas as pd

KATEGORI = ["Sesuai SLA", "Terlambat", "Pending (dalam SLA)", "Pending (lewat SLA)", "Tidak dihitung"]


def _hari(mulai: pd.Series, akhir: pd.Series, kerja: bool, libur) -> pd.Series:
    """Selisih hari antar dua kolom tanggal. NaN kalau salah satunya kosong atau urutannya terbalik."""
    ok = mulai.notna() & akhir.notna()
    hasil = pd.Series(np.nan, index=mulai.index, dtype="float64")
    if ok.any():
        a = pd.to_datetime(mulai[ok]).values.astype("datetime64[D]")
        b = pd.to_datetime(akhir[ok]).values.astype("datetime64[D]")
        if kerja:
            hasil[ok] = np.busday_count(a, b, holidays=libur).astype(float)
        else:
            hasil[ok] = (b - a).astype(int).astype(float)
    hasil[hasil < 0] = np.nan
    return hasil


def hitung_sla(df: pd.DataFrame, target: int, hari_kerja: bool = True, libur=None, hari_ini=None) -> pd.DataFrame:
    d = df.copy()
    libur_np = np.array(libur or [], dtype="datetime64[D]")   # kosong = tanpa hari libur
    hari_ini = pd.Timestamp(hari_ini if hari_ini is not None else pd.Timestamp.today()).normalize()

    def hari(m, a):
        return _hari(m, a, hari_kerja, libur_np)

    sekarang = pd.Series(hari_ini, index=d.index)
    d["Lama total"] = hari(d["Tgl Permintaan"], d["Tgl Selesai"])
    d["Lama ke auditi"] = hari(d["Tgl Permintaan"], d["Tgl ke Auditi"])
    d["Lama auditi"] = hari(d["Tgl ke Auditi"], d["Tgl dari Auditi"])
    d["Lama finalisasi"] = hari(d["Tgl dari Auditi"], d["Tgl Selesai"])
    berjalan = hari(d["Tgl Permintaan"], sekarang)
    d["Hari berjalan"] = berjalan.where(d["Status"].eq("Pending"))

    status = pd.Series("Tidak dihitung", index=d.index, dtype=object)
    selesai = d["Status"].eq("Done") & d["Lama total"].notna()
    pending = d["Status"].eq("Pending") & berjalan.notna()
    status[selesai & (d["Lama total"] <= target)] = "Sesuai SLA"
    status[selesai & (d["Lama total"] > target)] = "Terlambat"
    status[pending & (berjalan <= target)] = "Pending (dalam SLA)"
    status[pending & (berjalan > target)] = "Pending (lewat SLA)"
    d["Status SLA"] = status
    return d
