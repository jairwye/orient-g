from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from backend.services import knowledge_pipeline as kp
from backend.services.kb_vector_store import _pgvector_literal, search_doc_chunks


class TestPgvectorLiteral(unittest.TestCase):
    def test_pgvector_literal_bracket_format(self):
        s = _pgvector_literal([0.1, -0.2, 1.0])
        self.assertTrue(s.startswith("["))
        self.assertTrue(s.endswith("]"))
        self.assertIn("0.1", s)
        self.assertIn("-0.2", s)

    def test_search_uses_cast_as_vector(self):
        captured: dict = {}

        def fake_execute(stmt, params=None):
            captured["sql"] = str(stmt)
            captured["params"] = params or {}
            return MagicMock(fetchall=lambda: [])

        mock_db = MagicMock()
        mock_db.execute = fake_execute
        mock_cm = MagicMock()
        mock_cm.__enter__ = lambda s: mock_db
        mock_cm.__exit__ = lambda s, *a: None

        with patch("backend.services.kb_vector_store.vector_enabled", return_value=True):
            with patch("backend.services.kb_vector_store.embed_texts", return_value=[[0.1] * 1024]):
                with patch("backend.services.kb_vector_store.get_db", return_value=mock_cm):
                    with patch("backend.services.kb_vector_store.settings") as st:
                        st.ollama_embed_model = "bge-m3"
                        st.kb_embedding_dim = 1024
                        search_doc_chunks(
                            "tenant1",
                            query="华清营业收入",
                            candidate_doc_ids=["ud_abc"],
                            k=3,
                        )
        self.assertIn("CAST(:qv AS vector)", captured["sql"])
        qv = captured["params"].get("qv")
        self.assertIsInstance(qv, str)
        self.assertTrue(str(qv).startswith("["))


class TestRetrievalTermExpansion(unittest.TestCase):
    def test_expand_adds_yingyeshouru_when_query_has_yingshou(self):
        terms = kp._expand_retrieval_terms(["华清", "营收"], "华清25年的营收是多少")
        self.assertIn("营业收入", terms)

    def test_expand_adds_profit_table_hints(self):
        terms = kp._expand_retrieval_terms(["华清", "营收"], "华清25年的营收是多少")
        self.assertTrue(any(t in terms for t in ("利润表", "主要会计数据")))

    def test_expand_adds_terms_for_pl_compare_query(self):
        terms = kp._expand_retrieval_terms(["华清", "损益"], "华清25、24两年损益对比")
        self.assertIn("利润表", terms)
        self.assertTrue("2024" in terms or "2025" in terms)


class TestChunkScoring(unittest.TestCase):
    def test_revenue_chunk_outranks_entity_only_notes(self):
        q = "华清25年的营收是多少"
        terms = kp._expand_retrieval_terms(kp._tokenize_query(q), q)
        entity_only = ("## 审计报告附注\n" + "华清股份有限公司税率说明。\n") * 15
        revenue_table = (
            "## 主要会计数据和财务指标\n"
            "华清股份有限公司 2025 年度\n"
            "| 项目 | 2025年 |\n| 营业收入 | 834,527,936.00 |\n"
        )
        s_entity = kp._score_chunk_for_retrieval(entity_only, terms, q)
        s_revenue = kp._score_chunk_for_retrieval(revenue_table, terms, q)
        self.assertGreater(s_revenue, s_entity)

    def test_compound_yingyeshouru_boosts_even_if_term_is_yingshou_only(self):
        q = "华清25年的营收是多少"
        terms = kp._expand_retrieval_terms(kp._tokenize_query(q), q)
        txt = "## section\n营业收入 123456789.00 华清"
        score = kp._score_chunk_for_retrieval(txt, terms, q)
        self.assertGreaterEqual(score, 100)


class TestHybridRetrieveIntegration(unittest.TestCase):
    def test_hybrid_prefers_revenue_doc_over_entity_doc(self):
        revenue_doc = "ud_revenue"
        entity_doc = "ud_entity"
        revenue_chunk = (
            "## 合并利润表\n华清 2025 营业收入 834,527,936.00\n"
        )
        entity_chunk = ("## 附注\n华清 华清 华清 税率 审计意见\n") * 10

        def fake_kw(tenant_id, *, doc_ids, query, limit):
            q = kp._normalize_query(query)
            terms = kp._expand_retrieval_terms(kp._tokenize_query(q), q)
            out = []
            for did, txt in (
                (revenue_doc, revenue_chunk),
                (entity_doc, entity_chunk),
            ):
                if did not in doc_ids:
                    continue
                sc = kp._score_chunk_for_retrieval(txt, terms, q)
                out.append(
                    {
                        "doc_id": did,
                        "chunk_id": f"{did}_c1",
                        "chunk_seq_no": 1,
                        "_kw_score": sc,
                    }
                )
            out.sort(key=lambda x: -x["_kw_score"])
            return out[:limit]

        with patch.object(kp, "vector_enabled", return_value=False):
            with patch.object(kp, "_retrieve_uploaded_doc_chunks", side_effect=fake_kw):
                hits = kp._hybrid_retrieve(
                    "tenant1",
                    query="华清25年的营收是多少",
                    candidate_doc_ids={revenue_doc, entity_doc},
                    k=5,
                )
        self.assertTrue(hits)
        self.assertEqual(hits[0]["doc_id"], revenue_doc)


if __name__ == "__main__":
    unittest.main()
