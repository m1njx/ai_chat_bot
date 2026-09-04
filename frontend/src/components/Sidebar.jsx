import { useState } from 'react'

export default function Sidebar({
  collapsed, chats, currentId, onSelect, onCreate, onRename, onDelete, onToggleDashboard, showDashboard,
}) {
  const [renaming, setRenaming] = useState(null)
  const [draft, setDraft] = useState('')

  function startRename(id) {
    setRenaming(id)
    setDraft(id)
  }

  async function commitRename(id) {
    const next = draft.trim()
    setRenaming(null)
    if (next && next !== id) await onRename(id, next)
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

      {chats.map((chat) =>
        renaming === chat.id ? (
          <div className="rename-row" key={chat.id}>
            <input
              value={draft}
              autoFocus
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') commitRename(chat.id)
                if (e.key === 'Escape') setRenaming(null)
              }}
            />
            <button className="icon-btn" title="확인" onClick={() => commitRename(chat.id)}>✓</button>
            <button className="icon-btn" title="취소" onClick={() => setRenaming(null)}>✕</button>
          </div>
        ) : (
          <div className="chat-row" key={chat.id}>
            <button
              className={`side-btn${chat.id === currentId && !showDashboard ? ' active' : ''}`}
              onClick={() => onSelect(chat.id)}
              title={chat.id}
            >
              {chat.id === currentId && !showDashboard ? '📍' : '💬'} {chat.id}
            </button>
            <button className="icon-btn" title="이름 수정" onClick={() => startRename(chat.id)}>✏️</button>
            <button className="icon-btn" title="삭제" onClick={() => onDelete(chat.id)}>🗑️</button>
          </div>
        )
      )}

      <div className="spacer" />
      <hr className="divider" />
      <button className={`side-btn${showDashboard ? ' active' : ''}`} onClick={onToggleDashboard}>
        📊 지식 대시보드
      </button>
    </aside>
  )
}
