"""Pembaca GeoTIFF seadanya untuk keluaran GrADS 2.0.2 di server WRF Citarum.

SENGAJA tanpa GDAL dan tanpa rasterio. Berkasnya sangat seragam, jadi tak perlu
pustaka besar yang harus ikut ke requirements CI.

Bentuk berkasnya selalu sama, sudah diperiksa lintas parameter dan lintas bulan.
Little endian, 153x54, 1 sampel per piksel, float32 IEEE, TANPA kompresi,
strip satu baris. Kalau suatu saat berubah, fungsi ini melempar ValueError
dengan alasan yang jelas, bukan diam diam mengembalikan sampah.
"""
from __future__ import annotations

import struct

import numpy as np

_UKURAN_TIPE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 11: 4, 12: 8}

TAG_LEBAR = 256
TAG_TINGGI = 257
TAG_BIT = 258
TAG_KOMPRESI = 259
TAG_SAMPEL = 277
TAG_OFFSET_STRIP = 273
TAG_PANJANG_STRIP = 279
TAG_FORMAT_SAMPEL = 339
TAG_TIEPOINT = 33922


def _baca_tag(b: bytes) -> tuple[str, dict]:
    if b[:2] == b"II":
        bo = "<"
    elif b[:2] == b"MM":
        bo = ">"
    else:
        raise ValueError("bukan TIFF, magic tak dikenal")
    if struct.unpack(bo + "H", b[2:4])[0] != 42:
        raise ValueError("bukan TIFF klasik")
    off = struct.unpack(bo + "I", b[4:8])[0]
    n = struct.unpack(bo + "H", b[off:off + 2])[0]
    tags: dict[int, tuple] = {}
    for i in range(n):
        e = off + 2 + i * 12
        tag, typ, cnt = struct.unpack(bo + "HHI", b[e:e + 8])
        mentah = b[e + 8:e + 12]
        sz = _UKURAN_TIPE.get(typ, 1) * cnt
        if sz > 4:
            p = struct.unpack(bo + "I", mentah)[0]
            data = b[p:p + sz]
        else:
            data = mentah[:sz]
        try:
            if typ == 3:
                v = struct.unpack(bo + f"{cnt}H", data)
            elif typ == 4:
                v = struct.unpack(bo + f"{cnt}I", data)
            elif typ == 11:
                v = struct.unpack(bo + f"{cnt}f", data)
            elif typ == 12:
                v = struct.unpack(bo + f"{cnt}d", data)
            else:
                v = (data,)
        except struct.error:
            v = (data,)
        tags[tag] = v
    return bo, tags


def baca(raw: bytes) -> tuple[np.ndarray, dict]:
    """Kembalikan (array float32 bentuk (ny, nx), info).

    Baris 0 = UTARA. Urutan ini sudah dibuktikan dengan mengadu |u,v| dari
    velocity JSON lawan raster Kecepatan_Angin, cocok 100 persen.
    """
    bo, t = _baca_tag(raw)

    def satu(tag, nama, wajib=None):
        v = t.get(tag)
        if v is None:
            raise ValueError(f"tag {nama} tak ada")
        if wajib is not None and v[0] != wajib:
            raise ValueError(f"{nama} = {v[0]}, diharapkan {wajib}")
        return v[0]

    nx = satu(TAG_LEBAR, "ImageWidth")
    ny = satu(TAG_TINGGI, "ImageLength")
    satu(TAG_BIT, "BitsPerSample", 32)
    satu(TAG_KOMPRESI, "Compression", 1)          # 1 = tanpa kompresi
    satu(TAG_SAMPEL, "SamplesPerPixel", 1)
    satu(TAG_FORMAT_SAMPEL, "SampleFormat", 3)    # 3 = float IEEE

    offsets = t.get(TAG_OFFSET_STRIP)
    panjang = t.get(TAG_PANJANG_STRIP)
    if not offsets or not panjang:
        raise ValueError("StripOffsets / StripByteCounts tak ada")

    potong = [raw[o:o + c] for o, c in zip(offsets, panjang)]
    nilai = np.frombuffer(b"".join(potong), dtype=bo + "f4")
    if nilai.size != nx * ny:
        raise ValueError(f"jumlah piksel {nilai.size}, diharapkan {nx * ny}")

    info: dict = {"nx": nx, "ny": ny}
    tp = t.get(TAG_TIEPOINT)
    if tp and len(tp) >= 6:
        # Tiepoint GrADS = TEPI sel kiri-atas, bukan pusat sel.
        info["west_edge"], info["north_edge"] = float(tp[3]), float(tp[4])
        if len(tp) >= 24:
            info["south_edge"], info["east_edge"] = float(tp[10]), float(tp[15])

    return nilai.reshape(ny, nx).astype("float32", copy=True), info
