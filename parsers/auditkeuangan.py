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
- file ini TIDAK boleh mengimpor streamlit, supaya bisa dites dari notebook
"""
import re
from datetime import date, datetime
import pandas as pd

NAMA = "Audit Keuangan"
KUNCI = "auditkeuangan"   # nama di [link] secrets.toml
SHEET = None              # None = membaca semua sheet entitas
SIAP = True               # True = punya parse() lengkap, tampil sebagai dashboard

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
    sheets = getattr(raw, "attrs", {}).get("sheets")
    if not sheets:
        sheets = {SHEET or "IFG_Holding": raw}

    all_items = []
    for sheet_name, df_sheet in sheets.items():
        if df_sheet is not None and not df_sheet.empty:
            all_items.extend(_parse_single_sheet(df_sheet, sheet_name))

    if not all_items:
        raise ValueError("Tidak ada data permintaan valid yang ditemukan di sheet.")

    out = pd.DataFrame(all_items)
    return out.reset_index(drop=True)
