import { useState } from 'react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'

export default function CodeBlock({ language, value }) {
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
