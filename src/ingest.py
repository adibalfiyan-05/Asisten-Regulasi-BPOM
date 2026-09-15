"""
ingest.py
Script utama pipeline ingestion (tanggung jawab Anggota 2).

Alur (sesuai dokumen rencana proyek bagian 5 & 7):
  1. Baca daftar metadata dokumen dari data/metadata/dataset_index.csv
     (disiapkan oleh Anggota 1).
  2. Untuk setiap PDF di data/raw_docs/:
       - cek apakah file baru/berubah (via hash) -> kalau sudah ada & tidak
         berubah, SKIP (ini fungsi update/re-ingest incremental).
       - ekstrak teks per halaman (pdf_extract.py)
       - bersihkan teks (cleaning.py)
       - chunking berbasis Pasal/BAB + ukuran (chunking.py)
       - lampirkan metadata dokumen (dari CSV) + metadata chunk (halaman, pasal, bab)
  3. Embedding seluruh chunk baru (embedding.py)
  4. Simpan/replace ke Vector DB (vector_store.py)
  5. Simpan juga preview hasil chunk ke data/processed/<nama_file>.jsonl
     supaya mudah diperiksa manual ("contoh hasil chunk" -> deliverable).
  6. Update manifest.json (data/metadata/manifest.json) supaya run berikutnya
     tahu file mana yang sudah diproses.

Cara pakai:
    python src/ingest.py                     # ingest semua file baru/berubah
    python src/ingest.py --force              # paksa re-ingest SEMUA file
    python src/ingest.py --file namafile.pdf  # ingest satu file saja
"""

import argparse
import csv
import hashlib
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))

from chunking import chunk_document
from cleaning import clean_document_pages
from embedding import embed_texts
from pdf_extract import extract_pages, get_pdf_basic_info
from vector_store import count, delete_by_source, upsert_chunks

RAW_DIR = "data/raw_docs"
METADATA_CSV = "data/metadata/dataset_index.csv"
MANIFEST_PATH = "data/metadata/manifest.json"
PROCESSED_DIR = "data/processed"


# ---------------------------------------------------------------------------
# Metadata dokumen (dari Anggota 1)
# ---------------------------------------------------------------------------

def load_document_metadata(csv_path: str) -> dict:
    """
    Baca dataset_index.csv -> dict {filename: {title, number_year, topic,
    status, source_url, document_type, ...}}.
    Kalau file belum ada (mis. Anggota 1 belum submit), kembalikan dict kosong
    dan beri peringatan -> ingestion tetap jalan dengan metadata minimal.
    """
    if not os.path.exists(csv_path):
        print(f"[PERINGATAN] {csv_path} tidak ditemukan. "
              f"Ingestion tetap jalan tapi metadata dokumen (title/topic/status/dst) "
              f"tidak akan lengkap. Minta Anggota 1 menyiapkan file ini.")
        return {}
    meta = {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            fname = row.get("filename", "").strip()
            if fname:
                meta[fname] = row
    return meta


# ---------------------------------------------------------------------------
# Manifest untuk incremental re-ingest
# ---------------------------------------------------------------------------

def load_manifest(path: str) -> dict:
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_manifest(path: str, manifest: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)


def file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(8192), b""):
            h.update(block)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Proses satu dokumen
# ---------------------------------------------------------------------------

def process_one_pdf(filename: str, doc_meta: dict) -> list[dict]:
    """
    Proses satu file PDF -> list of dict siap embed & index.
    Setiap dict: {chunk_id, text, metadata}
    """
    path = os.path.join(RAW_DIR, filename)

    info = get_pdf_basic_info(path)
    if not info["has_text_layer"]:
        print(f"  [SKIP-WARN] '{filename}' sepertinya hasil scan (tidak ada text layer). "
              f"Perlu OCR dulu sebelum bisa di-ingest -- lihat pdf-reading skill / pytesseract.")
        return []

    pages = extract_pages(path)
    raw_page_texts = [p.text for p in pages]
    cleaned_page_texts = clean_document_pages(raw_page_texts)
    page_tuples = [(p.page_number, txt) for p, txt in zip(pages, cleaned_page_texts)]

    chunks = chunk_document(page_tuples, max_chars=1600, overlap=200)

    title = doc_meta.get("title") or filename
    records = []
    for c in chunks:
        chunk_id = f"{filename}::chunk{c.chunk_index:04d}"
        metadata = {
            "source_file": filename,
            "title": title,
            "number_year": doc_meta.get("number_year", ""),
            "topic": doc_meta.get("topic", ""),
            "status": doc_meta.get("status", ""),
            "source_url": doc_meta.get("source_url", ""),
            "document_type": doc_meta.get("document_type", ""),
            "page_start": c.page_start,
            "page_end": c.page_end,
            "bab": c.bab or "",
            "pasal": c.pasal or "",
            "chunk_index": c.chunk_index,
        }
        records.append({"chunk_id": chunk_id, "text": c.text, "metadata": metadata})
    return records


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Ingestion pipeline: PDF -> Vector DB")
    parser.add_argument("--force", action="store_true", help="Paksa re-ingest semua file, abaikan manifest")
    parser.add_argument("--file", type=str, default=None, help="Hanya ingest satu file (nama file di raw_docs)")
    args = parser.parse_args()

    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(PROCESSED_DIR, exist_ok=True)

    doc_metadata = load_document_metadata(METADATA_CSV)
    manifest = load_manifest(MANIFEST_PATH)

    if args.file:
        candidate_files = [args.file]
    else:
        candidate_files = sorted(
            f for f in os.listdir(RAW_DIR) if f.lower().endswith(".pdf")
        )

    if not candidate_files:
        print(f"Tidak ada file PDF di '{RAW_DIR}/'. Taruh PDF di sana lalu jalankan ulang.")
        return

    to_process = []
    skipped = 0
    for fname in candidate_files:
        path = os.path.join(RAW_DIR, fname)
        if not os.path.exists(path):
            print(f"[WARNING] File '{fname}' tidak ditemukan, dilewati.")
            continue
        h = file_hash(path)
        prev = manifest.get(fname)
        if (not args.force) and prev and prev.get("hash") == h:
            skipped += 1
            continue
        to_process.append((fname, h))

    print(f"Total PDF ditemukan : {len(candidate_files)}")
    print(f"Sudah up-to-date    : {skipped} (dilewati, hemat waktu & biaya embedding)")
    print(f"Akan diproses       : {len(to_process)}")

    total_new_chunks = 0
    for fname, h in to_process:
        print(f"\n>> Memproses: {fname}")
        meta_row = doc_metadata.get(fname, {})
        if not meta_row:
            print(f"  [INFO] Tidak ada entri metadata untuk '{fname}' di {METADATA_CSV}. "
                  f"Menggunakan metadata minimal (title=filename).")

        try:
            records = process_one_pdf(fname, meta_row)
        except Exception as e:
            print(f"  [ERROR] Gagal memproses '{fname}': {e}")
            continue

        if not records:
            print(f"  [INFO] 0 chunk dihasilkan dari '{fname}' (kemungkinan file kosong/scan).")
            continue

        # Hapus chunk lama milik file ini (kalau ada) sebelum menambah versi baru
        delete_by_source(fname)

        texts = [r["text"] for r in records]
        print(f"  Embedding {len(texts)} chunk...")
        embeddings = embed_texts(texts)

        ids = [r["chunk_id"] for r in records]
        metadatas = [r["metadata"] for r in records]
        upsert_chunks(ids=ids, documents=texts, embeddings=embeddings, metadatas=metadatas)

        # Simpan preview chunk untuk inspeksi manual (deliverable: contoh hasil chunk)
        preview_path = os.path.join(PROCESSED_DIR, f"{fname}.jsonl")
        with open(preview_path, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        manifest[fname] = {
            "hash": h,
            "n_chunks": len(records),
            "last_ingested": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        total_new_chunks += len(records)
        print(f"  Selesai: {len(records)} chunk diindex, preview -> {preview_path}")

    save_manifest(MANIFEST_PATH, manifest)

    print("\n=== RINGKASAN ===")
    print(f"File baru/berubah diproses : {len(to_process)}")
    print(f"Chunk baru diindex         : {total_new_chunks}")
    print(f"Total chunk di Vector DB   : {count()}")
    print(f"Manifest disimpan di       : {MANIFEST_PATH}")


if __name__ == "__main__":
    main()