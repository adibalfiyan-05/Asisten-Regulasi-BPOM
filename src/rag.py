"""
rag.py
Fungsi utama RAG: retrieval + prompt + generation (LLM: Google Gemini).
Tugas Anggota 3.

Cara pakai:
    python src/rag.py "Apa arti nomor izin edar?"
    atau
    python src/rag.py "Apa syarat sarana distribusi obat yang baik?"
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
import google.generativeai as genai

from embedding import embed_query
from vector_store import search

load_dotenv()  # baca file .env

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY belum diset. Cek file .env kamu.")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-3.6-flash")

SYSTEM_INSTRUCTION = (
    "Kamu adalah asisten regulasi BPOM untuk pangan dan obat-obatan. "
    "Jawab HANYA berdasarkan context dokumen yang diberikan. "
    "Jika context tidak cukup untuk menjawab, katakan dengan jelas bahwa "
    "informasi tidak ditemukan dalam dokumen yang tersedia, jangan mengarang. "
    "Jangan memberikan diagnosis kesehatan, dosis obat pribadi, atau nasihat hukum. "
    "Gunakan bahasa yang mudah dipahami orang awam. "
    "Di akhir jawaban, sebutkan sumber yang kamu pakai."
)


def build_context(results: dict) -> tuple[str, list[dict]]:
    """Susun teks context dari hasil search(), sekalian siapin daftar sumber."""
    docs = results["documents"][0]
    metas = results["metadatas"][0]

    context_parts = []
    sources = []
    for i, (doc, meta) in enumerate(zip(docs, metas), start=1):
        label = f"[Dokumen {i}] {meta.get('title')} (hlm. {meta.get('page_start')}-{meta.get('page_end')}"
        if meta.get("pasal"):
            label += f", {meta['pasal']}"
        label += ")"
        context_parts.append(f"{label}\n{doc}")
        sources.append({
            "title": meta.get("title"),
            "page_start": meta.get("page_start"),
            "page_end": meta.get("page_end"),
            "pasal": meta.get("pasal"),
        })

    context_text = "\n\n---\n\n".join(context_parts)
    return context_text, sources


def generate_answer(query: str, top_k: int = 5, where: dict | None = None) -> dict:
    """Alur lengkap: embed query -> search -> prompt -> LLM -> jawaban + sumber."""
    q_emb = embed_query(query)
    results = search(q_emb, top_k=top_k, where=where)

    if not results["documents"][0]:
        return {
            "answer": "Informasi tidak ditemukan dalam dokumen yang tersedia.",
            "sources": [],
        }

    context_text, sources = build_context(results)

    prompt = (
        f"{SYSTEM_INSTRUCTION}\n\n"
        f"=== CONTEXT DOKUMEN ===\n{context_text}\n\n"
        f"=== PERTANYAAN PENGGUNA ===\n{query}\n\n"
        f"=== JAWABAN ==="
    )

    response = model.generate_content(prompt)

    return {
        "answer": response.text,
        "sources": sources,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("query", type=str, help="Pertanyaan pengguna")
    parser.add_argument("--top_k", type=int, default=5)
    args = parser.parse_args()

    result = generate_answer(args.query, top_k=args.top_k)

    print(f"\nPertanyaan: {args.query}\n")
    print(f"Jawaban:\n{result['answer']}\n")
    print("Sumber:")
    for s in result["sources"]:
        pasal_info = f", {s['pasal']}" if s.get("pasal") else ""
        print(f"  - {s['title']} (hlm. {s['page_start']}-{s['page_end']}{pasal_info})")


if __name__ == "__main__":
    main()