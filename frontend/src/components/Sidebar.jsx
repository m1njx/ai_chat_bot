import { useState } from 'react'

export default function Sidebar({
  collapsed, chats, currentId, onSelect, onCreate, onRename, onDelete, onToggleDashboard, showDashboard,
}) {
  const [renaming, setRenaming] = useState(null)
  const [draft, setDraft] = useState('')

  function startRename(chat) {
    setRenaming(chat.id)
    setDraft(chat.title || chat.id || '')
  }

  async function commitRename(chat) {
    const next = draft.trim()
    setRenaming(null)
    const currentTitle = chat.title || chat.id
    if (next && next !== currentTitle) await onRename(chat.id, next)
  }

  return (
    <aside className={`sidebar${collapsed ? ' collapsed' : ''}`}>
      <h2>📂 대화 목록</h2>
      <button className="side-btn primary" onClick={onCreate}>➕ 새 대화 시작</button>
      <hr className="divider" />

      {chats.length === 0 && (
        <div style={{ color: 'var(--toss-subtext)', fontSize: 14, padding: '4px 12px' }}>
          아직 대화가 없습니다.
        </div>
      )}

      {chats.map((chat) => {
        const displayTitle = chat.title || chat.id
        return renaming === chat.id ? (
          <div className="rename-row" key={chat.id}>
            <input
              value={draft}
              autoFocus
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') commitRename(chat)
                if (e.key === 'Escape') setRenaming(null)
              }}
            />
            <button className="icon-btn" title="확인" onClick={() => commitRename(chat)}>✓</button>
            <button className="icon-btn" title="취소" onClick={() => setRenaming(null)}>✕</button>
          </div>
        ) : (
          <div className="chat-row" key={chat.id}>
            <button
              className={`side-btn${chat.id === currentId && !showDashboard ? ' active' : ''}`}
              onClick={() => onSelect(chat.id)}
              title={displayTitle}
            >
              {chat.id === currentId && !showDashboard ? '📍' : '💬'} {displayTitle}
            </button>
            <button className="icon-btn" title="이름 수정" onClick={() => startRename(chat)}>✏️</button>
            <button className="icon-btn" title="삭제" onClick={() => onDelete(chat.id)}>🗑️</button>
          </div>
        )
      })}

      <div className="spacer" />
      <hr className="divider" />
      <button className={`side-btn${showDashboard ? ' active' : ''}`} onClick={onToggleDashboard}>
        📊 지식 대시보드
      </button>
    </aside>
  )
}
