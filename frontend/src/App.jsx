import { useState, useEffect } from 'react'

const API = 'http://100.121.62.50:8000'

function App() {
  const [prices, setPrices] = useState([])
  const [indicators, setIndicators] = useState([])

  useEffect(() => {
    fetch(`${API}/api/prices`).then(r => r.json()).then(setPrices)
    fetch(`${API}/api/indicators`).then(r => r.json()).then(setIndicators)
  }, [])

  const lastPrice = prices[prices.length - 1]
  const lastCpi = indicators[indicators.length - 1]

  return (
    <div className="wrap">
      <style>{CSS}</style>
      <header>
        <h1>📈 경제 지표 · 주가 대시보드</h1>
        <p>경제 지표·주가 관계 분석 (예측 아님 · 분석·통계용)</p>
      </header>

      <div className="cards">
        <div className="stat">
          <span className="label">최근 종가 (AAPL)</span>
          <span className="value">{lastPrice ? `$${lastPrice.close.toFixed(2)}` : '—'}</span>
          <span className="sub">{lastPrice ? lastPrice.date : ''}</span>
        </div>
        <div className="stat">
          <span className="label">최근 CPI</span>
          <span className="value">{lastCpi ? lastCpi.value : '—'}</span>
          <span className="sub">{lastCpi ? lastCpi.date : ''}</span>
        </div>
      </div>

      <div className="grid">
        <section className="card">
          <h2>주가 (AAPL)</h2>
          <table>
            <thead><tr><th>날짜</th><th className="num">시가</th><th className="num">종가</th></tr></thead>
            <tbody>
              {prices.map(p => (
                <tr key={p.id}>
                  <td>{p.date}</td>
                  <td className="num">{p.open.toFixed(2)}</td>
                  <td className="num">{p.close.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="card">
          <h2>경제지표 (CPI)</h2>
          <table>
            <thead><tr><th>발표일</th><th className="num">값</th></tr></thead>
            <tbody>
              {indicators.map(i => (
                <tr key={i.id}>
                  <td>{i.date}</td>
                  <td className="num">{i.value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>
    </div>
  )
}

const CSS = `
  body { background:#0f1117; color:#e6e8eb; font-family:system-ui,sans-serif; }
  .wrap { max-width:900px; margin:0 auto; padding:32px 20px; }
  header h1 { margin:0 0 4px; font-size:1.6rem; }
  header p { margin:0 0 24px; color:#8b93a1; font-size:.9rem; }
  .cards { display:flex; gap:16px; margin-bottom:24px; flex-wrap:wrap; }
  .stat { flex:1; min-width:180px; background:#1a1e29; border:1px solid #262c3a; border-radius:12px; padding:18px; display:flex; flex-direction:column; gap:4px; }
  .stat .label { color:#8b93a1; font-size:.8rem; }
  .stat .value { font-size:1.8rem; font-weight:700; color:#4ade80; }
  .stat .sub { color:#6b7280; font-size:.75rem; }
  .grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
  @media (max-width:700px){ .grid { grid-template-columns:1fr; } }
  .card { background:#1a1e29; border:1px solid #262c3a; border-radius:12px; padding:18px; }
  .card h2 { margin:0 0 12px; font-size:1rem; color:#cbd5e1; }
  table { width:100%; border-collapse:collapse; font-size:.85rem; }
  th { color:#8b93a1; font-weight:500; padding:6px 8px; border-bottom:1px solid #262c3a; text-align:left; }
  td { padding:6px 8px; border-bottom:1px solid #1f2430; }
  .num { text-align:right; font-variant-numeric:tabular-nums; }
  tr:last-child td { border-bottom:none; }
`

export default App
