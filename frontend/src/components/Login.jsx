import { useState } from 'react'
import { api, setToken } from '../api'

export default function Login({ onSuccess }) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const { token } = await api.login(password)
      setToken(token)
      onSuccess()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-wrap">
      <form className="toss-card login-card" onSubmit={submit}>
        <h2 style={{ margin: 0 }}>🔒 접근 인증</h2>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="비밀번호"
          autoFocus
        />
        {error && <div className="banner error">{error}</div>}
        <button className="side-btn primary" type="submit" disabled={busy}>
          {busy ? '확인 중…' : '입장'}
        </button>
      </form>
    </div>
  )
}
