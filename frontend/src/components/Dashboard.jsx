import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'

function formatBytes(bytes) {
  if (!bytes || bytes <= 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`
}

function formatDate(dateStr) {
  if (!dateStr) return '-'
  try {
    const normalized = String(dateStr).trim().replace(' ', 'T')
    const d = new Date(normalized)
    if (isNaN(d.getTime())) return dateStr
    return d.toLocaleString('ko-KR', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return dateStr
  }
}

export default function Dashboard() {
  const [data, setData] = useState(null)
  const [files, setFiles] = useState([])
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [busy, setBusy] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [deletingId, setDeletingId] = useState(null)
  const [dragActive, setDragActive] = useState(false)
  const fileInputRef = useRef(null)

  const load = useCallback(async () => {
    try {
      const [kData, fData] = await Promise.all([
        api.knowledge(),
        api.listKnowledgeFiles(),
      ])
      setData(kData)
      setFiles(fData?.files ?? [])
    } catch (err) {
      setError(err.message)
    }
  }, [])

  useEffect(() => {
    let ignore = false
    async function init() {
      try {
        const [kData, fData] = await Promise.all([
          api.knowledge(),
          api.listKnowledgeFiles(),
        ])
        if (!ignore) {
          setData(kData)
          setFiles(fData?.files ?? [])
        }
      } catch (err) {
        if (!ignore) setError(err.message)
      }
    }
    init()
    return () => { ignore = true }
  }, [])

  async function refresh() {
    setBusy(true)
    setError('')
    setSuccess('')
    try {
      await api.refreshKnowledge()
      await load()
      setSuccess('지식 인덱스를 성공적으로 새로고침했습니다.')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function handleUpload(file) {
    if (!file) return
    const name = file.name.toLowerCase()
    if (!name.endsWith('.pdf') && !name.endsWith('.txt')) {
      setError('지원하지 않는 파일 형식입니다. .pdf 및 .txt 파일만 업로드할 수 있습니다.')
      return
    }
    if (file.size > 20 * 1024 * 1024) {
      setError('파일 크기가 최대 제한(20MB)을 초과했습니다.')
      return
    }

    setUploading(true)
    setError('')
    setSuccess('')
    try {
      const res = await api.uploadKnowledgeFile(file)
      setSuccess(`"${res.original_name}" 문서가 성공적으로 업로드 및 색인되었습니다. (${res.num_chunks}개 청크)`)
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  function handleFileSelect(e) {
    if (e.target.files && e.target.files[0]) {
      handleUpload(e.target.files[0])
    }
  }

  function handleDrag(e) {
    e.preventDefault()
    e.stopPropagation()
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true)
    } else if (e.type === 'dragleave') {
      setDragActive(false)
    }
  }

  function handleDrop(e) {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)
    if (e.dataTransfer?.files && e.dataTransfer.files[0]) {
      handleUpload(e.dataTransfer.files[0])
    }
  }

  async function handleDelete(file) {
    const ok = window.confirm(`"${file.original_name}" 문서를 지식 저장소에서 삭제하시겠습니까?\n색인 인덱스가 자동으로 재구축됩니다.`)
    if (!ok) return

    setDeletingId(file.id)
    setError('')
    setSuccess('')
    try {
      await api.deleteKnowledgeFile(file.id)
      setSuccess(`"${file.original_name}" 문서가 삭제되었습니다.`)
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <div className="chat-scroll">
      <div className="chat-inner">
        <h1 className="page-title">📁 통합 지식 저장소</h1>
        <p className="page-sub">시스템 기본 지식 및 사용자가 업로드한 문서 기반 지식 관리 페이지입니다.</p>

        {error && <div className="banner error" role="alert">{error}</div>}
        {success && <div className="banner success" role="status">{success}</div>}

        {/* ── 문서 업로드 & 관리 카드 ── */}
        <div className="toss-card" style={{ marginBottom: 20 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>📄 내 문서 업로드</h2>
            <span style={{ fontSize: 13, color: 'var(--toss-subtext)' }}>최대 20MB · PDF, TXT</span>
          </div>

          <div
            className={`upload-zone ${dragActive ? 'dragging' : ''}`}
            onDragEnter={handleDrag}
            onDragOver={handleDrag}
            onDragLeave={handleDrag}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') fileInputRef.current?.click() }}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.txt"
              style={{ display: 'none' }}
              onChange={handleFileSelect}
              disabled={uploading}
            />
            <div className="upload-icon">📤</div>
            <div className="upload-title">
              {uploading ? '파일 업로드 및 색인 중…' : '문서 파일을 끌어다 놓거나 클릭하여 선택하세요'}
            </div>
            <div className="upload-sub">
              {uploading
                ? '텍스트를 추출하고 FAISS 벡터 색인을 재구축하고 있습니다.'
                : 'PDF 또는 TXT 파일을 업로드하면 챗봇이 해당 내용을 참고하여 답변합니다.'}
            </div>
          </div>

          {/* 업로드된 파일 목록 */}
          <h3 style={{ fontSize: 15, fontWeight: 600, marginTop: 24, marginBottom: 10 }}>
            📚 업로드된 문서 목록 ({files.length}개)
          </h3>

          {files.length === 0 ? (
            <div className="banner" style={{ background: 'var(--toss-bg)', color: 'var(--toss-subtext)' }}>
              아직 업로드된 개인 문서가 없습니다. 위 영역에 PDF나 TXT 문서를 추가해보세요.
            </div>
          ) : (
            <div className="table-wrap" style={{ margin: 0 }}>
              <table className="file-table">
                <thead>
                  <tr>
                    <th>파일명</th>
                    <th style={{ width: 80, textAlign: 'center' }}>형식</th>
                    <th style={{ width: 90, textAlign: 'right' }}>크기</th>
                    <th style={{ width: 120, textAlign: 'center' }}>청크/페이지</th>
                    <th style={{ width: 140 }}>업로드 일시</th>
                    <th style={{ width: 80, textAlign: 'center' }}>관리</th>
                  </tr>
                </thead>
                <tbody>
                  {files.map((file) => {
                    const isDeleting = deletingId === file.id
                    const ext = (file.original_name.split('.').pop() || '').toLowerCase()
                    return (
                      <tr key={file.id}>
                        <td>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8, wordBreak: 'break-all' }}>
                            <span>{ext === 'pdf' ? '📕' : '📄'}</span>
                            <span style={{ fontWeight: 500 }}>{file.original_name}</span>
                          </div>
                        </td>
                        <td style={{ textAlign: 'center' }}>
                          <span className={`type-badge ${ext}`}>{ext}</span>
                        </td>
                        <td style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
                          {formatBytes(file.file_size)}
                        </td>
                        <td style={{ textAlign: 'center', color: 'var(--toss-subtext)', fontSize: 13 }}>
                          {file.num_chunks}개 청크
                          {file.num_pages > 1 ? ` (${file.num_pages}p)` : ''}
                        </td>
                        <td style={{ color: 'var(--toss-subtext)', fontSize: 13 }}>
                          {formatDate(file.uploaded_at)}
                        </td>
                        <td style={{ textAlign: 'center' }}>
                          <button
                            className="del-btn"
                            onClick={() => handleDelete(file)}
                            disabled={isDeleting || uploading}
                            title="문서 삭제 및 인덱스 갱신"
                          >
                            {isDeleting ? '삭제 중…' : '삭제'}
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* ── 지식 소스 신선도 및 수집 현황 ── */}
        <div style={{ marginTop: 28, marginBottom: 12 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h2 style={{ fontSize: 18, fontWeight: 700, margin: 0 }}>⏱️ 지식 소스 신선도 및 수집 현황</h2>
            <span style={{ fontSize: 13, color: 'var(--toss-subtext)' }}>
              실시간 질의 시 오래된 데이터는 자동 배제됩니다
            </span>
          </div>
          <div className="freshness-grid" style={{ marginTop: 12 }}>
            {(data?.sources_status || []).map((src) => {
              const iconMap = {
                weather: '🌤️',
                news: '📰',
                stock: '📈',
                upload: '📁',
                web: '🌐',
              }
              const icon = iconMap[src.type] || '📌'
              return (
                <div className="freshness-card" key={src.source_key}>
                  <div className="freshness-card-header">
                    <span className="freshness-card-title">
                      <span style={{ marginRight: 6 }}>{icon}</span>
                      {src.name}
                    </span>
                    <span className={`freshness-badge ${src.freshness}`}>
                      {src.freshness_label}
                    </span>
                  </div>
                  <div className="freshness-card-body">
                    <div className="freshness-stat-row">
                      <span className="freshness-stat-label">보유 데이터</span>
                      <span className="freshness-stat-val">{src.count.toLocaleString()}건</span>
                    </div>
                    <div className="freshness-stat-row">
                      <span className="freshness-stat-label">최신 시점</span>
                      <span className="freshness-stat-val" title={src.latest_at || '확인 불가'}>
                        {src.latest_at ? formatDate(src.latest_at) : '수집 일시 미제공'}
                      </span>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* ── 전체 지식 통계 ── */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 28 }}>
          <h2 style={{ fontSize: 18, fontWeight: 700, margin: 0 }}>📊 통합 지식 통계</h2>
          <button className="side-btn primary" style={{ width: 'auto', padding: '9px 16px', fontSize: 13 }}
                  onClick={refresh} disabled={busy || uploading}>
            {busy ? '동기화 중…' : '🔄 지식 전체 새로고침'}
          </button>
        </div>

        <div className="stat-grid" style={{ marginTop: 12 }}>
          {Object.entries(data?.stats ?? {}).map(([name, count]) => (
            <div className="toss-card" key={name} style={{ marginBottom: 0 }}>
              <div className="stat-label">{name}</div>
              <div className="stat-value">{count.toLocaleString()} <span>개</span></div>
            </div>
          ))}
        </div>

        <h3 style={{ marginTop: 28, marginBottom: 12 }}>🔍 최근 수집된 데이터 샘플</h3>
        {data?.samples?.length
          ? data.samples.map((s, i) => (
              <div className="toss-card sample" key={i}>{s}…</div>
            ))
          : <div className="banner">저장된 지식이 없습니다. 지식 새로고침을 진행해주세요.</div>}
      </div>
    </div>
  )
}
