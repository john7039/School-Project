import { useState, useEffect } from 'react'

const API = 'http://100.121.62.50:8000'

const TICKER_INFO = {
  AAPL: '애플 · 미국 기술주 (아이폰·맥). 금리에 민감.',
  MSFT: '마이크로소프트 · 미국 기술주 (윈도우·클라우드).',
  GOOGL: '알파벳(구글) · 미국 기술주 (검색·광고).',
  TSLA: '테슬라 · 미국 전기차. 변동성이 큰 성장주.',
}
const INDICATOR_INFO = {
  CPI: '소비자물가지수 · 물가. 높으면 금리 인상 우려 → 주가 부담.',
  금리: '기준금리 · 돈 빌리는 비용. 오르면 주가에 보통 부담.',
  실업률: '일자리 없는 비율. 너무 낮으면 금리 인상 우려.',
}

function groupBy(arr, key) {
  const m = {}
  for (const item of arr) (m[item[key]] = m[item[key]] || []).push(item)
  return m
}

function Info({ text }) {
  const [o, setO] = useState(false)
  useEffect(() => {
    if (!o) return
    const close = () => setO(false)
    window.addEventListener('click', close)
    return () => window.removeEventListener('click', close)
  }, [o])
  return (
    <>
      <button className="info" onClick={(e) => { e.stopPropagation(); setO(!o) }}>ⓘ</button>
      {o && <div className="tip">{text}</div>}
    </>
  )
}

function sentClass(s) {
  if (!s) return ''
  if (s.includes('Bull')) return 'pos'
  if (s.includes('Bear')) return 'neg'
  return ''
}

function App() {
  const [prices, setPrices] = useState([])
  const [indicators, setIndicators] = useState([])
  const [news, setNews] = useState([])

  useEffect(() => {
    fetch(`${API}/api/prices`).then(r => r.json()).then(setPrices)
    fetch(`${API}/api/indicators`).then(r => r.json()).then(setIndicators)
    fetch(`${API}/api/news`).then(r => r.json()).then(setNews)
  }, [])

  const byTicker = groupBy(prices, 'ticker')
  const byIndicator = groupBy(indicators, 'name')

  return (
    <div className="wrap">
      <style>{CSS}</style>
      <header>
        <h1>📈 경제 지표 · 주가 대시보드</h1>
        <p>경제 지표·뉴스·주가 (예측 아님 · 분석·통계용)</p>
      </header>

      <h2 className="section">주가</h2>
      <div className="grid">
        {Object.entries(byTicker).map(([ticker, rows]) => (
          <section className="card" key={ticker}>
            <div className="card-head">
              <span className="ticker">{ticker}<Info text={TICKER_INFO[ticker] || ticker} /></span>
              <span className="last">${rows[0]?.close.toFixed(2)}</span>
            </div>
            <table><tbody>
              {rows.slice(0, 5).map(p => (
                <tr key={p.id}><td>{p.date}</td><td className="num">{p.close.toFixed(2)}</td></tr>
              ))}
            </tbody></table>
          </section>
        ))}
      </div>

      <h2 className="section">경제지표</h2>
      <div className="grid">
        {Object.entries(byIndicator).map(([name, rows]) => (
          <section className="card" key={name}>
            <div className="card-head">
              <span className="ticker">{name}<Info text={INDICATOR_INFO[name] || name} /></span>
              <span className="last">{rows[0]?.value}</span>
            </div>
            <table><tbody>
              {rows.slice(0, 5).map(i => (
                <tr key={i.id}><td>{i.date}</td><td className="num">{i.value}</td></tr>
              ))}
            </tbody></table>
          </section>
        ))}
      </div>

      <h2 className="section">경제 뉴스</h2>
      <div className="news-list">
        {news.map((n, idx) => (
          <a className="news" href={n.url} target="_blank" rel="noreferrer" key={idx}>
            <div className="news-top">
              <span className={`sent ${sentClass(n.sentiment)}`}>{n.sentiment}</span>
              <span className="news-tickers">{n.tickers}</span>
            </div>
            <div className="news-title">{n.title}</div>
          </a>
        ))}
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
  .ticker { font-weight:700; font-size:1rem; display:flex; align-items:center; }
  .info { margin-left:6px; background:none; color:#6b7280; font-size:.8rem; cursor:pointer; border:1px solid #3a4152; border-radius:50%; width:18px; height:18px; padding:0; line-height:1; }
  .info:hover { color:#4ade80; border-color:#4ade80; }
  .tip { position:absolute; background:#0f1117; border:1px solid #4ade80; border-radius:8px; padding:8px 10px; font-size:.75rem; color:#cbd5e1; max-width:220px; margin-top:4px; z-index:5; }
  .last { color:#4ade80; font-weight:700; font-size:1.1rem; font-variant-numeric:tabular-nums; }
  table { width:100%; border-collapse:collapse; font-size:.82rem; }
  td { padding:5px 6px; border-bottom:1px solid #1f2430; }
  .num { text-align:right; font-variant-numeric:tabular-nums; }
  tr:last-child td { border-bottom:none; }
  .news-list { display:flex; flex-direction:column; gap:8px; }
  .news { background:#1a1e29; border:1px solid #262c3a; border-radius:10px; padding:12px 14px; text-decoration:none; color:inherit; }
  .news:hover { border-color:#4ade80; }
  .news-top { display:flex; gap:10px; margin-bottom:5px; font-size:.72rem; }
  .sent { padding:1px 7px; border-radius:20px; background:#262c3a; color:#8b93a1; }
  .sent.pos { background:#12351f; color:#4ade80; }
  .sent.neg { background:#3a1518; color:#f87171; }
  .news-tickers { color:#6b7280; }
  .news-title { font-size:.9rem; line-height:1.4; }
`

export default App
