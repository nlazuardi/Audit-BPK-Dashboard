"""Daftar halaman data. Satu file di folder ini = satu sheet = satu halaman di dashboard.

Menambah sheet baru:
1. bikin file baru di folder ini (salin dari auditkepatuhan.py atau wawancarakepatuhan.py)
2. tambahkan link-nya di secrets.toml bagian [link] (nama kunci = KUNCI di file itu)
3. daftarkan modulnya di bawah
"""
from . import auditkepatuhan, auditkeuangan, wawancarakepatuhan, wawancarakeuangan

HALAMAN = [auditkepatuhan, auditkeuangan, wawancarakepatuhan, wawancarakeuangan]
