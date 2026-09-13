"""
query_test.py
Skrip kecil untuk MENGUJI bahwa Vector DB hasil ingestion bisa di-query
(similarity search). Ini BUKAN sistem RAG lengkap (itu tugas Anggota 3),
tapi bukti bahwa pipeline ingestion menghasilkan sesuatu yang berfungsi.

Cara pakai:
    python src/query_test.py "Apa arti nomor izin edar?"
    python src/query_test.py "Apa arti nomor izin edar?" --top_k 3
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from embedding import embed_query
from vector_store import count, search


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("query", type=str, help="Pertanyaan uji")
    parser.add_argument("--top_k", type=int, default=5)
    args = parser.parse_args()

    n = count()
    print(f"Total chunk di Vector DB: {n}")
    if n == 0:
        print("Vector DB masih kosong. Jalankan `python src/ingest.py` dulu.")
        return

    q_emb = embed_query(args.query)
    results = search(q_emb, top_k=args.top_k)

    docs = results["documents"][0]
    metas = results["metadatas"][0]
    dists = results["distances"][0]

    print(f"\nPertanyaan: {args.query}")
    print(f"Top-{args.top_k} chunk paling relevan:\n")
    for i, (doc, meta, dist) in enumerate(zip(docs, metas, dists), start=1):
        similarity = 1 - dist  # karena kita pakai cosine space
        print(f"[{i}] similarity={similarity:.3f} | sumber: {meta.get('title')} "
              f"(hlm. {meta.get('page_start')}-{meta.get('page_end')}"
              f"{', ' + meta['pasal'] if meta.get('pasal') else ''})")
        snippet = doc[:220].replace("\n", " ")
        print(f"    \"{snippet}...\"\n")


if __name__ == "__main__":
    main()
