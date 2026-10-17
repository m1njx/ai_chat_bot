import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { api, streamChat, setToken } from './api'
import Sidebar from './components/Sidebar'
import ChatView from './components/ChatView'
import Login from './components/Login'
import ErrorBoundary from './components/ErrorBoundary'

const Dashboard = lazy(() => import('./components/Dashboard'))

export default function App() {
  const [session, setSession] = useState(null)   // null이면 아직 확인 전
  const [chats, setChats] = useState([])
  const [currentId, setCurrentId] = useState(null)
  const [pending, setPending] = useState(null)   // 스트리밍 중인 답변
  const [showDashboard, setShowDashboard] = useState(false)
  const [collapsed, setCollapsed] = useState(false)
  const [banner, setBanner] = useState('')
  const abortRef = useRef(null)

  const stop = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
    }
  }, [])

  const checkSession = useCallback(async () => {
    try {
      setSession(await api.session())
    } catch (err) {
      setSession({ error: err.message })
    }
  }, [])

  useEffect(() => { checkSession() }, [checkSession])

  // 모바일 사이드바가 열려 있을 때 ESC 키로 닫기
  useEffect(() => {
    function handleKeyDown(e) {
      if (e.key === 'Escape' && !collapsed && window.innerWidth <= 720) {
        setCollapsed(true)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [collapsed])

  // 화면 크기가 바뀌어도 모바일 사이드바의 배경과 키보드 포커스를 격리한다.
  useEffect(() => {
    if (collapsed) return
    const media = window.matchMedia('(max-width: 720px)')
    const sidebar = document.getElementById('app-sidebar')
    const main = document.querySelector('.main')
    if (!sidebar || !main) return
    const orig = document.body.style.overflow
    const opener = main.querySelector('[aria-controls="app-sidebar"]')
    let active = false
    function sync() {
      if (!media.matches) {
        main.inert = false
        document.body.style.overflow = orig
        if (active) opener?.focus()
        active = false
        return
      }
      main.inert = true
      document.body.style.overflow = 'hidden'
      sidebar.querySelector('button')?.focus()
      active = true
    }
    function trapFocus(e) {
      if (!active || e.key !== 'Tab') return
      const buttons = sidebar.querySelectorAll('button:not(:disabled), input:not(:disabled)')
      const first = buttons[0]
      const last = buttons[buttons.length - 1]
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last?.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first?.focus()
      }
    }
    sync()
    media.addEventListener('change', sync)
    sidebar.addEventListener('keydown', trapFocus)
    return () => {
      media.removeEventListener('change', sync)
      sidebar.removeEventListener('keydown', trapFocus)
      main.inert = false
      document.body.style.overflow = orig
      if (active) opener?.focus()
    }
  }, [collapsed, session])

  const handleAuthError = useCallback((err) => {
    if (err?.status === 401) {
      setToken('')
      checkSession()
      return true
    }
    return false
  }, [checkSession])

  const loadChats = useCallback(async () => {
    try {
      const { chats: list } = await api.listChats()
      setChats(list)
      setCurrentId((prev) => (prev && list.some((c) => c.id === prev) ? prev : list[0]?.id ?? null))
    } catch (err) {
      if (handleAuthError(err)) return
      setBanner(err.message)
    }
  }, [handleAuthError])

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

  const handleSelectChat = (id) => {
    stop()
    setCurrentId(id)
    setShowDashboard(false)
    if (typeof window !== 'undefined' && window.innerWidth <= 720) {
      setCollapsed(true)
    }
  }

  const handleToggleDashboard = () => {
    setShowDashboard((v) => !v)
    if (typeof window !== 'undefined' && window.innerWidth <= 720) {
      setCollapsed(true)
    }
  }

  async function createChat() {
    stop()
    try {
      const chat = await api.createChat()
      setChats((prev) => [...prev, chat])
      setCurrentId(chat.id)
      setShowDashboard(false)
      if (typeof window !== 'undefined' && window.innerWidth <= 720) {
        setCollapsed(true)
      }
    } catch (err) {
      if (handleAuthError(err)) return
      setBanner(err.message)
    }
  }

  async function renameChat(id, title) {
    try {
      const res = await api.renameChat(id, title)
      setChats((prev) => prev.map((c) => (c.id === id ? { ...c, title: res.title } : c)))
    } catch (err) {
      if (handleAuthError(err)) return
      setBanner(err.message)
    }
  }

  async function deleteChat(id) {
    if (currentId === id) {
      stop()
    }
    try {
      await api.deleteChat(id)
      setChats((prev) => {
        const next = prev.filter((c) => c.id !== id)
        setCurrentId((cur) => (cur === id ? next[0]?.id ?? null : cur))
        return next
      })
    } catch (err) {
      if (handleAuthError(err)) return
      setBanner(err.message)
    }
  }

  async function send(text) {
    stop()

    let chatId = currentId
    if (!chatId) {
      try {
        const chat = await api.createChat()
        setChats((prev) => [...prev, chat])
        setCurrentId(chat.id)
        chatId = chat.id
      } catch (err) {
        if (handleAuthError(err)) return
        setBanner(err.message)
        return
      }
    }

    // 사용자 메시지를 먼저 붙여 바로 보이게 한다
    setChats((prev) =>
      prev.map((c) => (c.id === chatId ? { ...c, messages: [...c.messages, { role: 'user', content: text }] } : c))
    )
    setPending({ text: '', provider: null, error: false, sources: [] })

    const controller = new AbortController()
    abortRef.current = controller
    let accumulatedText = ''
    let receivedSources = []

    try {
      await streamChat({
        chatId,
        message: text,
        signal: controller.signal,
        onEvent: (ev) => {
          if (ev.type === 'sources') {
            receivedSources = ev.sources || []
            setPending((p) => ({ ...p, sources: receivedSources }))
          } else if (ev.type === 'chunk') {
            accumulatedText += ev.text
            setPending((p) => ({ ...p, text: accumulatedText }))
          } else if (ev.type === 'provider') {
            setPending((p) => ({ ...p, provider: ev.provider }))
          } else if (ev.type === 'done') {
            const finalSources = ev.sources && ev.sources.length > 0 ? ev.sources : receivedSources
            // 서버가 최종 필터링한 전문으로 교체한다
            setChats((prev) =>
              prev.map((c) => (c.id === chatId
                ? { ...c, messages: [...c.messages, { role: 'assistant', content: ev.content, sources: finalSources }] }
                : c))
            )
            setPending(null)
          } else if (ev.type === 'error') {
            setPending({ text: ev.message, provider: null, error: true, sources: [] })
          }
        },
      })
    } catch (err) {
      if (err?.name === 'AbortError' || err?.message?.toLowerCase().includes('abort')) {
        // 사용자가 의도적으로 스트리밍을 중단한 경우
        if (accumulatedText) {
          setChats((prev) =>
            prev.map((c) => (c.id === chatId
              ? { ...c, messages: [...c.messages, { role: 'assistant', content: accumulatedText, sources: receivedSources }] }
              : c))
          )
        }
        setPending(null)
        return
      }
      if (handleAuthError(err)) return

      let errMsg = err.message || '오류가 발생했습니다.'
      if (err.status === 429 || errMsg.includes('429')) {
        errMsg = '요청이 너무 많습니다. 잠시 후 다시 시도해주세요. (Rate Limit)'
      } else if (errMsg.includes('Failed to fetch') || errMsg.includes('NetworkError')) {
        errMsg = '서버에 연결할 수 없습니다. 백엔드 서버 상태를 확인해주세요.'
      }
      setPending({ text: errMsg, provider: null, error: true, sources: [] })
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null
      }
    }
  }

  const isStreaming = Boolean(pending && !pending.error)

  return (
    <ErrorBoundary>
      <div className="layout">
        <div
          className={`sidebar-backdrop${!collapsed ? ' active' : ''}`}
          onClick={() => setCollapsed(true)}
          aria-hidden="true"
        />
        <Sidebar
          collapsed={collapsed}
          chats={chats}
          currentId={currentId}
          showDashboard={showDashboard}
          onSelect={handleSelectChat}
          onCreate={createChat}
          onRename={renameChat}
          onDelete={deleteChat}
          onToggleDashboard={handleToggleDashboard}
          onClose={() => setCollapsed(true)}
        />
        <main className="main">
          <div className="topbar">
            <button
              type="button"
              className="icon-btn"
              onClick={() => setCollapsed((v) => !v)}
              title={collapsed ? '사이드바 열기' : '사이드바 접기'}
              aria-label={collapsed ? '사이드바 열기' : '사이드바 접기'}
              aria-expanded={!collapsed}
              aria-controls="app-sidebar"
            >
              {collapsed ? '»' : '«'}
            </button>
            {banner && (
              <div className="banner error" style={{ margin: 0, flex: 1 }}
                   onClick={() => setBanner('')} role="alert">{banner}</div>
            )}
          </div>

          <Suspense fallback={<div className="login-wrap" style={{ flex: 1 }}>불러오는 중…</div>}>
            {showDashboard ? (
              <Dashboard />
            ) : (
              <ChatView
                title={current?.title || current?.id || '새 대화'}
                messages={current?.messages ?? []}
                pending={pending}
                onSend={send}
                disabled={isStreaming}
                isStreaming={isStreaming}
                onStop={stop}
              />
            )}
          </Suspense>
        </main>
      </div>
    </ErrorBoundary>
  )
}
