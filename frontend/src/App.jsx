import { useCallback, useEffect, useState } from 'react'
import { api, streamChat, setToken } from './api'
import Sidebar from './components/Sidebar'
import ChatView from './components/ChatView'
import Dashboard from './components/Dashboard'
import Login from './components/Login'

export default function App() {
  const [session, setSession] = useState(null)   // null이면 아직 확인 전
  const [chats, setChats] = useState([])
  const [currentId, setCurrentId] = useState(null)
  const [pending, setPending] = useState(null)   // 스트리밍 중인 답변
  const [showDashboard, setShowDashboard] = useState(false)
  const [collapsed, setCollapsed] = useState(false)
  const [banner, setBanner] = useState('')

  const checkSession = useCallback(async () => {
    try {
      setSession(await api.session())
    } catch (err) {
      setSession({ error: err.message })
    }
  }, [])

  useEffect(() => { checkSession() }, [checkSession])

  const loadChats = useCallback(async () => {
    try {
      const { chats: list } = await api.listChats()
      setChats(list)
      setCurrentId((prev) => (prev && list.some((c) => c.id === prev) ? prev : list[0]?.id ?? null))
    } catch (err) {
      if (err.status === 401) { setToken(''); checkSession() }
      else setBanner(err.message)
    }
  }, [checkSession])

  const ready = session && !session.error && (!session.auth_required || session.authenticated)

  useEffect(() => { if (ready) loadChats() }, [ready, loadChats])

  if (!session) return <div className="login-wrap">불러오는 중…</div>
  if (session.error) {
    return (
      <div className="login-wrap">
        <div className="toss-card login-card">
          <h2 style={{ marginTop: 0 }}>서버에 연결할 수 없습니다</h2>
          <div className="banner error">{session.error}</div>
          <p className="page-sub" style={{ fontSize: 14 }}>
            백엔드가 실행 중인지, <code>VITE_API_BASE</code> 설정이 맞는지 확인해주세요.
          </p>
          <button className="side-btn primary" onClick={checkSession}>다시 시도</button>
        </div>
      </div>
    )
  }
  if (!ready) return <Login onSuccess={() => { checkSession(); }} />

  const current = chats.find((c) => c.id === currentId)

  async function createChat() {
    try {
      const chat = await api.createChat()
      setChats((prev) => [...prev, chat])
      setCurrentId(chat.id)
      setShowDashboard(false)
    } catch (err) { setBanner(err.message) }
  }

  async function renameChat(id, title) {
    try {
      const { id: newId } = await api.renameChat(id, title)
      setChats((prev) => prev.map((c) => (c.id === id ? { ...c, id: newId } : c)))
      setCurrentId((prev) => (prev === id ? newId : prev))
    } catch (err) { setBanner(err.message) }
  }

  async function deleteChat(id) {
    try {
      await api.deleteChat(id)
      setChats((prev) => {
        const next = prev.filter((c) => c.id !== id)
        setCurrentId((cur) => (cur === id ? next[0]?.id ?? null : cur))
        return next
      })
    } catch (err) { setBanner(err.message) }
  }

  async function send(text) {
    let chatId = currentId
    if (!chatId) {
      try {
        const chat = await api.createChat()
        setChats((prev) => [...prev, chat])
        setCurrentId(chat.id)
        chatId = chat.id
      } catch (err) { setBanner(err.message); return }
    }

    // 사용자 메시지를 먼저 붙여 바로 보이게 한다
    setChats((prev) =>
      prev.map((c) => (c.id === chatId ? { ...c, messages: [...c.messages, { role: 'user', content: text }] } : c))
    )
    setPending({ text: '', provider: null, error: false })

    try {
      await streamChat({
        chatId,
        message: text,
        onEvent: (ev) => {
          if (ev.type === 'chunk') {
            setPending((p) => ({ ...p, text: (p?.text ?? '') + ev.text }))
          } else if (ev.type === 'provider') {
            setPending((p) => ({ ...p, provider: ev.provider }))
          } else if (ev.type === 'done') {
            // 서버가 최종 필터링한 전문으로 교체한다
            setChats((prev) =>
              prev.map((c) => (c.id === chatId
                ? { ...c, messages: [...c.messages, { role: 'assistant', content: ev.content }] }
                : c))
            )
            setPending(null)
          } else if (ev.type === 'error') {
            setPending({ text: ev.message, provider: null, error: true })
          }
        },
      })
    } catch (err) {
      setPending({ text: err.message, provider: null, error: true })
    }
  }

  return (
    <div className="layout">
      <Sidebar
        collapsed={collapsed}
        chats={chats}
        currentId={currentId}
        showDashboard={showDashboard}
        onSelect={(id) => { setCurrentId(id); setShowDashboard(false) }}
        onCreate={createChat}
        onRename={renameChat}
        onDelete={deleteChat}
        onToggleDashboard={() => setShowDashboard((v) => !v)}
      />
      <main className="main">
        <div className="topbar">
          <button className="icon-btn" onClick={() => setCollapsed((v) => !v)}
                  title={collapsed ? '사이드바 열기' : '사이드바 접기'}>
            {collapsed ? '»' : '«'}
          </button>
          {banner && (
            <div className="banner error" style={{ margin: 0, flex: 1 }}
                 onClick={() => setBanner('')} role="alert">{banner}</div>
          )}
        </div>

        {showDashboard ? (
          <Dashboard />
        ) : (
          <ChatView
            title={current?.id ?? '새 대화'}
            messages={current?.messages ?? []}
            pending={pending}
            onSend={send}
            disabled={!!pending && !pending.error}
          />
        )}
      </main>
    </div>
  )
}
