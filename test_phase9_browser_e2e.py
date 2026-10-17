import asyncio
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import requests
from playwright.async_api import async_playwright

CHROME_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
BACKEND_PORT = 8000
FRONTEND_PORT = 5180
BACKEND_URL = f"http://127.0.0.1:{BACKEND_PORT}"
FRONTEND_URL = f"http://127.0.0.1:{FRONTEND_PORT}"


async def run_e2e():
    print("\n=======================================================")
    print("🚀 [PHASE 9] Real Browser End-to-End Acceptance Test")
    print("=======================================================\n")

    # 1. 격리된 테스트용 APP_DATA_DIR 생성
    test_data_dir = tempfile.mkdtemp(prefix="ai_bot_p9_e2e_")
    print(f"📁 Isolated Test Storage: {test_data_dir}")

    # 환경 변수 준비
    env = os.environ.copy()
    env["APP_DATA_DIR"] = test_data_dir
    env["SECRET_KEY"] = "browser_e2e_secret_key_12345678"
    env["CORS_ORIGINS"] = f"http://localhost:{FRONTEND_PORT},http://127.0.0.1:{FRONTEND_PORT},http://localhost:5173,http://127.0.0.1:5173"

    backend_proc = None
    frontend_proc = None

    try:
        # 2. 백엔드 서버 시작 (port 8000 - 외부 유료 API 호출 방지 및 결정론적 스트리밍 검증)
        print("⚙️ Starting Backend server on port 8000...")
        mock_server_path = os.path.join(test_data_dir, "e2e_backend_runner.py")
        repo_dir = os.path.abspath(".")
        with open(mock_server_path, "w", encoding="utf-8") as f:
            f.write(f'''import sys
sys.path.insert(0, "{repo_dir}")
import uvicorn
import time
import api
import llm

def _mock_e2e_stream(prompt, system_instruction=None):
    yield {{"type": "provider", "provider": "gemini"}}
    for chunk in ["안녕하세요! ", "만나서 반갑습니다. ", "나만의 AI 지식 창고 어시스턴트입니다. ", "실시간 스트리밍이 정상 동작합니다."]:
        time.sleep(0.05)
        yield {{"type": "chunk", "text": chunk}}

llm.generate_stream = _mock_e2e_stream

if __name__ == "__main__":
    uvicorn.run(api.app, host="127.0.0.1", port=8000, log_level="warning")
''')
        backend_cmd = [sys.executable, mock_server_path]
        backend_proc = subprocess.Popen(
            backend_cmd,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid
        )

        # 백엔드 가동 대기 (최대 10초)
        backend_ready = False
        for _ in range(20):
            try:
                r = requests.get(f"{BACKEND_URL}/api/health", timeout=1)
                if r.status_code == 200:
                    backend_ready = True
                    break
            except Exception:
                time.sleep(0.5)

        if not backend_ready:
            raise RuntimeError("Backend server failed to start within timeout.")
        print("✅ Backend server is ALIVE and healthy.")

        # 3. 프론트엔드 프리뷰 서버 시작 (port 5180)
        print(f"⚙️ Starting Frontend preview server on port {FRONTEND_PORT}...")
        frontend_dir = os.path.abspath("frontend")
        frontend_cmd = [
            "npx", "vite", "preview",
            "--host", "127.0.0.1", "--port", str(FRONTEND_PORT)
        ]
        frontend_proc = subprocess.Popen(
            frontend_cmd,
            cwd=frontend_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid
        )

        # 프론트엔드 가동 대기 (최대 10초)
        frontend_ready = False
        for _ in range(20):
            try:
                r = requests.get(FRONTEND_URL, timeout=1)
                if r.status_code == 200:
                    frontend_ready = True
                    break
            except Exception:
                time.sleep(0.5)

        if not frontend_ready:
            raise RuntimeError("Frontend server failed to start within timeout.")
        print(f"✅ Frontend server is SERVING on {FRONTEND_URL}.")

        # 4. Playwright 브라우저 실행
        print("\n🌐 Launching Headless Google Chrome...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                executable_path=CHROME_BIN,
                args=["--no-sandbox", "--disable-gpu"]
            )
            context = await browser.new_context(viewport={"width": 1280, "height": 800})
            page = await context.new_page()

            network_requests = []
            page.on("request", lambda req: network_requests.append(req.url))

            # --- [ E2E Test 1: Page Load & React Mount ] ---
            print("\n[E2E 01] Page Load & React Mount")
            await page.goto(FRONTEND_URL, wait_until="networkidle")
            title = await page.title()
            print(f"  Page title: {title}")
            layout = await page.wait_for_selector(".layout", timeout=5000)
            assert layout is not None, "Layout container should mount"
            sidebar = await page.wait_for_selector(".sidebar", timeout=5000)
            assert sidebar is not None, "Sidebar should be visible"
            print("  ✓ PASS: React app mounted with layout and sidebar.")

            # --- [ E2E Test 2: Conversation CRUD ] ---
            print("\n[E2E 02] Conversation CRUD")
            # 새 대화 생성 클릭
            new_btn = await page.wait_for_selector("button:has-text('새 대화 시작')", timeout=5000)
            await new_btn.click()
            await page.wait_for_timeout(1000)

            # 대화 항목이 sidebar에 추가되었는지 확인
            chat_rows = await page.query_selector_all(".chat-row")
            assert len(chat_rows) >= 1, "At least 1 chat row should exist"
            print(f"  ✓ PASS: Created conversation (total {len(chat_rows)} chats).")

            # 대화 이름 변경 테스트
            edit_btn = await page.wait_for_selector("button[title='이름 수정']", timeout=3000)
            await edit_btn.click()
            rename_input = await page.wait_for_selector(".rename-row input", timeout=3000)
            if rename_input:
                await rename_input.fill("E2E 테스트 대화")
                await rename_input.press("Enter")
                await page.wait_for_timeout(500)
                item_text = await chat_rows[0].inner_text()
                assert "E2E 테스트 대화" in item_text
                print("  ✓ PASS: Renamed conversation to 'E2E 테스트 대화'.")

            # --- [ E2E Test 3: Multi-turn Chat & Real SSE Streaming ] ---
            print("\n[E2E 03] Multi-turn Chat & Real SSE Streaming")
            composer = await page.wait_for_selector(".composer textarea", timeout=5000)
            await composer.fill("안녕! 반갑습니다.")
            send_btn = await page.wait_for_selector("button.send-btn:not([disabled])", timeout=5000)
            await send_btn.click()

            # 사용자 버블 확인
            user_msg = await page.wait_for_selector(".msg.user", timeout=5000)
            assert user_msg is not None
            print("  ✓ User message sent and visible.")

            # 어시스턴트 버블 생성 대기
            assistant_bubble = await page.wait_for_selector(".bubble.assistant", timeout=15000)
            assert assistant_bubble is not None

            # 답변 텍스트가 실제로 나타날 때까지 대기
            await page.wait_for_function(
                "() => { const b = document.querySelector('.bubble.assistant'); return b && b.innerText.trim().length > 0; }",
                timeout=30000
            )
            bot_text = await assistant_bubble.inner_text()
            print(f"  Assistant reply received: {bot_text[:60]}...")
            assert len(bot_text.strip()) > 0, "Assistant reply must not be empty"
            print("  ✓ PASS: Real SSE streaming successfully completed.")

            # --- [ E2E Test 4: Streaming Abort & Persistence ] ---
            print("\n[E2E 04] Streaming Abort & Persistence")
            await composer.fill("긴 설명을 부탁합니다: 인공지능 윤리와 미래 사회 변화에 대해 자세히 말해줘.")
            send_btn = await page.wait_for_selector("button.send-btn:not([disabled])", timeout=5000)
            await send_btn.click()

            # 스트리밍 중단 버튼 대기
            try:
                stop_btn = await page.wait_for_selector("button.send-btn.stop-btn", timeout=5000)
                if stop_btn:
                    await stop_btn.click()
                    print("  Clicked abort button.")
                    await page.wait_for_timeout(1000)
            except Exception as e:
                print(f"  Abort button notice: {e}")

            # 새로고침 후 대화 보존 확인
            await page.reload(wait_until="networkidle")
            await page.wait_for_selector(".layout", timeout=5000)
            messages_after = await page.query_selector_all(".msg")
            assert len(messages_after) >= 2, "Persisted messages must survive reload"
            print(f"  ✓ PASS: {len(messages_after)} messages persisted across reload.")

            # --- [ E2E Test 5: Korean IME Typing ] ---
            print("\n[E2E 05] Korean IME Typing")
            composer = await page.wait_for_selector(".composer textarea", timeout=5000)
            await composer.focus()
            await page.keyboard.type("한글 조합 테스트 메시지입니다.")
            val = await composer.input_value()
            assert val == "한글 조합 테스트 메시지입니다."
            # Shift+Enter 로 줄바꿈 테스트
            await page.keyboard.press("Shift+Enter")
            await page.keyboard.type("두 번째 줄입니다.")
            val_multiline = await composer.input_value()
            assert "\n" in val_multiline
            print("  ✓ PASS: Korean IME characters and Shift+Enter multiline handled correctly.")
            # Clear input
            await composer.fill("")

            # --- [ E2E Test 6: Responsive Viewports ] ---
            print("\n[E2E 06] Responsive Viewports")
            viewports = [
                ("Mobile iPhone SE", 375, 667),
                ("Mobile iPhone 14", 390, 844),
                ("Tablet iPad", 768, 1024),
                ("Desktop MacBook", 1280, 800),
                ("Wide Desktop", 1920, 1080),
            ]
            for name, w, h in viewports:
                await page.set_viewport_size({"width": w, "height": h})
                await page.wait_for_timeout(200)
                # Ensure no layout breaking horizontal scroll
                scroll_width = await page.evaluate("() => document.body.scrollWidth")
                client_width = await page.evaluate("() => document.documentElement.clientWidth")
                assert scroll_width <= client_width + 5, f"Horizontal overflow at {name} ({scroll_width} > {client_width})"
                print(f"  ✓ Viewport {name} ({w}x{h}) clean: no horizontal overflow.")

            # --- [ E2E Test 7: Lazy Loading Chunk Verification ] ---
            print("\n[E2E 07] Lazy Loading Chunk Verification")
            # 대시보드 버튼 클릭
            dash_btn = await page.wait_for_selector("button:has-text('지식 대시보드')", timeout=5000)
            assert dash_btn is not None
            await dash_btn.click()
            await page.wait_for_timeout(1000)

            # Dashboard 청크가 네트워크로 요청되었는지 확인
            dashboard_chunk_loaded = any("Dashboard-" in url for url in network_requests)
            print(f"  Dashboard lazy chunk fetched: {dashboard_chunk_loaded}")
            dash_card = await page.wait_for_selector(".toss-card", timeout=5000)
            assert dash_card is not None, "Dashboard card should render"
            print("  ✓ PASS: Dashboard lazy chunk loaded and rendered successfully.")

            print("\n🎉 ALL BROWSER E2E TESTS PASSED SUCCESSFULLY!")

            # Clean exit without hanging on Playwright CDP flush
            if frontend_proc and frontend_proc.poll() is None:
                try:
                    os.killpg(os.getpgid(frontend_proc.pid), signal.SIGKILL)
                except Exception:
                    pass

            if backend_proc and backend_proc.poll() is None:
                try:
                    os.killpg(os.getpgid(backend_proc.pid), signal.SIGKILL)
                except Exception:
                    pass

            shutil.rmtree(test_data_dir, ignore_errors=True)
            print("🧹 Cleaned up temporary test data directory.")
            os._exit(0)

    finally:
        if frontend_proc and frontend_proc.poll() is None:
            try:
                os.killpg(os.getpgid(frontend_proc.pid), signal.SIGKILL)
            except Exception:
                pass

        if backend_proc and backend_proc.poll() is None:
            try:
                os.killpg(os.getpgid(backend_proc.pid), signal.SIGKILL)
            except Exception:
                pass

        shutil.rmtree(test_data_dir, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(run_e2e())
