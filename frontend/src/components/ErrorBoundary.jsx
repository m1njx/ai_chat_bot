import React from 'react'

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, errorInfo) {
    // 프로덕션 에러 로깅 (콘솔 및 선택적 모니터링)
    console.error('[ErrorBoundary caught error]', error, errorInfo)
  }

  handleReload = () => {
    window.location.reload()
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null })
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="login-wrap" role="alert">
          <div className="toss-card login-card" style={{ maxWidth: '440px' }}>
            <div style={{ fontSize: '32px', marginBottom: '12px' }}>⚠️</div>
            <h2 style={{ marginTop: 0, marginBottom: '8px', fontSize: '18px', fontWeight: 600 }}>
              화면을 불러오는 중 오류가 발생했습니다
            </h2>
            <p className="page-sub" style={{ fontSize: '13.5px', margin: '0 0 16px 0', lineHeight: 1.5 }}>
              일시적인 문제가 발생했습니다. 페이지를 새로고침하거나 다시 시도해주세요.
            </p>
            {this.state.error && (
              <div
                className="banner error"
                style={{
                  fontSize: '12px',
                  fontFamily: 'monospace',
                  wordBreak: 'break-all',
                  marginBottom: '16px',
                  textAlign: 'left',
                }}
              >
                {this.state.error.message || String(this.state.error)}
              </div>
            )}
            <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
              <button
                type="button"
                className="side-btn"
                style={{ flex: 1, padding: '10px' }}
                onClick={this.handleReset}
              >
                다시 시도
              </button>
              <button
                type="button"
                className="side-btn primary"
                style={{ flex: 1, padding: '10px' }}
                onClick={this.handleReload}
              >
                페이지 새로고침
              </button>
            </div>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
