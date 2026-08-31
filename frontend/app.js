/* Peta Cuaca — frontend (angin + hujan, GFS)
 * Membaca catalog.json + aset dari pipeline backend; angin = partikel + heatmap
 * kecepatan, hujan = heatmap laju hujan. Layout & gaya ala BMKG Signature.
 */
// ================= MODEL =================
// Dua sumber data. GFS = pipeline utama (realtime, seluruh Asia Tenggara).
// WRF Citarum = arsip ITB, domain kecil sekitar Jawa, resolusi 7 km.
// Pindah model = MUAT ULANG halaman, bukan tukar state di tempat. Disengaja:
// ada belasan cache lazy (point_data, city_data, siklon, ITCZ, isobar, monsun,
// profil) yang semuanya terkunci ke DATA_BASE. Menukarnya di tempat berarti
// membatalkan semuanya satu per satu, dan satu yang kelewat = data model lama
// nempel di model baru. Muat ulang selalu benar dan ongkosnya sepersekian detik.
const MODELS = {
  gfs: { base: "../backend/data/output/", label: "GFS (NOAA) - 28 km", ekstra: true },
  wrf: { base: "../backend/data/output/wrf/", label: "WRF Citarum - 7 km", ekstra: false },
  wrf_itera: { base: "../backend/data/output/wrf_itera/", label: "Private Model - 9 km", ekstra: false },
};

// ================= SAKLAR MODEL =================
// Primeon Atmos tahap awal SENGAJA cuma menampilkan GFS. Kode dan pipeline dua
// model lain TIDAK dihapus, cuma dimatikan, supaya bisa dinyalakan lagi tanpa
// menulis apa pun dari nol.
//
// CARA MENYALAKAN LAGI, ubah false jadi true di bawah ini. Tapi ingat, ada DUA
// tempat yang harus cocok:
//   1. di sini, supaya modelnya muncul di dropdown
//   2. di .github/workflows/deploy.yml pada MASAK_MODEL_EXTRA, supaya datanya
//      betul betul dimasak. Kalau cuma yang di sini dinyalakan, dropdown-nya
//      muncul tapi petanya kosong karena berkasnya memang tak pernah dibuat.
const MODEL_AKTIF = {
  gfs: true,
  wrf: false,          // WRF Citarum 7 km
  wrf_itera: false,    // Private Model 9 km
};
const modelHidup = (id) => !!MODELS[id] && MODEL_AKTIF[id] === true;

// Model PAJANGAN. Sengaja cuma dipamerkan di dropdown supaya rencananya
// kelihatan, tapi MATI dan tidak bisa dipilih. Tidak ada pipeline, tidak ada
// data, tidak ada base path. Kalau nanti salah satunya betul betul digarap,
// pindahkan dia ke MODELS di atas lalu nyalakan lewat MODEL_AKTIF.
const MODEL_PAJANGAN = [
  { label: "WRF - 3 km" },
  { label: "WRFDA - 3 km" },
];

const _mp = new URLSearchParams(location.search).get("model");
// Dijaga juga di sini, bukan cuma di dropdown. Kalau tidak, model yang sudah
// dimatikan masih bisa dibuka orang cuma dengan mengetik ?model=wrf di alamat.
const MODEL_ID = modelHidup(_mp) ? _mp : "gfs";
const MODEL = MODELS[MODEL_ID];
const DATA_BASE = MODEL.base;
// Layer tambahan (siklon, ITCZ, isobar, monsun, Skew-T, level stratosfer) cuma
// ada di pipeline GFS. Di WRF berkasnya memang tak dibuat, jadi tombolnya
// disembunyikan daripada dibiarkan mengejar 404.
const PUNYA_EKSTRA = MODEL.ekstra;

// Definisi legend per layer: [label, warna, teksPutih?]
const LEGENDS = {
  wind_surface: {
    head: "KNOTS",
    cells: [["5", "#2b83ba", 1], ["10", "#5aa8cf", 0], ["15", "#abdda4", 0], ["20", "#66bd63", 0],
            ["25", "#d9ef8b", 0], ["34", "#fee08b", 0], ["48", "#fdae61", 0], ["64", "#f46d43", 1],
            ["80", "#d73027", 1], ["100+", "#a50026", 1]],
  },
  rain_surface: {
    head: "mm",
    cells: [["2", "#14378f", 1], ["4", "#2360c8", 1], ["8", "#22a5e0", 0], ["10", "#23d3c0", 0],
            ["15", "#35c84a", 0], ["20", "#8ed82a", 0], ["25", "#ead821", 0], ["30", "#f5a91e", 0],
            ["35", "#f2701c", 1], ["40", "#e42320", 1], ["50", "#e33bbf", 1], ["60", "#8a29c8", 1]],
  },
  rain_accum_surface: {
    head: "mm/hari",
    cells: [["5", "#14378f", 1], ["10", "#2360c8", 1], ["20", "#22a5e0", 0], ["40", "#23d3c0", 0],
            ["60", "#35c84a", 0], ["90", "#8ed82a", 0], ["120", "#ead821", 0], ["150", "#f5a91e", 0],
            ["200", "#f2701c", 1], ["300", "#e42320", 1], ["400", "#e33bbf", 1], ["500", "#8a29c8", 1]],
  },
  temp_surface: {
    head: "°C",
    cells: [["0", "#2450b4", 1], ["8", "#4a97dc", 1], ["16", "#cfe4f2", 0], ["22", "#ffe08a", 0],
            ["28", "#fbaa4a", 0], ["32", "#ee7233", 0], ["36", "#d43325", 1], ["42", "#7d0d1a", 1]],
  },
  humidity_surface: {
    head: "%",
    cells: [["0", "#7a450a", 1], ["25", "#b9843a", 1], ["50", "#88b055", 0], ["70", "#359a86", 1],
            ["85", "#216bb0", 1], ["100", "#123f86", 1]],
  },
  // Inferno dibalik. Angkanya WAJIB sama dengan _CLOUD_SCALE di process.py.
  // Sel 0% sengaja "transparent": dirender jadi kotak-kotak catur, bukan warna,
  // supaya jelas artinya TIDAK ADA awan dan peta di bawahnya tembus.
  cloud_surface: {
    head: "%",
    cells: [["0", "transparent", 0], ["10", "#f9dc5c", 0], ["20", "#fcac1c", 0],
            ["30", "#f4802a", 0], ["40", "#e05a41", 1], ["50", "#c2415c", 1],
            ["60", "#9c3273", 1], ["70", "#75248a", 1], ["80", "#4f1e8c", 1],
            ["90", "#2e1c7d", 1], ["100", "#0f1a5e", 1]],
  },
  pressure_surface: {
    head: "hPa",
    cells: [["980", "#5e3c99", 1], ["995", "#356bc4", 1], ["1005", "#7dc8d8", 0], ["1013", "#f0f0e0", 0],
            ["1020", "#f4c060", 0], ["1030", "#e05a3a", 1]],
  },
  // CAPE & CIN pakai ANGKA MENTAH J/kg. Ambangnya persis _CAPE_SCALE / _CIN_SCALE
  // di process.py, jadi warna di legenda selalu sama dengan warna di peta.
  storm_potential: {
    head: "CAPE, J/kg",
    cells: [["500", "#2f9e7a", 0], ["1000", "#5ac86a", 0], ["1800", "#ead821", 0],
            ["2600", "#f5a91e", 0], ["3400", "#e42320", 1], ["4200", "#8a29c8", 1]],
  },
  // CIN nilainya NEGATIF. Makin minus makin tebal tutupnya, makin sulit badai
  // terbentuk walau CAPE besar. Urutan sel dibuat dari tipis ke tebal.
  cin_surface: {
    head: "CIN, J/kg",
    cells: [["-10", "#5ac86a", 0], ["-25", "#ead821", 0], ["-50", "#f5a91e", 0],
            ["-100", "#e42320", 1], ["-200", "#8a29c8", 1], ["-400", "#4a0d67", 1]],
  },
  // --- Level stratosfer 70 hPa ---
  wind_strato: {
    head: "KNOTS",
    cells: [["5", "#2b83ba", 1], ["10", "#5aa8cf", 0], ["15", "#abdda4", 0], ["20", "#66bd63", 0],
            ["25", "#d9ef8b", 0], ["34", "#fee08b", 0], ["48", "#fdae61", 0], ["64", "#f46d43", 1],
            ["80", "#d73027", 1], ["100+", "#a50026", 1]],
  },
  temp_strato: {
    head: "°C",
    cells: [["-70", "#2450b4", 1], ["-64", "#4a97dc", 1], ["-58", "#cfe4f2", 0],
            ["-52", "#ffe08a", 0], ["-46", "#fbaa4a", 0], ["-40", "#ee7233", 0]],
  },
};

// Tiga layer WRF memakai ambang yang BEDA dari GFS, jadi legendanya ditimpa.
// Kalau tidak, warna di legenda dan warna di peta akan berbeda arti.
// Angkanya WAJIB sama persis dengan SKALA_SUHU / SKALA_TEKANAN / SKALA_KNOT
// di backend/pipeline/wrf_run.py.
const LEGENDS_WRF = {
  // Jawa cuma 14-35 derajat. Skala GFS -10..42 bikin seluruh pulau oranye rata.
  temp_surface: {
    head: "°C",
    cells: [["14", "#2450b4", 1], ["18", "#4a97dc", 1], ["22", "#cfe4f2", 0],
            ["25", "#ffe08a", 0], ["28", "#fbaa4a", 0], ["31", "#ee7233", 0],
            ["34", "#d43325", 1]],
  },
  // TEKANAN PERMUKAAN MENTAH, bukan tekanan muka laut. Nilai rendah = tempat
  // tinggi, bukan tekanan rendah cuaca. Judulnya sengaja dibedakan.
  pressure_surface: {
    head: "hPa permukaan",
    cells: [["780", "#3b0f5c", 1], ["850", "#5e3c99", 1], ["910", "#356bc4", 1],
            ["955", "#7dc8d8", 0], ["985", "#f0f0e0", 0], ["1000", "#f4c060", 0],
            ["1012", "#e05a3a", 1]],
  },
  // Angin WRF mentok sekitar 23 knot, skala GFS sampai 120 knot jadi biru semua.
  wind_surface: {
    head: "KNOTS",
    cells: [["3", "#2b83ba", 1], ["6", "#5aa8cf", 0], ["10", "#abdda4", 0],
            ["14", "#66bd63", 0], ["18", "#d9ef8b", 0], ["22", "#fee08b", 0],
            ["28", "#fdae61", 0], ["34", "#f46d43", 1], ["42+", "#d73027", 1]],
  },
};
if (MODEL_ID === "wrf") Object.assign(LEGENDS, LEGENDS_WRF);

// Tema per-layer: "dark" = latar peta gelap (overlay putih); "light" = latar
// terang (overlay gelap). Menentukan label/batas/partikel.
const LAYER_THEME = {
  wind_surface: "dark", rain_surface: "dark", rain_accum_surface: "dark",
  temp_surface: "dark", humidity_surface: "dark", cloud_surface: "dark", pressure_surface: "dark",
  storm_potential: "dark", cin_surface: "dark", wind_strato: "dark", temp_strato: "dark",
};

// Override warna border batas administrasi per-layer (selain default tema).
const BORDER_COLOR = {
  temp_surface: "#000000",       // batas hitam di atas heatmap suhu
  humidity_surface: "#000000",   // batas hitam di atas heatmap kelembapan
  // Tutupan awan TIDAK didaftar lagi. Dulu hijau neon #39ff14, sekarang jatuh ke
  // bawaan yaitu PUTIH di tema gelap, sama seperti parameter lain.
  pressure_surface: "#6d7787",   // batas ABU (redup) di layer tekanan → isobar jadi garis utama
  temp_strato: "#000000",        // batas hitam di atas heatmap suhu stratosfer
};

// --- LEVEL KETINGGIAN (dropdown LEVEL) ---
// Tombol layer memakai kunci PERMUKAAN (data-layer). Saat level "strato" dipilih,
// tombol Angin & Suhu dipetakan ke varian 70 hPa; variabel lain diredupkan.
const STRATO_OF = { wind_surface: "wind_strato", temp_surface: "temp_strato" };
const BASE_OF = { wind_strato: "wind_surface", temp_strato: "temp_surface" };
// Kunci katalog sebenarnya untuk sebuah tombol pada level aktif.
function resolveLayer(base) {
  return (mapLevel === "strato" && STRATO_OF[base]) ? STRATO_OF[base] : base;
}
// Apakah data stratosfer ada di katalog (kalau belum diregen, dropdown tetap mati).
function stratoAvailable() {
  return !!(catalog && catalog.layers && (catalog.layers.wind_strato || catalog.layers.temp_strato));
}

// Redupkan tombol yang tak tersedia di level aktif (di strato: hanya Angin & Suhu).
function applyLevelUI() {
  const strato = mapLevel === "strato";
  document.querySelectorAll(".layer-btn[data-layer]").forEach((b) => {
    const base = b.dataset.layer;
    const has = catalog && catalog.layers[resolveLayer(base)];
    const enabled = strato ? (!!STRATO_OF[base] && !!has) : !!has;
    b.classList.toggle("disabled", !enabled);
  });
}

// Samakan tampilan kontrol level: dropdown desktop + tombol level HP.
function syncLevelControls() {
  const sel = $("level-select"); if (sel) sel.value = mapLevel;
  document.querySelectorAll(".level-btn[data-level]").forEach((b) =>
    b.classList.toggle("active", b.dataset.level === mapLevel));
}

// Ganti level (dari dropdown, tombol HP, atau restore hash). Pindah ke Angin bila
// layer aktif tak punya versi di level tujuan.
function setLevel(lv) {
  if (lv === mapLevel || !catalog) return;
  mapLevel = lv;
  applyLevelUI();
  let base = activeBase;
  if (mapLevel === "strato" && !STRATO_OF[base]) base = "wind_surface";
  activeBase = base;
  setActiveLayer(resolveLayer(base));
  syncLevelControls();
}

// Hidupkan pemilih LEVEL (dropdown desktop + tombol HP) bila data strato tersedia.
// ================= GERBANG SANDI MODEL WRF =================
// PERINGATAN JUJUR: ini berjalan di browser, jadi TIDAK mengamankan apa pun.
// Sandinya ada di berkas ini dan bisa dibaca siapa saja lewat view-source, dan
// berkas datanya di /backend/data/output/wrf/ tetap bisa diambil langsung tanpa
// melewati halaman ini. Fungsinya cuma penghalang sopan supaya model ini tidak
// terbuka begitu saja bagi yang sekadar lewat. Kalau datanya benar benar harus
// dibatasi, satu satunya cara adalah tidak menerbitkannya di Pages publik.
const WRF_SANDI = "bungakertas123!";
const WRF_KUNCI = "kertas-cuaca:wrf-tiket";

// Sandinya TIDAK diingat. Tiap muat ulang, dan tiap balik lagi dari GFS ke WRF,
// harus diketik lagi. Permintaan user.
//
// Masalahnya, membuka WRF itu MEMUAT ULANG halaman (?model=wrf), jadi kalau
// sama sekali tak ada yang disimpan, sandi yang barusan benar akan langsung
// ditanya lagi begitu halaman baru terbuka. Jadi dipakai TIKET SEKALI PAKAI:
// ditulis tepat sebelum pindah, lalu DIHAPUS saat dibaca. Sekali dipakai habis.
// Akibatnya F5 menanyakan lagi, dan pulang pergi GFS-WRF juga menanyakan lagi,
// persis yang diminta.
function ambilTiket() {
  try {
    const ada = sessionStorage.getItem(WRF_KUNCI) === "1";
    sessionStorage.removeItem(WRF_KUNCI);   // sekali pakai, langsung hangus
    return ada;
  } catch { return false; }
}
function tulisTiket() {
  try { sessionStorage.setItem(WRF_KUNCI, "1"); } catch { /* mode privat, abaikan */ }
}

// Tampilkan modal, kembalikan janji true kalau sandinya benar.
function mintaSandi(label) {
  return new Promise((selesai) => {
    const ov = $("pw-overlay"), inp = $("pw-input"), err = $("pw-err");
    if (!ov || !inp) { selesai(false); return; }
    const judul = $("pw-title");
    if (judul && label) judul.textContent = "Buka " + label;
    ov.classList.add("show");
    inp.value = "";
    err.hidden = true;
    setTimeout(() => inp.focus(), 50);

    const tutup = (hasil) => {
      ov.classList.remove("show");
      $("pw-ok").removeEventListener("click", onOk);
      $("pw-cancel").removeEventListener("click", onBatal);
      inp.removeEventListener("keydown", onTombol);
      ov.removeEventListener("click", onLatar);
      selesai(hasil);
    };
    const onOk = () => {
      if (inp.value === WRF_SANDI) { tutup(true); }
      else { err.hidden = false; inp.select(); }
    };
    const onBatal = () => tutup(false);
    const onTombol = (e) => {
      if (e.key === "Enter") onOk();
      else if (e.key === "Escape") onBatal();
      else err.hidden = true;
    };
    const onLatar = (e) => { if (e.target === ov) onBatal(); };

    $("pw-ok").addEventListener("click", onOk);
    $("pw-cancel").addEventListener("click", onBatal);
    inp.addEventListener("keydown", onTombol);
    ov.addEventListener("click", onLatar);
  });
}

// Dropdown MODEL. Dulu dekoratif satu opsi, sekarang benar benar memindah sumber
// data. Pindah model = muat ulang halaman dengan ?model=..., alasannya ada di
// komentar MODELS di atas.
function setupModelSelect() {
  const sel = $("model-select");
  if (!sel) return;
  sel.innerHTML = "";
  const hidup = Object.entries(MODELS).filter(([id]) => modelHidup(id));
  for (const [id, m] of hidup) {
    const o = document.createElement("option");
    o.value = id;
    o.textContent = m.label;
    sel.appendChild(o);
  }
  // Model pajangan ditempel di ekor, mati dan tak bisa dipilih.
  for (const m of MODEL_PAJANGAN) {
    const o = document.createElement("option");
    o.textContent = m.label;
    o.disabled = true;
    sel.appendChild(o);
  }
  sel.value = MODEL_ID;
  // Dropdown disembunyikan HANYA kalau isinya betul betul cuma satu baris.
  // Yang dihitung isi seluruh dropdown, bukan cuma yang hidup, sebab model
  // pajangan pun tetap perlu kelihatan. Yang disembunyikan HARUS seluruh
  // .field, bukan cuma .select-wrap, sebab label "MODEL" ada di luar
  // select-wrap dan kalau salah sasaran dia nongol sendirian tanpa kotak
  // pilihan di bawahnya.
  if (hidup.length + MODEL_PAJANGAN.length < 2) {
    (sel.closest(".field") || sel.closest(".select-wrap") || sel).style.display = "none";
    return;
  }
  // Pindah model cuma boleh ke yang hidup. Option pajangan sudah disabled,
  // tapi penjagaan di bawah tetap diperlukan buat jalur lain.
  sel.addEventListener("change", async () => {
    const id = sel.value;
    if (id === MODEL_ID) return;
    if (id !== "gfs") {
      const boleh = await mintaSandi(MODELS[id].label);
      if (!boleh) { sel.value = MODEL_ID; return; }   // batal, kembalikan pilihan
      tulisTiket();                                   // tiket sekali pakai
    }
    // Hash (layer, waktu, titik) sengaja DIBUANG. Layer & waktu model lama
    // belum tentu ada di model baru, dan restore yang gagal separuh lebih
    // membingungkan daripada mulai bersih.
    location.href = location.pathname + (id === "gfs" ? "" : "?model=" + id);
  });
}

// Sembunyikan yang memang tak ada datanya di model ini, daripada membiarkan
// tombolnya mengejar berkas yang tak pernah dibuat lalu diam diam gagal.
function terapkanFiturModel() {
  if (PUNYA_EKSTRA) return;
  // Private Model punya monsun (dihitung dari anginnya sendiri), jadi toggle
  // Monsun tetap ada. Siklon & ITCZ belum dibuat untuk model ini, disembunyikan.
  const sembunyi = (MODEL_ID === "wrf_itera")
    ? ["cyclone-toggle", "itcz-toggle"]
    : ["cyclone-toggle", "itcz-toggle", "mon-toggle"];
  sembunyi.forEach((id) => {
    const el = $(id);
    if (el) el.style.display = "none";
  });
  document.querySelector(".level-bar")?.style.setProperty("display", "none", "important");
  const lv = $("level-select");
  if (lv) lv.closest(".field")?.style.setProperty("display", "none");
  document.body.classList.add("model-wrf");
  if (MODEL_ID === "wrf_itera") document.body.classList.add("model-private");
}

function setupLevelSelect() {
  const sel = $("level-select");
  const bar = document.querySelector(".level-bar");
  if (!stratoAvailable()) {   // data strato belum ada -> matikan pemilih level
    if (sel) { sel.disabled = true; sel.innerHTML = '<option value="surface">Permukaan</option>'; }
    if (bar) bar.style.display = "none";
    return;
  }
  if (sel) {
    sel.disabled = false;
    sel.innerHTML = '<option value="surface">Permukaan</option>'
                  + '<option value="strato">Stratosfer, 70 hPa</option>';
    sel.value = mapLevel;
    sel.addEventListener("change", () => setLevel(sel.value));
  }
  // HP: tombol level + toggle buka-tutup (sama seperti dropdown Parameter)
  document.querySelectorAll(".level-btn[data-level]").forEach((b) =>
    b.addEventListener("click", () => setLevel(b.dataset.level)));
  $("level-toggle")?.addEventListener("click", () =>
    document.querySelector(".level-bar")?.classList.toggle("level-open"));
  syncLevelControls();
}

// Layer dengan data HARIAN (1 frame/hari; slider = tanggal saja, tanpa jam).
const DAILY_LAYERS = new Set(["rain_accum_surface"]);

// Ibukota provinsi (nama persis di id_places.json) — TIER 0: ikon kondisi selalu
// tampil bahkan saat zoom-out penuh. Jakarta diwakili Jakarta Pusat saja.
const PROV_CAPITALS = new Set([
  "Kota Banda Aceh", "Kota Medan", "Kota Padang", "Kota Pekanbaru", "Kota Jambi",
  "Kota Palembang", "Kota Pangkal Pinang", "Kota Bengkulu", "Kota Bandar Lampung",
  "Kota Serang", "Kota Administrasi Jakarta Pusat", "Kota Bandung", "Kota Semarang",
  "Kota Yogyakarta", "Kota Surabaya", "Kota Denpasar", "Kota Mataram", "Kota Kupang",
  "Kota Pontianak", "Kota Palangka Raya", "Kota Banjarmasin", "Kota Samarinda",
  "Kabupaten Bulungan", "Kota Manado", "Kota Palu", "Kota Makassar", "Kota Kendari",
  "Kota Gorontalo", "Kabupaten Mamuju", "Kota Ambon", "Kota Ternate",
  "Kota Tidore Kepulauan", "Kota Jayapura", "Kabupaten Manokwari", "Kota Sorong",
]);

// ---- Peta dasar (gelap, ala screenshot) --------------------------------
const map = L.map("map", {
  center: [5, 116],
  zoom: 4,
  minZoom: 3,
  maxZoom: 9,
  zoomSnap: 0,             // izinkan zoom pecahan → bingkai bisa pas mengisi layar
  zoomControl: false,      // pakai tombol zoom neubrutalist sendiri
  attributionControl: false, // kredit ditaruh di footer sidebar
  maxBoundsViscosity: 1.0, // dinding keras: tak bisa geser keluar kotak
  preferCanvas: true,      // render vektor (batas) via Canvas: hanya yang masuk frame
  wheelPxPerZoomLevel: 120,// scroll-zoom lebih landai → terasa lebih mulus
  wheelDebounceTime: 30,
});

// Kotak inti yang WAJIB selalu tampak penuh: India–Pasifik Barat, Cina Selatan–
// tengah Australia. Bingkai tampilan diturunkan dari kotak ini, diperlebar
// mengikuti rasio layar. Domain DATA (dari catalog) lebih luas dari kotak ini di
// tiap sisi → tepi data tak pernah terlihat.
// Kotak inti tampilan awal. Default = domain GFS. Model lain boleh membawa
// kotaknya sendiri lewat catalog.region.view_core, jadi WRF membingkai Jawa
// bukan seluruh Asia Tenggara. Diganti di init() setelah katalog terbaca.
let VIEW_CORE = L.latLngBounds([-28, 68], [28, 174]);

// dark_NOLABELS, bukan dark_all. Alas sudah punya lapisan label sendiri di pane
// "labels"; kalau alasnya juga membawa nama, namanya muncul dua kali di tempat yang
// datanya transparan (mis. hujan saat kering).
// Basemap Esri World Dark Gray (GRATIS, tanpa API key). CARTO menghentikan akses
// tanpa-key (tile bertempel watermark "API key required"), jadi pindah ke Esri.
L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}", {
  attribution: 'Tiles &copy; Esri | Data: NOAA GFS',
  maxZoom: 12, maxNativeZoom: 16,
  updateWhenZooming: false, // tunda muat tile sampai zoom selesai → animasi mulus
  keepBuffer: 4,
}).addTo(map);

// Pane heatmap kecepatan angin: di atas peta dasar (z200), di bawah partikel
// (overlayPane z400) & label (z650). Ini "kontur warna" ala BMKG Signature.
const speedPane = map.createPane("speed");
speedPane.style.zIndex = 350;
speedPane.style.pointerEvents = "none";

// Pane batas administrasi (garis negara & provinsi): di atas partikel
// (overlayPane z400), di bawah label (z650).
const adminPane = map.createPane("admin");
adminPane.style.zIndex = 450;
adminPane.style.pointerEvents = "none";

// Label negara/laut di atas partikel supaya tetap terbaca
const labelPane = map.createPane("labels");
labelPane.style.zIndex = 650;
labelPane.style.pointerEvents = "none";
// Pane ikon kondisi cuaca per kota — di atas label, TETAP bisa diklik.
const cityPane = map.createPane("cityicons");
cityPane.style.zIndex = 660;
// Siklon: jalur (garis, non-interaktif) di bawah, ikon pusat (klik) di atas.
// Pos hujan WRF: penanda TETAP, selalu tampil selama model WRF dipilih.
// z 670, di ATAS label kota/kabupaten beserta nilainya (pane cityicons z660)
// dan di atas label negara/laut (pane labels z650). Pos ini titik acuan
// akurasi, jadi tak boleh ketutup nama kota.
const posPane = map.createPane("poshujan");
posPane.style.zIndex = 670;
// Tooltip pos hujan punya pane SENDIRI di z690. Kalau memakai tooltipPane
// bawaan Leaflet (z650) ia kalah dari label kota/kabupaten (z660) dan
// tertutup separuh. Harus di atas label kota DAN di atas ikon posnya sendiri.
const posTipPane = map.createPane("poshujan-tip");
posTipPane.style.zIndex = 690;
posTipPane.style.pointerEvents = "none";
const cyclonePathPane = map.createPane("cyclonepath");
cyclonePathPane.style.zIndex = 655;
cyclonePathPane.style.pointerEvents = "none";
const cyclonePane = map.createPane("cyclones");
cyclonePane.style.zIndex = 664;
// ITCZ: pita zona + garis sumbu, konteks latar (non-interaktif, klik tembus ke peta).
const itczPane = map.createPane("itcz");
itczPane.style.zIndex = 459;
itczPane.style.pointerEvents = "none";
// Isobar: garis kontur tekanan + penanda H/L (otomatis di layer Tekanan).
const isobarPane = map.createPane("isobar");
isobarPane.style.zIndex = 461;
isobarPane.style.pointerEvents = "none";
// Dua set label: GELAP (teks terang, utk tema gelap/angin) & TERANG (teks gelap,
// utk tema terang/hujan). Ditukar oleh applyTheme() sesuai layer aktif.
const _lblOpts = { pane: "labels", maxNativeZoom: 16, updateWhenZooming: false, keepBuffer: 4 };
const darkLabels = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}", _lblOpts).addTo(map);
const lightLabels = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}", _lblOpts);

// ---- State -------------------------------------------------------------
let frames = [];
let current = 0;
let velocityLayer = null;
let speedLayer = null;      // heatmap (imageOverlay preview PNG) — dipakai kedua layer
// Jarak antar langkah waktu, dalam JAM. GFS 3 jam, WRF Citarum 1 jam.
// Dipakai untuk mengubah laju hujan (mm/jam) jadi akumulasi. Dulu dipatok 3
// dan itu benar selama cuma ada GFS; begitu WRF masuk, patokan itu melebihkan
// akumulasi tepat 3 kali. Dihitung ulang dari deret waktu yang sebenarnya.
let STEP_JAM = 3;
function hitungStepJam(times) {
  if (!times || times.length < 2) return;
  const a = new Date(times[0]).getTime(), b = new Date(times[1]).getTime();
  const j = Math.round((b - a) / 3600000);
  if (j > 0 && j <= 24) STEP_JAM = j;
}

let dataBounds = null;      // L.latLngBounds untuk BINGKAI, minZoom, dan kunci pan
let imageBounds = null;     // L.latLngBounds tempat heatmap ditempel (bisa lebih kecil)
let playing = false;
let playTimer = null;
let activeLayer = "wind_surface";
let activeBase = "wind_surface";   // tombol layer aktif (kunci PERMUKAAN); di strato dipetakan ke varian _strato
let mapLevel = "surface";          // "surface" | "strato" (70 hPa) — dari dropdown LEVEL
let catalog = null;
let windVelByTime = {};     // PERMUKAAN: valid_time -> velocity_json (partikel angin)
let windVelStrato = {};     // STRATO 70 hPa: valid_time -> velocity_json
let worldLayer = null, provLayer = null;   // layer batas (warna diatur per-tema)
const dataCache = new Map();
// Tombol "Kondisi" HANYA mengatur ikon cuaca (cerah/berawan/hujan). Nama kota +
// nilai parameter aktif berdiri sendiri, selalu tampil, tak ikut tombol itu.
let cityIconsOn = false;    // toggle IKON kondisi cuaca per kota
let cityGroup = null;       // L.layerGroup penampung marker kota (label + ikon opsional)
let cyclonesOn = false;     // toggle deteksi siklon + jalur
let cyclones = null, cyclonesLoading = null;
let cycloneGroup = null;
let itczOn = false;         // toggle zona ITCZ (pita + garis pertemuan angin)
let itcz = null, itczLoading = null;
let itczGroup = null;
let isobars = null, isobarsLoading = null;   // garis isobar (auto di layer Tekanan)
let isobarGroup = null;
let monsoonOn = false;      // toggle: monsun DOMINAN (warna + banner ikut data) + arus beranimasi
let monsoon = null, monsoonLoading = null;
let monsoonVel = null, monsoonVelData = null, monsoonVelLoading = null;
let borneoVel = null, borneoVelData = null, borneoVelLoading = null, borneoMarker = null;

// Ubin label CARTO DIMATIKAN. Alasannya: ubin itu menulis nama kota juga, sedangkan
// label kita sendiri sudah menulis nama + angka parameter. Dua duanya hidup = tiap
// kota punya dua nama (mis. "Majalengka" muncul dua kali, salah satunya tanpa angka).
// Satu tempat cukup satu label, dan label yang menang adalah yang membawa angka.
//
// Naikkan angka ini untuk menghidupkan lagi label CARTO di bawah zoom tersebut
// (mis. 5.5 = hidup saat peta masih jauh, mati begitu label kota kita muncul).
const LABEL_TILE_MAX_Z = 0;

// ---- Nama negara & laut, digambar sendiri ----
// Ubin label CARTO dimatikan karena bikin nama kota kembar. Konteks geografis tetap
// perlu, jadi kita gambar sendiri dari daftar pendek ini. Karena daftarnya kita yang
// pegang, tak mungkin bentrok dengan label kota. Hanya yang masuk domain data
// (bujur 62-180 timur, lintang 33 selatan sampai 33 utara).
const GEO_LABELS = [
  { t: "India", lat: 22.0, lon: 79.0, k: "neg" },
  { t: "Sri Lanka", lat: 7.8, lon: 80.8, k: "neg" },
  { t: "Bangladesh", lat: 24.0, lon: 90.0, k: "neg" },
  { t: "Myanmar", lat: 21.0, lon: 96.2, k: "neg" },
  { t: "Thailand", lat: 15.5, lon: 101.0, k: "neg" },
  { t: "Laos", lat: 18.6, lon: 103.6, k: "neg" },
  { t: "Kamboja", lat: 12.4, lon: 104.9, k: "neg" },
  { t: "Vietnam", lat: 16.2, lon: 107.4, k: "neg" },
  { t: "Tiongkok", lat: 27.0, lon: 107.0, k: "neg" },
  { t: "Taiwan", lat: 23.7, lon: 121.0, k: "neg" },
  { t: "Filipina", lat: 12.5, lon: 122.5, k: "neg" },
  { t: "Malaysia", lat: 4.0, lon: 102.3, k: "neg" },
  { t: "Brunei", lat: 4.5, lon: 114.7, k: "neg" },
  { t: "Indonesia", lat: -4.2, lon: 109.8, k: "neg" },
  { t: "Timor Leste", lat: -8.8, lon: 125.9, k: "neg" },
  { t: "Papua Nugini", lat: -6.2, lon: 144.0, k: "neg" },
  { t: "Australia", lat: -24.0, lon: 133.0, k: "neg" },
  { t: "Samudra Hindia", lat: -15.0, lon: 85.0, k: "laut" },
  { t: "Laut Arab", lat: 15.0, lon: 65.0, k: "laut" },
  { t: "Teluk Benggala", lat: 15.0, lon: 88.0, k: "laut" },
  { t: "Laut Andaman", lat: 11.0, lon: 95.5, k: "laut" },
  { t: "Laut Cina Selatan", lat: 13.5, lon: 114.0, k: "laut" },
  { t: "Laut Jawa", lat: -5.4, lon: 114.6, k: "laut" },
  { t: "Laut Sulawesi", lat: 3.5, lon: 122.0, k: "laut" },
  { t: "Laut Banda", lat: -5.6, lon: 128.0, k: "laut" },
  { t: "Laut Timor", lat: -11.5, lon: 127.0, k: "laut" },
  { t: "Laut Arafura", lat: -9.5, lon: 136.0, k: "laut" },
  { t: "Laut Filipina", lat: 16.0, lon: 130.0, k: "laut" },
  { t: "Samudra Pasifik", lat: 5.0, lon: 158.0, k: "laut" },
];
// Di atas zoom ini pengguna sudah tahu sedang melihat mana, dan label kota yang
// membawa angka jadi yang lebih berguna.
const GEO_LABEL_MAX_Z = 6;
let geoGroup = null;
let cityPlacedPts = [];   // titik label kota terakhir, dipakai geo label biar tak tabrakan

function refreshGeoLabels() {
  if (!geoGroup) return;
  geoGroup.clearLayers();
  if (map.getZoom() >= GEO_LABEL_MAX_Z) return;
  const b = map.getBounds();
  // Nama negara/laut cuma konteks, jadi mengalah pada label kota yang membawa angka.
  // Titik label kota dipakai sebagai penghalang, lalu antar-geo saling menghindar juga.
  const halang = cityPlacedPts.slice(), GX = 66, GY = 22;
  for (const g of GEO_LABELS) {
    if (!b.contains([g.lat, g.lon])) continue;
    const pt = map.latLngToContainerPoint([g.lat, g.lon]);
    let ok = true;
    for (let i = 0; i < halang.length; i++)
      if (Math.abs(pt.x - halang[i].x) < GX && Math.abs(pt.y - halang[i].y) < GY) { ok = false; break; }
    if (!ok) continue;
    halang.push(pt);
    geoGroup.addLayer(L.marker([g.lat, g.lon], {
      pane: "labels", interactive: false, keyboard: false,
      icon: L.divIcon({ className: "geo-lbl geo-" + g.k, iconSize: [0, 0],
                        html: `<span>${g.t}</span>` }),
    }));
  }
}

// Pilih set label CARTO sesuai tema, atau matikan bila zoom sudah melewati ambang.
function applyLabelTiles() {
  const light = LAYER_THEME[activeLayer] === "light";
  const pakai = map.getZoom() < LABEL_TILE_MAX_Z ? (light ? lightLabels : darkLabels) : null;
  for (const l of [darkLabels, lightLabels])
    if (l !== pakai && map.hasLayer(l)) map.removeLayer(l);
  if (pakai && !map.hasLayer(pakai)) pakai.addTo(map);
}

// Tema per-layer: angin = gelap (latar peta gelap), hujan = terang (latar putih).
function applyTheme() {
  const light = LAYER_THEME[activeLayer] === "light";
  applyLabelTiles();
  map.getPane("labels").classList.toggle("lbl-light", light);   // teks gelap di peta terang
  // Batas: override per-layer bila ada, jika tidak ikut tema (gelap/putih).
  const color = BORDER_COLOR[activeLayer] || (light ? "#1c1b1b" : "#ffffff");
  const opacity = light ? 0.7 : 0.85;
  // Di layer Tekanan, batas dibuat lebih redup agar isobar jadi garis dominan.
  const bOpacity = activeLayer === "pressure_surface" ? 0.5 : opacity;
  if (worldLayer) worldLayer.setStyle({ color, opacity: bOpacity });
  if (provLayer) provLayer.setStyle({ color, opacity: bOpacity });
}

// Warna partikel angin sesuai tema: gelap di latar terang, putih di latar gelap.
function particleColor() {
  return LAYER_THEME[activeLayer] === "light" ? "#2b3550" : "#ffffff";
}

const $ = (id) => document.getElementById(id);

function toWIB(iso) {
  // GFS memberi waktu UTC; WIB = UTC+7.
  return new Date(new Date(iso).getTime() + 7 * 3600 * 1000);
}

function fmtValid(iso) {
  // "2026-07-31T00:00:00Z" -> "Jum, 31 Jul 07:00 WIB"
  const opt = { weekday: "short", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "UTC" };
  return toWIB(iso).toLocaleString("id-ID", opt).replace(/\./g, ":") + " WIB";
}

function fmtDay(iso) {
  // Untuk layer harian: tampilkan TANGGAL saja (hari akumulasi, UTC).
  return new Date(iso).toLocaleDateString("id-ID",
    { weekday: "short", day: "2-digit", month: "short", timeZone: "UTC" });
}

// Frame terdekat ke waktu "sekarang" (untuk posisi awal slider, karena window
// bisa memuat masa lalu -24 jam).
// "Sekarang" versi aplikasi. Untuk GFS ini jam dinding sungguhan. Untuk model
// ARSIP (WRF Citarum, datanya 2018) jam dinding tak ada gunanya, semua frame
// jadi masa lalu dan slider melompat ke ujung. Jadi dipakai run_time katalog,
// yaitu batas antara 1 hari lampau dan 3 hari ke depan di jendela itu.
function nowMs() {
  if (catalog?.arsip && catalog.run_time) {
    const t = new Date(catalog.run_time).getTime();
    if (isFinite(t)) return t;
  }
  return Date.now();
}

function nearestNowIndex() {
  const now = nowMs();
  let best = 0, bestDiff = Infinity;
  frames.forEach((f, i) => {
    const d = Math.abs(new Date(f.valid_time).getTime() - now);
    if (d < bestDiff) { bestDiff = d; best = i; }
  });
  return best;
}

// Label tanggal/jam (WIB) di bawah slider: tanggal ditandai tebal saat harinya
// berganti, sisanya jam saja.
function buildTicks() {
  const wrap = $("tl-ticks");
  if (!wrap || !frames.length) return;
  const n = frames.length;
  let prevDay = null;
  wrap.innerHTML = frames.map((f, i) => {
    const wib = toWIB(f.valid_time);
    const day = wib.getUTCDate();
    // Frame 0 hanya dilabeli kalau memang hari tersendiri (layer HARIAN). Di layer
    // per-jam frame 0 itu hari yang belum genap; dulu labelnya dipaksa muncul lalu
    // menyerempet label tengah malam pertama, jadi terlihat bertumpuk di awal.
    // Sekarang tanggal cuma muncul di pergantian hari yang sebenarnya.
    const isDay = i === 0
      ? (n <= 1 || day !== toWIB(frames[1].valid_time).getUTCDate())
      : day !== prevDay;
    prevDay = day;
    const pos = n === 1 ? 0 : (i / (n - 1)) * 100;
    const edge = i === 0 ? " edge-start" : (i === n - 1 ? " edge-end" : "");
    // Mark untuk tiap frame; label TANGGAL saja (di pergantian hari) biar tak berdesakan.
    const lbl = isDay
      ? `<span class="tl-tick-lbl">${wib.toLocaleDateString("id-ID", { day: "numeric", month: "short", timeZone: "UTC" })}</span>`
      : "";
    return `<div class="tl-tick${isDay ? " day" : ""}${edge}" style="left:${pos}%">` +
      `<span class="tl-tick-mark"></span>${lbl}</div>`;
  }).join("");
}

// ---- Batas administrasi -------------------------------------------------
// Indonesia: batas PROVINSI (garis tipis). Negara lain: batas NEGARA saja.
const ADMIN_BASE = "data/";
async function loadAdmin() {
  // Struktur styling mengikuti portofolio: batas negara solid & tegas,
  // batas provinsi tipis putus-putus. Warna putih agar kontras di atas heatmap gelap.
  const styleCountry = { color: "#ffffff", weight: 1.0, opacity: 0.85, fill: false, lineJoin: "round", lineCap: "round", interactive: false };
  const styleProv = { color: "#ffffff", weight: 1.0, opacity: 0.85, fill: false, dashArray: "3 2", lineJoin: "round", interactive: false };
  // Canvas renderer khusus pane admin: fitur di luar frame (+padding) tak digambar,
  // muncul lagi saat di-pan/zoom-out. Jauh lebih mulus daripada SVG.
  const renderer = L.canvas({ pane: "admin", padding: 0.5 });
  try {
    const [world, prov] = await Promise.all([
      fetch(ADMIN_BASE + "world_countries.geojson").then((r) => (r.ok ? r.json() : null)),
      fetch(ADMIN_BASE + "idn_provinces.geojson").then((r) => (r.ok ? r.json() : null)),
    ]);
    if (world) {
      worldLayer = L.geoJSON(world, {
        pane: "admin",
        renderer,
        style: styleCountry,
        // Indonesia digambar oleh layer provinsi → hindari garis pantai ganda kasar.
        filter: (f) => !f.properties || f.properties.name !== "Indonesia",
      }).addTo(map);
    }
    if (prov) provLayer = L.geoJSON(prov, { pane: "admin", renderer, style: styleProv }).addTo(map);
    applyTheme(); // warna batas sesuai layer aktif saat ini
  } catch (e) {
    console.warn("Batas administrasi gagal dimuat:", e);
  }
}

async function loadVelocity(vj) {
  if (dataCache.has(vj)) return dataCache.get(vj);
  const res = await fetch(DATA_BASE + vj);
  if (!res.ok) throw new Error("Gagal memuat " + vj);
  const data = await res.json();
  dataCache.set(vj, data);
  return data;
}

function renderLegend(layerKey) {
  const def = LEGENDS[layerKey];
  const head = $("legend-head"), cells = $("legend-cells");
  if (!def || !head || !cells) return;
  head.textContent = def.head;
  cells.classList.toggle("legend-words", !!def.words);   // sel melebar utk label kata
  // Warna dipindah ke anak `.lg-bar`, BUKAN latar selnya. Dengan begitu lebar
  // sel ditentukan oleh panjang labelnya sendiri, jadi legenda berlabel kata
  // (mis. kategori ISPU) tidak saling menabrak seperti waktu lebarnya dipatok.
  cells.innerHTML = def.cells.map(([label, bg, dark]) =>
    (bg === "transparent"
      ? `<div class="legend-cell kotak-catur${dark ? " dark" : ""}">${label}</div>`
      : `<div class="legend-cell${dark ? " dark" : ""}" style="background:${bg}">${label}</div>`)
  ).join("");
}

function setActiveLayer(layerKey) {
  if (!catalog || !catalog.layers[layerKey] || layerKey === activeLayer) return;
  activeLayer = layerKey;
  activeBase = BASE_OF[layerKey] || layerKey;   // tombol yang menyala = kunci permukaan
  frames = catalog.layers[layerKey].frames;
  document.querySelectorAll(".layer-btn[data-layer]").forEach((b) =>
    b.classList.toggle("active", b.dataset.layer === activeBase));
  renderLegend(layerKey);
  updateParChip();
  applyTheme();
  if (velocityLayer) { map.removeLayer(velocityLayer); velocityLayer = null; } // recreate warna partikel
  // Recreate imageOverlay heatmap tiap ganti layer: elemen <img> yang sama TAK
  // di-reuse antar-layer. Mencegah "ghost" palet layer sebelumnya menembus area
  // transparan layer hujan (bug sisa palet putih->biru saat pindah lalu balik).
  if (speedLayer) { map.removeLayer(speedLayer); speedLayer = null; }
  buildTicks();
  const slider = $("time-slider");
  if (slider) slider.max = String(frames.length - 1);
  // Index frame tak sebanding antar-layer (harian ~8 frame vs per-jam ~27). Selalu
  // resolve ulang ke frame terdekat "sekarang" agar tak melompat ke awal data.
  current = nearestNowIndex();
  showFrame(current);
  syncIsobars();                 // isobar auto muncul/lepas mengikuti layer Tekanan
  // panel titik ikut variabel aktif
  if (pointData && lastPoint && $("point-panel")?.classList.contains("open"))
    renderPoint(pointData, lastPoint.lat, lastPoint.lon);
  updateHash();
}

async function showFrame(i) {
  current = (i + frames.length) % frames.length;
  const frame = frames[current];

  // Heatmap (kedua layer punya preview_image): angin = kecepatan, hujan = laju hujan.
  const url = DATA_BASE + frame.preview_image;
  if (!speedLayer) {
    speedLayer = L.imageOverlay(url, imageBounds, { pane: "speed", opacity: 0.92, interactive: false });
    speedLayer.addTo(map);
  } else {
    speedLayer.setUrl(url);
  }
  const isVector = catalog.layers[activeLayer]?.kind === "vector";
  speedLayer.setOpacity(isVector ? 0.92 : 1); // scalar opaque; angin semi

  // Partikel angin PUTIH — SELALU ada (angin & hujan), dari medan angin waktu sama.
  // Ikut LEVEL: di stratosfer pakai medan angin 70 hPa agar konsisten dengan heatmap.
  const vsrc = (mapLevel === "strato") ? windVelStrato : windVelByTime;
  const vj = vsrc[frame.valid_time];
  if (vj) {
    const data = await loadVelocity(vj);
    if (!velocityLayer) {
      velocityLayer = L.velocityLayer({
        displayValues: false,
        displayOptions: {
          velocityType: "Angin", position: "bottomleft", emptyString: "Tidak ada data",
          angleConvention: "bearingCW", speedUnit: "kt", directionString: "Arah", speedString: "Kecepatan",
        },
        data,
        minVelocity: 0, maxVelocity: 25, velocityScale: 0.012,
        particleAge: 90, particleMultiplier: 1 / 260, lineWidth: 1.1,
        colorScale: [particleColor()], frameRate: 24,
      });
      velocityLayer.addTo(map);
    } else {
      if (!map.hasLayer(velocityLayer)) velocityLayer.addTo(map);
      velocityLayer.setData(data);
    }
  } else if (velocityLayer && map.hasLayer(velocityLayer)) {
    map.removeLayer(velocityLayer);
  }

  const vt = $("valid-time");
  if (vt) vt.textContent = DAILY_LAYERS.has(activeLayer) ? fmtDay(frame.valid_time) : fmtValid(frame.valid_time);
  const ts = $("time-slider");
  if (ts) {
    ts.value = String(current);
    // Isian "cairan" slider. Kotak hijau penanda jam sekarang sudah dibuang,
    // penggantinya justru isian ini: bagian yang sudah terlewati diwarnai
    // hijau neon dan ujungnya BERHENTI di waktu yang sedang dipilih. Posisinya
    // ditulis ke custom property, gradiennya digambar CSS.
    const maks = Math.max(1, (parseInt(ts.max, 10) || 1));
    ts.style.setProperty("--tl-isi", ((current / maks) * 100).toFixed(2) + "%");
  }
  refreshCityIcons();                    // label kota (+ikon bila aktif) ikut waktu aktif
  if (cyclonesOn) refreshCyclones();     // siklon + jalur ikut waktu aktif
  if (itczOn) refreshItcz();             // zona ITCZ ikut waktu aktif
  if (activeLayer === "pressure_surface") refreshIsobars();   // isobar ikut waktu aktif
  if (skewtOpen && lastPoint && $("point-panel")?.classList.contains("open")) renderSkewTCard();
  updateHash();
}

function togglePlay() {
  playing = !playing;
  $("play-icon").textContent = playing ? "pause" : "play_arrow";
  if (playing) {
    playTimer = setInterval(async () => { await showFrame(current + 1); }, 1100);
  } else {
    clearInterval(playTimer);
  }
}

// ================= POINT DETAIL =================
let pointData = null;      // { meta, vars: {name:{arr,scale,offset}} }
let pointLoading = null;
let pointMarker = null;
let sharedPoint = null;    // {lat,lon,name} titik aktif → dipakai untuk link Bagikan
let lastPoint = null;      // untuk export CSV
const MS_TO_KT = 1.943844;
const DIRS = ["U", "TL", "T", "TG", "S", "BD", "B", "BL"]; // 8 arah dari Utara searah jarum jam

async function loadPointData() {
  if (pointData) return pointData;
  if (pointLoading) return pointLoading;
  pointLoading = (async () => {
    const meta = await fetch(DATA_BASE + "point_meta.json").then((r) => r.json());
    const gz = await fetch(DATA_BASE + "point_data.bin.gz").then((r) => r.arrayBuffer());
    const stream = new Blob([gz]).stream().pipeThrough(new DecompressionStream("gzip"));
    const buf = await new Response(stream).arrayBuffer();
    const vars = {};
    for (const v of meta.vars) {
      const Ctor = v.dtype === "uint8" ? Uint8Array : Int16Array;
      vars[v.var] = { arr: new Ctor(buf, v.byteOffset, v.byteLength / Ctor.BYTES_PER_ELEMENT),
                      scale: v.scale, offset: v.offset };
    }
    pointData = { meta, vars };
    return pointData;
  })();
  return pointLoading;
}

// Bilinear di titik (lat,lon) untuk semua waktu -> array nilai.
function sampleVar(pd, name, lat, lon) {
  const v = pd.vars[name];
  if (!v) return null;
  const { nx, ny, bounds, dx, dy, times } = pd.meta;
  const [w, , , n] = bounds;
  let fx = Math.max(0, Math.min(nx - 1, (lon - w) / dx));
  let fy = Math.max(0, Math.min(ny - 1, (n - lat) / dy)); // baris-0 = utara
  const x0 = Math.floor(fx), x1 = Math.min(x0 + 1, nx - 1), tx = fx - x0;
  const y0 = Math.floor(fy), y1 = Math.min(y0 + 1, ny - 1), ty = fy - y0;
  const plane = nx * ny, out = [];
  for (let t = 0; t < times.length; t++) {
    const b = t * plane;
    const A = v.arr[b + y0 * nx + x0], B = v.arr[b + y0 * nx + x1];
    const C = v.arr[b + y1 * nx + x0], D = v.arr[b + y1 * nx + x1];
    const raw = (1 - tx) * (1 - ty) * A + tx * (1 - ty) * B + (1 - tx) * ty * C + tx * ty * D;
    out.push(raw * v.scale + v.offset);
  }
  return out;
}

function windAt(u, v) {
  const spd = Math.sqrt(u * u + v * v) * MS_TO_KT;
  const deg = (Math.atan2(-u, -v) * 180 / Math.PI + 360) % 360; // arah DATANG
  return { spd, dir: DIRS[Math.round(deg / 45) % 8] };
}

// ============== PROFIL VERTIKAL (Skew-T) — muat malas & sampel ==============
let profileData = null;      // { meta, vars:{t,r,u,v} }
let profileLoading = null;
let skewtOpen = false;       // kartu Skew-T sedang dibuka?

async function loadProfileData() {
  if (profileData) return profileData;
  if (profileLoading) return profileLoading;
  profileLoading = (async () => {
    const meta = await fetch(DATA_BASE + "profile_meta.json").then((r) => r.json());
    const gz = await fetch(DATA_BASE + "profile.bin.gz").then((r) => r.arrayBuffer());
    const stream = new Blob([gz]).stream().pipeThrough(new DecompressionStream("gzip"));
    const buf = await new Response(stream).arrayBuffer();
    const vars = {};
    for (const v of meta.vars) {
      const Ctor = v.dtype === "uint8" ? Uint8Array : Int16Array;
      vars[v.var] = { arr: new Ctor(buf, v.byteOffset, v.byteLength / Ctor.BYTES_PER_ELEMENT),
                      scale: v.scale, offset: v.offset };
    }
    profileData = { meta, vars };
    return profileData;
  })();
  return profileLoading;
}

// Index waktu profil terdekat dengan valid_time frame yang sedang ditampilkan.
function profileTimeIndex(pd) {
  const vt = frames && frames[current] && frames[current].valid_time;
  const ts = pd.meta.times;
  const hit = ts.indexOf(vt);
  if (hit >= 0) return hit;
  const target = new Date(vt || ts[0]).getTime();
  let best = 0, bd = Infinity;
  ts.forEach((t, i) => { const dd = Math.abs(new Date(t).getTime() - target); if (dd < bd) { bd = dd; best = i; } });
  return best;
}

// Profil vertikal di (lat,lon) untuk index waktu ti -> {levels,T,RH,u,v} per level.
function sampleProfile(pd, lat, lon, ti) {
  const { nx, ny, bounds, dx, dy, levels } = pd.meta;
  const nlev = levels.length, plane = nx * ny, [w, , , n] = bounds;
  const fx = Math.max(0, Math.min(nx - 1, (lon - w) / dx));
  const fy = Math.max(0, Math.min(ny - 1, (n - lat) / dy));
  const x0 = Math.floor(fx), x1 = Math.min(x0 + 1, nx - 1), tx = fx - x0;
  const y0 = Math.floor(fy), y1 = Math.min(y0 + 1, ny - 1), ty = fy - y0;
  const samp = (vv, lev) => {
    const b = (ti * nlev + lev) * plane;
    const A = vv.arr[b + y0 * nx + x0], B = vv.arr[b + y0 * nx + x1];
    const C = vv.arr[b + y1 * nx + x0], D = vv.arr[b + y1 * nx + x1];
    return ((1 - tx) * (1 - ty) * A + tx * (1 - ty) * B + (1 - tx) * ty * C + tx * ty * D) * vv.scale + vv.offset;
  };
  const out = { levels: levels.slice(), T: [], RH: [], u: [], v: [] };
  for (let l = 0; l < nlev; l++) {
    out.T.push(samp(pd.vars.t, l)); out.RH.push(Math.max(0, Math.min(100, samp(pd.vars.r, l))));
    out.u.push(samp(pd.vars.u, l)); out.v.push(samp(pd.vars.v, l));
  }
  return out;
}

// Export PLOT Skew-T (tanpa legenda) ke PNG. Rasterize SVG plot ke canvas,
// beri latar + border + bayangan neubrutalist agar rapi saat dibagikan.
function exportSkewTPng() {
  const wrap = $("pt-skewt-wrap");
  const svgEl = wrap && wrap.querySelector("svg");   // svg PERTAMA = plot (bukan swatch legenda)
  if (!svgEl) return;
  const vb = svgEl.viewBox.baseVal;
  const W = vb && vb.width ? vb.width : 340, H = vb && vb.height ? vb.height : 380;
  const xml = new XMLSerializer().serializeToString(svgEl);
  const img = new Image();
  img.onload = () => {
    const s = 2, M = 14, SH = 6;
    const cw = W + M * 2 + SH, ch = H + M * 2 + SH;
    const c = document.createElement("canvas");
    c.width = cw * s; c.height = ch * s;
    const x = c.getContext("2d");
    x.scale(s, s);
    x.fillStyle = "#fcf8f8"; x.fillRect(0, 0, cw, ch);         // latar
    x.fillStyle = "#1c1b1b"; x.fillRect(M + SH, M + SH, W, H); // bayangan keras
    x.fillStyle = "#ffffff"; x.fillRect(M, M, W, H);           // latar plot putih
    x.drawImage(img, M, M, W, H);
    x.lineWidth = 3; x.strokeStyle = "#1c1b1b"; x.strokeRect(M + 1.5, M + 1.5, W - 3, H - 3);
    c.toBlob((b) => {
      if (!b) return;
      const nm = (sharedPoint && sharedPoint.name) ? sharedPoint.name.replace(/[^\w-]+/g, "_")
        : (lastPoint ? lastPoint.lat.toFixed(2) + "_" + lastPoint.lon.toFixed(2) : "titik");
      const a = document.createElement("a");
      a.href = URL.createObjectURL(b); a.download = `skewt_${nm}.png`; a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    }, "image/png");
  };
  img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(xml);
}

// Legenda garis/elemen diagram (di bawah plot, sebelum kartu indeks).
function skewtLegend() {
  const line = (c, dash) => `<svg width="24" height="10" viewBox="0 0 24 10"><line x1="1" y1="5" x2="23" y2="5" stroke="${c}" stroke-width="2"${dash ? ` stroke-dasharray="${dash}"` : ""}/></svg>`;
  const box = (fill) => `<svg width="24" height="10" viewBox="0 0 24 10"><rect x="1" y="1" width="22" height="8" fill="${fill}" stroke="#9aa2b0" stroke-width="0.5"/></svg>`;
  const barbSw = `<svg width="24" height="12" viewBox="0 0 24 12"><line x1="2" y1="6" x2="19" y2="6" stroke="#222" stroke-width="1.2"/><line x1="19" y1="6" x2="23" y2="1" stroke="#222" stroke-width="1.2"/><line x1="15" y1="6" x2="19" y2="1" stroke="#222" stroke-width="1.2"/></svg>`;
  const it = (sw, label) => `<div class="skt-lg">${sw}<span>${label}</span></div>`;
  return `<div class="skt-legend">` +
    it(line("#e42320"), "Suhu (T)") +
    it(line("#1f8a4c"), "Titik embun (Td)") +
    it(line("#1c1b1b", "4 3"), "Jalur parcel") +
    it(barbSw, "Angin (barbs)") +
    it(line("#0029d7", "5 3"), "LCL · dasar awan") +
    it(line("#d97706", "5 3"), "LFC · mulai konveksi") +
    it(line("#7a1fa2", "5 3"), "EL · puncak konveksi") +
    it(box("rgba(226,35,32,.30)"), "CAPE · energi naik") +
    it(box("rgba(35,96,200,.25)"), "CIN · penghambat") +
    `</div>`;
}

// Kotak indeks konvektif di bawah diagram.
function skewtIndexBox(d) {
  const fmtP = (p) => p ? Math.round(p) + " hPa" : "–";
  const capeCol = d.cape > 2500 ? "#d61f1f" : d.cape > 1000 ? "#e8590c" : d.cape > 300 ? "#f59f00" : "#2b8a3e";
  const cell = (label, val, col) =>
    `<div class="skt-cell"><span class="skt-k">${label}</span><span class="skt-v" style="color:${col || "#1c1b1b"}">${val}</span></div>`;
  return `<div class="skt-idx">` +
    cell("CAPE", Math.round(d.cape) + " J/kg", capeCol) +
    cell("CIN", Math.round(d.cin) + " J/kg", d.cin < -50 ? "#e8590c" : "#5a6472") +
    cell("LCL", fmtP(d.lcl.p)) +
    cell("LFC", fmtP(d.lfc)) +
    cell("EL", fmtP(d.el)) +
    cell("LI", d.li !== null ? d.li.toFixed(1) : "–", d.li !== null && d.li < -2 ? "#d61f1f" : "#5a6472") +
    `</div>`;
}

// Skeleton loading kartu Skew-T (meniru layout: catatan + plot + export + legenda + indeks).
function skewtSkeleton() {
  return `<div class="pt-skel skt-skel">` +
    `<div class="sk-bar skt-sk-note"></div>` +
    `<div class="sk-bar skt-sk-plot"></div>` +
    `<div class="sk-bar skt-sk-exp"></div>` +
    `<div class="skt-sk-idx">${"<div class='sk-bar'></div>".repeat(6)}</div>` +
    `</div>`;
}

// Render (atau re-render) kartu Skew-T ke #pt-skewt-wrap untuk titik & waktu aktif.
async function renderSkewTCard() {
  const wrap = $("pt-skewt-wrap");
  if (!wrap || !lastPoint) return;
  wrap.innerHTML = skewtSkeleton();
  let pd;
  try { pd = await loadProfileData(); }
  catch (e) { wrap.innerHTML = `<div class="skt-load">Profil belum tersedia.</div>`; return; }
  if (!skewtOpen) return;                     // keburu ditutup
  const ti = profileTimeIndex(pd);
  const prof = sampleProfile(pd, lastPoint.lat, lastPoint.lon, ti);
  const d = window.SkewT.derive(prof);
  wrap.innerHTML =
    `<div class="skt-note">Profil ${fmtValid(pd.meta.times[ti])} · indikasi model GFS (grid ~1°), bukan sounding asli.</div>` +
    window.SkewT.svg(d, { W: 340, H: 380 }) +
    `<div class="skt-exp-row"><button type="button" class="skt-export" id="skt-export">` +
    `<span class="material-symbols-outlined">image</span> Export PNG</button></div>` +
    skewtLegend() +
    skewtIndexBox(d);
  $("skt-export")?.addEventListener("click", exportSkewTPng);
}

function fmtCoord(lat, lon) {
  return Math.abs(lat).toFixed(2) + "° " + (lat >= 0 ? "LU" : "LS") + " · " +
         Math.abs(lon).toFixed(2) + "° " + (lon >= 0 ? "BT" : "BB");
}
function fmtHour(iso) { const w = toWIB(iso); return w.getUTCDate() + "/" + String(w.getUTCHours()).padStart(2, "0"); }

// Judul panel titik: koordinat (klik acak), nama kota (search/ikon), atau
// alamat hasil reverse-geocoding (tombol "lokasi saya"). Token menjaga agar
// hasil geocoding yang datang telat tak menimpa titik lain yang keburu dipilih.
let pointToken = 0;
function setPointLabel(text, kind) { // kind: "coord" | "addr" | "loading"
  const c = $("pt-coords"); if (!c) return;
  c.textContent = text;
  c.classList.toggle("mono", kind === "coord");
  c.classList.toggle("pt-addr", kind === "addr" || kind === "loading");
}

// Susun alamat awam "Kelurahan, Kecamatan, Kota/Kabupaten" dari address
// Nominatim (tag OSM Indonesia tak konsisten → ambil sebisanya lalu dedup).
function addressLabel(a) {
  if (!a) return null;
  const kel = a.village || a.neighbourhood || a.hamlet || a.suburb;
  const kec = a.municipality || a.subdistrict || a.city_district;
  const kk  = a.city || a.town || a.county || a.regency;
  const seen = new Set(), parts = [];
  for (const x of [kel, kec, kk, a.state])
    if (x && !seen.has(x)) { seen.add(x); parts.push(x); }
  return parts.slice(0, 3).join(", ") || null;
}

// Reverse-geocode via Nominatim (OpenStreetMap) — dipakai HANYA untuk tombol
// "lokasi saya" (jarang & dipicu user, sesuai kebijakan pemakaian wajar).
async function reverseGeocode(lat, lon) {
  const url = "https://nominatim.openstreetmap.org/reverse?format=jsonv2" +
    "&lat=" + lat + "&lon=" + lon + "&zoom=14&addressdetails=1&accept-language=id";
  const r = await fetch(url, { headers: { Accept: "application/json" } });
  if (!r.ok) throw new Error("geocode " + r.status);
  return addressLabel((await r.json()).address);
}

// Cari alamat lalu perbarui judul; gagal / titik sudah diganti → koordinat.
async function fillAddress(lat, lon) {
  const token = pointToken;
  setPointLabel("Mencari alamat…", "loading");
  try {
    const addr = await reverseGeocode(lat, lon);
    if (pointToken !== token) return;
    setPointLabel(addr || fmtCoord(lat, lon), addr ? "addr" : "coord");
    if (sharedPoint && addr) { sharedPoint.name = addr; updateHash(); }
  } catch (_) {
    if (pointToken !== token) return;
    setPointLabel(fmtCoord(lat, lon), "coord");
  }
}

// Deret-waktu untuk VARIABEL yang sedang dipilih (ikut layer aktif).
function chartSeries(pd, lat, lon) {
  const times = pd.meta.times;
  // yDomain = [bawah, atas] skala sumbu Y tetap. Utk tekanan sengaja TERBALIK
  // (1200 di bawah → 400 di atas) meniru profil atmosfer vertikal: tekanan
  // tertinggi di permukaan. Tanpa yDomain → skala otomatis dari data (mulai 0).
  const num = (v, label, unit, color, type, yDomain) =>
    ({ label, unit, color, type, times, values: sampleVar(pd, v, lat, lon), yDomain });
  // Panel titik = prakiraan PERMUKAAN (di tempat berdiri). Bila peta sedang di
  // level strato, grafik ikut variabel permukaan padanannya (data titik = permukaan).
  switch (BASE_OF[activeLayer] || activeLayer) {
    case "wind_surface": {
      const u = sampleVar(pd, "u", lat, lon), v = sampleVar(pd, "v", lat, lon);
      return { label: "Kecepatan Angin", unit: "kt", color: "#0029d7", type: "line",
               times, values: u.map((uu, i) => Math.sqrt(uu * uu + v[i] * v[i]) * MS_TO_KT) };
    }
    case "temp_surface": return num("temp", "Suhu", "°C", "#e42320", "line", [0, 50]);
    case "humidity_surface": return num("humidity", "Kelembapan", "%", "#1f8a5c", "line", [0, 100]);
    case "cloud_surface": return num("cloud", "Tutupan Awan", "%", "#5a6472", "line", [0, 100]);
    case "pressure_surface": return num("pressure", "Tekanan", "hPa", "#7a3fb0", "line", [1200, 400]);
    case "storm_potential": return num("cape", "CAPE", "J/kg", "#e84a2f", "line", [0, 4000]);
    // Sumbu CIN sengaja 0 di atas, -400 di bawah: makin ke bawah makin tebal tutupnya.
    case "cin_surface": return num("cin", "CIN", "J/kg", "#8a29c8", "line", [-400, 0]);
    case "rain_accum_surface": {
      const rain = sampleVar(pd, "rain", lat, lon), days = {};
      times.forEach((t, i) => { const d = t.slice(0, 10); days[d] = (days[d] || 0) + rain[i] * STEP_JAM; });
      const dts = Object.keys(days).sort();
      return { label: "Akumulasi Hujan Harian", unit: "mm/hari", color: "#2360c8", type: "line",
               times: dts.map((d) => d + "T00:00:00Z"), values: dts.map((d) => days[d]), daily: true };
    }
    default: return num("rain", "Hujan", "mm", "#2360c8", "line"); // rain_surface
  }
}

function chartSVG(spec) {
  const { values, color, type, times, daily } = spec;
  const n = values.length;
  if (!n) return "";
  // Padding asimetris: kiri utk label sumbu-Y, bawah utk label waktu sumbu-X.
  const W = 330, H = 162, padL = 32, padR = 8, padT = 12, padB = 26;
  const plotW = W - padL - padR, plotH = H - padT - padB, y0 = padT + plotH;
  const vmin = Math.min(...values), vmax = Math.max(...values);
  // lo = nilai di DASAR sumbu, hi = nilai di PUNCAK. Bila yDomain diberi, pakai
  // itu (bisa terbalik spt tekanan: lo=1200 > hi=400). Selain itu otomatis mulai 0.
  const [lo, hi] = spec.yDomain
    ? [spec.yDomain[0], spec.yDomain[1]]
    : [Math.min(0, vmin), vmax === Math.min(0, vmin) ? Math.min(0, vmin) + 1 : vmax];
  const x = (i) => padL + plotW * (n <= 1 ? 0.5 : i / (n - 1));
  const y = (v) => y0 - plotH * ((v - lo) / (hi - lo));
  const fmt = (v) => (Math.abs(v) < 10 ? v.toFixed(1) : v.toFixed(0));
  const tms = times ? times.map((t) => new Date(t).getTime()) : [];
  const nowT = nowMs();

  // Posisi pecahan "kini" di dalam deret (utk memisah garis solid vs putus-putus).
  let sxi = n - 1;
  if (times && n > 1) {
    if (nowT <= tms[0]) sxi = 0;
    else if (nowT >= tms[n - 1]) sxi = n - 1;
    else for (let i = 0; i < n - 1; i++)
      if (nowT >= tms[i] && nowT <= tms[i + 1]) { sxi = i + (nowT - tms[i]) / (tms[i + 1] - tms[i]); break; }
  }
  const sx = x(sxi);

  // ---- data (bar: solid=terlewati, transparan+outline putus=forecast) ----
  let body = "";
  if (type === "bar") {
    const bw = Math.max(3, (plotW / n) * 0.6);
    for (let i = 0; i < n; i++) {
      const past = !times || tms[i] <= nowT;
      const bx = (x(i) - bw / 2).toFixed(1), by = y(values[i]).toFixed(1), bh = (y0 - y(values[i])).toFixed(1);
      body += `<rect x="${bx}" y="${by}" width="${bw.toFixed(1)}" height="${bh}" fill="${color}" ` +
        (past ? `opacity="0.82"/>` : `opacity="0.26" stroke="${color}" stroke-width="1" stroke-dasharray="3 2"/>`);
    }
  } else {
    const pts = values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
    if (type === "area")
      body += `<path d="${pts}L${x(n - 1).toFixed(1)},${y0}L${x(0).toFixed(1)},${y0}Z" fill="${color}" opacity="0.14"/>`;
    // Garis digambar 2x: klip kiri "kini" = solid, klip kanan = putus-putus.
    body += `<clipPath id="cpPast"><rect x="0" y="0" width="${sx.toFixed(1)}" height="${H}"/></clipPath>` +
            `<clipPath id="cpFut"><rect x="${sx.toFixed(1)}" y="0" width="${(W - sx).toFixed(1)}" height="${H}"/></clipPath>`;
    body += `<path d="${pts}" fill="none" stroke="${color}" stroke-width="2.5" stroke-linejoin="round" clip-path="url(#cpPast)"/>`;
    body += `<path d="${pts}" fill="none" stroke="${color}" stroke-width="2.5" stroke-linejoin="round" stroke-dasharray="5 4" opacity="0.8" clip-path="url(#cpFut)"/>`;
  }

  // ---- sumbu X & Y + tick label (tanpa grid) ----
  const AX = `stroke="#271717" stroke-width="1.4"`;
  let axes = `<line x1="${padL}" y1="${padT}" x2="${padL}" y2="${y0}" ${AX}/>` +
             `<line x1="${padL}" y1="${y0}" x2="${padL + plotW}" y2="${y0}" ${AX}/>`;
  for (const tv of [hi, (lo + hi) / 2, lo]) {
    const yy = y(tv);
    axes += `<line x1="${padL - 3}" y1="${yy.toFixed(1)}" x2="${padL}" y2="${yy.toFixed(1)}" ${AX}/>` +
            `<text x="${padL - 5}" y="${(yy + 3).toFixed(1)}" class="pt-ax" text-anchor="end">${fmt(tv)}</text>`;
  }
  if (times) {
    const nt = Math.min(5, n), last = n - 1;
    let prevDay = null;
    for (let k = 0; k < nt; k++) {
      const i = nt <= 1 ? 0 : Math.round((k * last) / (nt - 1));
      const xx = x(i), w = toWIB(times[i]), day = w.getUTCDate();
      const lbl = (daily || prevDay === null || day !== prevDay)
        ? day + "/" + (w.getUTCMonth() + 1)
        : String(w.getUTCHours()).padStart(2, "0") + ":00";
      prevDay = day;
      const anchor = i === 0 ? "start" : i === last ? "end" : "middle";
      axes += `<line x1="${xx.toFixed(1)}" y1="${y0}" x2="${xx.toFixed(1)}" y2="${y0 + 3}" ${AX}/>` +
              `<text x="${xx.toFixed(1)}" y="${y0 + 14}" class="pt-ax" text-anchor="${anchor}">${lbl}</text>`;
    }
    // garis acuan real-time di batas solid/forecast (tanpa teks — dijelaskan legenda)
    if (sx > padL + 1 && sx < padL + plotW - 1)
      axes += `<line x1="${sx.toFixed(1)}" y1="${padT}" x2="${sx.toFixed(1)}" y2="${y0}" stroke="#e8590c" stroke-width="1" stroke-dasharray="2 3" opacity="0.75"/>`;
  }

  return `<svg class="pt-meteo" viewBox="0 0 ${W} ${H}" width="100%">` +
    axes + body + `</svg>`;
}

// Legenda bawah frame grafik: garis solid = kondisi sekarang, putus = forecast.
function chartLegend(color) {
  const line = (dash) => `<svg width="24" height="8" viewBox="0 0 24 8">` +
    `<line x1="1" y1="4" x2="23" y2="4" stroke="${color}" stroke-width="2.5"${dash ? ` stroke-dasharray="5 4"` : ""}/></svg>`;
  return `<div class="chart-legend">` +
    `<span class="chl-key">${line(false)}Kondisi Sekarang</span>` +
    `<span class="chl-key">${line(true)}<i>Forecast</i></span></div>`;
}

async function openPoint(lat, lon, label, isMe) {
  ++pointToken; // titik baru → batalkan reverse-geocode titik sebelumnya
  const pp = $("point-panel");
  if (pp) { pp.classList.add("open"); pp.classList.remove("hidden"); }
  $("pt-reopen")?.classList.remove("show");
  // Marker: ikon "orang" (kamu di sini) utk geolokasi, belah-ketupat utk titik lain.
  if (pointMarker) map.removeLayer(pointMarker);
  const html = isMe
    ? '<span class="pm-me"><span class="material-symbols-outlined">person</span></span>'
    : '<span class="pm-diamond"></span>';
  const sz = isMe ? 32 : 20;
  pointMarker = L.marker([lat, lon], {
    icon: L.divIcon({ className: "point-mark", html, iconSize: [sz, sz], iconAnchor: [sz / 2, sz / 2] }),
    interactive: false, pane: "labels",
  }).addTo(map);
  setPointLabel(label || fmtCoord(lat, lon), label ? "addr" : "coord");
  sharedPoint = { lat, lon, name: label || null };
  updateHash();
  const body = $("pt-body"); if (body) body.innerHTML = pointSkeleton();
  try {
    renderPoint(await loadPointData(), lat, lon);
  } catch (e) {
    if (body) body.innerHTML = '<div class="pt-loading">Gagal memuat data titik.</div>';
    console.error(e);
  }
}

// Skeleton panel titik: tulang shimmer per-kontainer (ringkasan, chip, kartu
// 3-hari, grafik, tabel) meniru layout renderPoint — dipakai saat data dimuat.
function pointSkeleton() {
  const bar = (cls, w) => `<span class="sk-bar${cls ? " " + cls : ""}"${w ? ` style="width:${w}"` : ""}></span>`;
  return '<div class="pt-skel">' +
    `<div class="pt-skel-lines">${bar("", "100%")}${bar("", "94%")}${bar("", "60%")}</div>` +
    `<div class="pt-skel-chips">${bar()}${bar()}</div>` +
    bar("pt-skel-sec") +
    `<div class="pt-skel-cards">${bar()}${bar()}${bar()}</div>` +
    bar("pt-skel-sec") +
    bar("pt-skel-chart") +
    bar("pt-skel-sec") +
    `<div class="pt-skel-rows">${bar("", "100%")}${bar("", "100%")}${bar("", "100%")}${bar("", "100%")}${bar("", "100%")}</div>` +
    '</div>';
}

// ---- Ringkasan awam untuk panel titik --------------------------------
function hhWIB(iso) { const w = toWIB(iso); return String(w.getUTCHours()).padStart(2, "0") + ":00"; }
function windWord(kt) { return kt < 7 ? "tenang" : kt < 17 ? "sedang" : kt < 28 ? "kencang" : "sangat kencang"; }

// Suhu TERASA (apparent temperature, rumus BOM Australia) dari suhu(°C) +
// kelembapan(%) + angin(knot). Di iklim tropis lembap umumnya lebih PANAS dari
// suhu asli karena keringat sulit menguap. e = tekanan uap air (hPa).
function feelsLike(tC, rh, spdKt) {
  const e = (rh / 100) * 6.105 * Math.exp((17.27 * tC) / (237.7 + tC));
  const ws = (spdKt || 0) / MS_TO_KT; // knot -> m/s
  return tC + 0.33 * e - 0.70 * ws - 4.0;
}

// Kalimat bahasa manusia: kondisi kini + hujan mendatang + angin.
function pointSummary(times, temp, rain, cloud, wind, rh, ci) {
  const now = cityCondition(rain[ci], cloud ? cloud[ci] : null);
  let s = `Saat ini <b>${now.label}</b>`;
  if (temp) {
    const t = Math.round(temp[ci]);
    s += `, ${t}°C`;
    if (rh && wind) {
      const fl = Math.round(feelsLike(temp[ci], rh[ci], wind[ci].spd));
      if (Math.abs(fl - t) >= 1) s += ` <span class="feels">(terasa ${fl}°)</span>`;
    }
  }
  s += ".";
  if (rain[ci] >= 0.5) {
    let stop = -1;
    for (let i = ci + 1; i < times.length; i++) if (rain[i] < 0.5) { stop = i; break; }
    s += stop > 0 ? ` Hujan diperkirakan mereda sekitar <b>${hhWIB(times[stop])} WIB</b>.`
                  : " Hujan diperkirakan masih berlanjut beberapa jam.";
  } else {
    let onset = -1;
    for (let i = ci + 1; i < times.length; i++) if (rain[i] >= 0.5) { onset = i; break; }
    s += onset > 0 ? ` Hujan diperkirakan mulai sekitar <b>${hhWIB(times[onset])} WIB</b>.`
                   : " Tidak ada hujan berarti dalam beberapa jam ke depan.";
  }
  if (wind) s += ` Angin ${windWord(wind[ci].spd)}.`;
  return s;
}

// Saran aktivitas dari kondisi ~12 jam ke depan (chip yang relevan saja).
function pointAdvice(times, rain, cloud, wind, ci) {
  const to = Math.min(times.length, ci + 5), dry6To = Math.min(times.length, ci + 3);
  let maxRain = 0, storm = false, strongWind = false, dry6 = true;
  for (let i = ci; i < to; i++) {
    maxRain = Math.max(maxRain, rain[i]);
    if (rain[i] >= 20) storm = true;
    if (wind && wind[i].spd >= 22) strongWind = true;
    if (i < dry6To && rain[i] >= 0.5) dry6 = false;
  }
  const chips = [];
  if (maxRain >= 0.5) chips.push(["umbrella", "cc-rain", "Bawa payung"]);
  if (storm) chips.push(["thunderstorm", "cc-storm", "Waspada petir"]);
  if (maxRain >= 10 || strongWind) chips.push(["two_wheeler", "cc-heavy", "Hati-hati berkendara"]);
  if (dry6 && (!cloud || cloud[ci] < 85)) chips.push(["dry_cleaning", "cc-sunny", "Aman jemur"]);
  if (!chips.length) chips.push(["check_circle", "cc-pcloud", "Cuaca bersahabat"]);
  return chips.map(([ic, cls, txt]) =>
    `<span class="adv-chip ${cls}"><span class="material-symbols-outlined">${ic}</span>${txt}</span>`).join("");
}

// Potensi badai/petir dari CAPE (energi labil). Ambang konvektif yang lazim.
function stormLevel(c) {
  if (c >= 3000) return ["Ekstrem", "cc-storm", "thunderstorm", "atmosfer sangat labil, potensi badai petir kuat"];
  if (c >= 1800) return ["Tinggi", "cc-heavy", "bolt", "berpotensi badai dan petir"];
  if (c >= 1000) return ["Sedang", "cc-rain", "cloud", "awan hujan bisa tumbuh"];
  return ["Rendah", "cc-sunny", "wb_sunny", "atmosfer relatif stabil"];
}
function stormChip(cape, ci) {
  if (!cape) return "";
  const c = Math.round(cape[ci]);
  const [lvl, cls, ic, note] = stormLevel(c);
  return `<div class="pt-storm"><span class="adv-chip ${cls}"><span class="material-symbols-outlined">${ic}</span>Potensi badai: ${lvl}</span>` +
         `<span class="pt-storm-note">CAPE ${c} J/kg, ${note}</span></div>`;
}

// Kartu prakiraan harian (maks 3 hari): ikon dominan + suhu maks/min + hujan total.
function dailyCards(times, temp, rain, cloud, ci) {
  const days = {}, fromDate = times[ci].slice(0, 10); // mulai dari hari frame aktif (bukan masa lalu)
  for (let i = 0; i < times.length; i++) {
    const d = times[i].slice(0, 10);
    if (d < fromDate) continue;
    const o = days[d] || (days[d] = { tmax: -99, tmin: 99, peak: 0, rain: 0, cloud: 0, n: 0, nc: 0 });
    if (temp) { o.tmax = Math.max(o.tmax, temp[i]); o.tmin = Math.min(o.tmin, temp[i]); }
    o.peak = Math.max(o.peak, rain[i]); o.rain += rain[i] * STEP_JAM;
    if (cloud) { o.cloud += cloud[i]; o.nc++; }
    o.n++;
  }
  return Object.keys(days).sort().slice(0, 3).map((d) => {
    const o = days[d], cond = cityCondition(o.peak, o.nc ? o.cloud / o.nc : null);
    const base = new Date(d + "T00:00:00Z");
    const wd = base.toLocaleDateString("id-ID", { weekday: "short", timeZone: "UTC" });
    const dm = base.toLocaleDateString("id-ID", { day: "numeric", month: "short", timeZone: "UTC" });
    return `<div class="fc-card"><div class="fc-day">${wd}<span>${dm}</span></div>` +
      `<span class="cc-ico cc-mini ${cond.cls}"><span class="material-symbols-outlined">${cond.icon}</span></span>` +
      `<div class="fc-temp">` + (temp
        ? `<span class="material-symbols-outlined ft-ico">device_thermostat</span>` +
          `<span class="t-max">${Math.round(o.tmax)}°</span>` +
          `<span class="t-min">${Math.round(o.tmin)}°</span>`
        : "–") + `</div>` +
      `<div class="fc-rain">${o.rain >= 1 ? Math.round(o.rain) + " mm" : "–"}</div></div>`;
  }).join("");
}

function renderPoint(pd, lat, lon) {
  const times = pd.meta.times;
  const u = sampleVar(pd, "u", lat, lon), v = sampleVar(pd, "v", lat, lon);
  const temp = sampleVar(pd, "temp", lat, lon), rain = sampleVar(pd, "rain", lat, lon);
  const rh = sampleVar(pd, "humidity", lat, lon), cloud = sampleVar(pd, "cloud", lat, lon);
  const pres = sampleVar(pd, "pressure", lat, lon), cape = sampleVar(pd, "cape", lat, lon);
  const wind = u && v ? u.map((uu, i) => windAt(uu, v[i])) : null;
  lastPoint = { lat, lon, times, temp, rain, wind, rh, cloud, pres };

  // Kolom disusun dari variabel yang MEMANG ada. Model WRF tak punya tutupan
  // awan, dan kolom berisi "–" dari atas sampai bawah cuma memakan lebar.
  const kolom = [
    ["Tgl/Jam", (i) => fmtHour(times[i])],
    temp && ["°C", (i) => temp[i].toFixed(1)],
    wind && ["Angin", (i) => Math.round(wind[i].spd) + " " + wind[i].dir],
    rain && ["mm/j", (i) => rain[i].toFixed(1)],
    rh && ["RH%", (i) => Math.round(rh[i])],
    cloud && ["Awan%", (i) => Math.round(cloud[i])],
    pres && ["hPa", (i) => Math.round(pres[i])],
  ].filter(Boolean);
  let rows = "";
  for (let i = 0; i < times.length; i++) {
    rows += "<tr>" + kolom.map(([, f]) => `<td>${f(i)}</td>`).join("") + "</tr>";
  }
  const ci = currentTimeIndex(pd);
  const extras =
    `<div class="pt-summary">${pointSummary(times, temp, rain, cloud, wind, rh, ci)}</div>` +
    `<div class="pt-advice">${pointAdvice(times, rain, cloud, wind, ci)}</div>` +
    stormChip(cape, ci) +
    `<div class="pt-sec">PRAKIRAAN 3 HARI</div><div class="fc-cards">${dailyCards(times, temp, rain, cloud, ci)}</div>`;
  const spec = chartSeries(pd, lat, lon);
  $("pt-body").innerHTML = extras +
    `<div class="pt-sec">${spec.label.toUpperCase()} <span>${spec.unit}</span></div>${chartSVG(spec)}${chartLegend(spec.color)}` +
    `<div class="pt-sec">DATA PER-JAM (WIB)</div>` +
    `<div class="pt-table-wrap"><table class="pt-table"><thead><tr>` +
    kolom.map(([h]) => `<th>${h}</th>`).join("") +
    `</tr></thead><tbody>${rows}</tbody></table></div>` +
    // Kartu LANJUTAN: profil vertikal Skew-T (dimuat malas saat dibuka).
    // Butuh profile.bin.gz yang cuma dibuat pipeline GFS, jadi di WRF kartunya
    // tidak ditampilkan sama sekali daripada dibuka lalu gagal.
    (PUNYA_EKSTRA
      ? `<button type="button" class="pt-skewt-head${skewtOpen ? " open" : ""}" id="pt-skewt-toggle">` +
        `<span class="skt-lead material-symbols-outlined">stacked_line_chart</span>` +
        `<span class="skt-label">Profil Atmosfer · Skew-T</span>` +
        `<span class="skt-caret material-symbols-outlined">expand_more</span></button>` +
        `<div class="pt-skewt-wrap${skewtOpen ? " open" : ""}" id="pt-skewt-wrap"></div>`
      : "");

  const tog = $("pt-skewt-toggle");
  if (tog) tog.addEventListener("click", () => {
    skewtOpen = !skewtOpen;
    tog.classList.toggle("open", skewtOpen);
    $("pt-skewt-wrap")?.classList.toggle("open", skewtOpen);
    if (skewtOpen) {
      renderSkewTCard();
      // Jump: bawa kartu ke atas panel supaya profil mengisi layar (kondisi tergulir ke atas).
      requestAnimationFrame(() => $("pt-skewt-toggle")?.scrollIntoView({ behavior: "smooth", block: "start" }));
    } else { const w = $("pt-skewt-wrap"); if (w) w.innerHTML = ""; }
  });
  if (skewtOpen) renderSkewTCard();   // titik/waktu berubah saat kartu terbuka -> render ulang
}

function exportCSV() {
  if (!lastPoint) return;
  const p = lastPoint;
  let csv = "waktu_wib,suhu_C,angin_kt,arah,hujan_mmjam,kelembapan_pct,awan_pct,tekanan_hpa\n";
  for (let i = 0; i < p.times.length; i++) {
    const w = toWIB(p.times[i]);
    const wib = `${w.getUTCFullYear()}-${String(w.getUTCMonth() + 1).padStart(2, "0")}-${String(w.getUTCDate()).padStart(2, "0")} ${String(w.getUTCHours()).padStart(2, "0")}:00`;
    csv += [wib, p.temp ? p.temp[i].toFixed(1) : "", p.wind ? Math.round(p.wind[i].spd) : "",
            p.wind ? p.wind[i].dir : "", p.rain ? p.rain[i].toFixed(1) : "",
            p.rh ? Math.round(p.rh[i]) : "", p.cloud ? Math.round(p.cloud[i]) : "",
            p.pres ? Math.round(p.pres[i]) : ""].join(",") + "\n";
  }
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  a.download = `titik_${p.lat.toFixed(2)}_${p.lon.toFixed(2)}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}

function closePoint() {
  $("point-panel")?.classList.remove("open", "hidden");
  $("pt-reopen")?.classList.remove("show");
  if (pointMarker) { map.removeLayer(pointMarker); pointMarker = null; }
  sharedPoint = null;
  updateHash();
}
function hidePoint() {           // sembunyikan panel, marker & data tetap
  $("point-panel")?.classList.add("hidden");
  $("pt-reopen")?.classList.add("show");
}
function reopenPoint() {
  $("point-panel")?.classList.remove("hidden");
  $("pt-reopen")?.classList.remove("show");
}

// ================= FRESHNESS · SHARE · TOAST =================
// Waktu inisiasi model (run_time GFS) dalam WIB — jam & tanggal. Kredibilitas:
// user tahu kapan data terakhir diperbarui.
const MONTHS_ID = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"];
function updateFreshness() {
  const el = $("fresh-text"); if (!el || !catalog?.run_time) return;
  const w = toWIB(catalog.run_time);
  const hh = String(w.getUTCHours()).padStart(2, "0");
  const mm = String(w.getUTCMinutes()).padStart(2, "0");
  const tgl = `${hh}:${mm} WIB, ${w.getUTCDate()} ${MONTHS_ID[w.getUTCMonth()]} ${w.getUTCFullYear()}`;
  // Model arsip (WRF Citarum) tanggalnya 2018-2019. Kalau ditulis "Last update"
  // begitu saja orang mengira situsnya basi. Ditandai terang terangan.
  el.textContent = catalog.arsip ? `ARSIP : ${tgl}` : `Last update : ${tgl}`;
}

// Badge AKURASI. Angkanya statis, dihitung sekali di backend lawan pos hujan,
// jadi TIDAK berubah waktu slider digeser. Cuma muncul di model yang memang
// punya verifikasi. Rinciannya ditaruh di title supaya angka telanjang di
// layar tak dibaca sebagai klaim yang lebih kuat dari yang sebenarnya.
// ================= POS HUJAN (khusus WRF) =================
// Titik pengamatan yang dipakai menghitung akurasi. Digambar TETAP, tak ikut
// tombol Kondisi, supaya orang bisa melihat angka akurasi itu diuji di mana.
// Ikonnya divIcon, bukan gambar, biar tetap tajam dan sewarna tema.
let posLayer = null;

function posIcon() {
  return L.divIcon({
    className: "",
    iconSize: [18, 18], iconAnchor: [9, 9],
    // Ikon MENARA UKUR, bukan hujan atau awan. Yang ditandai di sini alatnya,
    // bukan cuacanya, jadi lambang cuaca malah rancu dengan ikon kondisi kota.
    html: '<span class="pos-mark"><span class="material-symbols-outlined">cell_tower</span></span>',
  });
}

function drawPosHujan() {
  if (posLayer) { map.removeLayer(posLayer); posLayer = null; }
  const pos = catalog?.pos_hujan;
  if (!pos || !pos.length) return;
  const a = catalog.akurasi || {};
  posLayer = L.layerGroup([], { pane: "poshujan" });
  pos.forEach((p) => {
    L.marker([p.lat, p.lon], { icon: posIcon(), pane: "poshujan", title: `Pos hujan ${p.n}` })
      .bindTooltip(
        `<b>${p.n}</b><br>Pos hujan DAS Citarum` +
        `<br><span class="mono">${p.lat.toFixed(4)}, ${p.lon.toFixed(4)}</span>` +
        (a.hari ? `<br>Dipakai verifikasi ${a.hari} hari` : ""),
        { direction: "top", offset: [0, -10], className: "pos-tip",
          pane: "poshujan-tip" })
      .addTo(posLayer);
  });
  posLayer.addTo(map);
}

function updateAkurasi() {
  const box = $("acc-badge"), el = $("acc-text");
  if (!box || !el) return;
  const a = catalog?.akurasi;
  if (!a) { box.hidden = true; return; }
  box.hidden = false;
  // Belum ada angka (mis. Private Model saat uji coba): tampil "segera",
  // nanti terisi otomatis setelah run harian penuh diverifikasi lawan METAR.
  if (a.status === "soon" || a.nilai == null) {
    el.textContent = "Akurasi : segera";
    box.title = "Akurasi otomatis lawan pengamatan METAR. Tampil setelah run harian penuh.";
    box.classList.add("acc-soon");
    return;
  }
  box.classList.remove("acc-soon");
  // Koma sebagai pemisah desimal, ikut kebiasaan Indonesia.
  const nil = a.nilai.toFixed(1).replace(".", ",");
  el.textContent = `Akurasi : ${nil}% ${a.label || ""}`.trim();

  // Rinciannya ditaruh di title, bukan di layar. Angka telanjang gampang dibaca
  // sebagai klaim yang lebih kuat dari yang sebenarnya, jadi dasarnya harus
  // selalu bisa dilihat. Dua model bentuk datanya beda, keduanya ditangani.
  const baris = [];
  if (a.catatan) baris.push(a.catatan);
  if (a.parameter) {
    baris.push("");
    for (const [nama, p] of Object.entries(a.parameter))
      baris.push(`${nama}: ${p.tepat}% dalam ${p.tol} ${p.sat}, MAE ${p.mae} ${p.sat}`);
  }
  if (a.dasar !== undefined) baris.push(`Tebakan sepele "selalu kering" dapat ${a.dasar}%.`);
  if (a.pod !== undefined) baris.push(`Tertangkap ${a.pod}% kejadian, ${a.far}% alarm palsu.`);
  if (a.pasangan) baris.push(`${a.pasangan} pasangan pengamatan.`);
  box.title = baris.join("\n");
}

let toastTimer = null;
function toast(msg) {
  const el = $("toast"); if (!el) return;
  el.textContent = msg; el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 2200);
}

// Hash saat halaman dibuka (sebelum showFrame/updateHash menimpanya) — sumber
// kebenaran untuk restore link yang dibagikan.
const INITIAL_HASH = location.hash;

// URL-hash state: layer + waktu (valid_time) + titik → link bisa dibagikan &
// kebuka persis. replaceState supaya tak menumpuk riwayat / memicu navigasi.
function updateHash() {
  if (!activeLayer) return;
  const p = new URLSearchParams();
  p.set("l", activeLayer);
  const f = frames && frames[current];
  if (f?.valid_time) p.set("t", f.valid_time);
  if (sharedPoint) {
    p.set("p", sharedPoint.lat.toFixed(4) + "," + sharedPoint.lon.toFixed(4));
    if (sharedPoint.name) p.set("n", sharedPoint.name);
  }
  if (cyclonesOn) p.set("c", "1");
  if (itczOn) p.set("z", "1");
  if (monsoonOn) p.set("m", "1");
  history.replaceState(null, "", location.pathname + location.search + "#" + p.toString());
}
function restoreFromHash() {
  const h = INITIAL_HASH.replace(/^#/, ""); if (!h || !catalog) return;
  const p = new URLSearchParams(h);
  const l = p.get("l");
  if (l && catalog.layers[l] && l !== activeLayer) {
    if (BASE_OF[l] && stratoAvailable()) {   // layer versi strato -> aktifkan level dulu
      mapLevel = "strato";
      applyLevelUI();
      syncLevelControls();
    }
    setActiveLayer(l);
  }
  const t = p.get("t");
  if (t && frames) {
    const idx = frames.findIndex((f) => f.valid_time === t);
    if (idx >= 0) { current = idx; showFrame(current); }
  }
  if (p.get("c") === "1" && !cyclonesOn) toggleCyclones();
  if (p.get("z") === "1" && !itczOn) toggleItcz();
  if (p.get("m") === "1" && !monsoonOn) toggleMonsoon();
  const pt = p.get("p");
  if (pt) {
    const [la, lo] = pt.split(",").map(parseFloat);
    if (isFinite(la) && isFinite(lo) && (!dataBounds || dataBounds.contains([la, lo]))) {
      map.setView([la, lo], 8, { animate: false });
      openPoint(la, lo, p.get("n") || null);
    }
  }
}
async function shareCurrent() {
  updateHash();
  const url = location.href;
  const data = { title: "Primeon Atmos", text: "Lihat cuaca di Primeon Atmos", url };
  try {
    if (navigator.share) { await navigator.share(data); return; }
    await navigator.clipboard.writeText(url);
    toast("Link disalin ke clipboard");
  } catch (_) { /* user batal atau clipboard diblokir */ }
}

// Layar penuh: sembunyikan semua panel kecuali brand + fullscreen browser (best-effort).
let immersive = false;
function setFsIcon() {
  const ic = document.querySelector("#fs-btn .material-symbols-outlined");
  if (ic) ic.textContent = immersive ? "fullscreen_exit" : "fullscreen";
  $("fs-btn")?.classList.toggle("active", immersive);
}
function toggleFullscreen() {
  immersive = !immersive;
  $("stage")?.classList.toggle("immersive", immersive);
  setFsIcon();
  try {
    if (immersive) document.documentElement.requestFullscreen?.();
    else if (document.fullscreenElement) document.exitFullscreen?.();
  } catch (_) { /* fullscreen API diblokir → mode sembunyi-panel tetap jalan */ }
  setTimeout(() => map.invalidateSize(), 200);
}
document.addEventListener("fullscreenchange", () => {
  if (!document.fullscreenElement && immersive) {   // keluar via ESC → sinkron
    immersive = false;
    $("stage")?.classList.remove("immersive");
    setFsIcon();
  }
  map.invalidateSize();
});

// Kartu Tentang (modal)
function openAbout() { $("about-overlay")?.classList.add("show"); }
function closeAbout() { $("about-overlay")?.classList.remove("show"); }

// ================= SEARCH KOTA/KABUPATEN =================
let places = null, placesLoading = null;
async function loadPlaces() {
  if (places) return places;
  if (!placesLoading) placesLoading = fetch(ADMIN_BASE + "id_places.json")
    .then((r) => r.json())
    .then((a) => {
      // b = nama tanpa prefix (utk cari "sleman"), f = nama penuh (lowercase).
      // tier 0=ibukota provinsi, 1=kota, 2=kabupaten → menentukan mulai zoom berapa
      // ikon kondisi kota boleh muncul (strategi anti-rame saat zoom-out).
      places = a.map((p) => {
        const tier = PROV_CAPITALS.has(p.n) ? 0 : (p.n.startsWith("Kota") ? 1 : 2);
        const minZoom = tier === 0 ? 0 : (tier === 1 ? 5.5 : 6.5);
        return { n: p.n, lat: p.lat, lon: p.lon, tier, minZoom,
          b: p.n.replace(/^(Kabupaten|Kota) /, "").toLowerCase(), f: p.n.toLowerCase() };
      });
      return places;
    });
  return placesLoading;
}
function renderSearch(q) {
  const box = $("search-results"); if (!box) return;
  q = q.trim().toLowerCase();
  if (!q || !places) { box.innerHTML = ""; return; }
  const pre = [], sub = [];
  for (const p of places) {
    if (p.b.startsWith(q) || p.f.startsWith(q)) pre.push(p);       // awalan diprioritaskan
    else if (p.b.includes(q) || p.f.includes(q)) sub.push(p);
  }
  const res = pre.concat(sub).slice(0, 12);
  box.innerHTML = res.length
    ? res.map((p) => `<div class="search-item" data-lat="${p.lat}" data-lon="${p.lon}">${p.n}</div>`).join("")
    : '<div class="search-empty">Tak ada hasil</div>';
}
function pickPlace(lat, lon, name) {
  map.setView([lat, lon], 8, { animate: true });
  openPoint(lat, lon, name);
  $("search-box")?.classList.remove("open");
}

// ================= LABEL & IKON KONDISI PER KOTA =================
// Kondisi cuaca titik dari hujan (mm/jam) + tutupan awan (%). sev = prioritas
// declutter (cuaca lebih parah menang saat berdesakan).
function cityCondition(rain, cloud) {
  if (rain >= 20) return { icon: "thunderstorm", cls: "cc-storm", sev: 5, label: "hujan sangat lebat" };
  if (rain >= 10) return { icon: "rainy_heavy", cls: "cc-heavy", sev: 4, label: "hujan lebat" };
  if (rain >= 0.5) return { icon: "rainy", cls: "cc-rain", sev: 3, label: "hujan" };
  // Model tanpa tutupan awan (WRF Citarum). Jangan mengaku "cerah", itu klaim
  // yang datanya tak ada. Cukup katakan tidak hujan.
  if (cloud === null || cloud === undefined || !isFinite(cloud))
    return { icon: "partly_cloudy_day", cls: "cc-pcloud", sev: 1, label: "tidak hujan" };
  if (cloud >= 85) return { icon: "cloud", cls: "cc-cloud", sev: 2, label: "berawan tebal" };
  if (cloud >= 40) return { icon: "partly_cloudy_day", cls: "cc-pcloud", sev: 1, label: "cerah berawan" };
  return { icon: "sunny", cls: "cc-sunny", sev: 0, label: "cerah" };
}

// Index waktu point_data terdekat dengan frame yang sedang ditampilkan.
const currentTimeIndex = (pd) => timeIndexOf(pd.meta.times);
function timeIndexOf(times) {
  const vt = frames[current] && frames[current].valid_time;
  if (!vt) return 0;
  const target = new Date(vt).getTime();
  let bi = 0, bd = Infinity;
  for (let i = 0; i < times.length; i++) {
    const d = Math.abs(new Date(times[i]).getTime() - target);
    if (d < bd) { bd = d; bi = i; }
  }
  return bi;
}

// Tempatkan ikon kota: filter tier×zoom + dalam layar, urut prioritas, lalu
// GREEDY anti-tabrakan piksel → hanya yang tak overlap yang digambar. Efeknya
// zoom-out = ibukota provinsi saja; makin zoom-in makin banyak kota/kabupaten.
// ---- Sumber nilai label kota ----
// SENGAJA bukan point_data.bin.gz. Berkas itu 21 MB (seluruh grid 473x265), padahal
// label cuma butuh 514 titik. city_data.json sudah disampel di backend: ~100 KB
// terkirim. point_data tetap ada, tapi kembali malas: baru diunduh saat pengguna
// mengklik peta atau membuka Skew-T.
let cityData = null, cityDataLoading = null, cityIndexByName = null;
function loadCityData() {
  if (cityData) return Promise.resolve(cityData);
  if (!cityDataLoading) {
    cityDataLoading = fetch(DATA_BASE + "city_data.json")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d) {
          cityIndexByName = new Map(d.places.map((n, i) => [n, i]));
          cityData = d;
        }
        return cityData;
      })
      .catch(() => null);
  }
  return cityDataLoading;
}
// Satu nilai, sudah dikembalikan ke satuan aslinya.
function cityRaw(key, i, ti) {
  const a = cityData && cityData.data[key];
  if (!a || !a[i] || a[i][ti] === undefined) return NaN;
  return a[i][ti] * cityData.scales[key];
}

// Satuan per parameter untuk label kota. Pakai SIMBOL, bukan kata.
// Derajat & persen menempel ke angka, sisanya diberi spasi (31°C, 88%, 12 kt).
const CITY_UNIT = {
  wind_surface: { u: "kt", d: 0 },
  rain_surface: { u: "mm", d: 1 },
  rain_accum_surface: { u: "mm", d: 0 },
  temp_surface: { u: "\u00b0C", d: 0 },
  humidity_surface: { u: "%", d: 0 },
  cloud_surface: { u: "%", d: 0 },
  pressure_surface: { u: "hPa", d: 0 },
  storm_potential: { u: "J/kg", d: 0 },
  cin_surface: { u: "J/kg", d: 0 },
};
const CITY_VAR = { wind_surface: "wind", rain_surface: "rain", temp_surface: "temp",
                   humidity_surface: "humidity", cloud_surface: "cloud",
                   pressure_surface: "pressure", storm_potential: "cape",
                   cin_surface: "cin" };

// Nilai parameter aktif di satu kota. Rumusnya SENGAJA disamakan dengan chartSeries
// supaya angka di label dan angka di grafik panel titik tak pernah berbeda.
function cityValueText(i, ti) {
  if (BASE_OF[activeLayer]) return "";        // level strato: data titik hanya permukaan
  const s = CITY_UNIT[activeLayer];
  if (!s || !cityData) return "";
  let v;
  if (activeLayer === "rain_accum_surface") {
    const d = cityData.times[ti].slice(0, 10);   // total sepanjang TANGGAL frame aktif
    v = 0;
    cityData.times.forEach((t, k) => { if (t.slice(0, 10) === d) v += cityRaw("rain", i, k) * STEP_JAM; });
  } else {
    v = cityRaw(CITY_VAR[activeLayer], i, ti);
  }
  if (!isFinite(v)) return "";
  // Hujan per jam angkanya kecil, jadi 1 desimal. Tapi "0.0 mm" di seluruh peta
  // cuma jadi sampah visual, dan di atas 10 mm desimalnya tak berguna.
  const dec = (activeLayer === "rain_surface" && (v < 0.05 || v >= 10)) ? 0 : s.d;
  const sep = (s.u === "\u00b0C" || s.u === "%") ? "" : " ";
  return v.toFixed(dec) + sep + s.u;
}

// Nama untuk DI PETA saja, biar label pendek. Judul panel titik & tooltip tetap
// memakai nama lengkap.
//
// Awalan "Kabupaten"/"Kota" dibuang, TAPI "Kota" dipertahankan kalau ada kabupaten
// bernama sama. Tanpa ini "Kota Bandung" dan "Kabupaten Bandung" sama sama jadi
// "Bandung", padahal wilayah dan angkanya berbeda. Ada 26 pasangan seperti itu.
let cityDupNames = null;
const cityBaseName = (n) => n.replace(/^(Kabupaten|Kota)(\s+Administrasi)?\s+/, "");
function buildCityDupNames(places) {
  if (cityDupNames) return;
  const hitung = {};
  for (const p of places) { const b = cityBaseName(p.n); hitung[b] = (hitung[b] || 0) + 1; }
  cityDupNames = new Set(Object.keys(hitung).filter((k) => hitung[k] > 1));
}
function cityShortName(n) {
  const base = cityBaseName(n);
  return (/^Kota\b/.test(n) && cityDupNames && cityDupNames.has(base)) ? "Kota " + base : base;
}
const escHtml = (t) => String(t).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

async function refreshCityIcons() {
  if (!cityGroup) return;
  let cd, pl;
  try { cd = await loadCityData(); pl = await loadPlaces(); }
  catch (e) { console.warn("Label kota gagal dimuat:", e); return; }
  if (!cityGroup || !cd) return;   // bisa dibongkar selama await
  buildCityDupNames(pl);
  const ti = timeIndexOf(cd.times);
  const z = map.getZoom(), b = map.getBounds();
  const cands = [];
  for (const p of pl) {
    if (z < p.minZoom || !b.contains([p.lat, p.lon])) continue;
    const i = cityIndexByName.get(p.n);
    if (i === undefined) continue;   // daftar tempat & city_data tak sinkron
    cands.push({ p, cond: cityCondition(cityRaw("rain", i, ti), cityRaw("cloud", i, ti)),
                 val: cityValueText(i, ti) });
  }
  cands.sort((a, c) => a.p.tier - c.p.tier || c.cond.sev - a.cond.sev);
  cityGroup.clearLayers();
  // Kotak anti-tabrakan LEBIH LEBAR dari ikon, karena ada nama + nilai di bawahnya.
  // Kalau tetap 32px, labelnya saling tindih dan tak terbaca. Tanpa ikon, tumpukannya
  // lebih pendek jadi jarak tegaknya boleh lebih rapat.
  const placed = [], RX = 68, RY = cityIconsOn ? 44 : 34;
  for (const c of cands) {
    const pt = map.latLngToContainerPoint([c.p.lat, c.p.lon]);
    let ok = true;
    for (let i = 0; i < placed.length; i++)
      if (Math.abs(pt.x - placed[i].x) < RX && Math.abs(pt.y - placed[i].y) < RY) { ok = false; break; }
    if (!ok) continue;
    placed.push(pt);
    const ico = cityIconsOn
      ? `<span class="cc-ico ${c.cond.cls}${c.p.tier === 0 ? " cc-cap" : ""}">` +
        `<span class="material-symbols-outlined">${c.cond.icon}</span></span>`
      : "";
    const m = L.marker([c.p.lat, c.p.lon], {
      pane: "cityicons", title: c.p.n, keyboard: false,
      icon: L.divIcon({ className: "city-cond" + (cityIconsOn ? "" : " no-ico"),
        iconSize: [30, 30], iconAnchor: [15, 15],
        html: ico + `<span class="cc-lbl"><b>${escHtml(cityShortName(c.p.n))}</b>` +
              (c.val ? `<i>${escHtml(c.val)}</i>` : "") + `</span>` }),
    });
    m.on("click", (e) => { L.DomEvent.stopPropagation(e); openPoint(c.p.lat, c.p.lon, c.p.n); });
    cityGroup.addLayer(m);
  }
  cityPlacedPts = placed;
  refreshGeoLabels();   // nama negara/laut ditata ULANG supaya menghindari label kota
}

// Legenda kecil kategori ikon (cermin cityCondition) — dibangun sekali.
const COND_LEGEND = [
  { icon: "sunny", cls: "cc-sunny", label: "Cerah" },
  { icon: "partly_cloudy_day", cls: "cc-pcloud", label: "Berawan" },
  { icon: "cloud", cls: "cc-cloud", label: "Mendung" },
  { icon: "rainy", cls: "cc-rain", label: "Hujan" },
  { icon: "rainy_heavy", cls: "cc-heavy", label: "Lebat" },
  { icon: "thunderstorm", cls: "cc-storm", label: "Sangat lebat" },
];
function buildCondLegend() {
  const el = $("cond-legend");
  if (!el || el.dataset.built) return;
  el.innerHTML = '<div class="cl-head mono">KONDISI</div><div class="cl-grid">' +
    COND_LEGEND.map((c) =>
      `<div class="cl-item"><span class="cc-ico cc-mini ${c.cls}">` +
      `<span class="material-symbols-outlined">${c.icon}</span></span>` +
      `<span class="cl-lbl">${c.label}</span></div>`).join("") +
    "</div>";
  el.dataset.built = "1";
}

// Tombol "Kondisi" kini HANYA menyalakan ikon cuaca + legendanya. Label nama & nilai
// tak ikut mati, karena itu informasi parameter yang sedang dipilih, bukan kondisi.
// Sembunyikan/tampilkan panel Parameter + Model. Brand sengaja TETAP terlihat,
// jadi identitas dan tombol Tentang tak ikut hilang.
function togglePanels() {
  const col = document.querySelector("#ui .col:not(.items-end)");
  const btn = $("panel-toggle");
  if (!col || !btn) return;
  const tutup = col.classList.toggle("panels-hidden");
  const ic = btn.querySelector(".material-symbols-outlined");
  if (ic) ic.textContent = tutup ? "chevron_right" : "chevron_left";
  const label = tutup ? "Tampilkan panel" : "Sembunyikan panel";
  btn.setAttribute("aria-label", label);
  btn.title = label;
}

function toggleCityIcons() {
  cityIconsOn = !cityIconsOn;
  $("city-toggle") && $("city-toggle").classList.toggle("active", cityIconsOn);
  const cl = $("cond-legend");
  if (cityIconsOn) { buildCondLegend(); if (cl) cl.classList.add("show"); }
  else if (cl) cl.classList.remove("show");
  refreshCityIcons();
}

// Label kota selalu ada sejak peta dibuka. point_data dimuat di latar, jadi peta
// tetap bisa dipakai selagi berkasnya turun; labelnya menyusul saat sudah siap.
function initCityLabels() {
  if (!cityGroup) cityGroup = L.layerGroup([], { pane: "cityicons" });
  cityGroup.addTo(map);
  refreshCityIcons();
}

// ================= SIKLON (indikasi model GFS) =================
async function loadCyclones() {
  if (cyclones) return cyclones;
  if (!cyclonesLoading) cyclonesLoading = fetch(DATA_BASE + "cyclones.json")
    .then((r) => (r.ok ? r.json() : { tracks: [] }))
    .then((j) => (cyclones = j))
    .catch(() => (cyclones = { tracks: [] }));
  return cyclonesLoading;
}
// Warna ikut TINGKAT: Siklon Lintang Tinggi (UNGU), Siklon Tropis (MERAH),
// Bibit Siklon (ORANYE), Sirkulasi Siklonik (HIJAU TUA). Kunci legenda identifikasi.
function cycloneColor(tier, cat) {
  // Triad Bauhaus: merah untuk bahaya, biru untuk perairan dan keadaan
  // interaktif, kuning untuk peringatan sekunder. Tanpa warna dekoratif.
  if (tier === "CIRC") return "#485f84";              // Sirkulasi Siklonik, paling lemah
  if (tier === "EXTRA") return "#5b403f";             // Siklon Lintang Tinggi
  if (tier === "SEED") return "#e0a500";              // Bibit Siklon, peringatan
  return cat >= 3 ? "#7d0a1c" : "#b7102a";            // Siklon Tropis, merah utama
}
function refreshCyclones() {
  if (!cycloneGroup) return;
  cycloneGroup.clearLayers();
  if (!cyclonesOn || !cyclones || !frames[current]) return;
  const nowT = frames[current].valid_time;
  for (const tr of cyclones.tracks) {
    // Hanya sistem yang ADA di waktu aktif → jalur selalu ada ikon siklonnya
    // (buang bug garis nyasar dari sistem yang baru terbentuk di jam lain).
    const cur = tr.points.find((p) => p.t === nowT);
    if (!cur) continue;
    const color = cycloneColor(tr.tier, tr.peak_cat);
    const sz = (tr.tier === "TC" || tr.tier === "EXTRA") ? 36 : tr.tier === "SEED" ? 30 : 26;
    const past = [], future = [];
    for (const p of tr.points) (p.t < nowT ? past : future).push([p.lat, p.lon]);
    if (past.length && future.length) future.unshift(past[past.length - 1]); // sambung
    if (past.length > 1)
      L.polyline(past, { pane: "cyclonepath", color, weight: 2, opacity: 0.3, dashArray: "3 5", interactive: false }).addTo(cycloneGroup);
    if (future.length > 1)
      L.polyline(future, { pane: "cyclonepath", color, weight: 3, opacity: 0.9, interactive: false }).addTo(cycloneGroup);
    for (const p of tr.points) {
      if (p.t < nowT) continue;       // titik prakiraan ke depan
      L.circleMarker([p.lat, p.lon], { pane: "cyclonepath", radius: 2.5, weight: 0,
        fillColor: color, fillOpacity: 0.9, interactive: false }).addTo(cycloneGroup);
    }
    const m = L.marker([cur.lat, cur.lon], {
      pane: "cyclones", keyboard: false,
      title: `${tr.name} · ${cur.label} · ${cur.wind_kt} kt · ${cur.mslp} hPa`,
      icon: L.divIcon({ className: "cyc-mark", iconSize: [sz, sz], iconAnchor: [sz / 2, sz / 2],
        html: `<span class="cyc-spin" style="color:${color};font-size:${sz - 4}px"><span class="material-symbols-outlined" style="font-size:${sz - 4}px">cyclone</span></span>` }),
    });
    m.on("click", (e) => { L.DomEvent.stopPropagation(e); openPoint(cur.lat, cur.lon, tr.name); });
    cycloneGroup.addLayer(m);
  }
}
function toggleCyclones() {
  cyclonesOn = !cyclonesOn;
  $("cyclone-toggle") && $("cyclone-toggle").classList.toggle("active", cyclonesOn);
  const note = $("cyc-note");
  if (cyclonesOn) {
    if (!cycloneGroup) cycloneGroup = L.layerGroup([], { pane: "cyclones" });
    cycloneGroup.addTo(map);
    if (note) note.classList.add("show");
    loadCyclones().then(() => { if (cyclonesOn) refreshCyclones(); });
  } else {
    if (cycloneGroup) { cycloneGroup.clearLayers(); map.removeLayer(cycloneGroup); }
    if (note) note.classList.remove("show", "open");
  }
  updateHash();
}

// ================= ZONA ITCZ (indikasi model GFS) =================
// Sabuk pertemuan angin pasat dua belahan bumi → banyak awan & hujan. Digambar
// sebagai PITA zona (konvergensi kuat) + GARIS sumbu. Hanya untuk jam prakiraan
// run aktif (0..72 jam); waktu lampau tak punya data (konsisten dgn siklon).
const ITCZ_COLOR = "#ff2ea6";   // magenta terang — kontras di semua warna heatmap
async function loadItcz() {
  if (itcz) return itcz;
  if (!itczLoading) itczLoading = fetch(DATA_BASE + "itcz.json")
    .then((r) => (r.ok ? r.json() : { times: [], frames: [] }))
    .then((j) => (itcz = j))
    .catch(() => (itcz = { times: [], frames: [] }));
  return itczLoading;
}
function refreshItcz() {
  if (!itczGroup) return;
  itczGroup.clearLayers();
  if (!itczOn || !itcz || !itcz.times || !frames[current]) return;
  const ti = itcz.times.indexOf(frames[current].valid_time);
  if (ti < 0) return;                         // waktu lampau → tak ada garis
  for (const sg of itcz.frames[ti] || []) {
    if (sg.length < 2) continue;
    // Pita zona: tepi utara (maju) + tepi selatan (mundur) → poligon terisi.
    const ring = [];
    for (const p of sg) ring.push([p[2], p[0]]);                // [latN, lon]
    for (let i = sg.length - 1; i >= 0; i--) ring.push([sg[i][3], sg[i][0]]); // [latS, lon]
    L.polygon(ring, { pane: "itcz", color: ITCZ_COLOR, weight: 1, opacity: 0.35,
      fillColor: ITCZ_COLOR, fillOpacity: 0.2, interactive: false }).addTo(itczGroup);
    // Garis sumbu: casing putih (kontras di latar gelap/terang) + garis teal putus.
    const axis = sg.map((p) => [p[1], p[0]]);
    L.polyline(axis, { pane: "itcz", color: "#ffffff", weight: 6, opacity: 0.35,
      interactive: false, lineCap: "round", lineJoin: "round" }).addTo(itczGroup);
    L.polyline(axis, { pane: "itcz", color: ITCZ_COLOR, weight: 3, opacity: 0.95,
      dashArray: "7 5", interactive: false, lineCap: "round", lineJoin: "round" }).addTo(itczGroup);
  }
}
function toggleItcz() {
  itczOn = !itczOn;
  $("itcz-toggle") && $("itcz-toggle").classList.toggle("active", itczOn);
  const note = $("itcz-note");
  if (itczOn) {
    if (!itczGroup) itczGroup = L.layerGroup([], { pane: "itcz" });
    itczGroup.addTo(map);
    if (note) note.classList.add("show");
    loadItcz().then(() => { if (itczOn) refreshItcz(); });
  } else {
    if (itczGroup) { itczGroup.clearLayers(); map.removeLayer(itczGroup); }
    if (note) note.classList.remove("show", "open");
  }
  updateHash();
}

// ================= ISOBAR (garis tekanan) =================
// Otomatis muncul HANYA di layer Tekanan (tanpa tombol): garis kontur PRMSL
// tiap 4 hPa + penanda pusat tekanan Tinggi (H) / Rendah (L). Melengkapi heatmap
// jadi peta tekanan gaya klasik. Hanya jam prakiraan run aktif (0..72 jam).
// Warna isobar MENGIKUTI palet tekanan (dari legenda) pada nilai hPa garis itu,
// lalu digelapkan ("lebih tua") agar kontras; dipadu halo putih supaya terbaca
// di zona terang (~1013) maupun gelap (biru/oranye).
const _PRESS_STOPS = LEGENDS.pressure_surface.cells.map(([lab, hex]) => [parseFloat(lab), hex]);
const _hex2rgb = (h) => { h = h.replace("#", ""); return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)]; };
const _rgb2hex = (r, g, b) => "#" + [r, g, b].map((x) => Math.max(0, Math.min(255, Math.round(x))).toString(16).padStart(2, "0")).join("");
function _rgb2hsl(r, g, b) {
  r /= 255; g /= 255; b /= 255;
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn;
  let h = 0; const l = (mx + mn) / 2;
  const s = d === 0 ? 0 : d / (1 - Math.abs(2 * l - 1));
  if (d !== 0) {
    if (mx === r) h = ((g - b) / d) % 6;
    else if (mx === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
    h *= 60; if (h < 0) h += 360;
  }
  return [h, s, l];
}
function _hsl2rgb(h, s, l) {
  const c = (1 - Math.abs(2 * l - 1)) * s, x = c * (1 - Math.abs(((h / 60) % 2) - 1)), m = l - c / 2;
  let r = 0, g = 0, b = 0;
  if (h < 60) [r, g] = [c, x]; else if (h < 120) [r, g] = [x, c];
  else if (h < 180) [g, b] = [c, x]; else if (h < 240) [g, b] = [x, c];
  else if (h < 300) [r, b] = [x, c]; else [r, b] = [c, x];
  return [(r + m) * 255, (g + m) * 255, (b + m) * 255];
}
// Warna isobar: ambil HUE dari palet tekanan pd nilai hPa garis, tapi paksa
// saturasi cukup & kecerahan medium (0.40) → jelas berwarna spt palet, "lebih
// tua" tanpa jadi hitam; zona pucat (~1013) pun tampil sbg warna, bukan abu.
function isobarColor(hPa) {
  const s = _PRESS_STOPS;
  let a = s[0], b = s[s.length - 1];
  if (hPa <= s[0][0]) b = a = s[0];
  else if (hPa >= s[s.length - 1][0]) a = b = s[s.length - 1];
  else for (let i = 0; i < s.length - 1; i++) if (hPa >= s[i][0] && hPa <= s[i + 1][0]) { a = s[i]; b = s[i + 1]; break; }
  const t = b[0] === a[0] ? 0 : (hPa - a[0]) / (b[0] - a[0]);
  const ca = _hex2rgb(a[1]), cb = _hex2rgb(b[1]);
  const rgb = [0, 1, 2].map((k) => ca[k] + (cb[k] - ca[k]) * t);
  const [h, sat] = _rgb2hsl(rgb[0], rgb[1], rgb[2]);
  const [r, g, bl] = _hsl2rgb(h, Math.min(0.9, Math.max(0.55, sat * 1.25)), 0.4);
  return _rgb2hex(r, g, bl);
}
async function loadIsobars() {
  if (isobars) return isobars;
  if (!isobarsLoading) isobarsLoading = fetch(DATA_BASE + "isobars.json")
    .then((r) => (r.ok ? r.json() : { times: [], frames: [] }))
    .then((j) => (isobars = j))
    .catch(() => (isobars = { times: [], frames: [] }));
  return isobarsLoading;
}
function refreshIsobars() {
  if (!isobarGroup) return;
  isobarGroup.clearLayers();
  if (activeLayer !== "pressure_surface" || !isobars || !isobars.times || !frames[current]) return;
  const ti = isobars.times.indexOf(frames[current].valid_time);
  if (ti < 0) return;                         // waktu lampau → tak ada isobar
  const fr = isobars.frames[ti];
  if (!fr) return;
  for (const [lv, pts] of fr.iso) {
    const latlng = pts.map((p) => [p[1], p[0]]);
    const bold = lv % 20 === 0;               // pertegas tiap 20 hPa (gaya peta cuaca)
    // Inti = warna palet tekanan (digelapkan) pada nilai hPa garis + HALO PUTIH.
    // Border admin diredupkan (abu) supaya isobar jadi garis dominan.
    L.polyline(latlng, { pane: "isobar", color: "#ffffff", weight: bold ? 4 : 3,
      opacity: 0.6, interactive: false, lineJoin: "round" }).addTo(isobarGroup);
    L.polyline(latlng, { pane: "isobar", color: isobarColor(lv), weight: bold ? 2.2 : 1.4,
      opacity: 0.97, interactive: false, lineJoin: "round" }).addTo(isobarGroup);
  }
  for (const [t, v, lat, lon] of fr.hl) {
    const high = t === 1;
    isobarGroup.addLayer(L.marker([lat, lon], {
      pane: "isobar", interactive: false, keyboard: false,
      icon: L.divIcon({ className: "hl-wrap", iconSize: [44, 44], iconAnchor: [22, 22],
        html: `<span class="hl-mark ${high ? "hl-h" : "hl-l"}">${high ? "H" : "L"}<b>${v}</b></span>` }),
    }));
  }
}
// Tampilkan/lepas isobar sesuai layer aktif (dipanggil saat ganti layer).
function syncIsobars() {
  if (activeLayer === "pressure_surface") {
    if (!isobarGroup) isobarGroup = L.layerGroup([], { pane: "isobar" });
    if (!map.hasLayer(isobarGroup)) isobarGroup.addTo(map);
    loadIsobars().then(() => { if (activeLayer === "pressure_surface") refreshIsobars(); });
  } else if (isobarGroup) {
    isobarGroup.clearLayers();
    if (map.hasLayer(isobarGroup)) map.removeLayer(isobarGroup);
  }
}

// ================= MONSUN (indikasi model GFS) =================
// Status monsun (badge) + ARUS AMBER beranimasi = angin rata-rata musiman lewat
// leaflet-velocity (warna amber, partikel lebih tebal & jarang → beda dari angin
// putih sesaat). Medan rata-rata bersifat statik (tak ikut slider).
async function loadMonsoon() {
  if (monsoon) return monsoon;
  if (!monsoonLoading) monsoonLoading = fetch(DATA_BASE + "monsoon.json")
    .then((r) => (r.ok ? r.json() : { phase: null }))
    .then((j) => (monsoon = j))
    .catch(() => (monsoon = { phase: null }));
  return monsoonLoading;
}
// Warna arus & banner mengikuti MONSUN DOMINAN (dari data): Australia=amber,
// Asia=biru, Peralihan=hijau. Gradasi satu rona → partikel jelas berwarna.
const MON_AMBER = ["#ffe0a3", "#ffc760", "#ffb020", "#f59e0b", "#e07b00"];
const MON_BLUE = ["#a9c6f5", "#6f9ae6", "#3f6fce", "#2650a8", "#173b7d"];
const MON_GREEN = ["#c3e8ae", "#8fd06b", "#5cb63f", "#3f9330", "#2c6f24"];
function monColors(code) {
  if (code === "ASIA") return { scale: MON_BLUE, banner: "#1e3f8f" };
  if (code === "TRANS") return { scale: MON_GREEN, banner: "#1a7a4f" };
  return { scale: MON_AMBER, banner: "#b26a00" };        // AUS (default)
}
async function loadMonsoonVel() {
  if (monsoonVelData) return monsoonVelData;
  if (!monsoonVelLoading) monsoonVelLoading = fetch(DATA_BASE + "monsoon_velocity.json")
    .then((r) => (r.ok ? r.json() : null))
    .then((j) => (monsoonVelData = j))
    .catch(() => (monsoonVelData = null));
  return monsoonVelLoading;
}
async function loadBorneoVel() {
  if (borneoVelData) return borneoVelData;
  if (!borneoVelLoading) borneoVelLoading = fetch(DATA_BASE + "monsoon_velocity_bv.json")
    .then((r) => (r.ok ? r.json() : null))
    .then((j) => (borneoVelData = j))
    .catch(() => (borneoVelData = null));
  return borneoVelLoading;
}
// Borneo Vortex: swirl partikel TEAL (medan angin kotak Kalimantan → berpilin sendiri)
// + ikon pusaran di pusat. HANYA saat vorteks terdeteksi (musim DJF).
function showBorneoVortex(vx) {
  if (!vx || !vx.active) return;
  loadBorneoVel().then((bv) => {
    if (!monsoonOn || !bv) return;
    if (!borneoVel) borneoVel = L.velocityLayer({
      displayValues: false, data: bv,
      minVelocity: 0, maxVelocity: 12, velocityScale: 0.025,
      particleAge: 110, particleMultiplier: 1 / 300, lineWidth: 2.2,
      colorScale: ["#7fe6df", "#2fd0c6", "#0fb5ae", "#0a8f89", "#076d68"], frameRate: 24,
    });
    if (!map.hasLayer(borneoVel)) borneoVel.addTo(map);
    if (!borneoMarker && vx.lat != null) borneoMarker = L.marker([vx.lat, vx.lon], {
      interactive: false, keyboard: false, title: "Borneo Vortex",
      icon: L.divIcon({ className: "bv-mark", iconSize: [40, 40], iconAnchor: [20, 20],
        html: `<span class="cyc-spin" style="color:#0fb5ae;font-size:34px"><span class="material-symbols-outlined" style="font-size:34px">cyclone</span></span>` }),
    });
    if (borneoMarker && !map.hasLayer(borneoMarker)) borneoMarker.addTo(map);
  });
}
function hideBorneoVortex() {
  if (borneoVel && map.hasLayer(borneoVel)) map.removeLayer(borneoVel);
  if (borneoMarker && map.hasLayer(borneoMarker)) map.removeLayer(borneoMarker);
}
// Panel FENOMENA: daftar semua fenomena + status. Dot HIJAU NEON = sedang terjadi,
// MERAH = belum; baris tak-aktif diredupkan (kelas ph-off).
function fillPhenomPanel() {
  const el = $("phenom-panel");
  if (!el || !monsoon) return;
  const p = monsoon.phase || {};
  const s = monsoon.surge || {};
  const vx = monsoon.vortex || {};
  const konst = p.steadiness != null ? Math.round(p.steadiness * 100) + "%" : "-";
  // Dot AKTIF ikut warna arus/velocity fenomena; BELUM terjadi = merah menyala.
  const MON_DOT = { AUS: "#ffb020", ASIA: "#3f6fce", TRANS: "#5cb63f" };
  const SURGE_DOT = "#3f6fce", BV_DOT = "#0fb5ae", OFF = "#ff2d2d";
  const row = (active, color, name, status) => {
    const c = active ? color : OFF;
    return `<div class="ph-row ${active ? "" : "ph-off"}">` +
      `<span class="ph-dot" style="background:${c};box-shadow:0 0 6px 1px ${c}"></span>` +
      `<div class="ph-txt"><b>${name}</b><span>${status}</span></div></div>`;
  };
  el.innerHTML = `<div class="ph-head">FENOMENA</div>` +
    row(true, MON_DOT[p.code] || "#ffb020", "Monsun", `${p.label || "-"}${p.season ? " · " + p.season : ""}. Angin dari ${p.wind_from || "-"}, konsistensi ${konst}.`) +
    row(!!s.active, SURGE_DOT, "<i>Cold Surge</i>", s.active ? `${s.level}, angin utara ${s.north_kt || 0} kt. ${s.note}` : "Belum terjadi (fenomena musim hujan / DJF).") +
    row(!!vx.active, BV_DOT, "<i>Borneo Vortex</i>", vx.active ? `Vortisitas ${vx.vort}. ${vx.note}` : "Belum terjadi (fenomena musim hujan / DJF).");
}
// Terapkan keadaan tiga fenomena. Dipanggil tombol HP (satu satu) maupun
// tombol desktop #mon-toggle (ketiganya sekaligus). Cold Surge sengaja tak
// punya lapisan peta, karena BMKG-pun tak menggambarnya; yang ada cuma status,
// jadi tombolnya hanya memunculkan barisnya di kotak keterangan.
function terapkanFenomena() {
  const adaYangNyala = fenOn.monsun || fenOn.bv || fenOn.surge;
  monsoonOn = adaYangNyala;
  $("mon-toggle")?.classList.toggle("active", adaYangNyala);
  document.querySelectorAll("#lowbar-body .lb-btn[data-fen]").forEach((b) =>
    b.classList.toggle("active", !!fenOn[b.dataset.fen]));

  const panel = $("phenom-panel");
  if (!adaYangNyala) {
    if (monsoonVel && map.hasLayer(monsoonVel)) map.removeLayer(monsoonVel);
    hideBorneoVortex();
    panel?.classList.remove("show");
    updateHash();
    return;
  }
  Promise.all([loadMonsoon(), fenOn.monsun ? loadMonsoonVel() : null]).then(([mon, data]) => {
    segarkanTombolFenomena();
    fillPhenomPanel();
    panel?.classList.add("show");

    if (fenOn.bv) showBorneoVortex(mon && mon.vortex); else hideBorneoVortex();

    if (fenOn.monsun && data) {
      const code = mon && mon.phase ? mon.phase.code : "AUS";
      if (!monsoonVel) {
        monsoonVel = L.velocityLayer({
          displayValues: false, data,
          minVelocity: 0, maxVelocity: 14, velocityScale: 0.02,
          particleAge: 120, particleMultiplier: 1 / 500, lineWidth: 2.4,
          colorScale: monColors(code).scale, frameRate: 22,
        });
        monsoonVel.addTo(map);
      } else if (!map.hasLayer(monsoonVel)) {
        monsoonVel.addTo(map);
      }
    } else if (monsoonVel && map.hasLayer(monsoonVel)) {
      map.removeLayer(monsoonVel);
    }
  });
  updateHash();
}

function toggleMonsoon() {
  // Tombol desktop: satu klik menyalakan/mematikan KETIGANYA, perilaku lama.
  const nyala = !(fenOn.monsun || fenOn.bv || fenOn.surge);
  fenOn = { monsun: nyala, bv: nyala, surge: nyala };
  terapkanFenomena();
}

function toggleMonsoonLama() {
  monsoonOn = !monsoonOn;
  $("mon-toggle") && $("mon-toggle").classList.toggle("active", monsoonOn);
  const panel = $("phenom-panel");
  if (monsoonOn) {
    Promise.all([loadMonsoon(), loadMonsoonVel()]).then(([mon, data]) => {
      if (!monsoonOn) return;
      fillPhenomPanel();
      if (panel) panel.classList.add("show");
      showBorneoVortex(mon && mon.vortex);
      if (data) {
        const code = mon && mon.phase ? mon.phase.code : "AUS";
        if (!monsoonVel) {
          monsoonVel = L.velocityLayer({
            displayValues: false, data,
            minVelocity: 0, maxVelocity: 14, velocityScale: 0.02,
            particleAge: 120, particleMultiplier: 1 / 500, lineWidth: 2.4,
            colorScale: monColors(code).scale, frameRate: 22,
          });
          monsoonVel.addTo(map);
        } else if (!map.hasLayer(monsoonVel)) {
          monsoonVel.addTo(map);
        }
      }
    });
  } else {
    if (monsoonVel && map.hasLayer(monsoonVel)) map.removeLayer(monsoonVel);
    hideBorneoVortex();
    if (panel) panel.classList.remove("show");
  }
  updateHash();
}

// ---- Skeleton loading ---------------------------------------------------
function hideSkeleton() {
  const s = $("skeleton");
  if (!s || s.classList.contains("hide")) return;
  s.classList.add("hide");                 // fade-out (transition CSS)
  setTimeout(() => s.remove(), 480);
}
// Tampilkan pesan (error/diagnosa) di kotak #loading & lepas skeleton.
function showLoadMsg(msg, asHtml) {
  const el = $("loading");
  if (el) { el[asHtml ? "innerHTML" : "textContent"] = msg; el.style.display = "block"; }
  hideSkeleton();
}
// Tunggu frame heatmap PERTAMA benar-benar tergambar sebelum skeleton dilepas,
// biar reveal-nya mulus (bukan peta kosong sekejap). Ada fallback timeout.
function whenHeatmapReady() {
  return new Promise((resolve) => {
    const img = speedLayer && speedLayer.getElement();
    if (!img || img.complete) return resolve();
    let done = false;
    const fin = () => { if (!done) { done = true; resolve(); } };
    img.addEventListener("load", fin, { once: true });
    img.addEventListener("error", fin, { once: true });
    setTimeout(fin, 1600);
  });
}

// ---- Init --------------------------------------------------------------
async function init() {
  // Diagnosa dini penyebab umum gagal-muat
  if (location.protocol === "file:") {
    showLoadMsg(
      "⚠️ Halaman dibuka via <b>file://</b> — browser memblokir pemuatan data.<br><br>" +
      "Buka lewat alamat server:<br><b>http://127.0.0.1:8000/frontend/index.html</b>", true);
    return;
  }
  if (typeof L === "undefined" || typeof L.velocityLayer !== "function") {
    showLoadMsg("⚠️ Library peta gagal dimuat (cek koneksi internet ke unpkg.com / CDN diblokir).");
    return;
  }
  // Dibuka langsung lewat ?model=wrf juga harus lewat gerbang, kalau tidak
  // penguncian di dropdown gampang dilewati cuma dengan mengetik alamatnya.
  if (MODEL_ID !== "gfs" && !ambilTiket()) {
    const boleh = await mintaSandi(MODEL.label);
    if (!boleh) { location.replace(location.pathname); return; }
  }
  try {
    const catRes = await fetch(DATA_BASE + "catalog.json");
    if (!catRes.ok) throw new Error(`catalog.json HTTP ${catRes.status} (${DATA_BASE}catalog.json)`);
    const cat = await catRes.json();
    catalog = cat;
    const avail = Object.keys(cat.layers || {});
    // Cadence sebenarnya, dari layer non-harian pertama yang punya >= 2 frame.
    for (const k of avail) {
      if (DAILY_LAYERS.has(k)) continue;
      const fr = cat.layers[k].frames;
      if (fr && fr.length > 1) { hitungStepJam(fr.map((f) => f.valid_time)); break; }
    }
    if (!avail.length) throw new Error("catalog.json tidak punya layer");
    activeLayer = cat.layers["wind_surface"] ? "wind_surface" : avail[0];
    frames = cat.layers[activeLayer].frames;

    // Tiga kotak yang beda peran, jangan tertukar.
    //   bounds        domain data model (pusat sel). Dipakai panel titik.
    //   image_bounds  tepi sel, tempat heatmap ditempel. Kalau tak ada, pakai bounds.
    //   frame_bounds  kotak untuk bingkai, minZoom, dan kunci pan.
    // WRF domainnya cuma sekitar Jawa. Kalau bingkainya ikut domain itu, peta
    // melompat ke Jawa saat ganti model. Sementara ini frame_bounds-nya sengaja
    // diisi domain GFS supaya tampilannya tak berubah, WRF jadi tempelan kecil
    // di dalamnya. Nanti disesuaikan bareng user.
    const [dw, ds, de, dn] = cat.region.bounds;
    const [iw, is_, ie, iN] = cat.region.image_bounds || cat.region.bounds;
    const [fw, fs, fe, fn] = cat.region.frame_bounds || cat.region.bounds;
    dataBounds = L.latLngBounds([fs, fw], [fn, fe]);
    imageBounds = L.latLngBounds([is_, iw], [iN, ie]);
    if (cat.region.view_core) {
      const [vw, vs, ve, vn] = cat.region.view_core;
      VIEW_CORE = L.latLngBounds([vs, vw], [vn, ve]);
    }

    // Wire tombol layer: klik memilih varian sesuai LEVEL aktif (permukaan/strato).
    // Tombol tanpa data (atau diredupkan oleh level) diabaikan saat diklik.
    document.querySelectorAll(".layer-btn[data-layer]").forEach((btn) => {
      const key = btn.dataset.layer;
      if (cat.layers[key]) {
        btn.classList.remove("disabled");
        // Pilih variabel TIDAK menutup dropdown; hanya tombol panah "Parameter" yg menutup.
        btn.addEventListener("click", () => {
          if (btn.classList.contains("disabled")) return;   // diredupkan (mis. di strato)
          if (playing) togglePlay();
          activeBase = key;
          setActiveLayer(resolveLayer(key));
        });
      } else {
        btn.classList.add("disabled");
      }
      btn.classList.toggle("active", key === activeLayer);
    });
    renderLegend(activeLayer);

    // Medan angin per-waktu — partikel dipakai di SEMUA layer (termasuk hujan).
    const windL = cat.layers["wind_surface"];
    if (windL) windL.frames.forEach((f) => { if (f.velocity_json) windVelByTime[f.valid_time] = f.velocity_json; });
    const windS = cat.layers["wind_strato"];
    if (windS) windS.frames.forEach((f) => { if (f.velocity_json) windVelStrato[f.valid_time] = f.velocity_json; });

    setupModelSelect();      // dropdown MODEL: GFS <-> WRF Citarum
    setupHP();               // bilah bawah + chip parameter + kotak keterangan (HP)
    terapkanFiturModel();    // sembunyikan fitur yang tak punya data di model ini
    setupLevelSelect();      // hidupkan dropdown LEVEL kalau data strato ada

    // Bingkai tampilan = kotak inti (VIEW_CORE) yang diperlebar pada sumbu yang
    // perlu hingga RASIONYA sama dengan jendela desktop. Efeknya: seluruh wilayah
    // inti (India–Pasifik Barat, Cina Selatan–tengah Australia) mengisi layar
    // penuh, tanpa bar kosong dan tanpa terpotong; tepi domain data (yang lebih
    // luas) tak pernah terlihat. Dihitung ulang tiap kali jendela di-resize.
    function frameRegion() {
      const crs = map.options.crs;
      const sw = crs.project(VIEW_CORE.getSouthWest());
      const ne = crs.project(VIEW_CORE.getNorthEast());
      const cx = (sw.x + ne.x) / 2, cy = (sw.y + ne.y) / 2; // pusat (proyeksi Mercator)
      let halfW = Math.abs(ne.x - sw.x) / 2;
      let halfH = Math.abs(ne.y - sw.y) / 2;
      const size = map.getSize();
      const screenRatio = size.x / size.y;
      // Setengah-ukuran domain data GRIB. Bingkai tak boleh melewati ini di sumbu
      // mana pun, kalau lewat yang kelihatan cuma latar kosong di tepi.
      const dsw = crs.project(dataBounds.getSouthWest());
      const dne = crs.project(dataBounds.getNorthEast());
      const dataHalfW = Math.abs(dne.x - dsw.x) / 2;
      const dataHalfH = Math.abs(dne.y - dsw.y) / 2;
      if (screenRatio > halfW / halfH) {
        // Layar lebih lebar (mis. jendela browser yang tingginya termakan bilah
        // alamat) → perlebar bujur. TAPI jangan keluar domain data (lon 62-180E),
        // nanti tepi KIRI/KANAN kosong. Bila melebihi, KUNCI bujur ke domain data
        // & POTONG lintang: layar terisi penuh, zoom sedikit lebih dekat.
        halfW = halfH * screenRatio;
        if (halfW > dataHalfW) { halfW = dataHalfW; halfH = halfW / screenRatio; }
      } else {
        // Layar lebih tinggi (mis. HP potret) → kebalikannya. Pertinggi lintang,
        // tapi jangan keluar domain data (lat ±33), nanti tepi ATAS/BAWAH kosong.
        // Bila melebihi, KUNCI lintang & POTONG bujur: tampil strip vertikal.
        halfH = halfW / screenRatio;
        if (halfH > dataHalfH) { halfH = dataHalfH; halfW = halfH * screenRatio; }
      }
      const box = L.latLngBounds(
        crs.unproject(L.point(cx - halfW, cy - halfH)),
        crs.unproject(L.point(cx + halfW, cy + halfH))
      );
      // Kunci HANYA zoom-out pada tampilan awal (bingkai inti mengisi layar);
      // zoom-in dan geser tetap bebas di dalam domain data.
      const z = map.getBoundsZoom(box);      // zoom saat bingkai inti mengisi layar
      map.setMinZoom(z);                     // tak bisa zoom-out lebih jauh dari ini
      map.setMaxBounds(dataBounds);          // pan dibatasi domain data, bukan bingkai
      map.setView(crs.unproject(L.point(cx, cy)), z, { animate: false });
    }
    frameRegion();
    map.on("resize", frameRegion);
    loadAdmin(); // batas negara + provinsi Indonesia (non-blocking)
    initCityLabels(); // nama kota + nilai parameter aktif (non-blocking)
    geoGroup = L.layerGroup([], { pane: "labels" }).addTo(map);
    refreshGeoLabels();   // nama negara & laut (pengganti label CARTO)

    // Wiring UI dibuat tahan-null: elemen dekoratif yang hilang (mis. cache
    // index.html lama) tak boleh menggagalkan pemuatan peta & data.
    const slider = $("time-slider");
    if (slider) {
      slider.max = String(frames.length - 1);
      slider.addEventListener("input", (ev) => {
        if (playing) togglePlay();
        showFrame(parseInt(ev.target.value, 10));
      });
    }
    $("panel-toggle")?.addEventListener("click", togglePanels);
    $("play-btn")?.addEventListener("click", togglePlay);
    buildTicks(); // label tanggal/jam WIB di bawah slider

    // Tombol zoom neubrutalist → kontrol peta
    $("zoom-in")?.addEventListener("click", () => map.zoomIn());
    $("zoom-out")?.addEventListener("click", () => map.zoomOut());

    // Panah geser variabel (HP): gulir strip layer + auto-redup panah di ujung.
    const layersEl = document.querySelector(".layers");
    const layerStep = () => Math.max(120, (layersEl ? layersEl.clientWidth : 200) * 0.7);
    function updateLayerNav() {
      if (!layersEl) return;
      const atStart = layersEl.scrollLeft <= 1;
      const atEnd = layersEl.scrollLeft + layersEl.clientWidth >= layersEl.scrollWidth - 1;
      $("layer-prev")?.classList.toggle("nav-hidden", atStart);
      $("layer-next")?.classList.toggle("nav-hidden", atEnd);
    }
    $("layer-prev")?.addEventListener("click", () => layersEl?.scrollBy({ left: -layerStep(), behavior: "smooth" }));
    $("layer-next")?.addEventListener("click", () => layersEl?.scrollBy({ left: layerStep(), behavior: "smooth" }));
    layersEl?.addEventListener("scroll", updateLayerNav);
    window.addEventListener("resize", updateLayerNav);
    updateLayerNav();

    // HP: dropdown "Parameter" (variabel) & dropdown kontrol kanan (buka/tutup)
    $("param-toggle")?.addEventListener("click", () =>
      document.querySelector(".layer-bar")?.classList.toggle("param-open"));
    $("ctrl-toggle")?.addEventListener("click", () =>
      document.querySelector(".col.items-end")?.classList.toggle("ctrl-open"));

    // Toggle ikon kondisi cuaca per kota + hitung ulang declutter tiap pindah/zoom
    $("city-toggle")?.addEventListener("click", toggleCityIcons);
    $("cyclone-toggle")?.addEventListener("click", toggleCyclones);
    $("itcz-toggle")?.addEventListener("click", toggleItcz);
    $("mon-toggle")?.addEventListener("click", toggleMonsoon);
    map.on("moveend", () => { refreshCityIcons(); });
    map.on("zoomend", applyLabelTiles);   // ambang label CARTO vs label kota sendiri

    // "Cuaca lokasi saya" — geolokasi browser → buka detail di titik pengguna
    $("geo-btn")?.addEventListener("click", () => {
      const btn = $("geo-btn");
      if (!navigator.geolocation) { alert("Browser tidak mendukung geolokasi."); return; }
      btn.classList.add("active");
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          btn.classList.remove("active");
          const { latitude, longitude } = pos.coords;
          if (dataBounds && !dataBounds.contains([latitude, longitude])) {
            alert("Lokasi kamu di luar cakupan peta (Asia–Pasifik).");
            return;
          }
          map.setView([latitude, longitude], 8, { animate: true });
          openPoint(latitude, longitude, null, true); // marker "kamu di sini"
          fillAddress(latitude, longitude); // koordinat → alamat kecamatan/kota
        },
        () => { btn.classList.remove("active"); alert("Tidak bisa mengakses lokasi. Izinkan akses lokasi di browser."); },
        { enableHighAccuracy: true, timeout: 8000 }
      );
    });

    // Point detail: klik peta → panel titik
    map.on("click", (e) => openPoint(e.latlng.lat, e.latlng.lng));
    $("pt-close")?.addEventListener("click", closePoint);
    $("pt-export")?.addEventListener("click", exportCSV);
    $("pt-hide")?.addEventListener("click", hidePoint);
    $("pt-reopen")?.addEventListener("click", reopenPoint);
    $("share-btn")?.addEventListener("click", shareCurrent);
    $("fs-btn")?.addEventListener("click", toggleFullscreen);
    $("about-btn")?.addEventListener("click", openAbout);
    $("nav-arrow")?.addEventListener("click", () => $("nav-arrow").closest(".brand-row")?.classList.toggle("nav-open"));
    $("about-close")?.addEventListener("click", closeAbout);
    $("about-close-team")?.addEventListener("click", closeAbout);
    $("about-overlay")?.addEventListener("click", (e) => { if (e.target === e.currentTarget) closeAbout(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeAbout(); });
    // Badge "Last update" (HP): tap ikon "!" → buka teks; tap lagi/panah → tutup.
    $("data-fresh")?.addEventListener("click", () => $("data-fresh").classList.toggle("open"));
    // Tempatkan badge: desktop → kontainer slider (atas-kanan); HP → dalam legend-col
    // (di atas legenda; otomatis naik di atas tabel kondisi saat ikon kota aktif).
    const freshBadge = $("data-fresh");
    const placeFreshBadge = () => {
      if (!freshBadge) return;
      const hp = window.matchMedia("(max-width: 640px)").matches;
      const host = document.querySelector(hp ? ".legend-col" : ".timeline");
      if (host && freshBadge.parentElement !== host) host.insertBefore(freshBadge, host.firstChild);
    };
    placeFreshBadge();
    window.addEventListener("resize", placeFreshBadge);
    // Dropdown legenda+threshold di banner indikasi siklon.
    $("cyc-note-toggle")?.addEventListener("click", () => $("cyc-note").classList.toggle("open"));
    $("itcz-note-toggle")?.addEventListener("click", () => $("itcz-note").classList.toggle("open"));

    // Pencarian kota/kabupaten
    const sbox = $("search-box"), sin = $("search-input");
    $("search-btn")?.addEventListener("click", () => {
      if (sbox.classList.toggle("open")) { loadPlaces(); sin.focus(); }
    });
    sin?.addEventListener("input", (e) => renderSearch(e.target.value));
    sin?.addEventListener("keydown", (e) => {
      if (e.key === "Escape") sbox.classList.remove("open");
      if (e.key === "Enter") {
        const f = $("search-results").querySelector(".search-item");
        if (f) pickPlace(parseFloat(f.dataset.lat), parseFloat(f.dataset.lon), f.textContent);
      }
    });
    $("search-results")?.addEventListener("click", (e) => {
      const it = e.target.closest(".search-item");
      if (it) pickPlace(parseFloat(it.dataset.lat), parseFloat(it.dataset.lon), it.textContent);
    });
    // Initial time (dekoratif) diisi dari run model
    const io = $("init-opt");
    if (io) io.textContent = cat.run_time;

    const runEl = $("run-info");
    if (runEl) runEl.title = "Run model: " + cat.run_time;
    current = nearestNowIndex();       // mulai di frame terdekat "sekarang"
    await showFrame(current);
    restoreFromHash();                 // pulihkan layer/waktu/titik dari link dibagikan
    updateFreshness();
    updateAkurasi();
    drawPosHujan();
    await whenHeatmapReady();          // reveal setelah frame pertama tergambar
    hideSkeleton();
  } catch (err) {
    showLoadMsg("Gagal memuat data: " + err.message);
    console.error(err);
  }
}

init();

// PWA: daftarkan service worker (cache shell berversi; data cuaca tetap online).
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () =>
    navigator.serviceWorker.register("sw.js").catch((e) => console.warn("SW gagal:", e)));
}

/* ==================================================================
   TATA LETAK HP: bilah bawah, chip parameter, tumpukan keterangan.

   Prinsip yang dipegang: bilah bawah TIDAK punya tombol sendiri. Isinya
   dibangun dari tombol yang sudah ada di DOM, dan kliknya diteruskan ke
   tombol aslinya. Jadi tak ada dua tempat yang harus disamakan tiap kali
   ada parameter baru, dan status aktif/redup selalu ikut yang asli.
   Penyelarasan statusnya pakai MutationObserver, bukan memanggil ulang
   dari belasan tempat, supaya tak ada jalur yang kelewat.
   ================================================================== */
const HP = () => window.matchMedia("(max-width: 640px)").matches;

// Seksi bilah bawah. `sel` = pemilih tombol ASLI yang diwakili.
const LB_SEKSI = [
  { judul: "Model", jenis: "model" },
  { judul: "Parameter", sel: ".layer-btn[data-layer]" },
  // Nama seksi ini dipilih sendiri: isinya penanda yang digambar DI ATAS peta
  // (ikon kondisi kota, ikon siklon, garis ITCZ), bukan parameter dan bukan
  // fenomena. "Penanda" paling pas dan tetap awam.
  { judul: "Penanda", sel: "#city-toggle, #cyclone-toggle, #itcz-toggle" },
  { judul: "Fenomena", jenis: "fenomena" },
];

// Tiga fenomena jadi tombol TERPISAH di HP. Di desktop satu tombol
// #mon-toggle tetap menyalakan ketiganya sekaligus (perilaku lama).
const FEN = [
  { k: "monsun", label: "Monsun", ikon: "air" },
  { k: "bv", label: "Borneo Vortex", ikon: "cyclone" },
  { k: "surge", label: "Cold Surge", ikon: "ac_unit" },
];
let fenOn = { monsun: false, bv: false, surge: false };

function ikonDari(btn) {
  const i = btn.querySelector(".material-symbols-outlined");
  return i ? i.textContent.trim() : "";
}
function labelDari(btn) {
  // Urutan: .lb-txt, lalu TEKS TOMBOL ITU SENDIRI, baru data-tip.
  // data-tip sering berisi keterangan panjang yang tak muat di tombol selebar
  // sepertiga layar. Ikon dikeluarkan dulu, kalau tidak nama ligature Material
  // ikut terbaca sebagai teks.
  const t = btn.querySelector(".lb-txt")?.textContent.trim();
  if (t) return t;
  const salin = btn.cloneNode(true);
  salin.querySelectorAll(".material-symbols-outlined").forEach((e) => e.remove());
  const teks = salin.textContent.replace(/\s+/g, " ").trim();
  if (teks) return teks;
  return btn.dataset.tip || btn.getAttribute("aria-label") || "";
}

function bangunLowbar() {
  const body = $("lowbar-body");
  if (!body) return;
  body.innerHTML = "";
  for (const sec of LB_SEKSI) {
    let isi = [];
    if (sec.jenis === "model") {
      const selEl = $("model-select");
      if (!selEl) continue;
      isi = [...selEl.options].map((o) => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "lb-btn" + (o.value === MODEL_ID ? " active" : "");
        b.textContent = o.textContent.replace(/\s*-\s*\d+\s*km$/, "");
        b.addEventListener("click", () => {
          if (o.value === MODEL_ID) return;
          selEl.value = o.value;
          selEl.dispatchEvent(new Event("change"));
        });
        return b;
      });
    } else if (sec.jenis === "fenomena") {
      if (!$("mon-toggle")) continue;
      isi = FEN.map((f) => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "lb-btn" + (fenOn[f.k] ? " active" : "");
        b.dataset.fen = f.k;
        b.innerHTML = `<span class="material-symbols-outlined">${f.ikon}</span>${f.label}`;
        b.addEventListener("click", () => {
          if (b.classList.contains("disabled")) return;
          fenOn[f.k] = !fenOn[f.k];
          terapkanFenomena();
        });
        return b;
      });
      // Borneo Vortex & Cold Surge BUKAN saklar bebas. Keduanya kejadian yang
      // ada atau tidak ada hari itu; kalau sedang tak terjadi, tak ada yang
      // bisa digambar. Jadi tombolnya diredupkan dan tak bisa dipencet,
      // menjadi penunjuk keadaan. Monsun selalu ada, jadi selalu bisa dipencet.
      loadMonsoon().then(() => segarkanTombolFenomena());
    } else {
      const asli = [...document.querySelectorAll(sec.sel)];
      if (!asli.length) continue;
      isi = asli.map((src) => {
        const b = document.createElement("button");
        b.type = "button";
        b.dataset.sumber = src.id || src.dataset.layer;
        b.innerHTML = `<span class="material-symbols-outlined">${ikonDari(src)}</span>${labelDari(src)}`;
        b.addEventListener("click", () => { if (!src.classList.contains("disabled")) src.click(); });
        return b;
      });
      // Status awal + ikut berubah otomatis kalau kelas tombol asli berubah.
      asli.forEach((src, i) => {
        const cermin = () => {
          isi[i].className = "lb-btn"
            + (src.classList.contains("active") ? " active" : "")
            + (src.classList.contains("disabled") ? " disabled" : "");
        };
        cermin();
        new MutationObserver(cermin).observe(src, { attributes: true, attributeFilter: ["class"] });
      });
    }
    if (!isi.length) continue;
    const wrap = document.createElement("div");
    wrap.className = "lb-sec";
    wrap.innerHTML = `<div class="lb-head">${sec.judul}</div><div class="lb-rule"></div>`;
    const box = document.createElement("div");
    box.className = "lb-items";
    isi.forEach((b) => box.appendChild(b));
    wrap.appendChild(box);
    body.appendChild(wrap);
  }
}

// Redupkan tombol fenomena yang kejadiannya sedang TIDAK berlangsung.
function segarkanTombolFenomena() {
  const vx = monsoon?.vortex || {}, sg = monsoon?.surge || {};
  const hidup = { monsun: true, bv: !!vx.active, surge: !!sg.active };
  document.querySelectorAll("#lowbar-body .lb-btn[data-fen]").forEach((b) => {
    const k = b.dataset.fen;
    const bisa = hidup[k];
    b.classList.toggle("disabled", !bisa);
    b.title = bisa ? "" : "Sedang tidak terjadi";
    if (!bisa && fenOn[k]) { fenOn[k] = false; }   // matikan kalau terlanjur nyala
    b.classList.toggle("active", !!fenOn[k]);
  });
}

function setLowbar(buka) {
  const lb = $("lowbar"), h = $("lowbar-handle"), st = $("stage");
  if (!lb || !h) return;
  lb.classList.toggle("open", buka);
  h.classList.toggle("open", buka);
  lb.setAttribute("aria-hidden", String(!buka));
  st && st.classList.toggle("lowbar-open", buka);
  // Peta berubah tinggi (jadi 4:3), Leaflet harus diberi tahu.
  setTimeout(() => map && map.invalidateSize({ animate: false }), 300);
}

// Chip nama parameter aktif di tengah atas.
function updateParChip() {
  const el = $("par-chip");
  if (!el) return;
  if (!HP()) { el.hidden = true; return; }
  const src = document.querySelector(`.layer-btn[data-layer="${activeBase}"]`);
  if (!src) { el.hidden = true; return; }
  el.hidden = false;
  el.innerHTML = `<span class="material-symbols-outlined">${ikonDari(src)}</span>${labelDari(src)}`;
}

// Keterangan (Kondisi, Siklon, ITCZ, Fenomena) dikumpulkan ke kiri bawah.
// Elemen ASLINYA yang dipindah, bukan disalin, supaya isinya tetap ikut
// diperbarui oleh kode yang sudah ada.
const KET_SUMBER = [
  ["cond-legend", "Kondisi"], ["cyc-note", "Siklon"],
  ["itcz-note", "ITCZ"], ["phenom-panel", "Fenomena"],
];
const ketAsal = new Map();
function susunKeterangan() {
  const stack = $("ket-stack"), body = $("ket-body");
  if (!stack || !body) return;
  if (!HP()) {                       // desktop: kembalikan ke tempat semula
    for (const [id] of KET_SUMBER) {
      const el = $(id), asal = ketAsal.get(id);
      if (el && asal && el.parentElement === body) { el.classList.remove("di-ket"); asal.appendChild(el); }
    }
    stack.hidden = true;
    return;
  }
  let ada = 0;
  for (const [id, judul] of KET_SUMBER) {
    const el = $(id);
    if (!el) continue;
    if (!ketAsal.has(id)) ketAsal.set(id, el.parentElement);
    const tampil = el.classList.contains("show") || el.classList.contains("open")
                || getComputedStyle(el).display !== "none";
    if (tampil) {
      if (el.parentElement !== body) {
        el.classList.add("di-ket");
        const t = document.createElement("div");
        t.className = "ket-judul"; t.textContent = judul.toUpperCase();
        body.appendChild(t); body.appendChild(el);
      }
      ada++;
    } else if (el.parentElement === body) {
      el.classList.remove("di-ket");
      el.previousElementSibling?.classList.contains("ket-judul") && el.previousElementSibling.remove();
      ketAsal.get(id)?.appendChild(el);
    }
  }
  stack.hidden = ada === 0;
}

function setupHP() {
  bangunLowbar();
  updateParChip();
  $("lowbar-handle")?.addEventListener("click", () => setLowbar(true));
  $("lowbar")?.addEventListener("click", (e) => {
    // Klik di area kosong bilah menutupnya kembali.
    if (e.target === $("lowbar") || e.target.classList.contains("lowbar-grip")) setLowbar(false);
  });
  $("ket-toggle")?.addEventListener("click", () => $("ket-stack").classList.toggle("ciut"));
  window.addEventListener("resize", () => { updateParChip(); susunKeterangan(); });
  // Keterangan bisa muncul/hilang dari mana saja; pantau saja perubahannya.
  new MutationObserver(susunKeterangan).observe(document.body,
    { attributes: true, subtree: true, attributeFilter: ["class", "style"] });
  susunKeterangan();
}
