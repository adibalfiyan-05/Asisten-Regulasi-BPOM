"""
evaluate.py (Tugas Anggota 4)
Script pengujian otomatis untuk mengukur kinerja RAG berdasarkan test_questions.csv
"""

import csv
import os
import sys
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))

from rag import generate_answer

TEST_CSV = "data/test_questions/test_questions.csv"
OUTPUT_EVAL_CSV = "data/processed/evaluation_results.csv"

def run_evaluation():
    if not os.path.exists(TEST_CSV):
        print(f"[ERROR] File {TEST_CSV} tidak ditemukan. Minta Anggota 1/4 menyiapkannya.")
        return

    questions_df = pd.read_csv(TEST_CSV)
    results = []

    print(f"Memulai evaluasi terhadap {len(questions_df)} pertanyaan uji...")

    for idx, row in questions_df.iterrows():
        q_id = row.get("id", idx + 1)
        question = row.get("question")
        category = row.get("category", "Umum")
        
        print(f"[{idx+1}/{len(questions_df)}] Testing: {question}")
        res = generate_answer(question, top_k=8)
        
        num_sources = len(res["sources"])
        found_sources = "; ".join([s["title"] for s in res["sources"][:3]])

        results.append({
            "question_id": q_id,
            "category": category,
            "question": question,
            "answer_generated": res["answer"],
            "num_sources_retrieved": num_sources,
            "top_sources": found_sources
        })

    os.makedirs("data/processed", exist_ok=True)
    eval_df = pd.DataFrame(results)
    eval_df.to_csv(OUTPUT_EVAL_CSV, index=False, encoding="utf-8")
    print(f"\nEvaluasi selesai! Hasil disimpan di: {OUTPUT_EVAL_CSV}")

if __name__ == "__main__":
    run_evaluation()