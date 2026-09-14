import { useState, useEffect } from 'react'

const API = 'http://100.121.62.50:8000'

function groupBy(arr, key) {
  const m = {}
  for (const item of arr) {
    (m[item[key]] = m[item[key]] || []).push(item)
  }
  return m
}

function App() {
  const [prices, setPrices] = useState([])
  const [indicators, setIndicators] = useState([])

  useEffect(() => {
    fetch(`${API}/api/prices`).then(r => r.json()).then(setPrices)
    fetch(`${API}/api/indicators`).then(r => r.json()).then(setIndicators)
  }, [])

  const byTicker = groupBy(prices, 'ticker')
  const byIndicator = groupBy(indicators, 'name')

  return (
    <div className="wrap">
      <style>{CSS}</style>
      <header>
        <h1>📈 경제 지표 · 주가 대시보드</h1>
        <p>경제 지표·주가 관계 분석 (예측 아님 · 분석·통계용)</p>
      </header>

      <h2 className="section">주가</h2>
      <div className="grid">
        {Object.entries(byTicker).map(([ticker, rows]) => {
          const last = rows[rows.length - 1]
          return (
            <section className="card" key={ticker}>
              <div className="card-head">
                <span className="ticker">{ticker}</span>
                <span className="last">${last?.close.toFixed(2)}</span>
              </div>
              <table>
                <thead><tr><th>날짜</th><th className="num">종가</th></tr></thead>
                <tbody>
                  {rows.map(p => (
                    <tr key={p.id}><td>{p.date}</td><td className="num">{p.close.toFixed(2)}</td></tr>
                  ))}
                </tbody>
              </table>
            </section>
          )
        })}
      </div>

      <h2 className="section">경제지표</h2>
      <div className="grid">
        {Object.entries(byIndicator).map(([name, rows]) => {
          const last = rows[rows.length - 1]
          return (
            <section className="card" key={name}>
              <div className="card-head">
                <span className="ticker">{name}</span>
                <span className="last">{last?.value}</span>
              </div>
              <table>
                <thead><tr><th>발표일</th><th className="num">값</th></tr></thead>
                <tbody>
                  {rows.map(i => (
                    <tr key={i.id}><td>{i.date}</td><td className="num">{i.value}</td></tr>
                  ))}
                </tbody>
              </table>
            </section>
          )
        })}
      </div>
    </div>
  )
}

const CSS = `
  body { background:#0f1117; color:#e6e8eb; font-family:system-ui,sans-serif; }
  .wrap { max-width:1000px; margin:0 auto; padding:32px 20px; }
  header h1 { margin:0 0 4px; font-size:1.6rem; }
  header p { margin:0 0 20px; color:#8b93a1; font-size:.9rem; }
  .section { font-size:1.1rem; color:#cbd5e1; margin:24px 0 12px; border-bottom:1px solid #262c3a; padding-bottom:6px; }
  .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); gap:14px; }
  .card { background:#1a1e29; border:1px solid #262c3a; border-radius:12px; padding:16px; }
  .card-head { display:flex; justify-content:space-between; align-items:baseline; margin-bottom:10px; }
  .ticker { font-weight:700; font-size:1rem; }
  .last { color:#4ade80; font-weight:700; font-size:1.1rem; font-variant-numeric:tabular-nums; }
  table { width:100%; border-collapse:collapse; font-size:.82rem; }
  th { color:#8b93a1; font-weight:500; padding:5px 6px; border-bottom:1px solid #262c3a; text-align:left; }
  td { padding:5px 6px; border-bottom:1px solid #1f2430; }
  .num { text-align:right; font-variant-numeric:tabular-nums; }
  tr:last-child td { border-bottom:none; }
`

export default App
