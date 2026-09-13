# Ingestion Pipeline — Asisten Regulasi BPOM
**Peran: Anggota 2 (Data Engineer / RAG Ingestion)**

Pipeline ini mengubah kumpulan PDF regulasi BPOM menjadi Vector Database
yang bisa di-query oleh modul retrieval (Anggota 3). Sudah diuji end-to-end
dengan dokumen contoh dan **berhasil jalan** (lihat bagian "Hasil Pengujian").

## 1. Struktur Folder

```
project/
├── data/
│   ├── raw_docs/        <- taruh PDF asli di sini (dari Anggota 1)
│   ├── metadata/
│   │   ├── dataset_index.csv  <- metadata dokumen (dari Anggota 1)
│   │   └── manifest.json      <- auto-generated, tracking file yg sudah di-ingest
│   ├── processed/        <- auto-generated, preview hasil chunk (.jsonl) per file
│   └── test_questions/   <- (opsional) pertanyaan uji dari Anggota 1/4
├── vector_db/             <- auto-generated, database ChromaDB (persisten)
├── src/
│   ├── pdf_extract.py     <- ekstraksi teks per halaman (PyMuPDF)
│   ├── cleaning.py        <- pembersihan teks (noise, header/footer, halaman)
│   ├── chunking.py        <- chunking berbasis Pasal/BAB + fallback ukuran
│   ├── embedding.py        <- wrapper model embedding (+ fallback offline)
│   ├── vector_store.py     <- wrapper ChromaDB (simpan & search)
│   ├── ingest.py           <- SCRIPT UTAMA, jalankan ini
│   └── query_test.py       <- skrip cepat untuk tes query manual
├── requirements.txt
└── README.md (file ini)
```

## 2. Cara Menjalankan

```bash
pip install -r requirements.txt

# 1. Taruh semua PDF regulasi di data/raw_docs/
# 2. Pastikan data/metadata/dataset_index.csv sudah diisi Anggota 1
#    (kolom: filename, title, number_year, topic, status, source_url, document_type)

# 3. Jalankan ingestion
python src/ingest.py

# 4. Uji hasilnya
python src/query_test.py "Apa arti nomor izin edar?"
```

Kalau ada PDF baru ditambahkan atau ada PDF yang diganti isinya, tinggal
jalankan `python src/ingest.py` lagi — pipeline otomatis:
- **skip** file yang tidak berubah (dicek via SHA-256 hash, tersimpan di
  `manifest.json`) → hemat waktu & tidak perlu embed ulang semua dokumen,
- **re-index** hanya file yang baru/berubah (chunk lama dihapus dulu,
  baru diganti dengan versi baru).

Untuk paksa proses ulang semua file: `python src/ingest.py --force`
Untuk proses satu file saja: `python src/ingest.py --file namafile.pdf`

## 3. Mekanisme Detail (untuk bagian dokumentasi/laporan kelompok)

### a. Ekstraksi (`pdf_extract.py`)
Pakai **PyMuPDF (fitz)** — sesuai rekomendasi dokumen rencana proyek.
Teks diekstrak **per halaman** (bukan digabung langsung) supaya setiap
chunk nanti bisa membawa informasi nomor halaman untuk citation.
Ada pengecekan `has_text_layer`: jika PDF hasil scan (tidak ada teks,
cuma gambar), file otomatis dilewati dengan peringatan — perlu OCR dulu
(lihat referensi di pdf-reading skill / pytesseract) sebelum bisa di-ingest.

### b. Cleaning (`cleaning.py`)
- Normalisasi unicode.
- Buang karakter kontrol.
- Deteksi & buang baris nomor halaman murni ("12", "- 12 -", "Halaman 12").
- Deteksi baris yang **berulang di banyak halaman** dalam dokumen yang sama
  (kandidat header/footer institusional, misal nama badan yang dicetak di
  tiap halaman) dan membuangnya.
- Isi regulasi (pasal, ayat, angka, definisi) **tidak disentuh** — hanya
  noise struktural yang dibuang.

### c. Chunking (`chunking.py`)
Strategi berlapis:
1. **Deteksi struktur regulasi**: cari pola `BAB ...` dan `Pasal N` dengan
   regex. Peraturan Indonesia terstruktur per Pasal, jadi ini dipakai
   sebagai **unit semantik utama** (satu Pasal = idealnya satu chunk).
2. Setiap chunk mencatat: `bab` (BAB terakhir sebelum pasal tsb), `pasal`
   (label pasal), `page_start`, `page_end`.
3. Kalau satu Pasal terlalu panjang (>1600 karakter, ~350-450 token), chunk
   dipecah lagi dengan **overlap 200 karakter** supaya konteks tidak
   terputus mendadak, dan pemotongan diusahakan jatuh di batas kalimat.
4. **Fallback**: kalau dokumen tidak berstruktur Pasal (mis. FAQ, pedoman
   umum, brosur informasi konsumen), chunking jatuh ke mode berbasis
   paragraf + ukuran karakter.

### d. Embedding (`embedding.py`)
Model default: **`paraphrase-multilingual-MiniLM-L12-v2`** (sentence-transformers)
— gratis, jalan lokal (tanpa API key/biaya), mendukung Bahasa Indonesia.
Vektor dinormalisasi (`normalize_embeddings=True`) supaya cosine similarity
konsisten dengan konfigurasi index.

> **Catatan koneksi internet**: model perlu diunduh sekali dari HuggingFace
> saat pertama kali dipakai (lalu otomatis ter-cache lokal). Kalau saat
> testing tidak ada koneksi sama sekali, kode ini **otomatis fallback**
> ke embedding berbasis hashing (scikit-learn) supaya pipeline tetap bisa
> di-demo — akan muncul peringatan di console. Untuk kualitas retrieval
> terbaik, pastikan run pertama dilakukan saat online.

### e. Indexing / Vector DB (`vector_store.py`)
Pakai **ChromaDB** (`PersistentClient`, disimpan di folder `vector_db/`),
dengan `hnsw:space="cosine"`. Setiap chunk disimpan dengan:
- `id` unik: `<nama_file>::chunk<index>`
- `document`: teks chunk
- `embedding`: vector hasil embedding
- `metadata`: `source_file, title, number_year, topic, status, source_url,
  document_type, page_start, page_end, bab, pasal, chunk_index`

Metadata ini yang dipakai Anggota 3 untuk menampilkan **sumber/citation**
("Sumber: [title], hlm. [page_start]-[page_end], [pasal]") dan untuk
filter pencarian per topik (`where={"topic": "Pangan"}`).

### f. Update / Re-ingest (`ingest.py`)
Setiap file di-hash (SHA-256). Hash + jumlah chunk + waktu terakhir
di-ingest disimpan di `data/metadata/manifest.json`. Saat pipeline
dijalankan lagi:
- hash sama → **skip** (tidak reprocess, tidak re-embed).
- hash beda / file baru → chunk lama untuk file itu dihapus dari
  ChromaDB (`delete_by_source`), lalu diproses & di-index ulang.

Ini memenuhi requirement "fungsi update/re-ingest sehingga jika dokumen
ditambah tidak perlu mengulang seluruh proses secara manual."

## 4. Hasil Pengujian (dengan dokumen contoh)

Karena dataset asli dari Anggota 1 belum tersedia saat pipeline ini dibuat,
pipeline diuji dengan **satu dokumen contoh** yang meniru struktur peraturan
BPOM asli (`data/raw_docs/contoh_peraturan_izin_edar.pdf`, berisi BAB I–IV,
Pasal 1–7 tentang izin edar pangan olahan).

**Hasil:**
- 4 halaman PDF berhasil diekstrak & dibersihkan.
- Menghasilkan **8 chunk**, masing-masing berhasil memetakan `pasal`, `bab`,
  dan rentang halaman dengan benar (dicek manual, lihat
  `data/processed/contoh_peraturan_izin_edar.pdf.jsonl`).
- Vector DB berhasil dibuat & di-query: pertanyaan *"Bagaimana cara konsumen
  memeriksa nomor izin edar produk?"* mengembalikan **Pasal 6** (pasal yang
  memang membahas hal itu) sebagai hasil #1 dari top-3.
- Fitur re-ingest incremental diuji: run kedua tanpa perubahan file
  correctly melewati (skip) file tersebut, 0 chunk baru diproses.

**Langkah selanjutnya**: begitu Anggota 1 menyerahkan 10–20 dokumen asli +
`dataset_index.csv` yang terisi, ganti/hapus file contoh di `raw_docs/`
dengan dokumen asli lalu jalankan `python src/ingest.py`.

## 5. Yang Perlu Dikoordinasikan dengan Anggota Lain
- **Anggota 1**: pastikan `filename` di `dataset_index.csv` **persis sama**
  dengan nama file PDF di `raw_docs/` (termasuk huruf besar/kecil & ekstensi),
  supaya metadata bisa ter-join otomatis.
- **Anggota 3**: gunakan `src/vector_store.py::search()` dan
  `src/embedding.py::embed_query()` untuk retrieval di layer prompt/LLM.
  Metadata chunk sudah siap dipakai untuk citation.
- **Anggota 4**: `src/query_test.py` bisa dipakai sebagai starting point
  untuk membuat test set evaluasi retrieval.
