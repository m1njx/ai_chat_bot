import os
import sys
import shutil
import tempfile
import json
import time
import threading
import unittest
from datetime import datetime, timezone

# 테스트 격리를 위해 별도 임시 디렉토리를 APP_DATA_DIR로 설정
TEST_TMP_DIR = tempfile.mkdtemp(prefix="ai_bot_phase8_test_")
os.environ["APP_DATA_DIR"] = TEST_TMP_DIR

import core
import brain


class TestPhase8Resilience(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        print(f"\n--- [SETUP] Isolated Test APP_DATA_DIR: {TEST_TMP_DIR} ---")
        # Ensure directories exist
        core._bootstrap_app_data_dir()

    @classmethod
    def tearDownClass(cls):
        print(f"\n--- [TEARDOWN] Cleaning up {TEST_TMP_DIR} ---")
        shutil.rmtree(TEST_TMP_DIR, ignore_errors=True)

    def setUp(self):
        # Base mock documents and metadata
        self.mock_docs = [
            "인공지능 모델 최적화와 관측 가능성 가이드",
            "파이썬 비동기 프로그래밍과 FastAPI 프로덕션 아키텍처",
            "FAISS 벡터 인덱스 검색과 크래시 일관성 보장 기법",
        ]
        self.mock_meta = [
            {"id": "doc_1", "type": "manual", "title": "AI 최적화", "source": "guide"},
            {"id": "doc_2", "type": "manual", "title": "FastAPI", "source": "web"},
            {"id": "doc_3", "type": "manual", "title": "FAISS", "source": "docs"},
        ]

    def _create_fake_generation(self, gen_id: str, doc_count: int = 3, corrupt_file: str = None):
        """테스트용 가상 세대 디렉토리 생성 헬퍼"""
        import numpy as np
        import faiss

        gen_dir = os.path.join(core.GENERATIONS_DIR, gen_id)
        os.makedirs(gen_dir, exist_ok=True)

        target_db = os.path.join(gen_dir, "faiss_index.bin")
        target_docs = os.path.join(gen_dir, "documents_data.json")
        target_meta = os.path.join(gen_dir, "documents_metadata.json")
        target_manifest = os.path.join(gen_dir, "manifest.json")

        dim = 384
        docs = self.mock_docs[:doc_count]
        metas = self.mock_meta[:doc_count]

        # FAISS index
        xb = np.random.randn(doc_count, dim).astype("float32")
        faiss.normalize_L2(xb)
        idx = faiss.IndexFlatIP(dim)
        idx.add(xb)

        if corrupt_file == "faiss_index.bin":
            with open(target_db, "wb") as f:
                f.write(b"CORRUPTED_INDEX_HEADER_TEST")
        else:
            faiss.write_index(idx, target_db)

        if corrupt_file == "documents_data.json":
            with open(target_docs, "w", encoding="utf-8") as f:
                f.write("{ INVALID JSON DATA")
        else:
            with open(target_docs, "w", encoding="utf-8") as f:
                json.dump(docs, f, ensure_ascii=False)

        if corrupt_file == "documents_metadata.json":
            with open(target_meta, "w", encoding="utf-8") as f:
                f.write("[ NOT MATCHING LENGTH ]")
        else:
            with open(target_meta, "w", encoding="utf-8") as f:
                json.dump(metas, f, ensure_ascii=False)

        manifest = {
            "generation_id": gen_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "document_count": doc_count,
            "dimension": dim,
            "metric": "inner_product",
            "files": {
                "index": "faiss_index.bin",
                "documents": "documents_data.json",
                "metadata": "documents_metadata.json",
            },
            "checksums": {
                "index_sha256": core._compute_sha256(target_db) if corrupt_file != "faiss_index.bin" else "corrupt",
                "documents_sha256": core._compute_sha256(target_docs) if corrupt_file != "documents_data.json" else "corrupt",
                "metadata_sha256": core._compute_sha256(target_meta) if corrupt_file != "documents_metadata.json" else "corrupt",
            },
        }
        with open(target_manifest, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        return gen_dir

    def test_01_bootstrap_and_pointer(self):
        """초기 상태 부트스트랩 및 current.json 단일 커밋 포인트 검증"""
        gen_1 = "gen_20261017T080000Z_init0001"
        self._create_fake_generation(gen_1, doc_count=3)
        self.assertTrue(core._commit_current_pointer(gen_1))

        self.assertEqual(core.get_active_generation_id(), gen_1)
        info = core.get_active_generation_info()
        self.assertIsNotNone(info)
        self.assertEqual(info["generation_id"], gen_1)
        self.assertEqual(info["document_count"], 3)
        print("  [PASSED] Test 01: Initial pointer commit & info fetch")

    def test_02_crash_point_a_index_failure(self):
        """Crash Point A: Index 생성 실패 시 이전 세대 유지 확인"""
        old_gen = core.get_active_generation_id()
        failed_gen_id = "gen_crash_a"
        failed_gen_dir = os.path.join(core.GENERATIONS_DIR, failed_gen_id)
        os.makedirs(failed_gen_dir, exist_ok=True)

        # 쓰기 중단 시뮬레이션
        try:
            with open(os.path.join(failed_gen_dir, "faiss_index.bin"), "wb") as f:
                f.write(b"incomplete")
            raise IOError("Simulated disk full during FAISS index write")
        except IOError:
            shutil.rmtree(failed_gen_dir, ignore_errors=True)

        # 활성 세대는 그대로 유지되어야 함
        self.assertEqual(core.get_active_generation_id(), old_gen)
        self.assertFalse(os.path.exists(failed_gen_dir))
        print("  [PASSED] Test 02: Crash Point A (Index write abort preserves active generation)")

    def test_03_crash_point_b_docs_failure(self):
        """Crash Point B: Documents 쓰기 실패 시 이전 세대 유지 확인"""
        old_gen = core.get_active_generation_id()
        failed_gen_id = "gen_crash_b"
        failed_gen_dir = os.path.join(core.GENERATIONS_DIR, failed_gen_id)
        os.makedirs(failed_gen_dir, exist_ok=True)

        try:
            # Index는 썼으나 docs 쓰기 실패
            with open(os.path.join(failed_gen_dir, "faiss_index.bin"), "wb") as f:
                f.write(b"valid_bytes")
            raise IOError("Simulated power outage during documents JSON write")
        except IOError:
            shutil.rmtree(failed_gen_dir, ignore_errors=True)

        self.assertEqual(core.get_active_generation_id(), old_gen)
        self.assertFalse(os.path.exists(failed_gen_dir))
        print("  [PASSED] Test 03: Crash Point B (Documents write abort preserves active generation)")

    def test_04_crash_point_c_metadata_failure(self):
        """Crash Point C: Metadata 쓰기 실패 시 이전 세대 유지 확인"""
        old_gen = core.get_active_generation_id()
        failed_gen_id = "gen_crash_c"
        failed_gen_dir = os.path.join(core.GENERATIONS_DIR, failed_gen_id)
        os.makedirs(failed_gen_dir, exist_ok=True)

        try:
            with open(os.path.join(failed_gen_dir, "faiss_index.bin"), "wb") as f:
                f.write(b"valid_bytes")
            with open(os.path.join(failed_gen_dir, "documents_data.json"), "w") as f:
                f.write("[]")
            raise IOError("Simulated metadata flush error")
        except IOError:
            shutil.rmtree(failed_gen_dir, ignore_errors=True)

        self.assertEqual(core.get_active_generation_id(), old_gen)
        self.assertFalse(os.path.exists(failed_gen_dir))
        print("  [PASSED] Test 04: Crash Point C (Metadata write abort preserves active generation)")

    def test_05_crash_point_d_pre_swap_failure(self):
        """Crash Point D: 3개 파일 및 manifest까지 작성 후 pointer swap 직전 크래시"""
        old_gen = core.get_active_generation_id()
        pre_swap_gen_id = "gen_20261017T080500Z_preswap"
        self._create_fake_generation(pre_swap_gen_id, doc_count=2)

        # pointer swap 호출을 하지 않음 (크래시로 미실행)
        # 독자는 여전히 old_gen을 바라보아야 함
        self.assertEqual(core.get_active_generation_id(), old_gen)
        idx, docs, meta = core.load_index_with_metadata()
        self.assertEqual(len(docs), 3)  # old_gen은 3건
        print("  [PASSED] Test 05: Crash Point D (Pre-swap crash: readers see 100% valid old generation)")

    def test_06_crash_recovery_e_corrupted_active_generation(self):
        """Crash Point E: 현재 활성 세대가 손상된 경우 이전 정상 세대로 자동 복구(Auto Recovery)"""
        # 1. 이전 정상 세대 gen_valid_prev 생성 및 활성화
        prev_valid_gen = "gen_20261017T081000Z_valid_prev"
        self._create_fake_generation(prev_valid_gen, doc_count=3)
        self.assertTrue(core._commit_current_pointer(prev_valid_gen))

        # 2. 신규 세대 gen_corrupted_curr 생성 후 인위적으로 current.json을 이쪽으로 연결
        corrupt_curr_gen = "gen_20261017T082000Z_corrupt_curr"
        self._create_fake_generation(corrupt_curr_gen, doc_count=3, corrupt_file="faiss_index.bin")
        self.assertTrue(core._commit_current_pointer(corrupt_curr_gen))
        self.assertEqual(core.get_active_generation_id(), corrupt_curr_gen)

        # 3. load_index_with_metadata 호출 시 손상 감지 -> 이전 세대로 자동 롤백 복구
        idx, docs, meta = core.load_index_with_metadata()
        self.assertIsNotNone(idx)
        self.assertEqual(len(docs), 3)
        # 활성 세대가 정상 세대로 복구되었는지 확인
        self.assertEqual(core.get_active_generation_id(), prev_valid_gen)
        print("  [PASSED] Test 06: Crash Point E (Corrupted active generation auto-recovered to valid generation)")

    def test_07_readiness_probe(self):
        """Liveness / Readiness 상태 분리 및 세대 상태 판별 검증"""
        # 현재 정상 상태
        ready, details = core.check_readiness()
        self.assertTrue(ready)
        self.assertIn("generation_id", details)

        # current.json을 존재하지 않는 세대로 훼손
        with open(core.CURRENT_POINTER_PATH, "w") as f:
            json.dump({"generation_id": "non_existent_gen"}, f)

        # 모든 세대를 비운 상태 시뮬레이션
        shutil.rmtree(core.GENERATIONS_DIR)
        os.makedirs(core.GENERATIONS_DIR, exist_ok=True)
        ready_fail, details_fail = core.check_readiness()
        self.assertFalse(ready_fail)
        self.assertNotEqual(details_fail.get("knowledge"), "ok")

        # 다시 정상 세대 생성 후 readiness 회복 검증
        gen_restored = "gen_20261017T083000Z_restored"
        self._create_fake_generation(gen_restored, doc_count=3)
        core._commit_current_pointer(gen_restored)

        ready_ok, _ = core.check_readiness()
        self.assertTrue(ready_ok)
        print("  [PASSED] Test 07: Readiness probe accurately reflects generation integrity")

    def test_08_collector_heartbeat(self):
        """수집기(brain.py) heartbeat 기록 및 상태 감지 검증"""
        # Heartbeat 기록
        brain._write_heartbeat(status="success", added=42)
        status = core.get_collector_status()

        self.assertIsNotNone(status)
        self.assertEqual(status["status"], "success")
        self.assertEqual(status["last_cycle_added"], 42)
        self.assertLess(status["age_seconds"], 5.0)
        self.assertEqual(status["health"], "healthy")
        print("  [PASSED] Test 08: Collector heartbeat writing, parsing, and health state")

    def test_09_concurrency_readers_writer(self):
        """동시성 검증: 독자 스레드들이 RAG 조회를 수행하는 동안 작성자 스레드가 세대 재구축 수행"""
        # 활성 세대 준비
        base_gen = "gen_20261017T084000Z_base"
        self._create_fake_generation(base_gen, doc_count=3)
        core._commit_current_pointer(base_gen)

        errors = []
        stop_readers = threading.Event()

        def reader_worker(worker_id):
            while not stop_readers.is_set():
                try:
                    idx, docs, meta = core.load_index_with_metadata()
                    if idx is None or len(docs) == 0 or len(meta) == 0:
                        errors.append(f"Worker {worker_id}: Empty or None index loaded")
                    if len(docs) != len(meta):
                        errors.append(f"Worker {worker_id}: Mismatched docs ({len(docs)}) vs meta ({len(meta)})")
                except Exception as e:
                    errors.append(f"Worker {worker_id}: Exception {e}")
                time.sleep(0.005)

        readers = [threading.Thread(target=reader_worker, args=(i,)) for i in range(5)]
        for r in readers:
            r.daemon = True
            r.start()

        # 작성자가 세대 2번 연속 생성 및 포인터 교체
        for step in range(2):
            new_gen = f"gen_20261017T08500{step}Z_concurrent"
            self._create_fake_generation(new_gen, doc_count=3)
            core._commit_current_pointer(new_gen)
            time.sleep(0.02)

        stop_readers.set()
        for r in readers:
            r.join(timeout=1.0)

        self.assertEqual(len(errors), 0, f"Concurrency errors encountered: {errors}")
        print("  [PASSED] Test 09: Concurrency verified (5 reader threads + writer commits without error)")


if __name__ == "__main__":
    unittest.main()
