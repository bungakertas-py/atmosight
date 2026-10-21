"""Pintu masuk ECMWF 9 km untuk GitHub Actions, dengan GAGAL LEMBUT.

    python ecmwf_terbit.py

Kenapa ini ada dan tidak langsung `python ecmwf.py`.

Layanan 0p1 ECMWF baru dibuka 20 Oktober 2026 dan RILISNYA BELUM TERATUR.
Diukur 21 Oktober 2026 jam 06:16 UTC: tanggal 20 membawa tiga run (06z, 12z,
18z), tanggal 19 tidak ada sama sekali, dan tanggal 21 belum ada apa apa
padahal run 00z plus latensi dua jam seharusnya sudah mendarat empat jam
sebelumnya. Arsipnya sendiri cuma bertahan sekitar satu hari.

Alur kerja yang memanggil pipeline langsung akan merah tiap kali jadwalnya
jatuh di jam yang kebetulan tidak ada runnya, dan log merah yang artinya
"memang belum ada" itu melatih orang mengabaikan log. Jadi di sini tiga
keadaan dipisah dengan jelas:

  tidak ada run      -> keluar 0, berubah=false, tidak menerbitkan apa apa
  run sama           -> keluar 0, berubah=false, tidak menerbitkan apa apa
  run baru           -> masak, berubah=true

Keadaan ketiga saja yang membuat situs diterbitkan ulang. Polanya disalin
dari himawari.yml, yang juga membandingkan dulu sebelum menerbitkan.

Keluarannya ditulis ke $GITHUB_OUTPUT kalau ada, jadi di luar runner skrip
ini tetap jalan dan cuma mencetak ke layar.
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

import ecmwf

# Dua blob lama ini TIDAK IKUT TERBIT, dan itu bukan kelalaian.
#
# `profile.bin.gz` dan `point_data.bin.gz` adalah bentuk lama dari dua berkas
# per sel yang sudah ada di sebelahnya. Yang membacanya cuma dua, dan dua
# duanya di dalam pipeline ini sendiri: ausmi.py dan mjo.py membaca
# profile.bin.gz sesudah ditulis, di jalan yang sama. Jadi dia perlu ADA
# waktu memasak, tapi tidak perlu ikut ke situs.
#
# Frontend tidak memerlukannya. `ambilTitik` cuma mundur ke blob lama kalau
# metanya tidak punya `cells`, sedangkan ECMWF selalu punya.
#
# Terukur 21 Oktober 2026, dua berkas ini 38,5 MB dari 271 MB keluaran satu
# run. GitHub Pages punya batas lunak 1 GB untuk seluruh situs, dan di situs
# itu sudah ada GFS dan Himawari, jadi 38,5 MB yang tidak ada yang membaca
# itu sayang.
JANGAN_TERBIT = ("profile.bin.gz", "point_data.bin.gz")


def _tulis_keluaran(**kv) -> None:
    """Tulis ke $GITHUB_OUTPUT, dan selalu cetak ke layar."""
    baris = "".join("%s=%s\n" % (k, v) for k, v in kv.items())
    sys.stdout.write(baris)
    jalur = os.environ.get("GITHUB_OUTPUT")
    if jalur:
        with open(jalur, "a", encoding="utf-8") as f:
            f.write(baris)


def run_terbit() -> str | None:
    """run_time yang sudah ada di katalog terbitan, atau None."""
    k = ecmwf.OUTPUT / "catalog.json"
    try:
        return json.loads(k.read_text(encoding="utf-8")).get("run_time")
    except Exception:
        return None


def main() -> int:
    sudah = run_terbit()
    print("sudah terbit:", sudah or "belum ada")

    try:
        run = ecmwf.run_terbaru()
    except Exception as e:
        # BUKAN kegagalan. Di luar jam rilis memang tidak ada yang bisa
        # diambil, dan itu keadaan normal selama layanannya belum teratur.
        print("tidak ada run 0p1 yang bisa diambil sekarang (%s)" % str(e)[:120])
        _tulis_keluaran(berubah="false", alasan="tidak ada run")
        return 0

    jam = run.strftime("%Y-%m-%dT%H:00:00Z")
    print("run terbaru di server:", jam)
    if sudah == jam:
        print("run yang sama sudah terbit, tidak dimasak ulang")
        _tulis_keluaran(berubah="false", alasan="run sama", run=jam)
        return 0

    try:
        ecmwf.jalan()
    except Exception:
        # Yang ini BETUL kegagalan, dan harus merah. Runnya ada, tapi
        # memasaknya gugur di tengah, dan itu perlu dilihat orang.
        traceback.print_exc()
        _tulis_keluaran(berubah="false", alasan="gagal masak", run=jam)
        return 1

    buang = 0
    for nama in JANGAN_TERBIT:
        f = ecmwf.OUTPUT / nama
        if f.is_file():
            buang += f.stat().st_size
            f.unlink()
    if buang:
        print("blob lama dibuang sebelum terbit: %.1f MB" % (buang / 1e6))

    besar = sum(f.stat().st_size for f in ecmwf.OUTPUT.rglob("*") if f.is_file())
    print("folder terbit: %.1f MB" % (besar / 1e6))
    _tulis_keluaran(berubah="true", run=jam, mb="%.1f" % (besar / 1e6))
    return 0


if __name__ == "__main__":
    sys.exit(main())
