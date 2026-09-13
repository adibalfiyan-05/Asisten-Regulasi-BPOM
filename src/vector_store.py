"""
vector_store.py
Wrapper penyimpanan & pencarian ke Vector Database (ChromaDB, persistent
di disk -> folder vector_db/, sesuai struktur folder proyek).

Kita simpan embedding secara manual (precomputed lewat embedding.py) supaya
proses embedding & penyimpanan terpisah jelas dan mudah di-debug/di-test.
"""

import chromadb

DB_DIR = "vector_db"
COLLECTION_NAME = "bpom_regulasi"


def get_client(db_dir: str = DB_DIR):
    return chromadb.PersistentClient(path=db_dir)


def get_collection(db_dir: str = DB_DIR, collection_name: str = COLLECTION_NAME):
    client = get_client(db_dir)
    return client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )


def delete_by_source(source_file: str, db_dir: str = DB_DIR, collection_name: str = COLLECTION_NAME):
    """Hapus semua chunk milik satu file sumber (dipakai saat re-ingest file yang berubah)."""
    col = get_collection(db_dir, collection_name)
    col.delete(where={"source_file": source_file})


def upsert_chunks(
    ids: list[str],
    documents: list[str],
    embeddings: list[list[float]],
    metadatas: list[dict],
    db_dir: str = DB_DIR,
    collection_name: str = COLLECTION_NAME,
):
    """Tambahkan/replace chunk ke collection."""
    if not ids:
        return
    col = get_collection(db_dir, collection_name)
    col.upsert(ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas)


def count(db_dir: str = DB_DIR, collection_name: str = COLLECTION_NAME) -> int:
    col = get_collection(db_dir, collection_name)
    return col.count()


def search(
    query_embedding: list[float],
    top_k: int = 5,
    where: dict | None = None,
    db_dir: str = DB_DIR,
    collection_name: str = COLLECTION_NAME,
) -> dict:
    """
    Cari top_k chunk paling relevan.
    `where` opsional untuk filter metadata, mis. {"topic": "Pangan"}.
    """
    col = get_collection(db_dir, collection_name)
    return col.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where=where,
        include=["documents", "metadatas", "distances"],
    )
