import os
import sys
import shutil
import tempfile
import json
import time
import unittest
import uuid
from datetime import datetime, timezone, timedelta

# 격리된 임시 디렉토리를 APP_DATA_DIR로 설정하여 기존 데이터를 오염시키지 않음
TEST_REGRESSION_DIR = tempfile.mkdtemp(prefix="ai_bot_phase1_7_test_")
os.environ["APP_DATA_DIR"] = TEST_REGRESSION_DIR
os.environ["SECRET_KEY"] = "test_phase8_secret_key_1234567890"

import core
import api
from starlette.testclient import TestClient


class TestPhase1To7Regression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        print(f"\n--- [SETUP] Phase 1~7 Regression APP_DATA_DIR: {TEST_REGRESSION_DIR} ---")
        core._bootstrap_app_data_dir()
        cls.client = TestClient(api.app)

    @classmethod
    def tearDownClass(cls):
        print(f"\n--- [TEARDOWN] Cleaning up {TEST_REGRESSION_DIR} ---")
        shutil.rmtree(TEST_REGRESSION_DIR, ignore_errors=True)

    # --- [ Phase 1 & 2: UUID Chat CRUD, Memory & Window ] ---
    def test_01_uuid_chat_crud(self):
        # API 엔드포인트를 통한 생성 및 UUID4 검증
        res = self.client.post("/api/chats", json={"title": "테스트 대화"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        chat_id = data["id"]
        parsed = uuid.UUID(chat_id, version=4)
        self.assertEqual(parsed.hex, chat_id)
        self.assertEqual(data["title"], "테스트 대화")

        # 목록 조회
        list_res = self.client.get("/api/chats")
        self.assertEqual(list_res.status_code, 200)
        chats = list_res.json().get("chats", [])
        self.assertTrue(any(c["id"] == chat_id for c in chats))

        # 이름 변경
        ren_res = self.client.patch(f"/api/chats/{chat_id}", json={"title": "수정된 대화명"})
        self.assertEqual(ren_res.status_code, 200)
        self.assertEqual(ren_res.json()["title"], "수정된 대화명")

        # 삭제
        del_res = self.client.delete(f"/api/chats/{chat_id}")
        self.assertEqual(del_res.status_code, 200)

        # 삭제 후 목록 확인
        list_res2 = self.client.get("/api/chats")
        self.assertFalse(any(c["id"] == chat_id for c in list_res2.json().get("chats", [])))
        print("  [PASSED] Test 01: UUID Chat CRUD via REST API")

    def test_02_sliding_window_memory(self):
        # 14개 메시지 생성
        history = []
        for i in range(14):
            role = "user" if i % 2 == 0 else "assistant"
            history.append({"role": role, "content": f"메시지 {i}"})

        # core.format_history는 MAX_HISTORY_MESSAGES(10개) 슬라이딩 윈도우를 강제함
        formatted = core.format_history(history)
        self.assertIn("<대화기록>", formatted)
        self.assertIn("</대화기록>", formatted)

        # 0~3번 메시지는 잘려나가고 4~13번(최근 10개)만 포함되어야 함
        self.assertNotIn("메시지 0\n", formatted)
        self.assertNotIn("메시지 1\n", formatted)
        self.assertNotIn("메시지 2\n", formatted)
        self.assertNotIn("메시지 3\n", formatted)
        self.assertIn("메시지 4", formatted)
        self.assertIn("메시지 13", formatted)
        print("  [PASSED] Test 02: 10-message sliding window memory invariance")

    # --- [ Phase 3: Auth, HMAC v2 & Session Token TTL ] ---
    def test_03_auth_hmac_v2_and_ttl(self):
        # 1. 유효 토큰 발행 및 검증
        token = api._issue_token()
        self.assertIsNotNone(token)
        claims = api._verify_token(token)
        self.assertIsNotNone(claims)
        self.assertIn("expires_at", claims)

        # 2. 위변조 토큰 거부
        tampered_token = token + "xyz"
        self.assertIsNone(api._verify_token(tampered_token))

        # 3. 만료 토큰 거부 (과거 exp 시뮬레이션)
        sid = uuid.uuid4().hex
        past_iat = int(time.time()) - 7200
        past_exp = int(time.time()) - 3600
        payload = f"v2.{sid}.{past_iat}.{past_exp}"
        expired_token = f"{payload}.{api._sign(payload)}"
        self.assertIsNone(api._verify_token(expired_token))
        print("  [PASSED] Test 03: HMAC v2 session token integrity & TTL expiration")

    # --- [ Phase 4: Rate Limiting & Streaming Abort Persistence ] ---
    def test_04_rate_limiting(self):
        client_key = f"test_rate_client_{uuid.uuid4().hex}"
        limit = 5
        window = 60
        # 5번까지는 통과
        for _ in range(limit):
            self.assertTrue(api.rate_limit(client_key, limit, window))

        # 6번째는 차단
        self.assertFalse(api.rate_limit(client_key, limit, window))
        print("  [PASSED] Test 04: In-memory sliding window rate limiter")

    def test_05_abort_partial_persistence(self):
        # 대화 생성
        res = self.client.post("/api/chats", json={"title": "중단 테스트"})
        chat_id = res.json()["id"]

        sources = [{"type": "weather", "title": "서울 날씨", "label": "서울 날씨"}]
        partial_content = "생성 도중 사용자가 중단한 응답 내용입니다."

        def append_aborted(chats):
            chat = chats.get(chat_id)
            if chat:
                chat["messages"].append({"role": "user", "content": "날씨 알려줘"})
                chat["messages"].append({
                    "role": "assistant",
                    "content": partial_content,
                    "sources": sources,
                })
            return chats

        core.modify_chats("local", append_aborted)

        # 조회하여 부분 응답 및 출처 보존 확인
        stored_chats = core.load_chats("local")
        chat = stored_chats[chat_id]
        self.assertEqual(len(chat["messages"]), 2)
        last_msg = chat["messages"][-1]
        self.assertEqual(last_msg["role"], "assistant")
        self.assertEqual(last_msg["content"], partial_content)
        self.assertEqual(len(last_msg["sources"]), 1)
        self.assertEqual(last_msg["sources"][0]["type"], "weather")
        print("  [PASSED] Test 05: Streaming abort partial response and source persistence")

    # --- [ Phase 5: RAG Retrieval Quality & Threshold Filtering ] ---
    def test_06_rag_similarity_threshold(self):
        # RAG_MIN_SIMILARITY 상수가 0.58로 설정되어 있는지 검증
        self.assertEqual(core.RAG_MIN_SIMILARITY, 0.58)

        # 쿼리 분석 함수 검증
        resolved = core._resolve_retrieval_query("최신 환율 정보 알려줘")
        self.assertIn("환율", resolved)
        print("  [PASSED] Test 06: RAG similarity threshold (0.58) invariant and query resolving")

    # --- [ Phase 6: File Upload Validation & Chunking ] ---
    def test_07_upload_validation_and_manifest(self):
        # 1. 비허용 확장자 거부
        with self.assertRaises(core.UploadValidationError):
            core._validate_and_extract_meta("evil.py", b"import os\nprint('bad')")

        # 2. 용량 초과 거부 (MAX_UPLOAD_BYTES 초과)
        too_large_bytes = b"x" * (core.MAX_UPLOAD_BYTES + 1024)
        with self.assertRaises(core.UploadValidationError):
            core._validate_and_extract_meta("toolarge.txt", too_large_bytes)

        # 3. 빈 파일 거부
        with self.assertRaises(core.UploadValidationError):
            core._validate_and_extract_meta("empty.txt", b"")

        # 4. 정상 텍스트 청킹 검증
        sample_text = "이 문서는 RAG 업로드 청킹 테스트를 위한 긴 텍스트입니다. " * 50
        chunks = core._chunk_text(sample_text, chunk_size=300, overlap=50)
        self.assertGreater(len(chunks), 1)

        print("  [PASSED] Test 07: Upload validation, size limits, and deterministic chunking")

    # --- [ Phase 7: Citation Structure & Freshness ] ---
    def test_08_citation_and_freshness(self):
        now = datetime.now(timezone.utc)

        # 날씨 신선도 검사 (6시간 이내 fresh, 24시간 초과 stale)
        fresh_weather = {"type": "weather", "collected_at": now.isoformat()}
        stale_weather = {"type": "weather", "collected_at": (now - timedelta(hours=30)).isoformat()}
        self.assertEqual(core.get_document_freshness(fresh_weather)[0], "fresh")
        self.assertEqual(core.get_document_freshness(stale_weather)[0], "stale")

        # 뉴스 신선도 검사 (7일 이내 fresh, 30일 초과 stale)
        fresh_news = {"type": "news", "collected_at": now.isoformat()}
        stale_news = {"type": "news", "collected_at": (now - timedelta(days=35)).isoformat()}
        self.assertEqual(core.get_document_freshness(fresh_news)[0], "fresh")
        self.assertEqual(core.get_document_freshness(stale_news)[0], "stale")

        # 업로드 문서는 항상 fresh
        upload_meta = {"type": "upload", "title": "회사규정.pdf", "collected_at": "2021-01-01T00:00:00Z"}
        self.assertEqual(core.get_document_freshness(upload_meta)[0], "fresh")

        # Citation 병합 검증 (PDF 중복 페이지 병합)
        citations_input = [
            {"type": "upload", "title": "매뉴얼.pdf", "page": 3, "file_id": "f1"},
            {"type": "upload", "title": "매뉴얼.pdf", "page": 5, "file_id": "f1"},
            {"type": "upload", "title": "매뉴얼.pdf", "page": 3, "file_id": "f1"},  # 중복
        ]
        merged = core._merge_and_format_citations(citations_input)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["pages"], [3, 5])
        self.assertIn("3, 5페이지", merged[0]["label"])
        print("  [PASSED] Test 08: Citation structure, page merging, and freshness policies")


if __name__ == "__main__":
    unittest.main()
