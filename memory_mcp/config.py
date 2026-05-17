# =============================================================================
#  config.py  —  孟婆汤碗加载器
# =============================================================================
#
#  读取 bowl.yaml，将乾（算法参数）+ 坤（运维参数）映射为 SimpleConfig（类似命名元组）。
#  环境变量 > YAML > 代码默认值。优先级：env → bowl.yaml → hardcoded default。
#
#  用法：
#      from memory_mcp.config import Config
#      cfg = Config.load()
#      cfg.storage.db_path
#      cfg.injection.memory_dir
# =============================================================================

import os
from pathlib import Path
from typing import Any


# ── 乾：算法参数 ──────────────────────────────────────────────────────────


class EmbeddingConfig:
    __slots__ = ("model", "dim")

    def __init__(self, model: str = "qwen3-embedding-0.6b", dim: int = 1024):
        self.model = model
        self.dim = dim

    def __repr__(self) -> str:
        return f"EmbeddingConfig(model={self.model!r}, dim={self.dim})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, EmbeddingConfig):
            return NotImplemented
        return self.model == other.model and self.dim == other.dim


class DecayConfig:
    __slots__ = ("tau", "initial_strength", "floor")

    def __init__(self, tau: float = 10.71, initial_strength: float = 1.0, floor: float = 0.01):
        self.tau = tau
        self.initial_strength = initial_strength
        self.floor = floor

    def __repr__(self) -> str:
        return f"DecayConfig(tau={self.tau}, initial_strength={self.initial_strength}, floor={self.floor})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DecayConfig):
            return NotImplemented
        return (self.tau == other.tau and self.initial_strength == other.initial_strength
                and self.floor == other.floor)


class RetrievalConfig:
    __slots__ = ("candidate_limit", "result_limit", "freshness_weight", "log_s1_stats")

    def __init__(self, candidate_limit: int = 45, result_limit: int = 5,
                 freshness_weight: float = 0.368, log_s1_stats: bool = False):
        self.candidate_limit = candidate_limit
        self.result_limit = result_limit
        self.freshness_weight = freshness_weight
        self.log_s1_stats = log_s1_stats

    def __repr__(self) -> str:
        return f"RetrievalConfig(candidate_limit={self.candidate_limit}, result_limit={self.result_limit}, freshness_weight={self.freshness_weight}, log_s1_stats={self.log_s1_stats})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, RetrievalConfig):
            return NotImplemented
        return (self.candidate_limit == other.candidate_limit
                and self.result_limit == other.result_limit
                and self.freshness_weight == other.freshness_weight
                and self.log_s1_stats == other.log_s1_stats)


class SanshengStoneConfig:
    __slots__ = ("shrink_factor",)

    def __init__(self, shrink_factor: float = 0.368):
        self.shrink_factor = shrink_factor

    def __repr__(self) -> str:
        return f"SanshengStoneConfig(shrink_factor={self.shrink_factor})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SanshengStoneConfig):
            return NotImplemented
        return self.shrink_factor == other.shrink_factor


class DedupConfig:
    __slots__ = ("threshold",)

    def __init__(self, threshold: float = 0.95):
        self.threshold = threshold

    def __repr__(self) -> str:
        return f"DedupConfig(threshold={self.threshold})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DedupConfig):
            return NotImplemented
        return self.threshold == other.threshold


class ChunkConfig:
    __slots__ = ("size_min", "size_max")

    def __init__(self, size_min: int = 160, size_max: int = 500):
        self.size_min = size_min
        self.size_max = size_max

    def __repr__(self) -> str:
        return f"ChunkConfig(size_min={self.size_min}, size_max={self.size_max})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ChunkConfig):
            return NotImplemented
        return self.size_min == other.size_min and self.size_max == other.size_max


# ── 坤：运维参数 ──────────────────────────────────────────────────────────


class ServerConfig:
    __slots__ = ("ollama_base_url", "mcp_port", "mcp_name", "rerank_model")

    def __init__(self, ollama_base_url: str = "http://127.0.0.1:11434",
                 mcp_port: int = 18081,
                 mcp_name: str = "MengPo Memory Server",
                 rerank_model: str = "qwen3-reranker-0.6b"):
        self.ollama_base_url = ollama_base_url
        self.mcp_port = mcp_port
        self.mcp_name = mcp_name
        self.rerank_model = rerank_model

    def __repr__(self) -> str:
        return f"ServerConfig(url={self.ollama_base_url!r}, port={self.mcp_port}, name={self.mcp_name!r}, rerank={self.rerank_model!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ServerConfig):
            return NotImplemented
        return (self.ollama_base_url == other.ollama_base_url
                and self.mcp_port == other.mcp_port
                and self.mcp_name == other.mcp_name
                and self.rerank_model == other.rerank_model)


class StorageConfig:
    __slots__ = ("db_path", "log_path", "debug_log_to_file", "debug_log_path")

    def __init__(self, db_path: str = "./mengpo_memory.db", log_path: str = "./mcp_access.log",
                 debug_log_to_file: bool = False, debug_log_path: str = "./mcp_debug.log"):
        self.db_path = db_path
        self.log_path = log_path
        self.debug_log_to_file = debug_log_to_file
        self.debug_log_path = debug_log_path

    def __repr__(self) -> str:
        return (
            f"StorageConfig(db_path={self.db_path!r}, log_path={self.log_path!r}, "
            f"debug_log_to_file={self.debug_log_to_file!r}, debug_log_path={self.debug_log_path!r})"
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, StorageConfig):
            return NotImplemented
        return (
            self.db_path == other.db_path
            and self.log_path == other.log_path
            and self.debug_log_to_file == other.debug_log_to_file
            and self.debug_log_path == other.debug_log_path
        )


class InjectionConfig:
    __slots__ = ("memory_dir", "file_pattern", "batch_size")

    def __init__(self, memory_dir: str = "./memory", file_pattern: str = "*.md", batch_size: int = 15):
        self.memory_dir = memory_dir
        self.file_pattern = file_pattern
        self.batch_size = batch_size

    def __repr__(self) -> str:
        return f"InjectionConfig(memory_dir={self.memory_dir!r}, file_pattern={self.file_pattern!r}, batch_size={self.batch_size})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, InjectionConfig):
            return NotImplemented
        return (self.memory_dir == other.memory_dir and self.file_pattern == other.file_pattern
                and self.batch_size == other.batch_size)


class RebuildConfig:
    __slots__ = ("warn_max_files", "hard_max_files", "warn_max_bytes", "hard_max_bytes")

    def __init__(self, warn_max_files: int = 250_000,
                 hard_max_files: int = 500_000,
                 warn_max_bytes: int = 25 * 1024 * 1024 * 1024,
                 hard_max_bytes: int = 50 * 1024 * 1024 * 1024):
        self.warn_max_files = warn_max_files
        self.hard_max_files = hard_max_files
        self.warn_max_bytes = warn_max_bytes
        self.hard_max_bytes = hard_max_bytes

    def __repr__(self) -> str:
        return f"RebuildConfig(warn_files={self.warn_max_files}, hard_files={self.hard_max_files}, warn_bytes={self.warn_max_bytes}, hard_bytes={self.hard_max_bytes})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, RebuildConfig):
            return NotImplemented
        return (self.warn_max_files == other.warn_max_files
                and self.hard_max_files == other.hard_max_files
                and self.warn_max_bytes == other.warn_max_bytes
                and self.hard_max_bytes == other.hard_max_bytes)


# ── 顶层 ──────────────────────────────────────────────────────────────────


class Config:
    """Complete MengPo configuration from bowl.yaml + env overrides.

    Construct via ``Config.load()`` which reads bowl.yaml and applies
    environment variable overrides.
    """

    __slots__ = ("embedding", "decay", "retrieval", "sansheng_stone",
                 "dedup", "chunk", "server", "storage", "injection", "rebuild")

    def __init__(self, embedding=None, decay=None, retrieval=None,
                 sansheng_stone=None, dedup=None, chunk=None,
                 server=None, storage=None, injection=None, rebuild=None):
        self.embedding = embedding or EmbeddingConfig()
        self.decay = decay or DecayConfig()
        self.retrieval = retrieval or RetrievalConfig()
        self.sansheng_stone = sansheng_stone or SanshengStoneConfig()
        self.dedup = dedup or DedupConfig()
        self.chunk = chunk or ChunkConfig()
        self.server = server or ServerConfig()
        self.storage = storage or StorageConfig()
        self.injection = injection or InjectionConfig()
        self.rebuild = rebuild or RebuildConfig()

    def __repr__(self) -> str:
        return (f"Config(embedding={self.embedding}, decay={self.decay}, "
                f"retrieval={self.retrieval}, sansheng_stone={self.sansheng_stone}, "
                f"dedup={self.dedup}, chunk={self.chunk}, server={self.server}, "
                f"storage={self.storage}, injection={self.injection}, rebuild={self.rebuild})")

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Config):
            return NotImplemented
        return (self.embedding == other.embedding
                and self.decay == other.decay
                and self.retrieval == other.retrieval
                and self.sansheng_stone == other.sansheng_stone
                and self.dedup == other.dedup
                and self.chunk == other.chunk
                and self.server == other.server
                and self.storage == other.storage
                and self.injection == other.injection
                and self.rebuild == other.rebuild)

    # ── class-level singleton cache ──
    _instance = None

    @classmethod
    def load(cls, bowl_path=None):
        """Load configuration from bowl.yaml, with optional env overrides.

        If *bowl_path* is given, load from that path.  Otherwise search
        upward from CWD and from the repo root.
        """
        raw = {}

        if bowl_path is not None:
            path = Path(bowl_path)
            if path.is_file():
                raw = _load_yaml(path)
        else:
            path = _find_bowl_yaml()
            if path is not None:
                raw = _load_yaml(path)

        cfg = cls._from_dict(raw)
        cfg = cls._apply_env_overrides(cfg)
        return cfg

    @classmethod
    def load_cached(cls, bowl_path=None):
        """Like load() but cache the result so repeated calls are free."""
        if cls._instance is None:
            cls._instance = cls.load(bowl_path)
        return cls._instance

    @classmethod
    def reset_cache(cls):
        cls._instance = None

    # ── internal helpers ─────────────────────────────────────────────────

    @staticmethod
    def _from_dict(raw):
        # Use code defaults as baseline, override with YAML values when present
        d = Config()
        return Config(
            embedding=EmbeddingConfig(
                model=_g_or(raw, "embedding", "model", typ=str, default=d.embedding.model),
                dim=_g_or(raw, "embedding", "dim", typ=int, default=d.embedding.dim),
            ),
            decay=DecayConfig(
                tau=_g_or(raw, "decay", "tau", typ=float, default=d.decay.tau),
                initial_strength=_g_or(raw, "decay", "initial_strength", typ=float, default=d.decay.initial_strength),
                floor=_g_or(raw, "decay", "floor", typ=float, default=d.decay.floor),
            ),
            retrieval=RetrievalConfig(
                candidate_limit=_g_or(raw, "retrieval", "candidate_limit", typ=int, default=d.retrieval.candidate_limit),
                result_limit=_g_or(raw, "retrieval", "result_limit", typ=int, default=d.retrieval.result_limit),
                freshness_weight=_g_or(raw, "retrieval", "freshness_weight", typ=float, default=d.retrieval.freshness_weight),
                log_s1_stats=_g_or(raw, "retrieval", "log_s1_stats", typ=bool, default=d.retrieval.log_s1_stats),
            ),
            sansheng_stone=SanshengStoneConfig(
                shrink_factor=_g_or(raw, "sansheng_stone", "shrink_factor", typ=float, default=d.sansheng_stone.shrink_factor),
            ),
            dedup=DedupConfig(
                threshold=_g_or(raw, "dedup", "threshold", typ=float, default=d.dedup.threshold),
            ),
            chunk=ChunkConfig(
                size_min=_g_or(raw, "chunk", "size_min", typ=int, default=d.chunk.size_min),
                size_max=_g_or(raw, "chunk", "size_max", typ=int, default=d.chunk.size_max),
            ),
            server=ServerConfig(
                ollama_base_url=_g_or(raw, "server", "ollama_base_url", typ=str, default=d.server.ollama_base_url),
                mcp_port=_g_or(raw, "server", "mcp_port", typ=int, default=d.server.mcp_port),
                mcp_name=_g_or(raw, "server", "mcp_name", typ=str, default=d.server.mcp_name),
                rerank_model=_g_or(raw, "server", "rerank_model", typ=str, default=d.server.rerank_model),
            ),
            storage=StorageConfig(
                db_path=_g_or(raw, "storage", "db_path", typ=str, default=d.storage.db_path),
                log_path=_g_or(raw, "storage", "log_path", typ=str, default=d.storage.log_path),
                debug_log_to_file=_g_or(raw, "storage", "debug_log_to_file", typ=bool, default=d.storage.debug_log_to_file),
                debug_log_path=_g_or(raw, "storage", "debug_log_path", typ=str, default=d.storage.debug_log_path),
            ),
            injection=InjectionConfig(
                memory_dir=_g_or(raw, "injection", "memory_dir", typ=str, default=d.injection.memory_dir),
                file_pattern=_g_or(raw, "injection", "file_pattern", typ=str, default=d.injection.file_pattern),
                batch_size=_g_or(raw, "injection", "batch_size", typ=int, default=d.injection.batch_size),
            ),
            rebuild=RebuildConfig(
                warn_max_files=_g_or(raw, "rebuild", "warn_max_files", typ=int, default=d.rebuild.warn_max_files),
                hard_max_files=_g_or(raw, "rebuild", "hard_max_files", typ=int, default=d.rebuild.hard_max_files),
                warn_max_bytes=_g_or(raw, "rebuild", "warn_max_bytes", typ=int, default=d.rebuild.warn_max_bytes),
                hard_max_bytes=_g_or(raw, "rebuild", "hard_max_bytes", typ=int, default=d.rebuild.hard_max_bytes),
            ),
        )

    @staticmethod
    def _apply_env_overrides(cfg):
        """Environment variables override YAML values.

        MENGPO_DB_PATH         -> storage.db_path
        MENGPO_LOG_PATH        -> storage.log_path
        MENGPO_MEMORY_DIR      -> injection.memory_dir
        MENGPO_OLLAMA_URL      -> server.ollama_base_url
        MENGPO_OLLAMA_MODEL    -> embedding.model
        MENGPO_CHUNK_MAX_SIZE  -> chunk.size_max
        MENGPO_CHUNK_MIN_SIZE  -> chunk.size_min
        MENGPO_BATCH_SIZE      -> injection.batch_size
        MENGPO_CANDIDATE_LIMIT -> retrieval.candidate_limit
        MENGPO_RESULT_LIMIT    -> retrieval.result_limit
        MENGPO_MCP_PORT        -> server.mcp_port
        MENGPO_MCP_NAME         -> server.mcp_name
        """
        def _ov(key):
            v = os.environ.get(key)
            return v if v and v.strip() else None

        return Config(
            embedding=EmbeddingConfig(
                model=_ov("MENGPO_OLLAMA_MODEL") or cfg.embedding.model,
                dim=cfg.embedding.dim,
            ),
            decay=cfg.decay,
            retrieval=RetrievalConfig(
                candidate_limit=int(_ov("MENGPO_CANDIDATE_LIMIT")) if _ov("MENGPO_CANDIDATE_LIMIT") is not None else cfg.retrieval.candidate_limit,
                result_limit=int(_ov("MENGPO_RESULT_LIMIT")) if _ov("MENGPO_RESULT_LIMIT") is not None else cfg.retrieval.result_limit,
                freshness_weight=cfg.retrieval.freshness_weight,
                log_s1_stats=cfg.retrieval.log_s1_stats,
            ),
            sansheng_stone=cfg.sansheng_stone,
            dedup=cfg.dedup,
            chunk=ChunkConfig(
                size_min=int(_ov("MENGPO_CHUNK_MIN_SIZE")) if _ov("MENGPO_CHUNK_MIN_SIZE") is not None else cfg.chunk.size_min,
                size_max=int(_ov("MENGPO_CHUNK_MAX_SIZE")) if _ov("MENGPO_CHUNK_MAX_SIZE") is not None else cfg.chunk.size_max,
            ),
            server=ServerConfig(
                ollama_base_url=_ov("MENGPO_OLLAMA_URL") or cfg.server.ollama_base_url,
                mcp_port=int(_ov("MENGPO_MCP_PORT")) if _ov("MENGPO_MCP_PORT") is not None else cfg.server.mcp_port,
                mcp_name=_ov("MENGPO_MCP_NAME") or cfg.server.mcp_name,
                rerank_model=cfg.server.rerank_model,
            ),
            storage=StorageConfig(
                db_path=_ov("MENGPO_DB_PATH") or cfg.storage.db_path,
                log_path=_ov("MENGPO_LOG_PATH") or cfg.storage.log_path,
                debug_log_to_file=cfg.storage.debug_log_to_file,
                debug_log_path=cfg.storage.debug_log_path,
            ),
            injection=InjectionConfig(
                memory_dir=_ov("MENGPO_MEMORY_DIR") or cfg.injection.memory_dir,
                file_pattern=cfg.injection.file_pattern,
                batch_size=int(_ov("MENGPO_BATCH_SIZE")) if _ov("MENGPO_BATCH_SIZE") is not None else cfg.injection.batch_size,
            ),
            rebuild=cfg.rebuild,
        )

    def dingzhen(self):
        """打印所有参数值用于验证"""
        parts = []
        for name, obj in [
            ("embedding", self.embedding),
            ("decay", self.decay),
            ("retrieval", self.retrieval),
            ("sansheng_stone", self.sansheng_stone),
            ("dedup", self.dedup),
            ("chunk", self.chunk),
            ("server", self.server),
            ("storage", self.storage),
            ("injection", self.injection),
            ("rebuild", self.rebuild),
        ]:
            parts.append(f"  {name}: {obj}")
        return "\n".join(parts)


# ── YAML 加载 ─────────────────────────────────────────────────────────────


def _load_yaml(path):
    """Load a YAML file and return a dict."""
    import yaml  # lazy import, may not be installed in all test envs
    text = path.read_text(encoding="utf-8")
    raw = yaml.safe_load(text) or {}
    return raw


def _find_bowl_yaml():
    """Search for bowl.yaml: CWD first, then repo root (parent of memory_mcp/)."""
    candidates = [
        Path.cwd() / "bowl.yaml",
    ]
    try:
        candidates.append(Path(__file__).resolve().parent.parent / "bowl.yaml")
    except NameError:
        pass  # loaded via exec(), __file__ not defined
    for p in candidates:
        if p.is_file():
            return p
    return None


def _g(raw, *keys, typ):
    """Safely get a nested value from the raw YAML dict.

    Returns ``typ()`` (e.g. 0 for int, 0.0 for float, '' for str) when
    the key path does not exist or conversion fails.
    """
    val = raw
    for key in keys:
        if not isinstance(val, dict):
            return typ()
        val = val.get(key)
        if val is None:
            return typ()
    try:
        return typ(val)
    except (TypeError, ValueError):
        return typ()


def _g_or(raw, *keys, typ, default):
    """Like _g() but returns *default* instead of ``typ()`` when missing."""
    val = raw
    for key in keys:
        if not isinstance(val, dict):
            return default
        val = val.get(key)
        if val is None:
            return default
    try:
        return typ(val)
    except (TypeError, ValueError):
        return default
