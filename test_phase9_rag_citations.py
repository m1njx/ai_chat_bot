import os
import unittest
from datetime import datetime, timezone, timedelta

import core


class TestPhase9RAGAndCitations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        print("\n--- [SETUP] RAG Retrieval & Citations Acceptance ---")
        cls.active_gen = core.get_active_generation_info()

    def test_01_active_generation_invariants(self):
        """Active Knowledge Generation 불변식 검증 (FAISS IndexFlatIP, 384 dim)"""
        self.assertIsNotNone(self.active_gen, "Active Generation이 존재해야 함")
        gen_id = self.active_gen.get("generation_id")
        doc_count = self.active_gen.get("document_count")
        dim = self.active_gen.get("dimension")
        metric = self.active_gen.get("metric")

        self.assertEqual(dim, 384)
        self.assertEqual(metric, "inner_product")
        self.assertGreater(doc_count, 0)
        self.assertEqual(core.RAG_MIN_SIMILARITY, 0.58)

        # 실제 로드하여 일치 여부 확인
        idx, docs, meta = core.load_index_with_metadata()
        self.assertEqual(idx.ntotal, doc_count)
        self.assertEqual(len(docs), doc_count)
        self.assertEqual(len(meta), doc_count)
        print(f"  [PASSED] Test 01: Generation Invariants: {gen_id} ({doc_count} docs, 384 dim, inner_product, threshold=0.58)")

    def test_02_relevance_and_empty_context_fallback(self):
        """무관한 질문(수학, 일반 코딩 등)에 대해 RAG Context가 비워지는지 검증"""
        irrelevant_questions = [
            "1+1은 뭐야?",
            "파이썬 리스트 정렬 방법 알려줘",
            "지구 둘레는 몇 킬로미터야?",
        ]
        for q in irrelevant_questions:
            prompt, sources = core.build_prompt_with_sources(q)
            # RAG_MIN_SIMILARITY(0.58) 미만으로 RAG 컨텍스트가 주입되지 않아야 함
            self.assertNotIn("<지식>", prompt, f"질문 '{q}'에 지식 블록이 삽입되지 않아야 함")
            self.assertEqual(len(sources), 0, f"질문 '{q}'의 출처는 비어 있어야 함")
        print("  [PASSED] Test 02: Irrelevant questions yield empty RAG context fallback")

    def test_03_freshness_policies(self):
        """Phase 7 Freshness 정책 검증 (Weather 24h, Stock 7d, News 30d, Upload indefinite)"""
        now = datetime.now(timezone.utc)

        # 1. Weather
        self.assertEqual(core.get_document_freshness({"type": "weather", "collected_at": now.isoformat()})[0], "fresh")
        self.assertEqual(core.get_document_freshness({"type": "weather", "collected_at": (now - timedelta(hours=10)).isoformat()})[0], "aging")
        self.assertEqual(core.get_document_freshness({"type": "weather", "collected_at": (now - timedelta(hours=25)).isoformat()})[0], "stale")

        # 2. Stock
        self.assertEqual(core.get_document_freshness({"type": "stock", "collected_at": now.isoformat()})[0], "fresh")
        self.assertEqual(core.get_document_freshness({"type": "stock", "collected_at": (now - timedelta(days=3)).isoformat()})[0], "aging")
        self.assertEqual(core.get_document_freshness({"type": "stock", "collected_at": (now - timedelta(days=10)).isoformat()})[0], "stale")

        # 3. News
        self.assertEqual(core.get_document_freshness({"type": "news", "collected_at": now.isoformat()})[0], "fresh")
        self.assertEqual(core.get_document_freshness({"type": "news", "collected_at": (now - timedelta(days=15)).isoformat()})[0], "aging")
        self.assertEqual(core.get_document_freshness({"type": "news", "collected_at": (now - timedelta(days=40)).isoformat()})[0], "stale")

        # 4. Upload
        self.assertEqual(core.get_document_freshness({"type": "upload", "title": "doc.pdf", "collected_at": "2020-01-01T00:00:00Z"})[0], "fresh")
        print("  [PASSED] Test 03: Freshness policies verified across all source categories")

    def test_04_temporal_query_distinction(self):
        """현재 시점 질문(오늘 날씨) vs 과거 기록 질문(특정 날짜 날씨) 구분 검증"""
        self.assertTrue(core.is_current_temporal_query("오늘 서울 날씨 어때?"))
        self.assertTrue(core.is_current_temporal_query("지금 날씨 알려줘"))
        self.assertFalse(core.is_current_temporal_query("2026년 9월 4일 서울 날씨 기록 알려줘"))

        # 과거 날짜 매칭 검사
        self.assertTrue(core.is_query_matching_doc_date("2026년 9월 4일 서울 날씨", "2026-09-04"))
        self.assertFalse(core.is_query_matching_doc_date("2026년 9월 4일 서울 날씨", "2026-08-01"))
        print("  [PASSED] Test 04: Current temporal query vs historical record query distinction")

    def test_05_citation_structure_and_matching(self):
        """Citation이 실제로 프롬프트에 채택된 문서만 포함하는지 검증"""
        # build_context_and_citations 단위 검증
        # 1+1 쿼리 -> context="" 및 citations=[]
        ctx, citations = core.build_context_and_citations("1+1은 뭐야?")
        self.assertEqual(ctx, "")
        self.assertEqual(len(citations), 0)

        # PDF 페이지 병합 검증
        raw_meta = [
            {"type": "upload", "title": "가이드.pdf", "page": 2, "file_id": "g1"},
            {"type": "upload", "title": "가이드.pdf", "page": 4, "file_id": "g1"},
            {"type": "upload", "title": "가이드.pdf", "page": 2, "file_id": "g1"},
        ]
        formatted = core._merge_and_format_citations(raw_meta)
        self.assertEqual(len(formatted), 1)
        self.assertEqual(formatted[0]["pages"], [2, 4])
        self.assertIn("2, 4페이지", formatted[0]["label"])
        print("  [PASSED] Test 05: Citation integrity and PDF page merging")


if __name__ == "__main__":
    unittest.main()
