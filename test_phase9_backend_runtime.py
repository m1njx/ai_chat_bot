import os
import shutil
import tempfile
import json
import unittest
import uuid
from starlette.testclient import TestClient

# 격리된 APP_DATA_DIR 설정
TEST_RUNTIME_DIR = tempfile.mkdtemp(prefix="ai_bot_p9_backend_")
os.environ["APP_DATA_DIR"] = TEST_RUNTIME_DIR
os.environ["SECRET_KEY"] = "phase9_backend_runtime_secret_key"

import core
import api


class TestPhase9BackendRuntime(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        core._bootstrap_app_data_dir()
        cls.client = TestClient(api.app)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TEST_RUNTIME_DIR, ignore_errors=True)

    def test_01_health_endpoint(self):
        """GET /api/health Liveness 프로브 즉시 200 OK 응답 검증"""
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("status"), "alive")
        self.assertTrue(data.get("ok"))
        # X-Request-ID 및 보안 헤더 검증
        self.assertIn("x-request-id", res.headers)
        self.assertEqual(res.headers.get("x-content-type-options"), "nosniff")
        self.assertEqual(res.headers.get("x-frame-options"), "DENY")
        print("  [PASSED] Test 01: GET /api/health Liveness probe & security headers")

    def test_02_ready_endpoint_healthy(self):
        """GET /api/ready 정상 세대 상태에서 200 OK 응답 검증"""
        # 정상 세대 확인
        ready_status, details = core.check_readiness()
        if not ready_status:
            # 부트스트랩
            core._bootstrap_legacy_generation()

        res = self.client.get("/api/ready")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("ready"))
        self.assertEqual(data.get("knowledge"), "ok")
        self.assertEqual(data.get("storage"), "ok")
        self.assertIn("generation_id", data)
        print("  [PASSED] Test 02: GET /api/ready returns 200 with valid generation info")

    def test_03_ready_endpoint_failure_503(self):
        """GET /api/ready 세대 손상 및 부재 시 503 Service Unavailable 검증"""
        # 임시 손상 디렉토리 생성
        corrupt_tmp_dir = tempfile.mkdtemp(prefix="ai_bot_p9_corrupt_")
        old_data_dir = core.APP_DATA_DIR
        old_gen_dir = core.GENERATIONS_DIR
        try:
            # 손상된 상태 시뮬레이션
            core.GENERATIONS_DIR = os.path.join(corrupt_tmp_dir, "generations")
            os.makedirs(core.GENERATIONS_DIR, exist_ok=True)
            core.CURRENT_POINTER_PATH = os.path.join(corrupt_tmp_dir, "current.json")
            with open(core.CURRENT_POINTER_PATH, "w") as f:
                json.dump({"generation_id": "missing_gen"}, f)

            res = self.client.get("/api/ready")
            self.assertEqual(res.status_code, 503)
            data = res.json()
            self.assertFalse(data.get("ready"))
            self.assertNotEqual(data.get("knowledge"), "ok")
            print("  [PASSED] Test 03: GET /api/ready returns 503 when generation is corrupt")
        finally:
            core.APP_DATA_DIR = old_data_dir
            core.GENERATIONS_DIR = old_gen_dir
            core.CURRENT_POINTER_PATH = os.path.join(core.KNOWLEDGE_DIR, "current.json")
            shutil.rmtree(corrupt_tmp_dir, ignore_errors=True)

    def test_04_session_endpoint(self):
        """GET /api/session 인증 상태 조회 엔드포인트 검증"""
        res = self.client.get("/api/session")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("auth_required", data)
        self.assertIn("authenticated", data)
        print("  [PASSED] Test 04: GET /api/session returns current session state")

    def test_05_knowledge_endpoint(self):
        """GET /api/knowledge 관측 가능성 및 메타데이터 반환 검증"""
        res = self.client.get("/api/knowledge")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("total_documents", data)
        self.assertIn("generation_id", data)
        self.assertIn("collector_status", data)
        self.assertIn("storage", data)
        print("  [PASSED] Test 05: GET /api/knowledge returns observability metrics")


if __name__ == "__main__":
    unittest.main()
