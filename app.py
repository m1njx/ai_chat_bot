import streamlit as st
import os
import time
import hmac
import uuid
import html
from dotenv import load_dotenv

import core   # UI에 의존하지 않는 공통 로직 (FastAPI 백엔드와 공유)
import llm    # Gemini → LM Studio → OpenAI 자동 전환 계층

# 1. 환경 및 경로 설정
load_dotenv()

# APP_PASSWORD를 설정하면 비밀번호 게이트 + 세션별 대화 격리가 켜진다.
# 설정하지 않으면(로컬 단독 사용) 하나의 'local' 네임스페이스를 쓴다.
APP_PASSWORD = os.getenv("APP_PASSWORD")

CHAT_RATE_LIMIT = (10, 60)     # 60초당 10회
REBUILD_RATE_LIMIT = (2, 300)  # 300초당 2회

st.set_page_config(page_title="나만의 AI 지식 창고", page_icon="🧠", layout="wide")

# 2. 토스(Toss) 디자인 시스템
# 주의: 아래는 개발자가 작성한 고정 CSS이므로 unsafe_allow_html이 안전하다.
# 외부에서 들어온 값은 반드시 esc()로 이스케이프한 뒤 삽입할 것.
css_styles = """
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css" />
<style>
    :root {
        --toss-blue: #0064FF;
        --toss-blue-light: #E8F3FF;
        --toss-bg: #F2F4F6;
        --toss-card: #FFFFFF;
        --toss-text: #191F28;
        --toss-subtext: #4E5968;
        --toss-border: #E5E8EB;
        --toss-shadow: rgba(0, 0, 0, 0.04);
    }

    @media (prefers-color-scheme: dark) {
        :root {
            --toss-blue: #3182F6;
            --toss-blue-light: #1A2333;
            --toss-bg: #101012;
            --toss-card: #1C1C1E;
            --toss-text: #F9FAFB;
            --toss-subtext: #ADB5BD;
            --toss-border: #2C2C2E;
            --toss-shadow: rgba(0, 0, 0, 0.2);
        }
    }

    html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
        font-family: "Pretendard Variable", -apple-system, sans-serif !important;
        background-color: var(--toss-bg) !important;
        color: var(--toss-text) !important;
    }

    header { visibility: hidden !important; height: 0 !important; }

    /* 사이드바 열기 버튼은 header 안에 있어 위 규칙에 같이 숨겨진다.
       그대로 두면 사이드바를 한 번 접었을 때 다시 열 방법이 없다. */
    [data-testid="stExpandSidebarButton"],
    [data-testid="stExpandSidebarButton"] * {
        visibility: visible !important;
    }
    [data-testid="stExpandSidebarButton"] {
        z-index: 1000 !important;
        color: var(--toss-subtext) !important;
    }

    [data-testid="stSidebar"] {
        background-color: var(--toss-card) !important;
        border-right: 1px solid var(--toss-border) !important;
    }

    /* Sidebar Button styling */
    [data-testid="stSidebar"] .stButton button {
        background-color: transparent !important;
        color: var(--toss-subtext) !important;
        border: none !important;
        border-radius: 12px !important;
        padding: 6px 10px !important;
        font-weight: 500 !important;
        text-align: left !important;
        width: 100% !important;
        transition: all 0.2s ease;
    }

    [data-testid="stSidebar"] .stButton button:hover {
        background-color: var(--toss-blue-light) !important;
        color: var(--toss-blue) !important;
    }

    .stChatMessage { background-color: transparent !important; padding: 0.5rem 0 !important; }

    [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) { flex-direction: row-reverse !important; }
    [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) > div:nth-child(2) {
        background-color: var(--toss-blue) !important; color: #FFFFFF !important;
        border-radius: 20px 20px 4px 20px !important; padding: 12px 16px !important;
        box-shadow: 0 4px 12px var(--toss-shadow) !important; font-size: 15px !important; max-width: 80% !important;
    }

    [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) > div:nth-child(2) {
        background-color: var(--toss-card) !important; color: var(--toss-text) !important;
        border-radius: 20px 20px 20px 4px !important; padding: 12px 16px !important;
        border: 1px solid var(--toss-border) !important; box-shadow: 0 2px 8px var(--toss-shadow) !important;
        font-size: 15px !important; max-width: 80% !important;
    }

    [data-testid="stChatInput"] {
        border-radius: 18px !important; border: 1px solid var(--toss-border) !important;
        background-color: var(--toss-card) !important; color: var(--toss-text) !important;
        box-shadow: 0 8px 30px var(--toss-shadow) !important;
    }

    .toss-card {
        background: var(--toss-card); padding: 20px; border-radius: 20px;
        border: 1px solid var(--toss-border); box-shadow: 0 4px 20px var(--toss-shadow); margin-bottom: 12px;
    }

    .stat-label { font-size: 14px; color: var(--toss-subtext); margin-bottom: 4px; }
    .stat-value { font-size: 24px; font-weight: 700; color: var(--toss-blue); }
</style>
"""
st.markdown(css_styles, unsafe_allow_html=True)


# --- [ Streamlit 전용 헬퍼 ] ---
def esc(value):
    """unsafe_allow_html 문자열에 외부 값을 넣기 전 반드시 통과시킨다."""
    return html.escape(str(value), quote=True)


def rate_limit(key, limit, window_sec):
    """세션 단위 슬라이딩 윈도우 제한. 통과하면 True."""
    now = time.time()
    buckets = st.session_state.setdefault("_rate_limits", {})
    hits = [t for t in buckets.get(key, []) if now - t < window_sec]
    if len(hits) >= limit:
        buckets[key] = hits
        return False
    hits.append(now)
    buckets[key] = hits
    return True


def require_auth():
    """APP_PASSWORD가 설정된 경우에만 동작하는 비밀번호 게이트."""
    if not APP_PASSWORD or st.session_state.get("_authed"):
        return
    st.markdown("<h2>🔒 접근 인증</h2>", unsafe_allow_html=True)
    pw = st.text_input("비밀번호", type="password", key="_pw_input")
    if st.button("입장", width="stretch"):
        if hmac.compare_digest(pw or "", APP_PASSWORD):
            st.session_state["_authed"] = True
            st.rerun()
        st.error("비밀번호가 올바르지 않습니다.")
    st.stop()


def get_user_key():
    """대화 기록 네임스페이스.
    로컬 단독 사용 시 'local' 고정, 인증 모드에서는 브라우저 세션마다 분리."""
    if not APP_PASSWORD:
        return "local"
    if "_user_key" not in st.session_state:
        st.session_state["_user_key"] = f"s-{uuid.uuid4().hex}"
    return st.session_state["_user_key"]


require_auth()

if not llm.available():
    st.error(
        "❌ 사용 가능한 AI 제공자가 없습니다. .env에 GOOGLE_API_KEY 또는 OPENAI_API_KEY를 "
        "설정하거나, LM Studio 로컬 서버를 실행해주세요."
    )
    st.stop()


@st.cache_resource
def warm_embedder():
    """임베딩 모델은 무거우므로 세션 간 캐시한다."""
    return core.get_embedder()


warm_embedder()


def generate_reply(question):
    """(답변, 오류메시지) 반환. Streamlit 제어 예외를 삼키지 않도록 st.* 호출을 하지 않는다."""
    try:
        text, _provider = llm.generate(
            core.build_prompt(question), system_instruction=core.SYSTEM_INSTRUCTION
        )
    except llm.LLMError as e:
        print(f"⚠️ 모든 LLM 제공자 실패: {e}", flush=True)
        return None, "AI 호출 중 에러가 발생했습니다. 잠시 후 다시 시도해주세요."
    except Exception as e:
        print(f"⚠️ 예기치 못한 LLM 오류: {e}", flush=True)
        return None, "AI 호출 중 에러가 발생했습니다. 잠시 후 다시 시도해주세요."
    return core.filter_output(text), None


# --- [ UI 구성 ] ---
USER_KEY = get_user_key()

if "all_chats" not in st.session_state:
    st.session_state.all_chats = core.load_chats(USER_KEY)
if "current_chat_id" not in st.session_state:
    st.session_state.current_chat_id = next(iter(st.session_state.all_chats), None) or "새 대화"
if "rename_target" not in st.session_state:
    st.session_state.rename_target = None


def persist():
    core.save_chats(USER_KEY, st.session_state.all_chats)


with st.sidebar:
    st.markdown("<h2>📂 대화 목록</h2>", unsafe_allow_html=True)
    if st.button("➕ 새 대화 시작", width="stretch"):
        new_id = core.unique_name(f"대화 {time.strftime('%H:%M:%S')}", st.session_state.all_chats)
        st.session_state.all_chats[new_id] = []
        st.session_state.current_chat_id = new_id
        persist()
        st.rerun()
    st.divider()

    for cid in list(st.session_state.all_chats.keys()):
        is_active = (cid == st.session_state.current_chat_id)

        if st.session_state.rename_target == cid:
            new_name = st.text_input("수정", value=cid, key=f"in_{cid}", label_visibility="collapsed")
            c1, c2 = st.columns(2)
            confirm = c1.button("확인", key=f"ok_{cid}")
            cancel = c2.button("취소", key=f"cn_{cid}")
            if confirm:
                new_name = (new_name or "").strip()
                if new_name and new_name != cid and new_name in st.session_state.all_chats:
                    st.error("같은 이름의 대화가 이미 있습니다.")
                else:
                    if new_name and new_name != cid:
                        st.session_state.all_chats = core.rename_chat(
                            st.session_state.all_chats, cid, new_name
                        )
                        st.session_state.current_chat_id = new_name
                        persist()
                    st.session_state.rename_target = None
                    st.rerun()
            if cancel:
                st.session_state.rename_target = None
                st.rerun()
        else:
            with st.container():
                col_btn, col_tool = st.columns([4, 1])
                with col_btn:
                    if st.button(f"{'📍' if is_active else '💬'} {cid[:10]}", key=f"sel_{cid}", width="stretch"):
                        st.session_state.current_chat_id = cid
                        st.rerun()
                with col_tool:
                    with st.popover("⚙️", width="stretch"):
                        if st.button("✏️ 이름 수정", key=f"ed_{cid}", width="stretch"):
                            st.session_state.rename_target = cid
                            st.rerun()
                        if st.button("🗑️ 삭제", key=f"dl_{cid}", width="stretch"):
                            st.session_state.all_chats.pop(cid, None)
                            if st.session_state.current_chat_id == cid:
                                st.session_state.current_chat_id = (
                                    next(iter(st.session_state.all_chats), None) or "새 대화"
                                )
                            persist()
                            st.rerun()

    st.sidebar.markdown("<div style='height: 100px;'></div>", unsafe_allow_html=True)
    if st.button("📊 지식 대시보드", width="stretch"):
        st.session_state.show_db = not st.session_state.get("show_db", False)
        st.rerun()

# --- [ 메인 화면 구성 ] ---
messages = st.session_state.all_chats.get(st.session_state.current_chat_id, [])

if st.session_state.get("show_db"):
    st.markdown("<h1>📁 통합 지식 저장소</h1>", unsafe_allow_html=True)
    st.markdown(
        "<p style='color: var(--toss-subtext); font-size: 15px;'>현재 시스템이 학습하여 보유 중인 지식 통계입니다.</p>",
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns([4, 1])
    with col2:
        refresh = st.button("🔄 지식 새로고침", width="stretch")
    if refresh:
        if not rate_limit("rebuild", *REBUILD_RATE_LIMIT):
            st.warning("요청이 너무 잦습니다. 잠시 후 다시 시도해주세요.")
        else:
            with st.spinner("지식을 동기화 중..."):
                ok = core.rebuild_knowledge()
            if not ok:
                st.warning("동기화할 지식이 없거나 재구축에 실패했습니다.")
            else:
                st.rerun()

    cols = st.columns(3)
    for i, (name, count) in enumerate(core.get_knowledge_stats().items()):
        with cols[i % 3]:
            st.markdown(
                f'''<div class="toss-card"><div class="stat-label">{esc(name)}</div>'''
                f'''<div class="stat-value">{count:,} <span style="font-size: 14px; font-weight: 400; color: #8B95A1;">개</span></div></div>''',
                unsafe_allow_html=True,
            )

    st.markdown("<h3>🔍 최근 수집된 데이터 샘플</h3>", unsafe_allow_html=True)
    _, docs = core.load_index()
    if docs:
        # 수집 문서는 외부 콘텐츠이므로 반드시 이스케이프한다
        for d in docs[:5]:
            st.markdown(
                f"<div class='toss-card' style='font-size: 14px;'>{esc(str(d)[:250])}...</div>",
                unsafe_allow_html=True,
            )
    else:
        st.info("저장된 지식이 없습니다. 지식 새로고침을 진행해주세요.")

    if st.button("💬 채팅으로 돌아가기", width="stretch"):
        st.session_state.show_db = False
        st.rerun()
else:
    st.markdown(f"<h1>🧠 {esc(st.session_state.current_chat_id)}</h1>", unsafe_allow_html=True)
    st.markdown(
        "<p style='color: var(--toss-subtext); font-size: 15px;'>학습된 지식을 기반으로 전문적인 답변을 제공합니다.</p>",
        unsafe_allow_html=True,
    )

    for msg in messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("메시지를 입력하세요"):
        if not rate_limit("chat", *CHAT_RATE_LIMIT):
            st.warning("요청이 너무 잦습니다. 잠시 후 다시 시도해주세요.")
        elif core.detect_injection(prompt):
            st.error("❌ 부적절한 요청입니다.")
        else:
            sanitized = core.sanitize_input(prompt)
            if sanitized:
                messages.append({"role": "user", "content": sanitized})
                st.session_state.all_chats[st.session_state.current_chat_id] = messages
                persist()
                st.rerun()

    if messages and messages[-1]["role"] == "user":
        answer, error = None, None
        with st.chat_message("assistant"):
            with st.spinner("분석 중..."):
                answer, error = generate_reply(messages[-1]["content"])
            if error:
                st.error(error)
            else:
                st.markdown(answer)
        # st.rerun()은 BaseException을 던지므로 반드시 try 밖에서 호출한다
        if answer:
            messages.append({"role": "assistant", "content": answer})
            st.session_state.all_chats[st.session_state.current_chat_id] = messages
            persist()
            st.rerun()
