"""FastAPI 백엔드.

프론트엔드(React)와 완전히 분리되어 JSON/SSE만 제공한다.
Streamlit판(app.py)과 core.py를 공유하므로 정제·인젝션 방어·RAG 정책이 동일하다.
"""

import os
import re
import json
import time
import hmac
import uuid
import hashlib
import threading
from collections import defaultdict

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

import core
import llm

load_dotenv()

APP_PASSWORD = os.getenv("APP_PASSWORD")
# 토큰 서명용. 지정하지 않으면 프로세스마다 새로 만들어져 재시작 시 로그인이 풀린다.
SECRET_KEY = os.getenv("SECRET_KEY") or uuid.uuid4().hex

CORS_ORIGINS = [
    o.strip() for o in os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",") if o.strip()
]

MAX_MESSAGE_CHARS = 4000
CHAT_RATE_LIMIT = (10, 60)        # 60초당 10회
REBUILD_RATE_LIMIT = (2, 300)     # 300초당 2회

app = FastAPI(title="AI 지식 창고 API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,       # 인증은 Authorization 헤더(Bearer)로만 한다
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- [ 인증 ] ---
# APP_PASSWORD가 없으면 로컬 단독 모드(인증 없음, 네임스페이스 'local').
# 있으면 로그인 시 서명된 토큰을 발급하고, 토큰 안의 세션 id가 대화 네임스페이스가 된다.
# 서명 방식이라 서버를 재시작해도 토큰이 살아 있다(SECRET_KEY 고정 시).

def _sign(session_id):
    return hmac.new(SECRET_KEY.encode(), session_id.encode(), hashlib.sha256).hexdigest()[:32]


def _issue_token():
    sid = uuid.uuid4().hex
    return f"{sid}.{_sign(sid)}"


def _verify_token(token):
    if not token or "." not in token:
        return None
    sid, sig = token.rsplit(".", 1)
    if not re.fullmatch(r"[0-9a-f]{32}", sid or ""):
        return None
    return sid if hmac.compare_digest(sig, _sign(sid)) else None


def user_key(authorization):
    """요청자의 대화 네임스페이스. 인증이 필요한데 실패하면 401."""
    if not APP_PASSWORD:
        return "local"
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    sid = _verify_token(token)
    if not sid:
        raise HTTPException(status_code=401, detail="인증이 필요합니다.")
    return f"s-{sid}"


# --- [ 요청 제한 ] ---

_rate_state = defaultdict(list)
_rate_lock = threading.Lock()


def rate_limit(key, limit, window_sec):
    now = time.time()
    with _rate_lock:
        hits = [t for t in _rate_state[key] if now - t < window_sec]
        if len(hits) >= limit:
            _rate_state[key] = hits
            return False
        hits.append(now)
        _rate_state[key] = hits
        return True


def client_id(request, key):
    """세션이 있으면 세션, 없으면 IP 기준으로 제한한다."""
    if key != "local":
        return key
    return request.client.host if request.client else "unknown"


# --- [ 스키마 ] ---

class LoginBody(BaseModel):
    password: str = Field(default="", max_length=200)


class ChatCreateBody(BaseModel):
    title: str | None = Field(default=None, max_length=100)


class ChatRenameBody(BaseModel):
    title: str = Field(min_length=1, max_length=100)


class MessageBody(BaseModel):
    chat_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


# --- [ 기본 정보 ] ---

@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/session")
def session_info(authorization: str | None = Header(default=None)):
    """프론트가 처음 뜰 때 인증 필요 여부와 제공자 상태를 확인한다."""
    authenticated = True
    if APP_PASSWORD:
        try:
            user_key(authorization)
        except HTTPException:
            authenticated = False
    return {
        "auth_required": bool(APP_PASSWORD),
        "authenticated": authenticated,
        "provider_order": list(llm.LLM_ORDER),
    }


@app.post("/api/auth/login")
def login(body: LoginBody, request: Request):
    if not APP_PASSWORD:
        return {"token": None, "auth_required": False}
    if not rate_limit(f"login:{request.client.host if request.client else '?'}", 5, 60):
        raise HTTPException(status_code=429, detail="시도가 너무 잦습니다. 잠시 후 다시 시도해주세요.")
    if not hmac.compare_digest(body.password or "", APP_PASSWORD):
        raise HTTPException(status_code=401, detail="비밀번호가 올바르지 않습니다.")
    return {"token": _issue_token(), "auth_required": True}


# --- [ 대화 관리 ] ---

@app.get("/api/chats")
def list_chats(authorization: str | None = Header(default=None)):
    chats = core.load_chats(user_key(authorization))
    return {"chats": [{"id": cid, "messages": msgs} for cid, msgs in chats.items()]}


@app.post("/api/chats")
def create_chat(body: ChatCreateBody, authorization: str | None = Header(default=None)):
    key = user_key(authorization)
    chats = core.load_chats(key)
    title = core.sanitize_input(body.title or "") or f"대화 {time.strftime('%H:%M:%S')}"
    title = core.unique_name(title, chats)
    chats[title] = []
    core.save_chats(key, chats)
    return {"id": title, "messages": []}


@app.patch("/api/chats/{chat_id}")
def rename(chat_id: str, body: ChatRenameBody, authorization: str | None = Header(default=None)):
    key = user_key(authorization)
    chats = core.load_chats(key)
    if chat_id not in chats:
        raise HTTPException(status_code=404, detail="대화를 찾을 수 없습니다.")
    new_title = core.sanitize_input(body.title)
    if not new_title:
        raise HTTPException(status_code=400, detail="이름이 비어 있습니다.")
    if new_title != chat_id and new_title in chats:
        raise HTTPException(status_code=409, detail="같은 이름의 대화가 이미 있습니다.")
    core.save_chats(key, core.rename_chat(chats, chat_id, new_title))
    return {"id": new_title}


@app.delete("/api/chats/{chat_id}")
def delete_chat(chat_id: str, authorization: str | None = Header(default=None)):
    key = user_key(authorization)
    chats = core.load_chats(key)
    if chats.pop(chat_id, None) is None:
        raise HTTPException(status_code=404, detail="대화를 찾을 수 없습니다.")
    core.save_chats(key, chats)
    return {"ok": True}


# --- [ 지식 ] ---

@app.get("/api/knowledge")
def knowledge(authorization: str | None = Header(default=None)):
    user_key(authorization)
    _, docs = core.load_index()
    return {
        "stats": core.get_knowledge_stats(),
        "total_documents": len(docs),
        # 원문 그대로 전달한다. 렌더링 시 이스케이프하는 것은 프론트 책임(React 기본 동작).
        "samples": [str(d)[:250] for d in docs[:5]],
    }


@app.post("/api/knowledge/refresh")
def refresh_knowledge(request: Request, authorization: str | None = Header(default=None)):
    key = user_key(authorization)
    if not rate_limit(f"rebuild:{client_id(request, key)}", *REBUILD_RATE_LIMIT):
        raise HTTPException(status_code=429, detail="요청이 너무 잦습니다. 잠시 후 다시 시도해주세요.")
    if not core.rebuild_knowledge():
        raise HTTPException(status_code=400, detail="동기화할 지식이 없거나 재구축에 실패했습니다.")
    _, docs = core.load_index()
    return {"ok": True, "total_documents": len(docs)}


# --- [ 채팅 스트리밍 (SSE) ] ---

def _sse(payload):
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@app.post("/api/chat/stream")
def chat_stream(body: MessageBody, request: Request,
                authorization: str | None = Header(default=None)):
    key = user_key(authorization)
    if not rate_limit(f"chat:{client_id(request, key)}", *CHAT_RATE_LIMIT):
        raise HTTPException(status_code=429, detail="요청이 너무 잦습니다. 잠시 후 다시 시도해주세요.")

    if core.detect_injection(body.message):
        raise HTTPException(status_code=400, detail="부적절한 요청입니다.")
    question = core.sanitize_input(body.message)
    if not question:
        raise HTTPException(status_code=400, detail="메시지가 비어 있습니다.")

    chats = core.load_chats(key)
    if body.chat_id not in chats:
        chats[body.chat_id] = []
    chats[body.chat_id].append({"role": "user", "content": question})
    core.save_chats(key, chats)

    def event_stream():
        # 동기 제너레이터를 넘기면 Starlette이 스레드풀에서 돌리므로 이벤트 루프를 막지 않는다
        parts = []
        try:
            for ev in llm.generate_stream(
                core.build_prompt(question), system_instruction=core.SYSTEM_INSTRUCTION
            ):
                if ev["type"] == "chunk":
                    # 조각 단위로도 비밀값을 가린다. 조각 경계에 걸쳐 잘린 비밀값은
                    # 여기서 놓칠 수 있으므로, 마지막 done 이벤트에 전문을 다시 필터링해
                    # 보내고 프론트가 그것으로 교체하도록 한다.
                    parts.append(ev["text"])
                    yield _sse({"type": "chunk", "text": core.filter_output(ev["text"])})
                elif ev["type"] == "provider":
                    yield _sse(ev)
                else:
                    yield _sse({"type": "error", "message": "AI 호출 중 에러가 발생했습니다."})
                    print(f"⚠️ 답변 생성 실패: {ev.get('message')}", flush=True)
                    return
        except Exception as e:
            print(f"⚠️ 스트림 처리 중 오류: {e}", flush=True)
            yield _sse({"type": "error", "message": "AI 호출 중 에러가 발생했습니다."})
            return

        answer = core.filter_output("".join(parts))
        if answer:
            saved = core.load_chats(key)
            saved.setdefault(body.chat_id, []).append({"role": "assistant", "content": answer})
            core.save_chats(key, saved)
        yield _sse({"type": "done", "content": answer})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
