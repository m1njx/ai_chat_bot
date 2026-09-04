import { useEffect, useState } from 'react'
import { api } from '../api'

export default function Dashboard() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function load() {
    try {
      setData(await api.knowledge())
      setError('')
    } catch (err) {
      setError(err.message)
    }
  }

  useEffect(() => { load() }, [])

  async function refresh() {
    setBusy(true)
    setError('')
    try {
      await api.refreshKnowledge()
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="chat-scroll">
      <div className="chat-inner">
        <h1 className="page-title">📁 통합 지식 저장소</h1>
        <p className="page-sub">현재 시스템이 학습하여 보유 중인 지식 통계입니다.</p>

        {error && <div className="banner error">{error}</div>}

        <button className="side-btn primary" style={{ width: 'auto', padding: '10px 18px' }}
                onClick={refresh} disabled={busy}>
          {busy ? '동기화 중…' : '🔄 지식 새로고침'}
        </button>

        <div className="stat-grid" style={{ marginTop: 16 }}>
          {Object.entries(data?.stats ?? {}).map(([name, count]) => (
            <div className="toss-card" key={name}>
              <div className="stat-label">{name}</div>
              <div className="stat-value">{count.toLocaleString()} <span>개</span></div>
            </div>
          ))}
        </div>

        <h3>🔍 최근 수집된 데이터 샘플</h3>
        {/* 수집 문서는 외부 콘텐츠지만 React가 기본으로 이스케이프한다 */}
        {data?.samples?.length
          ? data.samples.map((s, i) => (
              <div className="toss-card sample" key={i}>{s}…</div>
            ))
          : <div className="banner">저장된 지식이 없습니다. 지식 새로고침을 진행해주세요.</div>}
      </div>
    </div>
  )
}
