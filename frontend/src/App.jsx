import { useState, useEffect } from 'react'

const API = ''  // 같은 출처 (nginx 가 /api 프록시)

const COMPANIES = [
  { t: 'AAPL', n: '애플' }, { t: 'MSFT', n: '마이크로소프트' }, { t: 'NVDA', n: '엔비디아' },
  { t: 'AMZN', n: '아마존' }, { t: 'GOOGL', n: '알파벳' }, { t: 'TSLA', n: '테슬라' }, { t: 'META', n: '메타' },
]
const CO_NAME = Object.fromEntries(COMPANIES.map(c => [c.t, c.n]))

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
function fmtVol(v) {
  if (v == null) return '-'
  if (v >= 1e8) return (v / 1e8).toFixed(1) + '억주'
  if (v >= 1e4) return Math.round(v / 1e4).toLocaleString() + '만주'
  return v.toLocaleString()
}
function chgHtml(n) {
  if (n == null) return ''
  const cls = n > 0 ? 'up' : n < 0 ? 'down' : ''
  return <span className={cls}>{(n > 0 ? '+' : '') + n}%</span>
}
function flowClass(c) { return c > 0.5 ? 'buy' : c < -0.5 ? 'sell' : '' }
function flowLabel(c) { return c > 0.5 ? '매수세 강함 ↑' : c < -0.5 ? '매도세 ↓' : '보합' }
function sentClass(s) {
  if (!s) return ''
  if (s.includes('Bull') || s === '긍정') return 'pos'
  if (s.includes('Bear') || s === '부정') return 'neg'
  return ''
}
function sentText(s) {
  if (!s) return ''
  if (s.includes('Bull') || s === '긍정') return '긍정'
  if (s.includes('Bear') || s === '부정') return '부정'
  return '중립'
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

function Modal({ children, onClose }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <button className="mx" onClick={onClose} aria-label="닫기">×</button>
        {children}
      </div>
    </div>
  )
}

// 무의존 SVG 라인차트 (숫자 + 그래프). data: 숫자 배열(과거→최신)
function Chart({ data, dates, color = '#4ade80', mini = false, fmt = (v) => v, onPoint }) {
  if (!data || data.length < 2) return mini ? null : <div className="chart-empty">그래프를 그릴 데이터가 부족합니다</div>
  const W = mini ? 200 : 600
  const H = mini ? 46 : 150
  const pad = mini ? { x: 3, t: 5, b: 5 } : { x: 10, t: 16, b: 24 }
  const min = Math.min(...data), max = Math.max(...data), span = (max - min) || 1
  const n = data.length
  const px = (i) => pad.x + (i / (n - 1)) * (W - pad.x * 2)
  const py = (v) => pad.t + (1 - (v - min) / span) * (H - pad.t - pad.b)
  const line = data.map((v, i) => `${px(i).toFixed(1)},${py(v).toFixed(1)}`).join(' ')
  const area = `${px(0).toFixed(1)},${(H - pad.b).toFixed(1)} ${line} ${px(n - 1).toFixed(1)},${(H - pad.b).toFixed(1)}`
  const last = data[n - 1]
  return (
    <svg className={`chart${mini ? ' mini' : ''}`} viewBox={`0 0 ${W} ${H}`} role="img" aria-label="추이 그래프">
      <polygon points={area} fill={color} opacity="0.1" />
      <polyline points={line} fill="none" stroke={color} strokeWidth="2" vectorEffect="non-scaling-stroke" strokeLinejoin="round" strokeLinecap="round" />
      {mini
        ? <circle cx={px(n - 1)} cy={py(last)} r={3} fill={color} />
        : data.map((v, i) => (
          <g key={i} className={onPoint ? 'cpt' : undefined} onClick={onPoint ? () => onPoint(i) : undefined}>
            {onPoint && <circle cx={px(i)} cy={py(v)} r={13} fill="transparent" />}
            <circle cx={px(i)} cy={py(v)} r={i === n - 1 ? 5 : 3.5} fill={color} stroke="#161a24" strokeWidth="1.5">
              {dates && dates.length === n && <title>{dates[i]} · {fmt(v)}{onPoint ? ' (클릭하면 상세)' : ''}</title>}
            </circle>
          </g>
        ))
      }
      {!mini && <>
        <text x={pad.x} y={15} className="clbl" fill={color}>▲ {fmt(max)}</text>
        <text x={pad.x} y={31} className="clbl cmin">▼ {fmt(min)}</text>
        {dates && dates.length === n && <>
          <text x={pad.x} y={H - 7} className="clbl cmin">{(dates[0] || '').slice(5)}</text>
          <text x={W - pad.x} y={H - 7} className="clbl cmin" textAnchor="end">{(dates[n - 1] || '').slice(5)}</text>
        </>}
      </>}
    </svg>
  )
}

// ===== 탭 1: AI 추천 기사 =====
function ArticlesTab() {
  const [daily, setDaily] = useState([])
  const [sel, setSel] = useState(null)
  useEffect(() => { fetch(`${API}/api/daily`).then(r => r.json()).then(setDaily).catch(() => {}) }, [])
  const today = daily[0]
  const past = daily.slice(1)
  const Card = (a, isToday) => (
    <button className={`art${isToday ? ' today' : ''}`} key={a.date} onClick={() => setSel(a)}>
      <div className="atop">{isToday && <span className="badge">오늘</span>}<span>{a.date} ({dowOf(a.date)})</span>
        <span className={`sent ${sentClass(a.sentiment)}`}>{sentText(a.sentiment)}</span></div>
      <div className="atitle">{a.title}</div>
    </button>
  )
  return (
    <div className="panel">
      <p className="lead">📰 <b>LLM이 고른, 경제 초보가 읽기 좋은 오늘의 기사.</b> 하루 한 건씩 쌓여 지난 날짜도 다시 볼 수 있어요.</p>
      {today && <><div className="label">최신 기사</div>{Card(today, true)}</>}
      {past.length > 0 && <><div className="label">지난 기록 · {past.length}건</div>
        <div className="scroll">{past.map(a => Card(a, false))}</div></>}
      {daily.length === 0 && <p className="lead">아직 큐레이션된 기사가 없습니다.</p>}
      {sel && <Modal onClose={() => setSel(null)}>
        <div className="m-date">{sel.date} ({dowOf(sel.date)})</div>
        <h2 className="m-title">{sel.title}</h2>
        <div className="m-sub">출처 · {sel.source}</div>
        <a className="src-btn" href={sel.url} target="_blank" rel="noreferrer">🔗 원문 보기</a>
        <div className="sec-h">💡 이 기사를 고른 이유</div>
        <div className="ai">{sel.pick_reason}</div>
        {sel.brief && <><div className="sec-h">📄 요약</div>
        <p className="m-body">{sel.brief}</p></>}
        <div className="sec-h">💡 쉬운 설명</div>
        <p className="m-body">{sel.summary_easy}</p>
        {(sel.glossary || []).length > 0 && <><div className="sec-h">📖 용어 설명</div>
          <ul className="glossary">{sel.glossary.map((g, i) => <li key={i}><b>{g.term}</b>{g.desc}</li>)}</ul></>}
      </Modal>}
    </div>
  )
}

// ===== 탭 2: 종목별 =====
function StocksTab() {
  const [cur, setCur] = useState('AAPL')
  const [days, setDays] = useState([])
  const [sel, setSel] = useState(null)
  useEffect(() => {
    setDays([])
    fetch(`${API}/api/company/${cur}`).then(r => r.json()).then(setDays).catch(() => {})
  }, [cur])
  const co = CO_NAME[cur]
  const first = days[0]
  return (
    <div className="panel">
      <p className="lead">유명 회사 7곳의 <b>하루 상황</b>을 매일 기록. 회사를 고르면 날짜별로 주가·거래량·뉴스와 AI 종합을 볼 수 있어요.</p>
      <div className="chips">
        {COMPANIES.map(c => (
          <button className={`chip${c.t === cur ? ' on' : ''}`} key={c.t} onClick={() => setCur(c.t)}>
            <div className="ct">{c.t}</div><div className="cn">{c.n}</div>
          </button>
        ))}
      </div>
      <div className="cohead">
        <span className="coname">{cur} · {co}</span>
        {first && <span className="coprice">${first.close?.toFixed(2)} {chgHtml(first.change_pct)}</span>}
      </div>
      {days.length >= 2 && (() => {
        const s = [...days].reverse()
        const closes = s.map(d => d.close)
        const rising = closes[closes.length - 1] >= closes[0]
        return (
          <div className="chartbox">
            <p className="chartcap">최근 {s.length}일 종가 추이 · 점을 누르면 그날 상세</p>
            <Chart data={closes} dates={s.map(d => d.date)} color={rising ? '#4ade80' : '#f87171'} fmt={v => '$' + v.toFixed(0)} onPoint={(i) => setSel(s[i])} />
          </div>
        )
      })()}
      <div className="label">일자별 기록 (장 마감 후 종합)</div>
      <div className="scroll">
        {days.map((x, i) => (
          <button className={`day${i === 0 ? ' today' : ''}`} key={x.date} onClick={() => setSel(x)}>
            <div className="day-top">{i === 0 && <span className="badge">최신</span>}<span>{x.date} ({dowOf(x.date)})</span></div>
            <div className="day-metrics">
              <div className="metric"><span className="k">종가</span><span className="v">${x.close?.toFixed(2)} {chgHtml(x.change_pct)}</span></div>
              <div className="metric"><span className="k">거래량</span><span className="v">{fmtVol(x.volume)}</span></div>
              <span className={`flow ${flowClass(x.change_pct)}`}>{flowLabel(x.change_pct)}</span>
            </div>
            <div className="day-sum">{(x.ai_summary || '').slice(0, 52)}…</div>
            <div className="day-foot"><span>관련 뉴스 {(x.news || []).length}건</span><span className="arrow">그날 정보 보기 →</span></div>
          </button>
        ))}
        {days.length === 0 && <p className="lead">이 종목의 브리핑이 아직 없습니다.</p>}
      </div>
      {sel && <Modal onClose={() => setSel(null)}>
        <div className="m-date">{sel.date} ({dowOf(sel.date)})</div>
        <h2 className="m-title">{cur} · {co}</h2>
        <div className="m-row">
          <div className="metric"><span className="k">종가</span><span className="v big">${sel.close?.toFixed(2)} {chgHtml(sel.change_pct)}</span></div>
          <div className="metric"><span className="k">거래량</span><span className="v big">{fmtVol(sel.volume)}</span></div>
          <div className="metric"><span className="k">흐름</span><span className={`flow ${flowClass(sel.change_pct)}`}>{flowLabel(sel.change_pct)}</span></div>
        </div>
        <div className="sec-h">💬 AI 종합 (초보자용)</div>
        <div className="ai">{sel.ai_summary}</div>
        {(sel.news || []).length > 0 && <><div className="sec-h">📰 관련 뉴스</div>
          {sel.news.map((n, i) => <div className="newsline" key={i}><span className={`sent ${sentClass(n.sentiment)}`}>{sentText(n.sentiment)}</span><span>{n.title}</span></div>)}</>}
      </Modal>}
    </div>
  )
}

// 지표 날짜 라벨. FRED 의 date 는 '발표일'이 아니라 '기준월'이다.
// (9월분 물가는 10/14 에 발표) 그냥 date 만 찍으면 "9월에서 멈췄다"로 오해하게 돼서
// 기준월과 실제 발표일을 함께 보여준다.
function indLabel(r) {
  if (!r) return ''
  const m = `${r.date?.slice(0, 7).replace('-', '년 ')}월분`
  if (!r.release_date) return m
  const [, mm, dd] = r.release_date.split('-')
  return `${m} · ${Number(mm)}/${Number(dd)} 발표`
}

// ===== 탭 3: 시장·지표 =====
function MarketTab() {
  const [prices, setPrices] = useState([])
  const [indicators, setIndicators] = useState([])
  useEffect(() => {
    fetch(`${API}/api/prices`).then(r => r.json()).then(setPrices).catch(() => {})
    fetch(`${API}/api/indicators`).then(r => r.json()).then(setIndicators).catch(() => {})
  }, [])
  const byInd = groupBy(indicators, 'name')
  const byTicker = groupBy(prices, 'ticker')
  return (
    <div className="panel">
      <p className="lead">경제지표와 종목 시세 개요.</p>
      <div className="label">경제지표</div>
      <div className="grid">
        {Object.entries(byInd).map(([name, rows]) => (
          <div className="mcard" key={name}>
            <div className="k">{name}<Info text={INDICATOR_INFO[name] || name} /></div>
            <div className="v">{rows[0]?.value}</div>
            <div className="d">{indLabel(rows[0])}</div>
            <Chart data={[...rows].reverse().map(r => r.value)} mini color="#60a5fa" />
          </div>
        ))}
      </div>
      <div className="label">주가 (종가)</div>
      <div className="grid">
        {COMPANIES.map(c => {
          // close 가 비어 있는 행(yfinance 미완성 봉)은 버린다 — 하나라도 섞이면
          // toFixed 에서 터져 탭 전체가 흰 화면이 됐었다.
          const rows = (byTicker[c.t] || []).filter(r => r.close != null)
          if (!rows.length) return null
          const asc = [...rows].reverse().map(r => r.close)
          const rising = asc[asc.length - 1] >= asc[0]
          return (
            <div className="mcard" key={c.t}>
              <div className="k">{c.t} · {c.n}</div>
              <div className="v">${rows[0]?.close?.toFixed(2)}</div>
              <div className="d">{rows[0]?.date}</div>
              <Chart data={asc} mini color={rising ? '#4ade80' : '#f87171'} />
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ===== 탭 4: 환율 =====
// 환율은 '좋다/나쁘다'가 아니라 양면적이라, 감정(초록/빨강) 대신 방향(약세/강세) 색을 쓴다.
function fxDir(chg) {
  if (chg == null) return { label: '-', cls: '' }
  if (chg > 0.5) return { label: '원화 약세 ↑', cls: 'weak' }
  if (chg < -0.5) return { label: '원화 강세 ↓', cls: 'strong' }
  return { label: '보합', cls: '' }
}

function FxPair({ title, sub, rate, chg, series, color, main }) {
  const d = fxDir(chg)
  const asc = [...(series || [])].reverse()
  const pct = rate != null && chg != null && rate - chg ? (chg / (rate - chg)) * 100 : null
  return (
    <div className={`fxcard${main ? ' main' : ''}`}>
      <div className="fxhead">
        <div><span className="fxname">{title}</span> <span className="fxsub">{sub}</span></div>
        <span className={`fxdir ${d.cls}`}>{d.label}</span>
      </div>
      <div className="fxrate">
        {rate != null ? rate.toFixed(2) : '-'}<span className="won">원</span>
        {chg != null && <span className={`fxchg ${chg > 0 ? 'up' : chg < 0 ? 'down' : ''}`}>
          {chg > 0 ? '+' : ''}{chg.toFixed(2)}원{pct != null && ` (${pct > 0 ? '+' : ''}${pct.toFixed(2)}%)`}
        </span>}
      </div>
      {asc.length >= 2 && <Chart data={asc.map(x => x.rate)} dates={asc.map(x => x.date)}
        color={color} fmt={v => Math.round(v).toLocaleString()} />}
    </div>
  )
}

function fxLine(rate, chg) {
  if (rate == null) return '-'
  const sign = chg > 0 ? '+' : ''
  return `${rate.toFixed(2)}원 ${chg != null ? `(${sign}${chg.toFixed(2)})` : ''}`
}

function FxTab() {
  const [fx, setFx] = useState(null)
  const [sel, setSel] = useState(null)
  useEffect(() => { fetch(`${API}/api/fx`).then(r => r.json()).then(setFx).catch(() => setFx({ days: [], series: {} })) }, [])
  if (!fx) return <div className="panel"><p className="lead">불러오는 중…</p></div>
  const days = fx.days || []
  const s = fx.series || {}
  const t = days[0]
  const past = days.slice(1)
  return (
    <div className="panel">
      <p className="lead">💱 <b>원/달러·원/유로 환율과 그 의미.</b> 환율은 한쪽만 좋은 게 아니라 <b>양면적</b>이에요 — 누구에게 유리하고 누구에게 불리한지 함께 봅니다.</p>
      {!t && <p className="lead">아직 환율 분석이 없습니다.</p>}
      {t && <>
        <div className="label">최신 환율 · {t.date}</div>
        <FxPair title="원/달러" sub="USD · 한국 경제에 가장 큰 영향" rate={t.usdkrw} chg={t.usdkrw_chg}
          series={s.USDKRW} color="#60a5fa" main />
        <FxPair title="원/유로" sub="EUR · 보조 지표" rate={t.eurkrw} chg={t.eurkrw_chg}
          series={s.EURKRW} color="#a78bfa" />
        <div className="sec-h">💬 이날 환율이 우리 경제에 주는 영향 (AI)</div>
        <div className="ai">{t.ai_summary}</div>
      </>}
      {past.length > 0 && <>
        <div className="label">일자별 기록 · {past.length}건</div>
        <div className="scroll">
          {past.map(d => {
            const dir = fxDir(d.usdkrw_chg)
            return (
              <button className="day" key={d.date} onClick={() => setSel(d)}>
                <div className="day-top"><span>{d.date} ({dowOf(d.date)})</span>
                  <span className={`fxdir ${dir.cls}`}>{dir.label}</span></div>
                <div className="day-metrics">
                  <div className="metric"><span className="k">원/달러</span><span className="v">{fxLine(d.usdkrw, d.usdkrw_chg)}</span></div>
                  <div className="metric"><span className="k">원/유로</span><span className="v">{fxLine(d.eurkrw, d.eurkrw_chg)}</span></div>
                </div>
                <div className="day-sum">{(d.ai_summary || '').slice(0, 52)}…</div>
                <div className="day-foot"><span>환율 영향 분석</span><span className="arrow">그날 정보 보기 →</span></div>
              </button>
            )
          })}
        </div>
      </>}
      {sel && <Modal onClose={() => setSel(null)}>
        <div className="m-date">{sel.date} ({dowOf(sel.date)})</div>
        <h2 className="m-title">💱 환율</h2>
        <div className="m-row">
          <div className="metric"><span className="k">원/달러</span><span className="v big">{fxLine(sel.usdkrw, sel.usdkrw_chg)}</span></div>
          <div className="metric"><span className="k">원/유로</span><span className="v big">{fxLine(sel.eurkrw, sel.eurkrw_chg)}</span></div>
          <div className="metric"><span className="k">방향</span><span className={`fxdir ${fxDir(sel.usdkrw_chg).cls}`}>{fxDir(sel.usdkrw_chg).label}</span></div>
        </div>
        <div className="sec-h">💬 이날 환율이 우리 경제에 주는 영향 (AI)</div>
        <div className="ai">{sel.ai_summary}</div>
      </Modal>}
      <div className="sec-h">📖 환율이 왜 중요한가</div>
      <div className="fxedu">
        <p><b>환율이 오른다 = 원화 가치가 떨어진다(원화 약세).</b> 1달러를 사는 데 원화가 더 많이 든다는 뜻이에요.</p>
        <ul>
          <li><b>수출·수입</b> — 원화가 약해지면 우리 물건이 외국에서 싸져 <b>수출기업에 유리</b>하지만, 사 오는 물건값은 <b>비싸집니다</b>.</li>
          <li><b>물가</b> — 원유·원자재를 달러로 사 오기 때문에 환율이 오르면 <b>수입물가 → 생활물가</b>가 따라 오릅니다. (기름값·식료품)</li>
          <li><b>외국인 투자</b> — 원화 약세가 이어지면 외국인은 환차손을 걱정해 <b>자금을 빼기</b> 쉬워지고, 주식시장이 흔들릴 수 있습니다.</li>
          <li><b>금리</b> — 한국과 미국의 <b>금리 차</b>가 벌어지면 돈이 이자 높은 쪽(달러)으로 움직여 환율에 영향을 줍니다.</li>
        </ul>
        <p className="fxnote"><b>왜 오르내리나</b> — 한·미 금리차, 달러 강세, 무역수지(수출이 잘 되는지), 외국인 자금 흐름, 시장 심리.</p>
        <p className="fxnote"><b>왜 달러가 더 중요한가</b> — 무역 대금과 원유·원자재 결제가 대부분 달러로 이뤄져, 유로보다 우리 경제에 미치는 영향이 큽니다.</p>
      </div>
    </div>
  )
}

function App() {
  const [tab, setTab] = useState('articles')
  return (
    <div className="wrap">
      <style>{CSS}</style>
      <header>
        <h1>📈 경제 한 조각</h1>
        <p>경제 초보를 위한 자동 수집·AI 분석 (예측 아님 · 학습·참고용)</p>
      </header>
      <div className="tabs">
        <button className={`tab${tab === 'articles' ? ' active' : ''}`} onClick={() => setTab('articles')}>📰 AI 추천 기사</button>
        <button className={`tab${tab === 'stocks' ? ' active' : ''}`} onClick={() => setTab('stocks')}>📊 종목별</button>
        <button className={`tab${tab === 'market' ? ' active' : ''}`} onClick={() => setTab('market')}>📈 시장·지표</button>
        <button className={`tab${tab === 'fx' ? ' active' : ''}`} onClick={() => setTab('fx')}>💱 환율</button>
      </div>
      {tab === 'articles' && <ArticlesTab />}
      {tab === 'stocks' && <StocksTab />}
      {tab === 'market' && <MarketTab />}
      {tab === 'fx' && <FxTab />}
    </div>
  )
}

const CSS = `
  body { background:#0f1117; color:#e6e8eb; font-family:system-ui,"Apple SD Gothic Neo",sans-serif; margin:0; }
  .wrap { max-width:840px; margin:0 auto; padding:0 18px 60px; }
  header { padding:24px 0 10px; }
  header h1 { margin:0; font-size:1.4rem; }
  header p { margin:5px 0 0; color:#8b93a1; font-size:.85rem; }
  .tabs { position:sticky; top:0; background:#0f1117; display:flex; gap:4px; border-bottom:1px solid #262c3a; z-index:10; padding-top:4px; }
  .tab { flex:1; background:none; border:none; color:#8b93a1; font:inherit; font-size:.82rem; font-weight:600; padding:12px 4px; cursor:pointer; border-bottom:2px solid transparent; margin-bottom:-1px; white-space:nowrap; }
  @media (max-width:520px) { .tab { font-size:.7rem; padding:11px 2px; } }
  .tab:hover { color:#e6e8eb; }
  .tab.active { color:#4ade80; border-bottom-color:#4ade80; }
  .panel { padding-top:16px; }
  .lead { color:#8b93a1; font-size:.84rem; margin:0 0 14px; line-height:1.5; }
  .label { font-size:.72rem; text-transform:uppercase; letter-spacing:.08em; color:#6b7280; font-weight:700; margin:18px 0 10px; }
  .up { color:#4ade80; } .down { color:#f87171; }

  .chips { display:flex; gap:8px; overflow-x:auto; padding-bottom:6px; }
  .chip { flex:0 0 auto; background:#1a1e29; border:1px solid #262c3a; border-radius:10px; padding:9px 13px; cursor:pointer; font:inherit; color:#8b93a1; text-align:center; min-width:76px; }
  .chip:hover { border-color:#3a4358; color:#e6e8eb; }
  .chip.on { border-color:#1c4a2b; background:#12351f; color:#4ade80; }
  .ct { font-weight:700; font-size:.85rem; } .cn { font-size:.66rem; opacity:.85; margin-top:1px; }
  .cohead { display:flex; align-items:baseline; justify-content:space-between; gap:10px; margin:16px 0 4px; flex-wrap:wrap; }
  .coname { font-size:1.1rem; font-weight:700; } .coprice { font-weight:700; font-variant-numeric:tabular-nums; }

  .scroll { display:flex; flex-direction:column; gap:10px; max-height:460px; overflow-y:auto; padding-right:4px; }
  .scroll::-webkit-scrollbar { width:8px; } .scroll::-webkit-scrollbar-thumb { background:#2f3646; border-radius:4px; }

  .day, .art { display:block; width:100%; text-align:left; font:inherit; color:inherit; cursor:pointer; background:#1a1e29; border:1px solid #262c3a; border-radius:13px; padding:15px 16px; }
  .day:hover, .art:hover { border-color:#3a4358; }
  .day.today, .art.today { border-color:#1c4a2b; background:linear-gradient(180deg,#16241b 0%,#1a1e29 60%); }
  .day-top, .atop { display:flex; align-items:center; gap:8px; font-size:.78rem; color:#8b93a1; margin-bottom:9px; font-variant-numeric:tabular-nums; }
  .badge { background:#4ade80; color:#06210f; font-weight:800; font-size:.64rem; padding:2px 7px; border-radius:5px; }
  .day-metrics { display:flex; gap:16px; flex-wrap:wrap; align-items:baseline; }
  .metric .v { font-weight:700; font-variant-numeric:tabular-nums; } .metric .v.big { font-size:1.05rem; }
  .metric .k { font-size:.68rem; color:#6b7280; display:block; }
  .flow { font-size:.72rem; padding:2px 8px; border-radius:20px; background:#212734; color:#9aa4b2; }
  .flow.buy { background:#12351f; color:#4ade80; } .flow.sell { background:#3a1518; color:#f87171; }
  .day-sum { margin-top:10px; font-size:.78rem; color:#8b93a1; line-height:1.45; }
  .day-foot { margin-top:9px; font-size:.74rem; color:#6b7280; display:flex; justify-content:space-between; }
  .arrow { color:#4ade80; }
  .atitle { font-size:.98rem; font-weight:650; line-height:1.45; }
  .sent { font-size:.68rem; padding:2px 8px; border-radius:20px; background:#212734; color:#9aa4b2; }
  .sent.pos { background:#12351f; color:#4ade80; } .sent.neg { background:#3a1518; color:#f87171; }

  .fxcard { background:#1a1e29; border:1px solid #262c3a; border-radius:13px; padding:15px 16px 10px; margin-bottom:12px; }
  .fxcard.main { border-color:#2b3a55; background:linear-gradient(180deg,#161d2b 0%,#1a1e29 60%); }
  .fxhead { display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap; }
  .fxname { font-size:1rem; font-weight:700; } .fxsub { font-size:.7rem; color:#6b7280; }
  .fxdir { font-size:.72rem; padding:3px 9px; border-radius:20px; background:#212734; color:#9aa4b2; white-space:nowrap; }
  .fxdir.weak { background:#3a2a12; color:#fbbf24; }   /* 원화 약세 — 좋/나쁨 아닌 '방향' */
  .fxdir.strong { background:#13273f; color:#60a5fa; } /* 원화 강세 */
  .fxrate { font-size:1.5rem; font-weight:700; margin:8px 0 2px; font-variant-numeric:tabular-nums; }
  .fxrate .won { font-size:.9rem; font-weight:600; color:#8b93a1; margin-left:2px; }
  .fxchg { font-size:.82rem; font-weight:600; margin-left:10px; }
  .fxedu { background:#161a24; border:1px solid #262c3a; border-radius:12px; padding:14px 16px; font-size:.86rem; line-height:1.7; color:#c4cad4; }
  .fxedu p { margin:0 0 10px; } .fxedu ul { margin:0 0 10px; padding-left:18px; }
  .fxedu li { margin-bottom:7px; } .fxedu b { color:#e6e8eb; }
  .fxnote { font-size:.82rem; color:#8b93a1; margin-bottom:6px !important; }

  .chartbox { background:#161a24; border:1px solid #262c3a; border-radius:12px; padding:12px 14px 8px; margin:14px 0 4px; }
  .chartcap { font-size:.72rem; color:#6b7280; margin:0 0 8px; }
  .chart { width:100%; height:auto; display:block; }
  .chart.mini { margin-top:10px; }
  .chart .clbl { font-size:13px; font-variant-numeric:tabular-nums; }
  .chart .cmin { fill:#6b7280; }
  .chart .cpt { cursor:pointer; }
  .chart .cpt:hover circle:last-child { r:6; }
  .chart-empty { font-size:.78rem; color:#6b7280; padding:10px 0; }

  .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(150px,1fr)); gap:11px; }
  .mcard { background:#1a1e29; border:1px solid #262c3a; border-radius:12px; padding:14px; }
  .mcard .k { font-size:.78rem; color:#8b93a1; display:flex; align-items:center; }
  .mcard .v { font-size:1.15rem; font-weight:700; margin-top:6px; font-variant-numeric:tabular-nums; }
  .mcard .d { font-size:.72rem; color:#6b7280; margin-top:2px; }
  .info { margin-left:6px; background:none; color:#6b7280; font-size:.75rem; cursor:pointer; border:1px solid #3a4152; border-radius:50%; width:17px; height:17px; padding:0; line-height:1; }
  .tip { position:absolute; background:#0f1117; border:1px solid #4ade80; border-radius:8px; padding:8px 10px; font-size:.75rem; color:#cbd5e1; max-width:220px; margin-top:4px; z-index:5; }

  .modal-bg { position:fixed; inset:0; background:rgba(3,5,10,.72); display:flex; align-items:center; justify-content:center; padding:18px; z-index:50; }
  .modal { background:#1a1e29; border:1px solid #2f3646; border-radius:16px; padding:24px; max-width:540px; width:100%; max-height:86vh; overflow-y:auto; position:relative; }
  .mx { position:absolute; top:13px; right:15px; background:none; border:none; color:#8b93a1; font-size:1.5rem; cursor:pointer; line-height:1; }
  .mx:hover { color:#e6e8eb; }
  .m-date { font-size:.76rem; color:#4ade80; font-variant-numeric:tabular-nums; margin-bottom:6px; }
  .m-title { font-size:1.15rem; font-weight:700; margin:0 26px 6px 0; line-height:1.35; }
  .m-sub { font-size:.74rem; color:#6b7280; margin-bottom:14px; }
  .m-row { display:flex; gap:18px; flex-wrap:wrap; margin-bottom:14px; padding-bottom:14px; border-bottom:1px solid #262c3a; }
  .src-btn { display:inline-block; background:#212734; color:#e6e8eb; text-decoration:none; padding:8px 14px; border-radius:8px; font-size:.8rem; font-weight:600; border:1px solid #262c3a; margin-bottom:4px; }
  .src-btn:hover { border-color:#4ade80; color:#4ade80; }
  .sec-h { font-size:.8rem; font-weight:700; color:#4ade80; margin:18px 0 8px; }
  .ai { background:#12351f; border:1px solid #1c4a2b; border-radius:10px; padding:13px 15px; font-size:.88rem; line-height:1.65; color:#d5f0e0; }
  .m-body { font-size:.9rem; line-height:1.75; color:#d3d8e0; margin:0; }
  .newsline { background:#212734; border:1px solid #262c3a; border-radius:9px; padding:10px 12px; font-size:.83rem; line-height:1.5; display:flex; gap:9px; align-items:flex-start; margin-bottom:8px; }
  .glossary { list-style:none; margin:0; padding:0; display:flex; flex-direction:column; gap:9px; }
  .glossary li { background:#212734; border:1px solid #262c3a; border-radius:9px; padding:10px 12px; font-size:.83rem; line-height:1.55; color:#c4cad4; }
  .glossary b { color:#e6e8eb; display:block; margin-bottom:2px; }
`

export default App
