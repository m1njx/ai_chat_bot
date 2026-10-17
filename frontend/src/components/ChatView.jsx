import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const CodeBlock = lazy(() => import('./CodeBlock'))

function getSourceIcon(src) {
  if (src.type === 'weather') return '🌤️'
  if (src.type === 'news') return '📰'
  if (src.type === 'stock') return '📈'
  if (src.type === 'upload') {
    const isPdf = src.file_type === 'pdf' || (src.title && src.title.toLowerCase().endsWith('.pdf'))
    return isPdf ? '📄' : '📝'
  }
  if (src.type === 'web') return '🌐'
  return '📌'
}

function CitationChip({ source }) {
  const icon = getSourceIcon(source)
  const isSafeUrl = source.url && (source.url.startsWith('http://') || source.url.startsWith('https://'))

  if (isSafeUrl) {
    return (
      <a
        href={source.url}
        target="_blank"
        rel="noopener noreferrer"
        className="citation-chip clickable"
        title={`${source.title || source.label} (새 창에서 열기)`}
      >
        <span className="citation-icon">{icon}</span>
        <span className="citation-label">{source.label || source.title}</span>
        <span className="citation-external-icon">↗</span>
      </a>
    )
  }

  return (
    <span className="citation-chip" title={source.title || source.label}>
      <span className="citation-icon">{icon}</span>
      <span className="citation-label">{source.label || source.title}</span>
    </span>
  )
}

function CitationsList({ sources }) {
  if (!sources || sources.length === 0) return null
  return (
    <div className="citations-container">
      <div className="citations-header">
        <span className="citations-title">참고 출처</span>
        <span className="citations-count">{sources.length}개</span>
      </div>
      <div className="citation-wrap">
        {sources.map((src, idx) => (
          <CitationChip key={`${src.type}-${src.title || ''}-${idx}`} source={src} />
        ))}
      </div>
    </div>
  )
}

/** react-markdown은 기본적으로 원시 HTML을 실행하지 않는다(rehype-raw 미사용). */
function Bubble({ role, content, streaming, error, sources }) {
  if (role === 'user') {
    return (
      <div className="msg user">
        <div className="bubble user">{content}</div>
      </div>
    )
  }

  return (
    <div className="msg assistant-msg">
      <div className={`bubble assistant${error ? ' error' : ''}`}>
        {error ? (
          content
        ) : streaming && !content ? (
          <div className="typing-indicator" aria-label="답변 생성 중">
            <span></span>
            <span></span>
            <span></span>
          </div>
        ) : (
          <Markdown
            remarkPlugins={[remarkGfm]}
            components={{
              pre({ children }) {
                if (children && children.props) {
                  const className = children.props.className || ''
                  const match = /language-(\w+)/.exec(className)
                  const lang = match ? match[1] : ''
                  const code = String(children.props.children || '').replace(/\n$/, '')
                  return (
                    <Suspense fallback={<pre className="code-fallback"><code>{code}</code></pre>}>
                      <CodeBlock language={lang} value={code} />
                    </Suspense>
                  )
                }
                return <pre>{children}</pre>
              },
              code({ className, children, node: _node, ...props }) {
                return (
                  <code className={className ? `${className} inline-code` : 'inline-code'} {...props}>
                    {children}
                  </code>
                )
              },
              table({ children }) {
                return (
                  <div className="table-wrap">
                    <table>{children}</table>
                  </div>
                )
              },
            }}
          >
            {content}
          </Markdown>
        )}
        {streaming && content && <span className="caret" aria-hidden="true" />}
      </div>
      {!error && sources && sources.length > 0 && (
        <CitationsList sources={sources} />
      )}
    </div>
  )
}

export default function ChatView({
  title,
  messages,
  pending,
  onSend,
  onStop,
  disabled,
  isStreaming,
}) {
  const [draft, setDraft] = useState('')
  const bottomRef = useRef(null)
  const textareaRef = useRef(null)
  const scrollRef = useRef(null)
  const isNearBottomRef = useRef(true)

  const handleScroll = useCallback(() => {
    const el = scrollRef.current
    if (!el) return
    const distanceToBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    isNearBottomRef.current = distanceToBottom <= 120
  }, [])

  // 메시지 목록 변경 시(사용자 발송, 대화 변경 등) 즉시 맨 아래로 스크롤
  useEffect(() => {
    isNearBottomRef.current = true
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages])

  // 스트리밍 조각 수신 시 사용자가 하단 부근에 머물러 있을 때만 부드럽게 자동 스크롤
  useEffect(() => {
    if (isNearBottomRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
    }
  }, [pending?.text])

  function autosize(el) {
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`
  }

  function submit() {
    const text = draft.trim()
    if (!text || disabled || isStreaming) return
    setDraft('')
    autosize(textareaRef.current)
    onSend(text)
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter') {
      if (e.shiftKey) {
        // Shift + Enter: 줄바꿈 허용
        return
      }
      if (e.nativeEvent.isComposing) {
        // 한글 IME 조합 중 Enter 방어: 조합 완료 후 메시지 중복/조기 발송 차단
        return
      }
      e.preventDefault()
      submit()
    }
  }

  return (
    <>
      <div className="chat-scroll" ref={scrollRef} onScroll={handleScroll}>
        <div className="chat-inner">
          <h1 className="page-title">🧠 {title}</h1>
          <p className="page-sub">학습된 지식을 기반으로 전문적인 답변을 제공합니다.</p>

          {messages.map((m, i) => (
            <Bubble key={i} role={m.role} content={m.content} sources={m.sources} />
          ))}

          {pending && (
            <>
              <Bubble
                role="assistant"
                content={pending.text}
                streaming={!pending.error && isStreaming}
                error={pending.error}
                sources={pending.sources}
              />
              {pending.provider && pending.provider !== 'gemini' && (
                <div className="msg">
                  <span className="provider-tag">↪ {pending.provider}로 자동 전환됨</span>
                </div>
              )}
            </>
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      <div className="composer-wrap">
        <div className="composer">
          <textarea
            ref={textareaRef}
            rows={1}
            value={draft}
            placeholder="메시지를 입력하세요"
            aria-label="채팅 메시지 입력"
            onChange={(e) => { setDraft(e.target.value); autosize(e.target) }}
            onKeyDown={handleKeyDown}
          />
          {isStreaming ? (
            <button
              type="button"
              className="send-btn stop-btn"
              onClick={onStop}
              title="생성 중지"
              aria-label="응답 생성 중지"
            >
              ■
            </button>
          ) : (
            <button
              type="button"
              className="send-btn"
              onClick={submit}
              disabled={disabled || !draft.trim()}
              title="보내기"
              aria-label="메시지 전송"
            >
              ↑
            </button>
          )}
        </div>
      </div>
    </>
  )
}
