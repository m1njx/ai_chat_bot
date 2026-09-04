"""여러 LLM 제공자를 순서대로 시도하는 호출 계층.

기본 순서: Gemini → LM Studio(로컬) → OpenAI
어느 하나가 호출 오류·할당량 초과(429)·타임아웃·안전필터 차단 등으로 답을 주지
못하면 자동으로 다음 제공자로 넘어가고, 전부 실패하면 LLMError를 던진다.

LM Studio는 OpenAI 호환 서버라 openai SDK를 그대로 재사용한다. 서버가 꺼져 있으면
연결이 즉시 거부되므로 비용 없이 건너뛴다(배포 환경에서도 안전).
순서는 LLM_ORDER 환경변수로 바꿀 수 있다. 예: LLM_ORDER=lmstudio,gemini
"""

import os
import logging
from dotenv import load_dotenv

load_dotenv()

# google-genai가 매 호출마다 남기는 AFC 안내 로그 억제
logging.getLogger("google_genai.models").setLevel(logging.ERROR)

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL_ENV = os.getenv("OPENAI_MODEL")

GEMINI_TIMEOUT_MS = 60_000      # google-genai는 밀리초
OPENAI_TIMEOUT_S = 60.0         # openai는 초

# LM Studio: Developer 탭에서 Status를 Running으로 켜면 기본 http://127.0.0.1:1234
# localhost는 환경에 따라 IPv6(::1)로 풀려 접속이 안 될 수 있어 127.0.0.1을 기본으로 둔다.
LMSTUDIO_BASE_URL = os.getenv("LMSTUDIO_BASE_URL", "http://127.0.0.1:1234/v1")
LMSTUDIO_MODEL_ENV = os.getenv("LMSTUDIO_MODEL")
LMSTUDIO_TIMEOUT_S = float(os.getenv("LMSTUDIO_TIMEOUT_S", "120"))  # 로컬 추론은 느릴 수 있다

DEFAULT_ORDER = ("gemini", "lmstudio", "openai")
LLM_ORDER = tuple(
    p.strip().lower() for p in os.getenv("LLM_ORDER", ",".join(DEFAULT_ORDER)).split(",")
    if p.strip()
) or DEFAULT_ORDER

GEMINI_PREFERRED = [
    "models/gemini-3-flash-preview",
    "models/gemini-2.0-flash",
    "models/gemini-1.5-flash",
    "models/gemini-pro-latest",
    "models/gemini-pro",
]
# 비용이 낮은 순으로 우선 선택 (OPENAI_MODEL 환경변수로 덮어쓸 수 있다)
OPENAI_PREFERRED = ["gpt-5-mini", "gpt-4.1-mini", "gpt-4o-mini", "gpt-3.5-turbo"]

# 로그·예외 메시지에 섞여 나올 수 있는 비밀값
_SECRETS = [
    v for v in (
        os.getenv(n) for n in
        ("GOOGLE_API_KEY", "OPENAI_API_KEY", "NAVER_CLIENT_SECRET", "SERPER_API_KEY", "KMA_API_KEY")
    ) if v and len(v) >= 8
]


class LLMError(Exception):
    """Gemini와 OpenAI 양쪽 모두 실패했을 때."""


_state = {
    "gemini": None, "openai": None, "lmstudio": None,
    "gemini_model": None, "openai_model": None, "lmstudio_model": None,
}


def _brief(exc, limit=160):
    """예외 메시지를 짧게 줄이고 비밀값을 가린다."""
    msg = f"{type(exc).__name__}: {exc}"
    for secret in _SECRETS:
        msg = msg.replace(secret, "[REDACTED]")
    msg = " ".join(msg.split())
    return msg[:limit] + ("…" if len(msg) > limit else "")


def available():
    """최소 한 곳이라도 호출 가능한지. (LM Studio는 실행 여부를 미리 알 수 없어 항상 후보)"""
    return bool(GOOGLE_API_KEY or OPENAI_API_KEY or "lmstudio" in LLM_ORDER)


# --- [ Gemini ] ---

def _gemini():
    if not GOOGLE_API_KEY:
        return None
    if _state["gemini"] is None:
        from google import genai
        _state["gemini"] = genai.Client(api_key=GOOGLE_API_KEY)
    return _state["gemini"]


def gemini_model():
    if _state["gemini_model"]:
        return _state["gemini_model"]
    client = _gemini()
    if client is None:
        return None
    try:
        # 신 SDK는 supported_generation_methods 대신 supported_actions를 준다
        avail = [m.name for m in client.models.list()
                 if "generateContent" in (m.supported_actions or [])]
    except Exception as e:
        print(f"⚠️ Gemini 모델 목록 조회 실패: {_brief(e)}", flush=True)
        avail = []
    target = next((p for p in GEMINI_PREFERRED if p in avail), None)
    if target is None:
        target = next((m for m in avail if "flash" in m or "pro" in m), None) or "models/gemini-pro"
    _state["gemini_model"] = target
    return target


def _gemini_generate(prompt, system_instruction, timeout_ms):
    client = _gemini()
    if client is None:
        raise LLMError("GOOGLE_API_KEY 미설정")
    from google.genai import types
    config = types.GenerateContentConfig(
        http_options=types.HttpOptions(timeout=timeout_ms),
    )
    if system_instruction:
        config.system_instruction = system_instruction
    response = client.models.generate_content(
        model=gemini_model(), contents=prompt, config=config
    )
    try:
        text = (response.text or "").strip()
    except Exception as e:
        # 안전 필터에 걸리면 .text 접근 자체가 예외를 낸다
        raise LLMError(f"응답 추출 실패({_brief(e)})") from None
    if not text:
        raise LLMError("빈 응답 (안전 필터 차단 가능)")
    return text


# --- [ OpenAI 호환 제공자 (OpenAI / LM Studio 공용) ] ---

def _openai_compatible_generate(client, model, prompt, system_instruction):
    """OpenAI Chat Completions 규격. LM Studio도 같은 규격을 쓴다."""
    messages = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": prompt})
    response = client.chat.completions.create(model=model, messages=messages)
    if not response.choices:
        raise LLMError("빈 응답")
    text = (response.choices[0].message.content or "").strip()
    if not text:
        raise LLMError("빈 응답")
    return text


def _openai():
    if not OPENAI_API_KEY:
        return None
    if _state["openai"] is None:
        from openai import OpenAI
        _state["openai"] = OpenAI(api_key=OPENAI_API_KEY, timeout=OPENAI_TIMEOUT_S)
    return _state["openai"]


def openai_model():
    if _state["openai_model"]:
        return _state["openai_model"]
    if OPENAI_MODEL_ENV:
        _state["openai_model"] = OPENAI_MODEL_ENV
        return OPENAI_MODEL_ENV
    client = _openai()
    if client is None:
        return None
    try:
        avail = {m.id for m in client.models.list()}
    except Exception as e:
        print(f"⚠️ OpenAI 모델 목록 조회 실패: {_brief(e)}", flush=True)
        avail = set()
    _state["openai_model"] = next((p for p in OPENAI_PREFERRED if p in avail), "gpt-4o-mini")
    return _state["openai_model"]


def _openai_generate(prompt, system_instruction):
    client = _openai()
    if client is None:
        raise LLMError("OPENAI_API_KEY 미설정")
    return _openai_compatible_generate(client, openai_model(), prompt, system_instruction)


# --- [ LM Studio (로컬, OpenAI 호환) ] ---

def _lmstudio():
    if not LMSTUDIO_BASE_URL:
        return None
    if _state["lmstudio"] is None:
        from openai import OpenAI
        # 로컬 서버는 인증을 하지 않지만 SDK가 값을 요구하므로 더미를 넣는다
        _state["lmstudio"] = OpenAI(
            base_url=LMSTUDIO_BASE_URL, api_key="lm-studio", timeout=LMSTUDIO_TIMEOUT_S,
            max_retries=0,   # 서버가 꺼져 있으면 재시도 없이 즉시 다음 제공자로
        )
    return _state["lmstudio"]


# 채팅에 쓸 수 없는 모델(임베딩·음성·재랭커 등)을 자동 선택에서 제외
_NON_CHAT_HINTS = ("embed", "rerank", "whisper", "tts", "clip", "vae")


def lmstudio_model():
    """LM Studio에 로드된 채팅 모델 이름.

    LMSTUDIO_MODEL로 명시하지 않으면 임베딩 등 비채팅 모델을 걸러낸 뒤 첫 번째를 쓴다.
    (임베딩 모델을 chat.completions에 넘기면 그대로 실패한다)
    """
    if _state["lmstudio_model"]:
        return _state["lmstudio_model"]
    if LMSTUDIO_MODEL_ENV:
        _state["lmstudio_model"] = LMSTUDIO_MODEL_ENV
        return LMSTUDIO_MODEL_ENV
    client = _lmstudio()
    if client is None:
        return None
    models = [m.id for m in client.models.list()]   # 서버가 꺼져 있으면 여기서 예외
    chat_models = [m for m in models
                   if not any(h in m.lower() for h in _NON_CHAT_HINTS)]
    if not chat_models:
        raise LLMError(
            f"LM Studio에 채팅 가능한 모델이 없습니다 (로드된 모델: {', '.join(models) or '없음'})"
        )
    _state["lmstudio_model"] = chat_models[0]
    return chat_models[0]


def _lmstudio_generate(prompt, system_instruction):
    client = _lmstudio()
    if client is None:
        raise LLMError("LMSTUDIO_BASE_URL 미설정")
    return _openai_compatible_generate(client, lmstudio_model(), prompt, system_instruction)


# --- [ 공개 API ] ---

def generate(prompt, system_instruction=None, timeout_ms=GEMINI_TIMEOUT_MS):
    """(답변, 사용한 제공자) 반환. 모두 실패하면 LLMError.

    LLM_ORDER 순서대로 시도하며, 어떤 이유로든(429 할당량, 타임아웃, 안전필터,
    네트워크 오류, 서버 미실행 등) 실패하면 다음 제공자로 자동 전환한다.
    """
    runners = {
        "gemini": (
            bool(GOOGLE_API_KEY),
            "GOOGLE_API_KEY 미설정",
            lambda: _gemini_generate(prompt, system_instruction, timeout_ms),
        ),
        "lmstudio": (
            bool(LMSTUDIO_BASE_URL),
            "LMSTUDIO_BASE_URL 미설정",
            lambda: _lmstudio_generate(prompt, system_instruction),
        ),
        "openai": (
            bool(OPENAI_API_KEY),
            "OPENAI_API_KEY 미설정",
            lambda: _openai_generate(prompt, system_instruction),
        ),
    }

    errors = []
    for name in LLM_ORDER:
        entry = runners.get(name)
        if entry is None:
            continue
        enabled, disabled_reason, run = entry
        if not enabled:
            errors.append(f"{name}({disabled_reason})")
            continue
        try:
            text = run()
        except Exception as e:
            reason = _brief(e, 100)
            errors.append(f"{name}({reason})")
            print(f"⚠️ {name} 실패 → 다음 제공자로 전환: {reason}", flush=True)
            continue
        if errors:   # 1순위가 아니었다면 어디로 넘어갔는지 남긴다
            print(f"💡 {name}(으)로 응답했습니다.", flush=True)
        return text, name

    raise LLMError(" | ".join(errors) if errors else "사용 가능한 LLM 제공자가 없습니다")


# --- [ 스트리밍 ] ---

def _gemini_stream(prompt, system_instruction, timeout_ms):
    client = _gemini()
    if client is None:
        raise LLMError("GOOGLE_API_KEY 미설정")
    from google.genai import types
    config = types.GenerateContentConfig(
        http_options=types.HttpOptions(timeout=timeout_ms),
    )
    if system_instruction:
        config.system_instruction = system_instruction
    for chunk in client.models.generate_content_stream(
        model=gemini_model(), contents=prompt, config=config
    ):
        text = getattr(chunk, "text", None)
        if text:
            yield text


def _openai_compatible_stream(client, model, prompt, system_instruction):
    """OpenAI Chat Completions 스트리밍. LM Studio도 같은 규격."""
    messages = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": prompt})
    for chunk in client.chat.completions.create(model=model, messages=messages, stream=True):
        if not chunk.choices:
            continue
        text = getattr(chunk.choices[0].delta, "content", None)
        if text:
            yield text


def _openai_stream(prompt, system_instruction):
    client = _openai()
    if client is None:
        raise LLMError("OPENAI_API_KEY 미설정")
    return _openai_compatible_stream(client, openai_model(), prompt, system_instruction)


def _lmstudio_stream(prompt, system_instruction):
    client = _lmstudio()
    if client is None:
        raise LLMError("LMSTUDIO_BASE_URL 미설정")
    return _openai_compatible_stream(client, lmstudio_model(), prompt, system_instruction)


def generate_stream(prompt, system_instruction=None, timeout_ms=GEMINI_TIMEOUT_MS):
    """제공자를 순서대로 시도하며 이벤트 딕셔너리를 순차적으로 내보낸다.

    이벤트 종류:
      {"type": "provider", "provider": "gemini"}   첫 조각 직전에 한 번
      {"type": "chunk",    "text": "..."}          답변 조각
      {"type": "error",    "message": "..."}       더 시도할 곳이 없을 때

    폴백은 '첫 조각을 내보내기 전'에만 일어난다. 이미 일부를 전송한 뒤
    다른 제공자로 갈아타면 서로 다른 답변이 뒤섞이기 때문이다.
    """
    factories = {
        "gemini": (bool(GOOGLE_API_KEY), "GOOGLE_API_KEY 미설정",
                   lambda: _gemini_stream(prompt, system_instruction, timeout_ms)),
        "lmstudio": (bool(LMSTUDIO_BASE_URL), "LMSTUDIO_BASE_URL 미설정",
                     lambda: _lmstudio_stream(prompt, system_instruction)),
        "openai": (bool(OPENAI_API_KEY), "OPENAI_API_KEY 미설정",
                   lambda: _openai_stream(prompt, system_instruction)),
    }

    errors = []
    for name in LLM_ORDER:
        entry = factories.get(name)
        if entry is None:
            continue
        enabled, disabled_reason, factory = entry
        if not enabled:
            errors.append(f"{name}({disabled_reason})")
            continue

        emitted = False
        try:
            for piece in factory():
                if not emitted:
                    emitted = True
                    yield {"type": "provider", "provider": name}
                yield {"type": "chunk", "text": piece}
        except Exception as e:
            reason = _brief(e, 100)
            if emitted:
                # 되돌릴 수 없다 — 여기서 끊고 알린다
                print(f"⚠️ {name} 스트림 중단(전송 도중): {reason}", flush=True)
                yield {"type": "error", "message": "답변 전송이 중단되었습니다."}
                return
            errors.append(f"{name}({reason})")
            print(f"⚠️ {name} 실패 → 다음 제공자로 전환: {reason}", flush=True)
            continue

        if emitted:
            if errors:
                print(f"💡 {name}(으)로 응답했습니다.", flush=True)
            return
        errors.append(f"{name}(빈 응답)")

    yield {"type": "error",
           "message": " | ".join(errors) if errors else "사용 가능한 LLM 제공자가 없습니다"}
