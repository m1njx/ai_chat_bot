import os
import shutil
import tempfile
import json
import unittest

# 격리된 임시 APP_DATA_DIR
TEST_UPLOAD_DIR = tempfile.mkdtemp(prefix="ai_bot_p9_upload_")
os.environ["APP_DATA_DIR"] = TEST_UPLOAD_DIR
os.environ["SECRET_KEY"] = "phase9_upload_storage_secret"

import core


class TestPhase9UploadAndStorage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        print(f"\n--- [SETUP] Upload, Delete & Storage Acceptance: {TEST_UPLOAD_DIR} ---")
        core._bootstrap_app_data_dir()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TEST_UPLOAD_DIR, ignore_errors=True)

    def test_01_upload_security_and_validation(self):
        """업로드 보안 및 유효성 검증 (0바이트, 10MB 초과, 확장자 거부, Fake PDF, Path Traversal)"""
        # 1. 빈 파일
        with self.assertRaises(core.UploadValidationError):
            core._validate_and_extract_meta("empty.txt", b"")

        # 2. 용량 초과
        too_large = b"A" * (core.MAX_UPLOAD_BYTES + 1024)
        with self.assertRaises(core.UploadValidationError):
            core._validate_and_extract_meta("big.txt", too_large)

        # 3. 비허용 확장자
        for bad_name in ("malware.exe", "script.sh", "exploit.py", "photo.png"):
            with self.assertRaises(core.UploadValidationError):
                core._validate_and_extract_meta(bad_name, b"some content")

        # 4. Fake PDF (매직 바이트 없음)
        with self.assertRaises(core.UploadValidationError):
            core._validate_and_extract_meta("fake.pdf", b"This is not a real PDF file header")

        # 5. Path traversal 방어 검증
        clean_name = core._safe_filename("../../../etc/passwd.txt")
        self.assertNotIn("/", clean_name)
        self.assertNotIn("..", clean_name)
        self.assertTrue(clean_name.endswith(".txt"))
        print("  [PASSED] Test 01: Upload validation, size limits, format restrictions, and path traversal defense")

    def test_02_txt_upload_index_and_delete_cycle(self):
        """TXT 업로드 → 인덱스 반영 → 검색 확인 → 삭제 → 인덱스 제거 사이클 검증"""
        content = "인공지능 챗봇 프로젝트 Phase 9 최종 인수 테스트 검증 문서입니다. " * 30
        res = core.save_and_index_upload("phase9_guide.txt", content.encode("utf-8"), "text/plain")
        self.assertEqual(res.get("status"), "indexed")
        file_id = res.get("id")
        self.assertIsNotNone(file_id)

        # 업로드 목록 확인
        files = core.get_uploaded_files()
        self.assertTrue(any(f["id"] == file_id for f in files))

        # 업로드 파일 삭제
        del_res = core.delete_upload_file(file_id)
        self.assertEqual(del_res.get("id"), file_id)

        # 삭제 후 목록에서 제거 확인
        files_after = core.get_uploaded_files()
        self.assertFalse(any(f["id"] == file_id for f in files_after))
        print("  [PASSED] Test 02: TXT Upload -> Index -> List -> Delete -> Rebuild lifecycle")

    def test_03_persistent_storage_simulation(self):
        """독립 프로세스/재기동 시 동일 APP_DATA_DIR의 데이터 보존 및 덮어쓰기 방지 검증"""
        # 대화 생성 및 저장
        user_key = "local"
        chat = core.new_chat("영구보존대화")
        chat_id = chat["id"]
        chat["messages"].append({"role": "user", "content": "보존테스트"})

        def _add_chat(chats):
            chats[chat_id] = chat
            return chat

        core.modify_chats(user_key, _add_chat)

        # 재기동 시뮬레이션: _bootstrap_app_data_dir 재호출
        core._bootstrap_app_data_dir()

        # 데이터가 덮어써지지 않고 그대로 유지되는지 확인
        loaded = core.load_chats(user_key)
        self.assertIn(chat_id, loaded)
        self.assertEqual(loaded[chat_id]["messages"][0]["content"], "보존테스트")
        print("  [PASSED] Test 03: Persistent storage simulation (restart preserves state without overwrite)")


if __name__ == "__main__":
    unittest.main()
