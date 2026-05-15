"""Test config.py — bowl.yaml 配置加载器

Covers:
- Happy path: load from real bowl.yaml
- Missing bowl.yaml → defaults
- env var overrides
- Equality
- Singleton cache
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

# Bypass broken __init__.py import chain — load config directly.
_config_ns = {}
exec(open(Path(__file__).resolve().parent.parent / "memory_mcp" / "config.py", encoding="utf-8").read(), _config_ns)
Config = _config_ns["Config"]


class TestConfigBasic(unittest.TestCase):
    """Happy path: raw Config() with all defaults."""

    def test_default_values(self):
        cfg = Config()
        self.assertEqual(cfg.embedding.model, "qwen3-embedding-0.6b")
        self.assertEqual(cfg.embedding.dim, 1024)
        self.assertEqual(cfg.decay.tau, 10.71)
        self.assertEqual(cfg.decay.initial_strength, 1.0)
        self.assertEqual(cfg.decay.floor, 0.01)
        self.assertEqual(cfg.retrieval.candidate_limit, 45)
        self.assertEqual(cfg.retrieval.result_limit, 5)
        self.assertEqual(cfg.retrieval.freshness_weight, 0.368)
        self.assertEqual(cfg.sansheng_stone.shrink_factor, 0.368)
        self.assertEqual(cfg.dedup.threshold, 0.95)
        self.assertEqual(cfg.chunk.size_min, 160)
        self.assertEqual(cfg.chunk.size_max, 500)
        self.assertEqual(cfg.server.ollama_base_url, "http://127.0.0.1:11434")
        self.assertEqual(cfg.server.mcp_port, 18081)
        self.assertEqual(cfg.server.mcp_name, "MengPo Memory Server")
        self.assertEqual(cfg.server.rerank_model, "qwen3-reranker-0.6b")
        self.assertEqual(cfg.storage.db_path, "./mengpo_memory.db")
        self.assertEqual(cfg.storage.log_path, "./mcp_access.log")
        self.assertEqual(cfg.injection.memory_dir, "./memory")
        self.assertEqual(cfg.injection.file_pattern, "*.md")
        self.assertEqual(cfg.injection.batch_size, 15)
        self.assertEqual(cfg.rebuild.warn_max_files, 250_000)
        self.assertEqual(cfg.rebuild.hard_max_files, 500_000)
        self.assertEqual(cfg.rebuild.warn_max_bytes, 25 * 1024 * 1024 * 1024)
        self.assertEqual(cfg.rebuild.hard_max_bytes, 50 * 1024 * 1024 * 1024)

    def test_equality(self):
        cfg1 = Config()
        cfg2 = Config()
        self.assertEqual(cfg1, cfg2)

    def test_different_not_equal(self):
        cfg1 = Config()
        cfg2 = Config(embedding=_config_ns["EmbeddingConfig"](model="other-model"))
        self.assertNotEqual(cfg1, cfg2)

    def test_repr(self):
        cfg = Config()
        r = repr(cfg)
        self.assertIn("embedding", r)
        self.assertIn("decay", r)
        self.assertIn("retrieval", r)


class TestConfigLoad(unittest.TestCase):
    """Loading from bowl.yaml or fallback."""

    def test_load_with_bowl_file(self):
        """Load from the real bowl.yaml in the repo root."""
        repo_root = Path(__file__).resolve().parent.parent
        bowl = repo_root / "bowl.yaml"
        self.assertTrue(bowl.is_file(), "bowl.yaml must exist for this test")
        cfg = Config.load(str(bowl))
        self.assertEqual(cfg.decay.tau, 10.71)
        self.assertEqual(cfg.injection.memory_dir, "./memory")
        self.assertEqual(cfg.injection.file_pattern, "*.md")
        self.assertEqual(cfg.storage.db_path, "./mengpo_memory.db")
        self.assertEqual(cfg.retrieval.candidate_limit, 45)
        self.assertEqual(cfg.chunk.size_max, 500)

    def test_load_with_missing_file_falls_back(self):
        """Missing bowl.yaml → fall back to code defaults."""
        fake_path = "/nonexistent/bowl.yaml"
        cfg = Config.load(fake_path)
        self.assertEqual(cfg.decay.tau, 10.71)
        self.assertEqual(cfg.injection.memory_dir, "./memory")


class TestConfigEnvOverride(unittest.TestCase):
    """Environment variables override YAML values."""

    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in [
            "MENGPO_DB_PATH", "MENGPO_MEMORY_DIR", "MENGPO_OLLAMA_URL",
            "MENGPO_OLLAMA_MODEL", "MENGPO_MCP_PORT", "MENGPO_BATCH_SIZE",
        ]}

    def tearDown(self):
        for k, v in self._saved.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)
        Config.reset_cache()

    def test_env_overrides_db_path(self):
        os.environ["MENGPO_DB_PATH"] = "/custom/path/db.sqlite"
        cfg = Config.load()
        self.assertEqual(cfg.storage.db_path, "/custom/path/db.sqlite")

    def test_env_overrides_memory_dir(self):
        os.environ["MENGPO_MEMORY_DIR"] = "/custom/memory"
        cfg = Config.load()
        self.assertEqual(cfg.injection.memory_dir, "/custom/memory")

    def test_env_overrides_ollama_url(self):
        os.environ["MENGPO_OLLAMA_URL"] = "http://custom:1234"
        cfg = Config.load()
        self.assertEqual(cfg.server.ollama_base_url, "http://custom:1234")

    def test_env_overrides_model(self):
        os.environ["MENGPO_OLLAMA_MODEL"] = "test-model"
        cfg = Config.load()
        self.assertEqual(cfg.embedding.model, "test-model")

    def test_env_overrides_mcp_port(self):
        os.environ["MENGPO_MCP_PORT"] = "9999"
        cfg = Config.load()
        self.assertEqual(cfg.server.mcp_port, 9999)

    def test_env_empty_string_doesnt_override(self):
        os.environ["MENGPO_DB_PATH"] = ""
        cfg = Config.load()
        self.assertEqual(cfg.storage.db_path, "./mengpo_memory.db")

    def test_env_overrides_batch_size(self):
        os.environ["MENGPO_BATCH_SIZE"] = "30"
        cfg = Config.load()
        self.assertEqual(cfg.injection.batch_size, 30)


class TestConfigSingletons(unittest.TestCase):
    """load_cached and reset_cache."""

    def tearDown(self):
        Config.reset_cache()

    def test_load_cached_returns_same_instance(self):
        cfg1 = Config.load_cached()
        cfg2 = Config.load_cached()
        self.assertIs(cfg1, cfg2)

    def test_reset_cache_creates_new_instance(self):
        cfg1 = Config.load_cached()
        Config.reset_cache()
        cfg2 = Config.load_cached()
        self.assertIsNot(cfg1, cfg2)

    def test_load_always_returns_new_instance(self):
        cfg1 = Config.load()
        cfg2 = Config.load()
        self.assertIsNot(cfg1, cfg2)


class TestConfigDingzhen(unittest.TestCase):
    """dingzhen() health check."""

    def test_dingzhen_output(self):
        cfg = Config()
        output = cfg.dingzhen()
        self.assertIn("embedding", output)
        self.assertIn("decay", output)
        self.assertIn("retrieval", output)
        self.assertIn("injection", output)
        self.assertIn("memory_dir", output)


if __name__ == "__main__":
    unittest.main()
