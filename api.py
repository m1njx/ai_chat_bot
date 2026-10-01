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
from datetime import datetime, timezone

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

# 세션 토큰 유효 기간 (초). 기본값: 86400 (24시간)
def _get_session_ttl() -> int:
    raw = os.getenv("SESSION_TTL_SECONDS", "86400").strip()
    try:
        val = int(raw)
        if 0 < val <= 31536000:
            return val
    except ValueError:
        pass
    return 86400

SESSION_TTL_SECONDS = _get_session_ttl()

# 리버스 프록시(Render 등) 환경에서 X-Forwarded-For 헤더 신뢰 여부
TRUST_PROXY_HEADERS = os.getenv("TRUST_PROXY_HEADERS", "false").lower() in ("true", "1", "yes")

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


# --- [ 인증 및 세션 (Phase 3: Expiration & Stable Owner) ] ---
# APP_PASSWORD가 없으면 로컬 단독 모드(인증 없음, 네임스페이스 'local').
# 있으면 로그인 시 서명 및 만료시간(TTL)이 포함된 v2 토큰을 발급한다.
# 단일 APP_PASSWORD 기반 private chatbot이므로, 인증된 모든 세션은 안정적인 'local' 대화 저장소를 공유한다.
# 토큰 포맷: v2.<session_id>.<issued_at>.<expires_at>.<signature>

def _sign(payload: str) -> str:
    return hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()


def _issue_token() -> str:
    sid = uuid.uuid4().hex
    iat = int(time.time())
    exp = iat + SESSION_TTL_SECONDS
    payload = f"v2.{sid}.{iat}.{exp}"
    return f"{payload}.{_sign(payload)}"


def _verify_token(token: str) -> dict | None:
    """토큰 검증: 형식이 맞고, 서명이 일치하며, 만료되지 않은 경우 세션 정보 반환.
    만료되었거나 변조된 경우, 또는 구버전(v1 무만료) 토큰은 거부된다.
    """
    if not token or not isinstance(token, str):
        return None
    parts = token.split(".")
    if len(parts) != 5:
        return None
    version, sid, iat_s, exp_s, sig = parts
    if version != "v2":
        return None
    if not re.fullmatch(r"[0-9a-f]{32}", sid):
        return None
    try:
        iat = int(iat_s)
        exp = int(exp_s)
    except ValueError:
        return None

    payload = f"v2.{sid}.{iat}.{exp}"
    if not hmac.compare_digest(sig, _sign(payload)):
        return None

    now = int(time.time())
    if now > exp:
        return None

    return {"session_id": sid, "issued_at": iat, "expires_at": exp}


def user_key(authorization: str | None) -> str:
    """요청자의 대화 네임스페이스. 인증이 필요한데 실패하면 401.
    단일 APP_PASSWORD 기반 앱이므로 인증된 사용자는 모두 안정적인 'local' 네임스페이스를 공유한다.
    """
    if not APP_PASSWORD:
        return "local"
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    session = _verify_token(token)
    if not session:
        raise HTTPException(status_code=401, detail="인증이 필요합니다.")
    return "local"


# --- [ 요청 제한 & 프록시 헤더 처리 ] ---

def get_client_ip(request: Request) -> str:
    if TRUST_PROXY_HEADERS:
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
            if client_ip:
                return client_ip
    return request.client.host if request.client else "unknown"


_rate_state = defaultdict(list)
_rate_lock = threading.Lock()
_last_rate_cleanup = 0.0


def rate_limit(key: str, limit: int, window_sec: int) -> bool:
    global _last_rate_cleanup
    now = time.time()
    with _rate_lock:
        # 주기적 정리 (60초마다 만료된 키 완전히 제거 → 메모리 누수 차단)
        if now - _last_rate_cleanup > 60:
            stale_keys = []
            for k, timestamps in list(_rate_state.items()):
                valid = [t for t in timestamps if now - t < 300]
                if not valid:
                    stale_keys.append(k)
                else:
                    _rate_state[k] = valid
            for k in stale_keys:
                _rate_state.pop(k, None)
            _last_rate_cleanup = now

        hits = [t for t in _rate_state[key] if now - t < window_sec]
        if len(hits) >= limit:
            _rate_state[key] = hits
            return False
        hits.append(now)
        _rate_state[key] = hits
        return True


def client_id(request: Request, authorization: str | None = None) -> str:
    """세션 토큰이 유효하면 세션 식별자, 없으면 클라이언트 IP 기준으로 식별한다."""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        session = _verify_token(token)
        if session:
            return f"sid:{session['session_id']}"
    return f"ip:{get_client_ip(request)}"


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
    ip = get_client_ip(request)
    if not rate_limit(f"login:{ip}", 5, 60):
        raise HTTPException(status_code=429, detail="시도가 너무 잦습니다. 잠시 후 다시 시도해주세요.")
    if not hmac.compare_digest(body.password or "", APP_PASSWORD):
        raise HTTPException(status_code=401, detail="비밀번호가 올바르지 않습니다.")
    return {"token": _issue_token(), "auth_required": True}


# --- [ 대화 관리 ] ---

@app.get("/api/chats")
def list_chats(authorization: str | None = Header(default=None)):
    chats = core.load_chats(user_key(authorization))
    out = []
    for cid, chat in chats.items():
        if isinstance(chat, dict):
            out.append({
                "id": chat.get("id", cid),
                "title": chat.get("title", f"대화 {cid[:8]}"),
                "created_at": chat.get("created_at"),
                "updated_at": chat.get("updated_at"),
                "messages": chat.get("messages", []),
            })
        elif isinstance(chat, list):
            out.append({
                "id": cid,
                "title": cid,
                "messages": chat,
            })
    return {"chats": out}


@app.post("/api/chats")
def create_chat(body: ChatCreateBody, authorization: str | None = Header(default=None)):
    key = user_key(authorization)
    raw_title = core.sanitize_input(body.title or "")

    def _create(chats):
        title = raw_title
        if not title:
            default_title = f"대화 {time.strftime('%H:%M:%S')}"
            title = core.unique_title(default_title, chats)
        chat = core.new_chat(title=title)
        chats[chat["id"]] = chat
        return chat

    chat = core.modify_chats(key, _create)
    return {"id": chat["id"], "title": chat["title"], "messages": []}


@app.patch("/api/chats/{chat_id}")
def rename(chat_id: str, body: ChatRenameBody, authorization: str | None = Header(default=None)):
    key = user_key(authorization)
    new_title = core.sanitize_input(body.title)
    if not new_title:
        raise HTTPException(status_code=400, detail="이름이 비어 있습니다.")

    def _rename(chats):
        if chat_id not in chats:
            return None
        chat = chats[chat_id]
        if isinstance(chat, dict):
            chat["title"] = new_title
            chat["updated_at"] = datetime.now(timezone.utc).isoformat()
        else:
            chats[chat_id] = {"id": chat_id, "title": new_title, "messages": chat}
        return {"id": chat_id, "title": new_title}

    result = core.modify_chats(key, _rename)
    if not result:
        raise HTTPException(status_code=404, detail="대화를 찾을 수 없습니다.")
    return result


@app.delete("/api/chats/{chat_id}")
def delete_chat(chat_id: str, authorization: str | None = Header(default=None)):
    key = user_key(authorization)

    def _del(chats):
        return chats.pop(chat_id, None) is not None

    if not core.modify_chats(key, _del):
        raise HTTPException(status_code=404, detail="대화를 찾을 수 없습니다.")
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
    cid = client_id(request, authorization)
    if not rate_limit(f"rebuild:{cid}", *REBUILD_RATE_LIMIT):
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
    cid = client_id(request, authorization)
    if not rate_limit(f"chat:{cid}", *CHAT_RATE_LIMIT):
        raise HTTPException(status_code=429, detail="요청이 너무 잦습니다. 잠시 후 다시 시도해주세요.")

    if core.detect_injection(body.message):
        raise HTTPException(status_code=400, detail="부적절한 요청입니다.")
    question = core.sanitize_input(body.message)
    if not question:
        raise HTTPException(status_code=400, detail="메시지가 비어 있습니다.")

    def _append_user(chats):
        if body.chat_id not in chats:
            chats[body.chat_id] = core.new_chat(chat_id=body.chat_id)
        chat = chats[body.chat_id]
        if isinstance(chat, list):
            chat = {"id": body.chat_id, "title": body.chat_id, "messages": chat}
            chats[body.chat_id] = chat
        prior = list(chat.get("messages", []))
        chat.setdefault("messages", []).append({"role": "user", "content": question})
        chat["updated_at"] = datetime.now(timezone.utc).isoformat()
        return prior

    prior_history = core.modify_chats(key, _append_user)

    # Multi-turn 프롬프트 생성 (RAG 지식 + 이전 대화 맥락 + 현재 질문)
    prompt = core.build_prompt(question, history=prior_history)

    def event_stream():
        # 동기 제너레이터를 넘기면 Starlette이 스레드풀에서 돌리므로 이벤트 루프를 막지 않는다
        parts = []
        try:
            for ev in llm.generate_stream(
                prompt, system_instruction=core.SYSTEM_INSTRUCTION
            ):
                if ev["type"] == "chunk":
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
            def _append_assistant(chats):
                if body.chat_id in chats and isinstance(chats[body.chat_id], dict):
                    chats[body.chat_id].setdefault("messages", []).append({"role": "assistant", "content": answer})
                    chats[body.chat_id]["updated_at"] = datetime.now(timezone.utc).isoformat()
            core.modify_chats(key, _append_assistant)
        yield _sse({"type": "done", "content": answer})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
