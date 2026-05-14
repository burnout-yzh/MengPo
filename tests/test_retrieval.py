from __future__ import annotations

import unittest
from unittest.mock import MagicMock, Mock

from memory_mcp.retrieval import (
    RESULT_LIMIT,
    ProtocolErrorCode,
    RetrievalProtocolError,
    SessionDeliveryState,
    SEMANTIC_CANDIDATE_LIMIT,
    RetrievalCandidate,
    Naihe_Bridge,
    make_s3_writeback_plan,
    process_retrieval_round,
    Samsara_Rank,
    validate_s2_effectiveness_map,
    S1_vector_search,
)


def candidate(memory_id: int, semantic: float, freshness: float) -> RetrievalCandidate:
    return RetrievalCandidate(
        memory_id=memory_id,
        content=f"memory-{memory_id}",
        semantic_score=semantic,
        freshness_score=freshness,
    )


class RetrievalRankingTests(unittest.TestCase):
    def test_returns_fixed_result_limit_when_enough_candidates(self) -> None:
        candidates = [candidate(i, 1.0 - i * 0.001, 0.0) for i in range(20)]

        ranked = Samsara_Rank(candidates)

        self.assertEqual(len(ranked), RESULT_LIMIT)
        self.assertEqual([item.rank_after for item in ranked], list(range(1, 6)))

    def test_returns_all_when_fewer_than_result_limit(self) -> None:
        candidates = [candidate(i, 1.0 - i * 0.01, 0.0) for i in range(3)]

        self.assertEqual(len(Samsara_Rank(candidates)), 3)

    def test_freshness_reranks_inside_semantic_candidate_set_only(self) -> None:
        candidates = [candidate(i, 1.0 - i * 0.001, 0.0) for i in range(SEMANTIC_CANDIDATE_LIMIT)]
        outside = candidate(999, 0.01, 1_000_000.0)

        ranked = Samsara_Rank(candidates + [outside])

        self.assertNotIn(999, [item.memory_id for item in ranked])

    def test_freshness_can_reorder_close_semantic_candidates(self) -> None:
        stale = candidate(1, 0.900, 0.0)
        fresh = candidate(2, 0.895, 1.0)

        ranked = Samsara_Rank([stale, fresh])

        self.assertEqual([item.memory_id for item in ranked], [2, 1])
        self.assertEqual(ranked[0].rank_before, 2)
        self.assertEqual(ranked[0].rank_after, 1)

    def test_weight_slider_can_prefer_semantic_or_freshness(self) -> None:
        semantic_first = candidate(1, 0.90, 0.10)
        freshness_first = candidate(2, 0.80, 0.99)

        semantic_ranked = Samsara_Rank([semantic_first, freshness_first], freshness_weight=0.0)
        freshness_ranked = Samsara_Rank([semantic_first, freshness_first], freshness_weight=1.0)

        self.assertEqual([item.memory_id for item in semantic_ranked], [1, 2])
        self.assertEqual([item.memory_id for item in freshness_ranked], [2, 1])

    def test_invalid_limits_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _ = Samsara_Rank([], candidate_limit=0)
        with self.assertRaises(ValueError):
            _ = Samsara_Rank([], result_limit=0)
        with self.assertRaises(ValueError):
            _ = Samsara_Rank([], candidate_limit=-2)
        with self.assertRaises(ValueError):
            _ = Samsara_Rank([], result_limit=-2)
        with self.assertRaises(ValueError):
            _ = Samsara_Rank([], freshness_weight=-0.1)
        with self.assertRaises(ValueError):
            _ = Samsara_Rank([], freshness_weight=1.1)

    def test_minus_one_limit_means_unlimited(self) -> None:
        candidates = [candidate(i, 1.0 - i * 0.001, 0.0) for i in range(20)]
        ranked = Samsara_Rank(candidates, candidate_limit=-1, result_limit=-1)
        self.assertEqual(len(ranked), 20)


class RetrievalProtocolTests(unittest.TestCase):
    def test_validate_accepts_full_01_map(self) -> None:
        validated = validate_s2_effectiveness_map((101, 102), {"101": 1, "102": 0})
        self.assertEqual(validated, {101: True, 102: False})

    def test_validate_rejects_missing_ids(self) -> None:
        with self.assertRaises(RetrievalProtocolError) as ctx:
            _ = validate_s2_effectiveness_map((101, 102), {"101": 1})
        self.assertEqual(ctx.exception.code, ProtocolErrorCode.MISSING_MEMORY_IDS)

    def test_validate_rejects_unknown_ids(self) -> None:
        with self.assertRaises(RetrievalProtocolError) as ctx:
            _ = validate_s2_effectiveness_map((101,), {"101": 1, "999": 0})
        self.assertEqual(ctx.exception.code, ProtocolErrorCode.UNKNOWN_MEMORY_IDS)

    def test_validate_rejects_non_01_values(self) -> None:
        with self.assertRaises(RetrievalProtocolError) as ctx:
            _ = validate_s2_effectiveness_map((101,), {"101": 2})
        self.assertEqual(ctx.exception.code, ProtocolErrorCode.INVALID_VALUE)

    def test_writeback_plan_marks_all_invalid(self) -> None:
        plan = make_s3_writeback_plan({101: False, 102: False})
        self.assertTrue(plan.all_invalid)
        self.assertEqual(plan.effective_ids, ())

    def test_writeback_plan_collects_effective_ids(self) -> None:
        plan = make_s3_writeback_plan({101: True, 102: False, 103: True})
        self.assertFalse(plan.all_invalid)
        self.assertEqual(plan.effective_ids, (101, 103))

    def test_round_no_hit_returns_no_writeback(self) -> None:
        outcome = process_retrieval_round([], s2_effectiveness_map=None)
        self.assertEqual(outcome.delivered.delivered_ids, ())
        self.assertIsNone(outcome.writeback_plan)

    def test_round_all_invalid(self) -> None:
        cands = [candidate(1, 0.9, 0.1), candidate(2, 0.8, 0.1)]
        delivery = Naihe_Bridge(cands)
        payload = {str(memory_id): 0 for memory_id in delivery.delivered_ids}
        outcome = process_retrieval_round(cands, s2_effectiveness_map=payload)
        self.assertIsNotNone(outcome.writeback_plan)
        self.assertTrue(outcome.writeback_plan.all_invalid)
        self.assertEqual(outcome.writeback_plan.effective_ids, ())

    def test_round_protocol_error_fails(self) -> None:
        cands = [candidate(1, 0.9, 0.1)]
        with self.assertRaises(RetrievalProtocolError):
            _ = process_retrieval_round(cands, s2_effectiveness_map={"1": 2})


class ExpandStateTests(unittest.TestCase):
    def test_session_state_excludes_previously_judged_items(self) -> None:
        state = SessionDeliveryState()
        state.record_judged_ids("s1", [1, 2])
        delivery = Naihe_Bridge(
            [candidate(1, 0.9, 0.1), candidate(2, 0.8, 0.1), candidate(3, 0.7, 0.1)],
            excluded_memory_ids=state.excluded_ids("s1"),
        )
        self.assertEqual(delivery.delivered_ids, (3,))

    def test_session_state_clear(self) -> None:
        state = SessionDeliveryState()
        state.record_judged_ids("s1", [1])
        self.assertEqual(state.excluded_ids("s1"), {1})
        state.clear_session("s1")
        self.assertEqual(state.excluded_ids("s1"), set())


class S1VectorSearchTests(unittest.TestCase):
    def test_sqlite_operational_error_is_wrapped(self) -> None:
        db = MagicMock()
        tx = db.transaction.return_value
        conn = tx.__enter__.return_value
        conn.execute.side_effect = __import__("sqlite3").OperationalError("no such table: chunks_vec")

        with self.assertRaises(RuntimeError) as ctx:
            _ = S1_vector_search(db=db, query="hello", embed_client=Mock(embed=Mock(return_value=[0.1, 0.2])))

        self.assertIn("sqlite-vec search failed", str(ctx.exception))


if __name__ == "__main__":
    _ = unittest.main()
