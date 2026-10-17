import { useState } from 'react'

export default function Sidebar({
  collapsed, chats, currentId, onSelect, onCreate, onRename, onDelete, onToggleDashboard, showDashboard, onClose,
}) {
  const [renaming, setRenaming] = useState(null)
  const [draft, setDraft] = useState('')
  const [confirmDeleteId, setConfirmDeleteId] = useState(null)

  function startRename(chat) {
    setRenaming(chat.id)
    setDraft(chat.title || chat.id || '')
    setConfirmDeleteId(null)
  }

  async function commitRename(chat) {
    const next = draft.trim()
    setRenaming(null)
    const currentTitle = chat.title || chat.id
    if (next && next !== currentTitle) await onRename(chat.id, next)
  }

  function handleDeleteClick(chatId) {
    setConfirmDeleteId(chatId)
  }

  function cancelDelete() {
    setConfirmDeleteId(null)
  }

  async function confirmDelete(chatId) {
    setConfirmDeleteId(null)
    await onDelete(chatId)
  }

  return (
    <aside id="app-sidebar" className={`sidebar${collapsed ? ' collapsed' : ''}`} inert={collapsed} aria-label="대화 탐색 및 관리">
      <div className="sidebar-header">
        <h2>📂 대화 목록</h2>
        <button
          type="button"
          className="icon-btn sidebar-close-btn"
          onClick={onClose}
          title="사이드바 닫기"
          aria-label="사이드바 닫기"
        >
          ✕
        </button>
      </div>
      <button className="side-btn primary" onClick={onCreate}>➕ 새 대화 시작</button>
      <hr className="divider" />

      {chats.length === 0 && (
        <div style={{ color: 'var(--toss-subtext)', fontSize: 14, padding: '4px 12px' }}>
          아직 대화가 없습니다.
        </div>
      )}

      {chats.map((chat) => {
        const displayTitle = chat.title || chat.id
        if (renaming === chat.id) {
          return (
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
          )
        }

        if (confirmDeleteId === chat.id) {
          return (
            <div className="chat-delete-confirm" key={chat.id} role="alert">
              <span>삭제할까요?</span>
              <div className="actions">
                <button
                  type="button"
                  className="text-btn danger"
                  onClick={() => confirmDelete(chat.id)}
                  title="삭제 확인"
                >
                  삭제
                </button>
                <button
                  type="button"
                  className="text-btn"
                  onClick={cancelDelete}
                  title="취소"
                >
                  취소
                </button>
              </div>
            </div>
          )
        }

        return (
          <div className="chat-row" key={chat.id}>
            <button
              className={`side-btn${chat.id === currentId && !showDashboard ? ' active' : ''}`}
              onClick={() => onSelect(chat.id)}
              title={displayTitle}
            >
              {chat.id === currentId && !showDashboard ? '📍' : '💬'} {displayTitle}
            </button>
            <button className="icon-btn" title="이름 수정" onClick={() => startRename(chat)}>✏️</button>
            <button className="icon-btn" title="삭제" onClick={() => handleDeleteClick(chat.id)}>🗑️</button>
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
