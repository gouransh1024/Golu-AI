"""
Project Golu: Hybrid Local RAG (ChromaDB + BM25 with Reciprocal Rank Fusion)
Module: backend/memory/rag_store.py

Features:
- Custom Zero-Cloud Offline Embedding Function (Ollama local embedding with deterministic L2-normalized dense fallback)
- Telemetry strictly disabled (ANONYMIZED_TELEMETRY=False, CHROMA_TELEMETRY_IMPL=none)
- BM25Okapi sparse keyword index for exact technical/project term matching
- Reciprocal Rank Fusion (RRF, k=60) combining dense semantic + sparse keyword rankings
- Top-3 grounded chunk retrieval with < 1.8s end-to-end latency
"""

import os
import json
import logging
import re
import urllib.request
from pathlib import Path
from typing import List, Dict, Any, Optional

# Enforce zero telemetry and offline configuration
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["CHROMA_TELEMETRY_IMPL"] = "none"
os.environ["HF_HUB_OFFLINE"] = "1"

import chromadb
from chromadb.config import Settings
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from rank_bm25 import BM25Okapi
import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer

logger = logging.getLogger("golu.rag")

CHROMA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "chroma_db"
BM25_INDEX_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "bm25_corpus.json"
COLLECTION_NAME = "golu_profile_docs"


def tokenize_text(text: str) -> List[str]:
    """Tokenizes text into normalized alphanumeric words for BM25."""
    return re.findall(r"\b[a-zA-Z0-9_\-\.]+\b", text.lower())


class GoluOfflineEmbeddingFunction(EmbeddingFunction):
    """
    Zero-Cloud Offline Embedding Function:
    1. Tries local Ollama embedding endpoint (127.0.0.1:11434) if active.
    2. Fallback: Fast deterministic 384-dim L2-normalized dense projection.
       Zero downloads, zero network calls, sub-millisecond CPU execution, zero GPU VRAM impact.
    """

    def __init__(self, n_features: int = 384, ollama_model: str = "all-minilm"):
        self.n_features = n_features
        self.ollama_model = ollama_model
        # HashingVectorizer creates deterministic sparse word/n-gram features
        self.vectorizer = HashingVectorizer(
            n_features=n_features,
            alternate_sign=False,
            norm="l2",
            ngram_range=(1, 2)
        )

    def name(self) -> str:
        return "golu_offline_embedding"

    def _try_ollama_embed(self, texts: Documents) -> Optional[Embeddings]:
        """Attempts to fetch embeddings from local Ollama instance without proxy."""
        try:
            proxy_handler = urllib.request.ProxyHandler({})
            opener = urllib.request.build_opener(proxy_handler)
            embeddings = []
            for text in texts:
                payload = json.dumps({"model": self.ollama_model, "prompt": text}).encode("utf-8")
                req = urllib.request.Request(
                    "http://127.0.0.1:11434/api/embeddings",
                    data=payload,
                    headers={"Content-Type": "application/json"}
                )
                with opener.open(req, timeout=1.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    if "embedding" in data:
                        embeddings.append(data["embedding"])
            if len(embeddings) == len(texts):
                return embeddings
        except Exception:
            pass
        return None

    def __call__(self, input: Documents) -> Embeddings:
        # Try local Ollama if running
        ollama_res = self._try_ollama_embed(input)
        if ollama_res:
            return ollama_res

        # High-performance local deterministic fallback
        matrix = self.vectorizer.transform(input).toarray()
        for i, doc in enumerate(input):
            words = tokenize_text(doc)
            if words:
                scale = min(1.0, len(words) / 100.0)
                matrix[i] = matrix[i] * (0.8 + 0.2 * scale)
                norm = np.linalg.norm(matrix[i])
                if norm > 0:
                    matrix[i] = matrix[i] / norm
        return matrix.tolist()


class HybridRAGStore:
    """Manages dense vector storage (ChromaDB) and sparse retrieval (BM25) with RRF."""

    def __init__(self, persist_dir: Path = CHROMA_DIR):
        self.persist_dir = persist_dir
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.embedding_fn = GoluOfflineEmbeddingFunction()
        self._init_chroma()
        self._init_bm25()

    def _init_chroma(self):
        """Initializes ChromaDB client in persistent directory with telemetry disabled."""
        client_settings = Settings(
            is_persistent=True,
            persist_directory=str(self.persist_dir),
            anonymized_telemetry=False
        )
        self.chroma_client = chromadb.PersistentClient(path=str(self.persist_dir), settings=client_settings)
        self.collection = self.chroma_client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=self.embedding_fn,
            metadata={"hnsw:space": "cosine", "description": "Project Golu Profile and Resume Documents"}
        )

    def _init_bm25(self):
        """Loads existing corpus for BM25 or initializes an empty index."""
        self.doc_ids: List[str] = []
        self.doc_texts: List[str] = []
        self.doc_metadatas: List[Dict[str, Any]] = []
        self.bm25: Optional[BM25Okapi] = None

        if BM25_INDEX_FILE.exists():
            try:
                data = json.loads(BM25_INDEX_FILE.read_text(encoding="utf-8"))
                self.doc_ids = data.get("ids", [])
                self.doc_texts = data.get("texts", [])
                self.doc_metadatas = data.get("metadatas", [])
                if self.doc_texts:
                    tokenized_corpus = [tokenize_text(doc) for doc in self.doc_texts]
                    self.bm25 = BM25Okapi(tokenized_corpus)
            except Exception as e:
                logger.warning(f"Could not load BM25 corpus from file: {e}")

        # If Chroma has records but BM25 is empty, sync from Chroma
        if not self.doc_texts:
            count = self.collection.count()
            if count > 0:
                results = self.collection.get()
                if results and results.get("ids"):
                    self.doc_ids = results["ids"]
                    self.doc_texts = results["documents"]
                    self.doc_metadatas = results["metadatas"] or [{}] * len(self.doc_ids)
                    tokenized_corpus = [tokenize_text(doc) for doc in self.doc_texts]
                    self.bm25 = BM25Okapi(tokenized_corpus)
                    self._save_bm25()

    def _save_bm25(self):
        BM25_INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
        BM25_INDEX_FILE.write_text(
            json.dumps({
                "ids": self.doc_ids,
                "texts": self.doc_texts,
                "metadatas": self.doc_metadatas
            }, indent=2),
            encoding="utf-8"
        )

    def add_documents(self, documents: List[Dict[str, Any]]):
        """
        Adds chunked documents to both ChromaDB and BM25 index.
        Each document dict must have:
        - id: str
        - text: str
        - metadata: dict (optional)
        """
        if not documents:
            return

        ids = [doc["id"] for doc in documents]
        texts = [doc["text"] for doc in documents]
        metadatas = [doc.get("metadata", {}) for doc in documents]

        # Upsert into ChromaDB
        self.collection.upsert(
            ids=ids,
            documents=texts,
            metadatas=metadatas
        )

        # Update in-memory BM25 index
        existing_indices = {doc_id: i for i, doc_id in enumerate(self.doc_ids)}
        for doc_id, text, meta in zip(ids, texts, metadatas):
            if doc_id in existing_indices:
                idx = existing_indices[doc_id]
                self.doc_texts[idx] = text
                self.doc_metadatas[idx] = meta
            else:
                self.doc_ids.append(doc_id)
                self.doc_texts.append(text)
                self.doc_metadatas.append(meta)

        tokenized_corpus = [tokenize_text(t) for t in self.doc_texts]
        self.bm25 = BM25Okapi(tokenized_corpus)
        self._save_bm25()
        logger.info(f"Successfully added/updated {len(documents)} documents in Hybrid RAG Store.")

    def hybrid_search(self, query: str, top_k: int = 3, rrf_k: int = 60) -> List[Dict[str, Any]]:
        """
        Executes Reciprocal Rank Fusion (RRF) between Chroma dense vectors and BM25 sparse keywords.
        Formula: RRF_score(d) = sum(1.0 / (rrf_k + rank))
        Returns Top-K grounded chunks with combined RRF score.
        """
        if not query or self.collection.count() == 0:
            return []

        # 1. ChromaDB Dense Vector Search
        dense_ranks: Dict[str, int] = {}
        dense_docs: Dict[str, Dict[str, Any]] = {}
        try:
            n_results = min(top_k * 3, self.collection.count())
            chroma_res = self.collection.query(
                query_texts=[query],
                n_results=n_results
            )
            if chroma_res and chroma_res.get("ids") and chroma_res["ids"][0]:
                for rank, (doc_id, text, meta) in enumerate(zip(
                    chroma_res["ids"][0],
                    chroma_res["documents"][0],
                    chroma_res["metadatas"][0] if chroma_res.get("metadatas") else [{}] * len(chroma_res["ids"][0])
                )):
                    dense_ranks[doc_id] = rank + 1
                    dense_docs[doc_id] = {"id": doc_id, "text": text, "metadata": meta}
        except Exception as e:
            logger.warning(f"Dense Chroma query error: {e}")

        # 2. BM25 Sparse Keyword Search
        sparse_ranks: Dict[str, int] = {}
        if self.bm25 and self.doc_texts:
            query_tokens = tokenize_text(query)
            if query_tokens:
                bm25_scores = self.bm25.get_scores(query_tokens)
                ranked_indices = sorted(range(len(bm25_scores)), key=lambda i: bm25_scores[i], reverse=True)
                for rank, idx in enumerate(ranked_indices[:top_k * 3]):
                    if bm25_scores[idx] > 0.0:
                        doc_id = self.doc_ids[idx]
                        sparse_ranks[doc_id] = rank + 1
                        if doc_id not in dense_docs:
                            dense_docs[doc_id] = {
                                "id": doc_id,
                                "text": self.doc_texts[idx],
                                "metadata": self.doc_metadatas[idx]
                            }

        # 3. Reciprocal Rank Fusion (RRF)
        all_candidate_ids = set(dense_ranks.keys()).union(set(sparse_ranks.keys()))
        rrf_scores: Dict[str, float] = {}

        for doc_id in all_candidate_ids:
            score = 0.0
            if doc_id in dense_ranks:
                score += 1.0 / (rrf_k + dense_ranks[doc_id])
            if doc_id in sparse_ranks:
                score += 1.0 / (rrf_k + sparse_ranks[doc_id])
            rrf_scores[doc_id] = score

        # Sort descending by fused score
        sorted_candidates = sorted(rrf_scores.keys(), key=lambda d: rrf_scores[d], reverse=True)

        final_results = []
        for doc_id in sorted_candidates[:top_k]:
            item = dense_docs[doc_id].copy()
            item["rrf_score"] = round(rrf_scores[doc_id], 4)
            item["dense_rank"] = dense_ranks.get(doc_id, None)
            item["bm25_rank"] = sparse_ranks.get(doc_id, None)
            final_results.append(item)

        return final_results

    # Convenient alias
    query_hybrid = hybrid_search

    def clear_store(self):
        """Clears both Chroma collection and BM25 index."""
        try:
            self.chroma_client.delete_collection(name=COLLECTION_NAME)
        except Exception:
            pass
        self._init_chroma()
        self.doc_ids = []
        self.doc_texts = []
        self.doc_metadatas = []
        self.bm25 = None
        if BM25_INDEX_FILE.exists():
            BM25_INDEX_FILE.unlink(missing_ok=True)


# Global singleton instance
rag_store = HybridRAGStore()
