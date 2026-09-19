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

const DOW = ['일', '월', '화', '수', '목', '금', '토']

function dowOf(iso) {
  const [y, m, d] = String(iso || '').split('-').map(Number)
  if (!y || !m || !d) return ''
  return DOW[new Date(y, m - 1, d).getDay()]
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

function NewsCard({ row, today, onOpen }) {
  return (
    <button className={`daycard${today ? ' today' : ''}`} onClick={() => onOpen(row, today)}>
      <div className="date-row">
        {today && <span className="badge-today">최신</span>}
        <span>{row.date} ({dowOf(row.date)})</span>
      </div>
      <p className="daytitle">{row.title}</p>
      <div className="daymeta">
        <span className={`sent ${sentClass(row.sentiment)}`}>{row.sentiment}</span>
        <span className="news-tickers">{row.tickers}</span>
        <span className="read">읽기 →</span>
      </div>
    </button>
  )
}

function NewsModal({ item, onClose }) {
  useEffect(() => {
    if (!item) return
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [item, onClose])
  if (!item) return null
  const glossary = item.glossary || []
  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <button className="modal-x" onClick={onClose} aria-label="닫기">×</button>
        <div className="m-date">{item.date} ({dowOf(item.date)}){item.today ? ' · 최신 기사' : ''}</div>
        <h2 className="m-title">{item.title}</h2>
        <div className="m-source">출처 · {item.source}</div>
        <a className="src-btn" href={item.url} target="_blank" rel="noreferrer">🔗 원문 보기</a>

        <div className="m-sec">
          <div className="m-sec-h">💡 오늘 이 기사를 고른 이유</div>
          <div className="reason">{item.pick_reason}</div>
        </div>
        <div className="m-sec">
          <div className="m-sec-h">📄 내용 풀이</div>
          <p className="m-body">{item.summary_easy}</p>
        </div>
        {glossary.length > 0 && (
          <div className="m-sec">
            <div className="m-sec-h">📖 용어 설명</div>
            <ul className="glossary">
              {glossary.map((g, i) => (
                <li key={i}><b>{g.term}</b> {g.desc}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}

function App() {
  const [prices, setPrices] = useState([])
  const [indicators, setIndicators] = useState([])
  const [daily, setDaily] = useState([])
  const [selected, setSelected] = useState(null)

  useEffect(() => {
    fetch(`${API}/api/prices`).then(r => r.json()).then(setPrices)
    fetch(`${API}/api/indicators`).then(r => r.json()).then(setIndicators)
    fetch(`${API}/api/daily`).then(r => r.json()).then(setDaily)
  }, [])

  const byTicker = groupBy(prices, 'ticker')
  const byIndicator = groupBy(indicators, 'name')
  const today = daily[0]
  const past = daily.slice(1)

  const openModal = (row, isToday) => setSelected({ ...row, today: isToday })

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

      <h2 className="section">📰 오늘의 경제 기사</h2>
      <p className="hint">매일 한 건씩, AI가 초보자용으로 풀이·용어 설명을 붙입니다. 카드를 누르면 열립니다.</p>

      {today && (
        <>
          <div className="daylabel">최신 기사</div>
          <NewsCard row={today} today onOpen={openModal} />
        </>
      )}
      {past.length > 0 && (
        <>
          <div className="daylabel">지난 기록</div>
          <div className="daylist">
            {past.map(row => <NewsCard key={row.date} row={row} onOpen={openModal} />)}
          </div>
        </>
      )}
      {daily.length === 0 && <p className="hint">아직 큐레이션된 기사가 없습니다.</p>}

      <NewsModal item={selected} onClose={() => setSelected(null)} />
    </div>
  )
}

const CSS = `
  body { background:#0f1117; color:#e6e8eb; font-family:system-ui,sans-serif; }
  .wrap { max-width:1000px; margin:0 auto; padding:32px 20px; }
  header h1 { margin:0 0 4px; font-size:1.6rem; }
  header p { margin:0 0 20px; color:#8b93a1; font-size:.9rem; }
  .section { font-size:1.1rem; color:#cbd5e1; margin:24px 0 12px; border-bottom:1px solid #262c3a; padding-bottom:6px; }
  .hint { color:#6b7280; font-size:.8rem; margin:-6px 0 14px; }
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

  .daylabel { font-size:.72rem; text-transform:uppercase; letter-spacing:.08em; color:#6b7280; font-weight:700; margin:20px 0 10px; }
  .daylist { display:flex; flex-direction:column; gap:10px; max-height:440px; overflow-y:auto; padding-right:6px; }
  .daylist::-webkit-scrollbar { width:8px; }
  .daylist::-webkit-scrollbar-thumb { background:#2f3646; border-radius:4px; }
  .daylist::-webkit-scrollbar-track { background:transparent; }
  .daycard { display:block; width:100%; text-align:left; font:inherit; color:inherit; cursor:pointer;
             background:#1a1e29; border:1px solid #262c3a; border-radius:14px; padding:18px; }
  .daycard:hover { border-color:#3a4358; }
  .daycard:focus-visible { outline:2px solid #4ade80; outline-offset:2px; }
  .daycard.today { border-color:#1c4a2b; background:linear-gradient(180deg,#16241b 0%,#1a1e29 55%); padding:22px; }
  .daycard.today .date-row { color:#4ade80; }
  .daycard.today .daytitle { font-size:1.15rem; }
  .date-row { display:flex; align-items:center; gap:8px; font-size:.8rem; color:#8b93a1; margin-bottom:10px; font-variant-numeric:tabular-nums; }
  .badge-today { background:#4ade80; color:#06210f; font-weight:800; font-size:.68rem; padding:2px 8px; border-radius:6px; }
  .daytitle { font-size:1rem; font-weight:650; line-height:1.45; margin:0 0 12px; }
  .daymeta { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
  .sent { padding:2px 9px; border-radius:20px; background:#262c3a; color:#9aa4b2; font-size:.7rem; }
  .sent.pos { background:#12351f; color:#4ade80; }
  .sent.neg { background:#3a1518; color:#f87171; }
  .news-tickers { color:#6b7280; font-size:.72rem; }
  .read { margin-left:auto; font-size:.78rem; color:#4ade80; }

  .modal-bg { position:fixed; inset:0; background:rgba(3,5,10,.72); display:flex; align-items:center; justify-content:center; padding:20px; z-index:50; }
  .modal { background:#1a1e29; border:1px solid #2f3646; border-radius:16px; padding:26px; max-width:560px; width:100%; max-height:86vh; overflow-y:auto; position:relative; }
  .modal-x { position:absolute; top:14px; right:16px; background:none; border:none; color:#8b93a1; font-size:1.5rem; cursor:pointer; line-height:1; }
  .modal-x:hover { color:#e6e8eb; }
  .m-date { font-size:.78rem; color:#4ade80; font-variant-numeric:tabular-nums; margin-bottom:8px; }
  .m-title { font-size:1.15rem; font-weight:700; line-height:1.4; margin:0 30px 6px 0; }
  .m-source { font-size:.74rem; color:#6b7280; margin-bottom:16px; }
  .src-btn { display:inline-flex; align-items:center; gap:7px; background:#212734; color:#e6e8eb; text-decoration:none; padding:9px 15px; border-radius:9px; font-size:.82rem; font-weight:600; border:1px solid #262c3a; }
  .src-btn:hover { border-color:#4ade80; color:#4ade80; }
  .m-sec { margin-top:22px; }
  .m-sec-h { font-size:.8rem; font-weight:700; color:#4ade80; margin:0 0 9px; }
  .reason { background:#12351f; border:1px solid #1c4a2b; border-radius:10px; padding:12px 14px; font-size:.86rem; line-height:1.6; color:#d5f0e0; }
  .m-body { font-size:.9rem; line-height:1.75; color:#d3d8e0; margin:0; }
  .glossary { list-style:none; margin:0; padding:0; display:flex; flex-direction:column; gap:10px; }
  .glossary li { background:#212734; border:1px solid #262c3a; border-radius:10px; padding:11px 13px; font-size:.85rem; line-height:1.6; color:#c4cad4; }
  .glossary b { color:#e6e8eb; display:block; margin-bottom:2px; }
`

export default App
