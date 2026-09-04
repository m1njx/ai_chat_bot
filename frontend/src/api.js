const BASE = (import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000').replace(/\/$/, '')
const TOKEN_KEY = 'ai_knowledge_token'

export const getToken = () => {
  try { return localStorage.getItem(TOKEN_KEY) || '' } catch { return '' }
}
export const setToken = (t) => {
  try {
    if (t) localStorage.setItem(TOKEN_KEY, t)
    else localStorage.removeItem(TOKEN_KEY)
  } catch { /* 프라이빗 모드 등 저장 불가 환경 무시 */ }
}

function headers(json = true) {
  const h = {}
  if (json) h['Content-Type'] = 'application/json'
  const t = getToken()
  if (t) h['Authorization'] = `Bearer ${t}`
  return h
}

/** 응답에서 서버가 준 detail 메시지를 살려 던진다. */
async function toError(res) {
  let detail = `요청 실패 (${res.status})`
  try {
    const data = await res.json()
    if (data?.detail) detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
  } catch { /* 본문이 JSON이 아닐 수 있다 */ }
  const err = new Error(detail)
  err.status = res.status
  return err
}

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, { headers: headers(), ...options })
  if (!res.ok) throw await toError(res)
  return res.status === 204 ? null : res.json()
}

export const api = {
  session: () => request('/api/session'),
  login: (password) => request('/api/auth/login', { method: 'POST', body: JSON.stringify({ password }) }),
  listChats: () => request('/api/chats'),
  createChat: (title) => request('/api/chats', { method: 'POST', body: JSON.stringify({ title: title ?? null }) }),
  renameChat: (id, title) =>
    request(`/api/chats/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify({ title }) }),
  deleteChat: (id) => request(`/api/chats/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  knowledge: () => request('/api/knowledge'),
  refreshKnowledge: () => request('/api/knowledge/refresh', { method: 'POST' }),
}

/**
 * 채팅 스트리밍. POST + SSE라 EventSource를 쓸 수 없어 fetch 스트림을 직접 읽는다.
 * onEvent({type:'provider'|'chunk'|'done'|'error', ...})
 */
export async function streamChat({ chatId, message, signal, onEvent }) {
  const res = await fetch(`${BASE}/api/chat/stream`, {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify({ chat_id: chatId, message }),
    signal,
  })
  if (!res.ok) throw await toError(res)

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    // SSE 이벤트는 빈 줄로 구분된다
    let idx
    while ((idx = buffer.indexOf('\n\n')) !== -1) {
      const raw = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 2)
      for (const line of raw.split('\n')) {
        if (!line.startsWith('data:')) continue
        try {
          onEvent(JSON.parse(line.slice(5).trim()))
        } catch {
          /* 잘린 조각은 무시 */
        }
      }
    }
  }
}
