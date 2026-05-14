"""Memory MCP package root.

The package currently exposes a foundation surface: atomic storage, database
helpers, and dataclasses used by the executable tests. Retrieval, embedding
I/O, MCP tool registration, and dedup orchestration remain under active
iteration.
"""

from .atomic_store import (
    AtomicStoreError,
    ChunkInput,
    FaultPoint,
    StoreResult,
    store_memory_atomic,
)
from .consistency import ConsistencyReport, run_consistency_check
from .database import Database, connect
from .dedup import (
    DEFAULT_DEDUP_THRESHOLD,
    DedupResolution,
    ReviewVerdict,
    SimilarityCandidate,
    default_merge_target,
    requires_review,
    resolve_review,
)
from .dedup_audit import DedupAuditEvent, append_dedup_audit_event, make_dedup_audit_event
from .embeddings import (
    EMBEDDING_RETRY_COUNT,
    EMBEDDING_TIMEOUT_SECONDS,
    EmbeddingError,
    OllamaEmbeddingClient,
)
from .reranker import (
    DEFAULT_RERANK_MODEL,
    RERANK_RETRY_COUNT,
    RERANK_TIMEOUT_SECONDS,
    OllamaRerankerClient,
    RerankError,
    RerankResult,
)
from .retrieval import (
    RESULT_LIMIT,
    SEMANTIC_CANDIDATE_LIMIT,
    RankedMemory,
    RetrievalCandidate,
    Samsara_Rank,
)
from .retrieval_service import RetrievalService
from .store_preflight import PreflightResult, run_store_preflight
from .store_flow import StoreFlowResult, apply_merge_append, orchestrate_store_memory

__all__ = [
    "AtomicStoreError",
    "ChunkInput",
    "ConsistencyReport",
    "Database",
    "DEFAULT_DEDUP_THRESHOLD",
    "DedupResolution",
    "DedupAuditEvent",
    "FaultPoint",
    "StoreResult",
    "StoreFlowResult",
    "EMBEDDING_RETRY_COUNT",
    "EMBEDDING_TIMEOUT_SECONDS",
    "EmbeddingError",
    "DEFAULT_RERANK_MODEL",
    "RERANK_RETRY_COUNT",
    "RERANK_TIMEOUT_SECONDS",
    "ReviewVerdict",
    "RESULT_LIMIT",
    "OllamaEmbeddingClient",
    "OllamaRerankerClient",
    "PreflightResult",
    "RankedMemory",
    "RetrievalCandidate",
    "RetrievalService",
    "RerankError",
    "RerankResult",
    "SimilarityCandidate",
    "SEMANTIC_CANDIDATE_LIMIT",
    "connect",
    "default_merge_target",
    "append_dedup_audit_event",
    "make_dedup_audit_event",
    "run_store_preflight",
    "orchestrate_store_memory",
    "apply_merge_append",
    "requires_review",
    "Samsara_Rank",
    "run_consistency_check",
    "resolve_review",
    "store_memory_atomic",
]
