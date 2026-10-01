import { useCallback, useEffect, useRef, useState } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'

function CodeBlock({ language, value }) {
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(value)
      } else {
        const ta = document.createElement('textarea')
        ta.value = value
        ta.style.position = 'fixed'
        ta.style.opacity = '0'
        document.body.appendChild(ta)
        ta.select()
        document.execCommand('copy')
        document.body.removeChild(ta)
      }
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      /* 클립보드 접근 불가 환경 안전 처리 */
    }
  }

  const langLabel = language ? language.toLowerCase() : 'code'

  return (
    <div className="code-block-wrap">
      <div className="code-header">
        <span className="code-lang">{langLabel}</span>
        <button
          type="button"
          className={`copy-code-btn${copied ? ' copied' : ''}`}
          onClick={copy}
          title={copied ? '복사 완료' : '코드 복사'}
          aria-label={copied ? '코드가 클립보드에 복사됨' : '코드 복사'}
        >
          {copied ? '✓ 복사됨' : '복사'}
        </button>
      </div>
      <SyntaxHighlighter
        language={language || 'text'}
        style={vscDarkPlus}
        customStyle={{
          margin: 0,
          padding: '12px 14px',
          background: 'transparent',
          fontSize: '13.5px',
          lineHeight: '1.55',
          borderRadius: 0,
        }}
        PreTag="div"
      >
        {value}
      </SyntaxHighlighter>
    </div>
  )
}

/** react-markdown은 기본적으로 원시 HTML을 실행하지 않는다(rehype-raw 미사용). */
function Bubble({ role, content, streaming, error }) {
  if (role === 'user') {
    return (
      <div className="msg user">
        <div className="bubble user">{content}</div>
      </div>
    )
  }

  return (
    <div className="msg">
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
                  return <CodeBlock language={lang} value={code} />
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
            <Bubble key={i} role={m.role} content={m.content} />
          ))}

          {pending && (
            <>
              <Bubble
                role="assistant"
                content={pending.text}
                streaming={!pending.error && isStreaming}
                error={pending.error}
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
