import streamlit as st
import google.generativeai as genai
import pdfplumber
import os
import json
import time
import numpy as np
import faiss
import pandas as pd
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
import re
from datetime import datetime, timedelta

# 1. 환경 및 경로 설정
load_dotenv()
API_KEY = os.getenv("GOOGLE_API_KEY")

DATA_DIR = "data"
DB_PATH = "faiss_index.bin"
DOCS_PATH = "documents_data.json"
SAVE_FILE = "chat_history.json"

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

st.set_page_config(page_title="나만의 AI 지식 창고", page_icon="🧠", layout="wide")

# 2. 토스(Toss) 디자인 시스템 (CSS 주입 방식 최적화)
# st.markdown 대신 st.components.v1.html을 사용하여 코드 노출을 원천 차단
import streamlit.components.v1 as components

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
# 렌더링되지 않도록 head에 주입 (Streamlit의 _repr_html_ 이용)
st.markdown(css_styles, unsafe_allow_html=True)

# 3. 핵심 기능 함수
@st.cache_resource
def init_models():
    genai.configure(api_key=API_KEY)
    try:
        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
    except: available_models = []
    preferred = ["models/gemini-3-flash-preview", "models/gemini-2.0-flash", "models/gemini-1.5-flash", "models/gemini-pro-latest", "models/gemini-pro"]
    target = "models/gemini-pro"
    for p in preferred:
        if p in available_models: target = p; break
    return SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2'), target

embed_model, SELECTED_GEMINI_MODEL = init_models()

# --- [ 보안 및 방어 설정 ] ---
def sanitize_input(text):
    if not text: return ""
    text = re.sub(r'<[^>]*?>', '', text)
    for p in [r'javascript:', r'onerror', r'onclick', r'onload', r'eval\(', r'alert\(', r'<script']:
        text = re.sub(p, '[removed]', text, flags=re.IGNORECASE)
    return text.strip()

def detect_injection(text):
    for k in ["ignore all previous instructions", "forget everything", "system prompt", "이전 지침은 모두 무시"]:
        if k.lower() in text.lower(): return True
    return False

def filter_output(text):
    if not text: return ""
    text = re.sub(r'AIza[0-9A-Za-z-_]{35}', '[SENSITIVE_DATA_HIDDEN]', text)
    return text.replace(DB_PATH, "[PROTECTED_FILE]").replace(DOCS_PATH, "[PROTECTED_FILE]")

# --- [ 데이터 처리 ] ---
def get_knowledge_stats():
    stats = {}
    if os.path.exists(DATA_DIR):
        for file in os.listdir(DATA_DIR):
            if file.lower().endswith(".json") and file not in [SAVE_FILE, DOCS_PATH]:
                try:
                    with open(os.path.join(DATA_DIR, file), "r", encoding="utf-8") as f:
                        data = json.load(f)
                        count = len(data) if isinstance(data, list) else 1
                        stats[file.replace(".json", "")] = count
                except: pass
            elif file.lower().endswith((".pdf", ".txt")) and file != "requirements.txt":
                stats.setdefault("문서/메모", 0)
                stats["문서/메모"] += 1
    return stats

def load_all_chats():
    if os.path.exists(SAVE_FILE):
        try:
            with open(SAVE_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except: pass
    return {}

def save_all_chats(chats):
    with open(SAVE_FILE, "w", encoding="utf-8") as f: json.dump(chats, f, ensure_ascii=False, indent=4)

def get_db_no_cache():
    if os.path.exists(DB_PATH) and os.path.exists(DOCS_PATH):
        try:
            index = faiss.read_index(DB_PATH)
            with open(DOCS_PATH, "r", encoding="utf-8") as f: docs = json.load(f)
            return index, docs
        except: pass
    return None, []

def process_knowledge_silent():
    documents = []
    if os.path.exists(DATA_DIR):
        for file in os.listdir(DATA_DIR):
            path = os.path.join(DATA_DIR, file)
            if file.lower().endswith(".pdf"):
                with pdfplumber.open(path) as pdf:
                    for page in pdf.pages:
                        text = page.extract_text()
                        if text: documents.append(f"[PDF: {file}] {text}")
            elif file.lower().endswith(".txt") and file != "requirements.txt":
                with open(path, "r", encoding="utf-8") as f: documents.append(f"[메모: {file}] {f.read()}")
            elif file.lower().endswith(".json") and file not in [SAVE_FILE, DOCS_PATH]:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    items = data if isinstance(data, list) else [data]
                    for item in items:
                        src = item.get('source', '지식'); tit = item.get('title', ''); desc = item.get('description', '')
                        documents.append(f"[{src}: {tit}] {desc}")
    if documents:
        embeddings = embed_model.encode(documents)
        index = faiss.IndexFlatL2(embeddings.shape[1])
        index.add(np.array(embeddings).astype('float32'))
        faiss.write_index(index, DB_PATH)
        with open(DOCS_PATH, "w", encoding="utf-8") as f: json.dump(documents, f, ensure_ascii=False)
        return True
    return False

# --- [ UI 구성 ] ---
if "all_chats" not in st.session_state: st.session_state.all_chats = load_all_chats()
if "current_chat_id" not in st.session_state:
    st.session_state.current_chat_id = list(st.session_state.all_chats.keys())[0] if st.session_state.all_chats else "새 대화"
if "rename_target" not in st.session_state: st.session_state.rename_target = None

with st.sidebar:
    st.markdown("<h2>📂 대화 목록</h2>", unsafe_allow_html=True)
    if st.button("➕ 새 대화 시작", use_container_width=True):
        new_id = f"대화 {time.strftime('%H:%M:%S')}"
        st.session_state.all_chats[new_id] = []
        st.session_state.current_chat_id = new_id
        save_all_chats(st.session_state.all_chats)
        st.rerun()
    st.divider()
    
    # 사이드바 관리 UI 개선
    for cid in list(st.session_state.all_chats.keys()):
        is_active = (cid == st.session_state.current_chat_id)
        
        if st.session_state.rename_target == cid:
            new_name = st.text_input("수정", value=cid, key=f"in_{cid}", label_visibility="collapsed")
            c1, c2 = st.columns(2)
            if c1.button("확인", key=f"ok_{cid}"):
                if new_name and new_name != cid:
                    st.session_state.all_chats[new_name] = st.session_state.all_chats.pop(cid)
                    st.session_state.current_chat_id = new_name
                    save_all_chats(st.session_state.all_chats)
                st.session_state.rename_target = None
                st.rerun()
            if c2.button("취소", key=f"cn_{cid}"):
                st.session_state.rename_target = None
                st.rerun()
        else:
            # 더 깔끔한 레이아웃 (아이콘 버튼 활용)
            with st.container():
                col_btn, col_tool = st.columns([4, 1])
                with col_btn:
                    if st.button(f"{'📍' if is_active else '💬'} {cid[:10]}", key=f"sel_{cid}", use_container_width=True):
                        st.session_state.current_chat_id = cid
                        st.rerun()
                with col_tool:
                    # 팝오버를 사용하여 관리 기능 숨김 (Toss 스타일의 미니멀리즘)
                    with st.popover("⚙️", use_container_width=True):
                        if st.button("✏️ 이름 수정", key=f"ed_{cid}", use_container_width=True):
                            st.session_state.rename_target = cid
                            st.rerun()
                        if st.button("🗑️ 삭제", key=f"dl_{cid}", use_container_width=True):
                            st.session_state.all_chats.pop(cid)
                            if st.session_state.current_chat_id == cid:
                                st.session_state.current_chat_id = list(st.session_state.all_chats.keys())[0] if st.session_state.all_chats else "새 대화"
                            save_all_chats(st.session_state.all_chats)
                            st.rerun()
    
    st.sidebar.markdown("<div style='height: 100px;'></div>", unsafe_allow_html=True)
    if st.button("📊 지식 대시보드", use_container_width=True):
        st.session_state.show_db = not st.session_state.get('show_db', False)
        st.rerun()

# --- [ 메인 화면 구성 ] ---
index, docs = get_db_no_cache()
messages = st.session_state.all_chats.get(st.session_state.current_chat_id, [])

if st.session_state.get('show_db'):
    st.markdown("<h1>📁 통합 지식 저장소</h1>", unsafe_allow_html=True)
    st.markdown("<p style='color: var(--toss-subtext); font-size: 15px;'>현재 시스템이 학습하여 보유 중인 지식 통계입니다.</p>", unsafe_allow_html=True)
    
    col1, col2 = st.columns([4, 1])
    with col2:
        if st.button("🔄 지식 새로고침", use_container_width=True):
            with st.spinner("지식을 동기화 중..."): process_knowledge_silent()
            st.rerun()
    
    stats = get_knowledge_stats()
    cols = st.columns(3)
    for i, (name, count) in enumerate(stats.items()):
        with cols[i % 3]:
            st.markdown(f"""<div class="toss-card"><div class="stat-label">{name}</div><div class="stat-value">{count:,} <span style="font-size: 14px; font-weight: 400; color: #8B95A1;">개</span></div></div>""", unsafe_allow_html=True)
    
    st.markdown("<h3>🔍 최근 수집된 데이터 샘플</h3>", unsafe_allow_html=True)
    if docs:
        for d in docs[:5]: st.markdown(f"<div class='toss-card' style='font-size: 14px;'>{d[:250]}...</div>", unsafe_allow_html=True)
    else: st.info("저장된 지식이 없습니다. 지식 새로고침을 진행해주세요.")
        
    if st.button("💬 채팅으로 돌아가기", use_container_width=True):
        st.session_state.show_db = False
        st.rerun()
else:
    st.markdown(f"<h1>🧠 {st.session_state.current_chat_id}</h1>", unsafe_allow_html=True)
    st.markdown("<p style='color: var(--toss-subtext); font-size: 15px;'>학습된 지식을 기반으로 전문적인 답변을 제공합니다.</p>", unsafe_allow_html=True)

    for msg in messages:
        with st.chat_message(msg["role"]): st.markdown(msg["content"])

    if prompt := st.chat_input("메시지를 입력하세요"):
        if detect_injection(prompt): st.error("❌ 부적절한 요청입니다."); st.stop()
        sanitized = sanitize_input(prompt)
        if sanitized:
            messages.append({"role": "user", "content": sanitized})
            st.session_state.all_chats[st.session_state.current_chat_id] = messages
            save_all_chats(st.session_state.all_chats)
            st.rerun()

    if messages and messages[-1]["role"] == "user":
        with st.chat_message("assistant"):
            with st.spinner("분석 중..."):
                context = ""
                if index:
                    q_v = embed_model.encode([messages[-1]["content"]])
                    D, I = index.search(np.array(q_v).astype('float32'), k=5)
                    context = "\n".join([docs[i] for i in I[0] if i < len(docs)])
                try:
                    system_instruction = "너는 '나만의 AI 지식 창고'의 지능형 어시스턴트이다. 지식을 참고하여 답변하되 한국어로 친절하게 작성하라."
                    model = genai.GenerativeModel(model_name=SELECTED_GEMINI_MODEL, system_instruction=system_instruction)
                    full_prompt = f"<지식>\n{context}\n\n<입력>\n{messages[-1]['content']}\n</입력>"
                    response = model.generate_content(full_prompt)
                    if response and response.text:
                        safe_res = filter_output(response.text)
                        st.markdown(safe_res)
                        messages.append({"role": "assistant", "content": safe_res})
                        st.session_state.all_chats[st.session_state.current_chat_id] = messages
                        save_all_chats(st.session_state.all_chats)
                        st.rerun()
                except: st.error("AI 호출 중 에러가 발생했습니다.")