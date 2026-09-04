import { useEffect, useRef, useState } from 'react'
import Markdown from 'react-markdown'

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
        {error ? content : <Markdown>{content}</Markdown>}
        {streaming && <span className="caret" />}
      </div>
    </div>
  )
}

export default function ChatView({ title, messages, pending, onSend, disabled }) {
  const [draft, setDraft] = useState('')
  const bottomRef = useRef(null)
  const textareaRef = useRef(null)

  // 새 메시지·스트리밍 조각이 올 때마다 아래로 따라간다
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, pending])

  function autosize(el) {
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`
  }

  function submit() {
    const text = draft.trim()
    if (!text || disabled) return
    setDraft('')
    autosize(textareaRef.current)
    onSend(text)
  }

  return (
    <>
      <div className="chat-scroll">
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
                content={pending.text || '분석 중…'}
                streaming={!pending.error}
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
            onChange={(e) => { setDraft(e.target.value); autosize(e.target) }}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit() }
            }}
          />
          <button
            className="send-btn"
            onClick={submit}
            disabled={disabled || !draft.trim()}
            title="보내기"
          >↑</button>
        </div>
      </div>
    </>
  )
}
