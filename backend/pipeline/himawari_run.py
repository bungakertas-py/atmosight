# -*- coding: utf-8 -*-
"""Menjalankan sumber data SATELIT, folder dan katalognya sendiri.

   SENGAJA tidak menyisip ke katalog GFS. Satelit itu sumber tersendiri,
   domainnya sendiri, waktunya sendiri, dan parameternya sendiri. Kalau
   ditumpangkan ke GFS, garis waktu ramalan dan garis waktu pengamatan
   berebut satu penggeser, dan pembaca yang menggeser ke besok mendapat
   peta kosong. Di frontend dia muncul sebagai pilihan di panel Model dan
   Satelit, bukan sebagai parameter tambahan GFS.

   Bingkai yang sudah pernah dibuat TIDAK diulang. Alur kerjanya memulihkan
   keluaran lama dari cache, jadi biasanya tiap jalan cuma satu atau dua
   bingkai baru yang perlu diunduh."""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.pipeline import himawari as H
from backend.pipeline import himawari_angin as A

AKAR = Path(__file__).resolve().parents[1]
# Folder keluaran boleh ditimpa lewat argumen. Di repo ini data/output itu
# symlink WSL yang tidak bisa dibaca python Windows, jadi uji lokal perlu
# jalan lain. Lewat ARGUMEN, bukan lingkungan, sebab proses Windows yang
# dijalankan dari WSL tidak mewarisi variabel lingkungan begitu saja.
# Di GitAction dua duanya dibiarkan kosong dan jalurnya kembali ke bawaan.
KELUARAN = Path(sys.argv[1]) if len(sys.argv) > 1 else AKAR / "data" / "output" / "himawari"
SEMENTARA = Path(sys.argv[2]) if len(sys.argv) > 2 else AKAR / "data" / "tmp_himawari"


def nama_bingkai(w: dt.datetime) -> str:
    return "%s_%s_preview.webp" % (H.LAYER, w.strftime("%Y%m%d_%H%M"))


def nama_angin(w: dt.datetime) -> str:
    return "%s_%s_preview.webp" % (A.LAYER, w.strftime("%Y%m%d_%H%M"))


def versi_lama() -> int:
    """Cap versi gambar yang tersimpan di katalog, 0 kalau belum ada."""
    kat = KELUARAN / "catalog.json"
    if not kat.exists():
        return 0
    try:
        return int(json.loads(kat.read_text("utf-8")).get("versi_render", 0))
    except Exception:
        return 0


def main() -> int:
    KELUARAN.mkdir(parents=True, exist_ok=True)
    gambar_ulang = versi_lama() != H.VERSI_RENDER
    if gambar_ulang:
        print("cap versi gambar berubah, %d jadi %d, semua bingkai digambar ulang"
              % (versi_lama(), H.VERSI_RENDER))
    slot = H.slot_tersedia()
    if not slot:
        print("tidak ada slot yang terdaftar di ember, berhenti tanpa mengubah apa apa")
        return 0
    pakai = H.pilih_bingkai(slot)
    print("slot terbaru di ember:", slot[0].strftime("%Y-%m-%d %H:%M"), "UTC")
    print("bingkai yang dipakai :", ", ".join(w.strftime("%H:%M") for w in pakai))

    bingkai_jadi = []
    for w in sorted(pakai):
        berkas = KELUARAN / nama_bingkai(w)
        if berkas.exists() and berkas.stat().st_size > 1000 and not gambar_ulang:
            print("  %s sudah ada, dilewati" % w.strftime("%H:%M"))
            bingkai_jadi.append(w)
            continue
        print("  %s mengunduh %d segmen" % (w.strftime("%H:%M"), len(H.SEGMEN)))
        folder = SEMENTARA / w.strftime("%Y%m%d_%H%M")
        jalur = H.unduh(w, folder)
        hasil = H.bingkai(jalur)
        arr, redam = hasil if hasil else (None, None)
        shutil.rmtree(folder, ignore_errors=True)
        if arr is None:
            print("    gagal, dilewati")
            continue
        import numpy as np
        terisi = float(100.0 * np.isfinite(arr).mean())
        if terisi < 40:
            print("    cuma %.0f persen terisi, dibuang sebagai cacat" % terisi)
            continue
        H.simpan(arr, berkas, redam)
        print("    jadi, %.0f persen terisi, %.0f KB"
              % (terisi, berkas.stat().st_size / 1024))
        bingkai_jadi.append(w)

    # ---- ANGIN GERAK AWAN, berkas dan antrean sendiri ----
    # Sengaja dipisah dari gelung di atas. Kalau produk AMV satu jam bolong,
    # yang hilang cuma panahnya, suhu puncak awannya tetap terbit.
    angin_jadi = []
    for w in sorted(pakai):
        berkas = KELUARAN / nama_angin(w)
        if berkas.exists() and berkas.stat().st_size > 1000 and not gambar_ulang:
            angin_jadi.append(w)
            continue
        folder = SEMENTARA / ("amv_" + w.strftime("%Y%m%d_%H%M"))
        nc = A.unduh(w, folder)
        if nc is None:
            print("  angin %s tidak ada, dilewati" % w.strftime("%H:%M"))
            shutil.rmtree(folder, ignore_errors=True)
            continue
        try:
            lat, lon, spd, arah, pres, qi = A.baca(nc)
            lat, lon, spd, arah, pres = A.jarangkan(lat, lon, spd, arah, pres, qi)
            n = A.gambar(lat, lon, spd, arah, pres, berkas)
            print("  angin %s, %d panah, %.0f KB"
                  % (w.strftime("%H:%M"), n, berkas.stat().st_size / 1024))
            angin_jadi.append(w)
        except Exception as e:
            print("  angin %s gagal, %s" % (w.strftime("%H:%M"), e))
        shutil.rmtree(folder, ignore_errors=True)

    if not bingkai_jadi:
        print("tidak ada bingkai yang jadi, katalog tidak disentuh")
        return 0

    # bingkai lama dibuang, simpanan tidak boleh tumbuh tanpa batas
    sah = {nama_bingkai(w) for w in bingkai_jadi} | {nama_angin(w) for w in angin_jadi}
    for f in KELUARAN.glob("*_preview.webp"):
        if f.name not in sah:
            f.unlink()
            print("  buang bingkai lama", f.name)

    # Katalognya BERDIRI SENDIRI, bentuknya sama dengan katalog model supaya
    # frontend tidak perlu jalur khusus. `bounds` itu pusat sel pertama dan
    # terakhir, `image_bounds` tepi gambarnya, dan bedanya setengah sel.
    kat = KELUARAN / "catalog.json"
    data = {
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": "himawari9_ahi_b13",
        "model_label": "Satelit Himawari-9",
        "versi_render": H.VERSI_RENDER,
        # Satelit tidak punya jam inisiasi, jadi yang dipakai jam PENGAMATAN
        # terbaru. Frontend memakainya untuk lencana Last update, dan untuk
        # pengamatan itu justru angka yang paling benar di situ.
        "run_time": max(bingkai_jadi).strftime("%Y-%m-%dT%H:%M:00Z"),
        "observasi": True,
        "sumber": "Himawari-9 AHI kanal 13, NOAA Open Data di AWS",
        "region": {
            "bounds": [H.LON0, H.LAT0, H.LON1, H.LAT1],
            "image_bounds": H.image_bounds(),
        },
        "layers": {
            H.LAYER: {
                "kind": "scalar",
                "level": "surface",
                "units": "\u00b0C",
                "frames": [
                    {"valid_time": w.strftime("%Y-%m-%dT%H:%M:00Z"),
                     "preview_image": nama_bingkai(w)}
                    for w in sorted(bingkai_jadi)
                ],
            },
        },
    }
    if angin_jadi:
        data["layers"][A.LAYER] = {
            "kind": "scalar",
            "level": "surface",
            "units": "m/detik",
            "frames": [
                {"valid_time": w.strftime("%Y-%m-%dT%H:%M:00Z"),
                 "preview_image": nama_angin(w)}
                for w in sorted(angin_jadi)
            ],
        }
    kat.write_text(json.dumps(data, indent=1), "utf-8")
    print("katalog diperbarui, %d bingkai" % len(bingkai_jadi))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
