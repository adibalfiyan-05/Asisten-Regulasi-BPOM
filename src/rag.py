"""
rag.py (Tugas Anggota 3)
Pipeline Retrieval-Augmented Generation:
Query -> Embedding -> Vector Search -> Context Assembly -> Gemini LLM -> Answer + Citations
"""

import argparse
import os
import sys

from dotenv import load_dotenv
import google.generativeai as genai

sys.path.insert(0, os.path.dirname(__file__))

from embedding import embed_query
from vector_store import search

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY belum diset di file .env!")

genai.configure(api_key=GEMINI_API_KEY)
# Menggunakan model Gemini 2.5 Flash yang cepat dan stabil
model = genai.GenerativeModel("gemini-2.5-flash-latest")

SYSTEM_INSTRUCTION = (
    "Kamu adalah Asisten Regulasi BPOM berbasis RAG. Tugasmu membantu pemilik usaha dan konsumen "
    "memahami aturan regulasi pangan dan obat-obatan berdasarkan dokumen resmi.\n\n"
    "PRINSIP UTAMA:\n"
    "1. Jawab HANYA menggunakan informasi dari CONTEXT DOKUMEN yang diberikan.\n"
    "2. Jika informasi TIDAK ADA pada konteks, jawab dengan tegas: "
    "'Informasi tidak ditemukan dalam dokumen regulasi yang tersedia.' Jangan mengarang jawaban!\n"
    "3. DILARANG memberikan diagnosis medis, dosis obat pribadi, atau pertimbangan hukum resmi.\n"
    "4. Gunakan bahasa yang lugas, profesional, dan mudah dipahami.\n"
    "5. Cantumkan rincian dokumen dan nomor halaman/pasal sebagai referensi di dalam teks jawaban jika relevan."
)


def format_context(results: dict) -> tuple[str, list[dict]]:
    """Format hasil pencarian Vector DB menjadi blok teks context untuk prompt."""
    docs = results["documents"][0]
    metas = results["metadatas"][0]

    context_parts = []
    sources = []

    for i, (doc, meta) in enumerate(zip(docs, metas), start=1):
        title = meta.get("title", meta.get("source_file", "Dokumen Tanpa Judul"))
        page_start = meta.get("page_start", "?")
        page_end = meta.get("page_end", "?")
        pasal = f", {meta['pasal']}" if meta.get("pasal") else ""

        header = f"[Sumber {i}] {title} (Halaman {page_start}-{page_end}{pasal})"
        context_parts.append(f"{header}\n{doc}")

        sources.append({
            "id": i,
            "title": title,
            "filename": meta.get("source_file"),
            "page_start": page_start,
            "page_end": page_end,
            "pasal": meta.get("pasal", ""),
            "topic": meta.get("topic", ""),
            "source_url": meta.get("source_url", ""),
            "snippet": doc[:150] + "..."
        })

    full_context = "\n\n---\n\n".join(context_parts)
    return full_context, sources


def generate_answer(query: str, top_k: int = 8, topic_filter: str | None = None) -> dict:
    """Fungsi utama RAG pipeline."""
    where_clause = {"topic": topic_filter} if topic_filter else None
    
    # 1. Embedding Query & Vector Search
    q_emb = embed_query(query)
    results = search(q_emb, top_k=top_k, where=where_clause)

    if not results or not results.get("documents") or not results["documents"][0]:
        return {
            "answer": "Informasi tidak ditemukan dalam dokumen regulasi yang tersedia.",
            "sources": []
        }

    # 2. Build Context & Sources List
    context_text, sources = format_context(results)

    # 3. Construct Prompt
    prompt = (
        f"{SYSTEM_INSTRUCTION}\n\n"
        f"=== CONTEXT DOKUMEN REGULASI ===\n"
        f"{context_text}\n\n"
        f"=== PERTANYAAN PENGGUNA ===\n"
        f"{query}\n\n"
        f"=== JAWABAN ==="
    )

    # 4. LLM Generation
    try:
        response = model.generate_content(prompt)
        answer_text = response.text
    except Exception as e:
        answer_text = f"Terjadi kesalahan saat menghubungi LLM: {str(e)}"

    return {
        "query": query,
        "answer": answer_text,
        "sources": sources
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tes RAG Pipeline")
    parser.add_argument("query", type=str, help="Pertanyaan untuk RAG")
    parser.add_argument("--top_k", type=int, default=8, help="Jumlah chunk yang diambil")
    args = parser.parse_args()

    res = generate_answer(args.query, top_k=args.top_k)
    print(f"\nPertanyaan: {res['query']}\n")
    print(f"Jawaban:\n{res['answer']}\n")
    print("Sumber Referensi:")
    for s in res["sources"]:
        pasal_info = f", {s['pasal']}" if s['pasal'] else ""
        print(f"  [{s['id']}] {s['title']} (Hlm. {s['page_start']}-{s['page_end']}{pasal_info})")