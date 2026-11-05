import { useState, useEffect } from 'react'

const API = ''  // 같은 출처 (nginx 가 /api 프록시)

const COMPANIES = [
  { t: 'AAPL', n: '애플' }, { t: 'MSFT', n: '마이크로소프트' }, { t: 'NVDA', n: '엔비디아' },
  { t: 'AMZN', n: '아마존' }, { t: 'GOOGL', n: '알파벳' }, { t: 'TSLA', n: '테슬라' }, { t: 'META', n: '메타' },
]

const DOW = ['일', '월', '화', '수', '목', '금', '토']

function dowOf(iso) {
  const [y, m, d] = String(iso || '').split('-').map(Number)
  if (!y || !m || !d) return ''
  return DOW[new Date(y, m - 1, d).getDay()]
}
// news.published 는 "YYYYMMDDTHHMMSS" 이고 UTC 다. 그대로 잘라 쓰면
// 한국 시간으로 새벽에 나온 기사가 하루 전으로 찍힌다
// (20261026T171000 = KST 10-27 02:10). 9시간 더해 KST 달력으로 바꾼다.
function pubLabel(published) {
  const s = String(published || '')
  if (s.length < 8) return null
  const t = Date.UTC(+s.slice(0, 4), +s.slice(4, 6) - 1, +s.slice(6, 8),
                     +(s.slice(9, 11) || 0), +(s.slice(11, 13) || 0))
  if (Number.isNaN(t)) return null
  const k = new Date(t + 9 * 3600 * 1000)
  const pad = n => String(n).padStart(2, '0')
  const iso = `${k.getUTCFullYear()}-${pad(k.getUTCMonth() + 1)}-${pad(k.getUTCDate())}`

  const n = new Date(Date.now() + 9 * 3600 * 1000)
  const todayIso = `${n.getUTCFullYear()}-${pad(n.getUTCMonth() + 1)}-${pad(n.getUTCDate())}`
  const diff = Math.round((Date.parse(todayIso) - Date.parse(iso)) / 86400000)
  const ago = diff <= 0 ? '오늘' : diff === 1 ? '어제' : `${diff}일 전`

  return { iso, md: iso.slice(5), dow: DOW[k.getUTCDay()], ago }
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


// ===== 탭 1: AI 추천 기사 =====
// 방향 기호 — 긍정 ▲ / 부정 ▼ / 중립 ▬
function arrowOf(s) { const t = sentText(s); return t === '긍정' ? '▲' : t === '부정' ? '▼' : '▬' }

// 카드 겉면에 붙는 기업별 영향 요약.
// 회의에서 나온 지적이 "무슨 기업이 어떤 영향을 받아 긍부정인지 하나도
// 안 나와있음" 이었다. 모달을 열어야 보이면 그 지적이 안 풀리므로,
// 목록을 훑기만 해도 기업과 방향이 보이게 카드에 올린다. 이유는 눌러서 본다.
function ImpactBadges({ impacts }) {
  if (!impacts || impacts.length === 0) return null
  return (
    <div className="impbadges">
      <span className="impbadges-h">🏢</span>
      {impacts.slice(0, 3).map((x, i) => (
        <span className={`impbadge ${sentClass(x.sentiment)}`} key={i}>
          {x.company} {arrowOf(x.sentiment)}{x.kind === '간접' && <i className="est">추정</i>}
        </span>
      ))}
    </div>
  )
}

// 기사 카드 한 종류. 오늘의 추천도, 검색 결과도, 지난 기록도 이걸 쓴다.
// 같은 모양이어야 "검색해도 추천 기사처럼 분석해 준다"가 전달된다.
function ArticleCard({ a, badge, dateText, onClick }) {
  return (
    <button className={`art${badge ? ' today' : ''}`} onClick={onClick}>
      <div className="atop">
        {badge && <span className="badge">{badge}</span>}
        <span>{dateText}</span>
        <span className={`sent ${sentClass(a.sentiment)}`}>{sentText(a.sentiment)}</span>
        <span className="asrc">{a.source}</span>
      </div>
      <div className="atitle">{a.title_ko || a.title}</div>
      {a.title_ko && <div className="aorig">원제 · {a.title}</div>}
      {a.brief && <div className="day-sum">{a.brief}</div>}
      <ImpactBadges impacts={a.impacts} />
    </button>
  )
}

// 모달 본문 — 기업별 영향을 직접/간접으로 나눠 보여준다.
// 직접은 기사에 근거가 있고, 간접은 우리가 추론한 것이다. 섞어 놓으면
// 사용자가 추론을 사실로 읽으므로 "AI 추정" 이라고 밝혀서 나눈다.
function ArticleBody({ a }) {
  const imp = a.impacts || []
  const direct = imp.filter(x => x.kind !== '간접')
  const indirect = imp.filter(x => x.kind === '간접')

  const Row = (x, i) => (
    <div className="imp" key={i}>
      <div className="imp-top">
        <b>{x.company}</b>
        {x.ticker && <span className="imp-tk">{x.ticker}</span>}
        <span className={`sent ${sentClass(x.sentiment)}`}>
          {arrowOf(x.sentiment)} {sentText(x.sentiment)}
        </span>
      </div>
      <div className="imp-why">{x.reason}</div>
    </div>
  )

  return (
    <>
      <div className="m-sub">
        {(() => {
          const p = pubLabel(a.published)
          return p ? <><b>{p.iso} ({p.dow})</b> · {p.ago} · 출처 {a.source}</>
                   : <>출처 · {a.source}</>
        })()}
      </div>
      {a.title_ko && <div className="m-orig">원제 · {a.title}</div>}
      <a className="src-btn" href={a.url} target="_blank" rel="noreferrer">🔗 원문 보기</a>

      {/* 검색으로 들어온 기사는 Google 뉴스 RSS 가 제목만 준다. 본문 있는
          기사와 같은 화면에 섞이면 구분할 수가 없어서, 어디까지 믿을지
          판단할 수 있게 밝혀 둔다. */}
      {a.title_only === 1 && (
        <div className="m-warn">
          제목만 수집된 기사입니다 — 본문 없이 <b>제목을 근거로</b> 분석했습니다.
          자세한 내용은 원문을 확인해 주세요.
        </div>
      )}

      {a.brief && <><div className="sec-h">📄 한 줄 요약</div>
        <p className="m-body">{a.brief}</p></>}

      {imp.length > 0 && <>
        <div className="sec-h">🏢 이 기사가 기업에 주는 영향</div>
        {direct.length > 0 && <>
          <div className="imp-kind">직접 — 기사에 나온 기업</div>
          <div className="imps">{direct.map(Row)}</div>
        </>}
        {indirect.length > 0 && <>
          <div className="imp-kind">간접 — 우리가 보는 종목에 미칠 영향 <i>· AI 추정</i></div>
          <div className="imps">{indirect.map(Row)}</div>
        </>}
        {a.sentiment_reason && (
          <div className="imp-all">시장 전체로는 <b>{sentText(a.sentiment)}</b> · {a.sentiment_reason}</div>
        )}
      </>}

      {a.pick_reason && <><div className="sec-h">💡 이 기사를 고른 이유</div>
        <div className="ai">{a.pick_reason}</div></>}
      <div className="sec-h">💡 쉬운 설명</div>
      <p className="m-body">{a.summary_easy}</p>
      {(a.glossary || []).length > 0 && <><div className="sec-h">📖 용어 설명</div>
        <ul className="glossary">{a.glossary.map((g, i) => <li key={i}><b>{g.term}</b>{g.desc}</li>)}</ul></>}
    </>
  )
}

// ===== 탭 1: AI 추천 기사 =====
//
// 화면 순서가 곧 설계다 —
//   오늘의 추천  : 아무것도 안 해도 오늘 몫이 준비돼 있다 (기본값)
//   검색         : 궁금한 단어를 넣으면 그 주제로 한 건 골라 준다
//   지난 분석    : 쌓인 기록. 검색 중에는 감춰서 화면이 길어지지 않게 한다
function ArticlesTab() {
  const [daily, setDaily] = useState([])
  const [sel, setSel] = useState(null)

  const [q, setQ] = useState('')
  const [res, setRes] = useState(null)
  const [pick, setPick] = useState(null)
  const [busy, setBusy] = useState(false)
  const [showList, setShowList] = useState(false)

  useEffect(() => {
    fetch(`${API}/api/daily`).then(r => r.json()).then(setDaily).catch(() => {})
  }, [])

  // 분석은 1~2분 걸리므로 서버가 백그라운드로 돌리고, 여기서 몇 초마다
  // 상태를 물어본다. 긴 HTTP 연결을 붙잡고 있으면 nginx(60초)·브라우저·
  // Funnel 중 어디선가 끊긴다. 실제로 '유가' 가 60초에 끊겨서 화면에
  // 아무 일도 일어나지 않았다.
  useEffect(() => {
    if (!pick || pick.status !== 'working') return
    const t = setTimeout(() => {
      fetch(`${API}/api/news/pick?q=${encodeURIComponent(pick.query)}`)
        .then(r => r.json()).then(setPick)
        .catch(() => setPick(p => ({ ...p, status: 'error', message: '서버에 연결하지 못했습니다' })))
    }, 3000)
    return () => clearTimeout(t)
  }, [pick])

  const today = daily[0]
  const past = daily.slice(1)

  const run = (term) => {
    const word = (term ?? q).trim()
    if (!word) return
    setQ(word); setBusy(true); setPick(null); setShowList(false)
    fetch(`${API}/api/news/search?q=${encodeURIComponent(word)}&limit=30`)
      .then(r => r.json()).then(setRes)
      .catch(() => setRes({ query: word, expanded: [], count: 0, items: [], failed: true }))
      .finally(() => setBusy(false))
    fetch(`${API}/api/news/pick?q=${encodeURIComponent(word)}`)
      .then(r => r.json()).then(setPick)
      .catch(() => setPick({ status: 'error', query: word, message: '서버에 연결하지 못했습니다' }))
  }

  const analyze = () => {
    setPick(p => ({ ...p, status: 'working', elapsed: 0 }))
    fetch(`${API}/api/news/pick?q=${encodeURIComponent(q)}&force=true`)
      .then(r => r.json()).then(setPick)
      .catch(() => setPick(p => ({ ...p, status: 'error', message: '분석을 시작하지 못했습니다' })))
  }

  const clear = () => { setQ(''); setRes(null); setPick(null); setShowList(false) }

  const searching = !!res

  return (
    <div className="panel">
      <p className="lead">📰 <b>경제를 몰라도 읽히는 오늘의 뉴스.</b> AI가 기사를 골라 쉽게 풀어주고, 어느 기업에 어떤 영향인지까지 알려줘요.</p>

      {/* ① 기본값 — 오늘의 추천 */}
      {today && <>
        <div className="label">오늘의 추천</div>
        <ArticleCard a={today} badge="오늘"
          dateText={`${today.date} (${dowOf(today.date)})`}
          onClick={() => setSel(today)} />
      </>}
      {daily.length === 0 && <p className="lead">아직 분석된 기사가 없습니다.</p>}

      {/* ② 검색 */}
      <div className="search">
        <div className="label">다른 주제가 궁금하세요?</div>
        <div className="search-row">
          <input className="search-in"
            placeholder="알고 싶은 단어 — 금리, 테슬라, 반도체…"
            value={q}
            onChange={e => setQ(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') run() }} />
          <button className="search-btn" onClick={() => run()} disabled={busy}>
            {busy ? '찾는 중…' : '검색'}
          </button>
          {searching && <button className="search-clear" onClick={clear}>✕</button>}
        </div>
        <div className="search-chips">
          {['금리', '물가', '테슬라', '반도체', '환율', '실적'].map(w => (
            <button key={w} className={`chip${q === w ? ' on' : ''}`} onClick={() => run(w)}>{w}</button>
          ))}
        </div>
      </div>

      {searching && <div className="search-res">
        {res.count === 0 && <div className="empty">
          <p className="lead">
            &lsquo;{res.query}&rsquo; 로 찾은 기사가 없습니다.
            <br />뉴스를 미국 시장 중심으로 모으고 있어서, 국내 기업은 아직 기사가 없을 수 있어요.
          </p>
          {(res.suggest || []).length > 0 && <>
            <div className="empty-h">대신 이런 주제는 어떠세요?</div>
            <div className="search-chips">
              {res.suggest.map(w => (
                <button key={w} className="chip" onClick={() => run(w)}>{w}</button>
              ))}
            </div>
          </>}
        </div>}

        {/* 범위 안내 문구는 뺐다. 기사 날짜를 카드에 직접 붙이면서 중복이 됐고,
            "오늘 기사가 적어 최근 3일에서" 라고 떠 놓고 정작 오늘 기사를 보여 주는
            일이 있었다(사다리가 UTC 날짜를 KST 기준일과 비교하던 버그).
            범위는 고르는 쪽 사정이고, 보는 사람이 알고 싶은 건 기사 날짜다. */}

        {pick && pick.status === 'ready' && (
          <ArticleCard a={pick} badge="AI 선별"
            dateText={(() => {
              const p = pubLabel(pick.published)
              return p ? `‘${pick.query}’ · ${p.md} (${p.dow}) ${p.ago}` : `‘${pick.query}’`
            })()}
            onClick={() => setSel({ ...pick, date: null })} />
        )}

        {pick && pick.status === 'pending' && res.count > 0 && (
          <div className="pickbox">
            <div className="pickbox-t">이 단어는 아직 분석 전입니다.</div>
            <button className="search-btn wide" onClick={analyze}>
              🤖 AI에게 기사 골라 분석시키기 <span className="dim">· 1~2분</span>
            </button>
          </div>
        )}

        {pick && pick.status === 'working' && (
          <div className="pickbox">
            <div className="thinking">
              <span className="spin" />
              AI가 기사를 고르고 분석하는 중입니다… <b>{pick.elapsed || 0}초</b>
            </div>
            <div className="thinking-sub">
              서버 안의 로컬 AI가 직접 돌고 있어요. 보통 1~2분 걸립니다. 창을 닫지 말고 기다려 주세요.
            </div>
          </div>
        )}

        {pick && pick.status === 'error' && (
          <div className="pickbox err">
            <div className="pickbox-t">분석에 실패했습니다. {pick.message}</div>
            <button className="search-btn wide" onClick={analyze}>다시 시도</button>
          </div>
        )}

        {res.count > 0 && <>
          <button className="foldbtn" onClick={() => setShowList(v => !v)}>
            이 단어로 찾은 기사 {res.count}건 {showList ? '▴' : '▾'}
            {res.live && <span className="livetag">방금 새로 받아옴</span>}
            {res.expanded.length > 1 &&
              <span className="search-exp"> · 기사가 영어라 {res.expanded.slice(1, 4).join(', ')} 로도 찾음</span>}
          </button>
          {showList && <div className="scroll">
            {res.items.map((a, i) => (
              <a className="art thin" key={i} href={a.url} target="_blank" rel="noreferrer">
                <div className="atop">
                  <span>{(pubLabel(a.published) || {}).md || ''}</span>
                  <span className="hit">{a.matched} · {a.matched_in}</span>
                  <span className="asrc">{a.source} ↗</span>
                </div>
                <div className="atitle">{a.title_ko || a.title}</div>
              </a>
            ))}
          </div>}
        </>}
      </div>}

      {/* ③ 지난 기록 — 검색 중에는 감춘다 */}
      {!searching && past.length > 0 && <>
        <div className="label">지난 분석 · {past.length}건</div>
        <div className="scroll">
          {past.map(a => (
            <ArticleCard key={a.date} a={a}
              dateText={`${a.date} (${dowOf(a.date)})`}
              onClick={() => setSel(a)} />
          ))}
        </div>
      </>}

      {sel && <Modal onClose={() => setSel(null)}>
        <div className="m-date">
          {sel.date ? `${sel.date} (${dowOf(sel.date)})` : `🔎 ‘${sel.query}’ · AI가 고른 기사`}
        </div>
        <h2 className="m-title">{sel.title_ko || sel.title}</h2>
        <ArticleBody a={sel} />
      </Modal>}
    </div>
  )
}

// ===== 탭 2: 종목별 =====
// 통화는 종목마다 다르다. 달러는 소수점 둘, 원화는 없음, 지수는 단위 없음.
// 화면에 $ 를 박아두면 삼성전자가 "$225000.00" 이 된다.
function money(v, c) {
  if (v == null) return '—'
  const d = c?.decimals ?? 2
  const n = v.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d })
  if (c?.symbol) return c.symbol + n
  return n + (c?.unit ? c.unit : '')
}

function fmtCap(v, c) {
  if (!v) return '—'
  const u = c?.unit || '달러'
  if (v >= 1e12) return (v / 1e12).toFixed(2) + '조 ' + u
  if (v >= 1e8) return Math.round(v / 1e8).toLocaleString() + '억 ' + u
  return v.toLocaleString() + ' ' + u
}

// 52주 범위에서 현재가가 어디인가. 숫자 두 개보다 막대 하나가 빠르게 읽힌다
function W52Bar({ lo, hi, pos, cur, c }) {
  if (lo == null || hi == null || pos == null) return null
  return (
    <div className="w52">
      <div className="w52-top"><span>52주 최저</span><span>52주 최고</span></div>
      <div className="w52-bar">
        <div className="w52-dot" style={{ left: `${(pos * 100).toFixed(1)}%` }} />
      </div>
      <div className="w52-bot">
        <span>{money(lo, c)}</span>
        <span className="w52-cur">현재 {money(cur, c)}</span>
        <span>{money(hi, c)}</span>
      </div>
    </div>
  )
}

// 시세 카드 — 숫자만 보여주고 '언제 기준'인지 안 쓰면 사용자는 지금 값이라고
// 믿는다. 미국장은 한국시간 23:30~06:00 이라, 낮에 보는 값은 전날 종가다.
function QuoteCard({ q, ticker, name, volNote }) {
  if (!q) return null
  const up = (q.pct ?? 0) > 0, down = (q.pct ?? 0) < 0
  const col = up ? 'up' : down ? 'down' : ''
  const live = q.market_state === 'REGULAR'
  return (
    <div className="qcard">
      <div className="qhead">
        <div>
          <span className="qtk">{ticker}</span>
          <span className="qnm">{name}</span>
        </div>
        <span className={`qstate${live ? ' on' : ''}`}>{q.state_ko}</span>
      </div>

      <div className="qprice">
        <span className={`qnow ${col}`}>{money(q.price, q)}</span>
        {q.chg != null && (
          <span className={`qchg ${col}`}>
            {up ? '▲' : down ? '▼' : '▬'} {money(Math.abs(q.chg), q)} ({q.pct > 0 ? '+' : ''}{q.pct}%)
          </span>
        )}
      </div>

      <div className="qwhen">
        {q.quote_time ? `${q.quote_time.replace('T', ' ')} 기준` : '기준 시각 미확인'}
        {q.state_note && <> · {q.state_note}</>}
      </div>

      {q.ext_price != null && (
        <div className="qext">
          {q.ext_label} {money(q.ext_price, q)}
          {q.ext_pct != null && <> ({q.ext_pct > 0 ? '+' : ''}{q.ext_pct}%)</>}
        </div>
      )}

      <div className="qgrid">
        <div className="metric">
          <span className="k">거래량</span>
          <span className="v">{fmtVol(q.volume)}</span>
          {volNote && <span className="sub">{volNote.split(' — ')[1] || volNote}</span>}
        </div>
        <div className="metric"><span className="k">시가총액</span><span className="v">{fmtCap(q.market_cap, q)}</span></div>
        <div className="metric"><span className="k">PER</span><span className="v">{q.pe != null ? q.pe.toFixed(1) : '—'}</span></div>
        <div className="metric"><span className="k">거래소</span><span className="v">{q.exchange || '—'}</span></div>
      </div>

      <W52Bar lo={q.w52_low} hi={q.w52_high} pos={q.w52_pos} cur={q.price} c={q} />
    </div>
  )
}

// 하루 안의 움직임. 미 동부 시각으로 그린다 — 한국 시각으로 바꾸면
// 23:30 에 시작해 다음날 06:00 에 끝나서 '하루' 로 읽히지 않는다.
function StockDay({ d, ticker, c }) {
  if (!d || !d.points || d.points.length < 2) return null
  const pts = d.points.map(p => ({ t: p.t, rate: p.price }))
  const up = d.chg > 0, down = d.chg < 0
  return (
    <div className="chartbox">
      <div className="dayhead">
        <span className="daylabel">{d.session} 장</span>
        <span className={`qchg ${up ? 'up' : down ? 'down' : ''}`}>
          시작 대비 {up ? '▲' : down ? '▼' : '▬'} {money(Math.abs(d.chg), c)}
          {d.pct != null && <> ({d.pct > 0 ? '+' : ''}{d.pct}%)</>}
        </span>
      </div>
      <AxisChart pts={pts} baseline={d.open} baseName="시작"
        color={up ? '#4ade80' : down ? '#f87171' : '#8b93a1'}
        fmt={v => money(v, c)}
        label={`${ticker} ${d.session} 장중 5분 단위 주가`} />
      <p className="chartcap">
        {d.open_at}에 열고 {d.close_at}에 닫은 장 ({d.tz} 시각) · 5분마다 한 점.
        {!d.kr && <> 한국 시각으로는 밤 11시 30분부터 다음날 아침 6시까지예요.</>}
      </p>
      <p className="dayaxis">x축: 시각 · y축: 주가({c?.unit}) · 점선: 시작가</p>
    </div>
  )
}

// 오른쪽 칼럼 — 고르는 곳.
//
// 상세는 왼쪽 하나만 둔다. 양쪽에 상세를 두면 UI 가 두 벌이 되고, 오른쪽에서
// 고르는 동안 왼쪽이 놀게 된다. 여기서 종목을 누르면 왼쪽이 그 종목으로 바뀐다.
function ThemePanel({ chips, data, cur, busy, onTheme, onStock, picked }) {
  const st = data && data.stats
  return (
    <div className="tpanel">
      <div className="label">업종으로 찾기</div>
      <p className="segnote dim">회사 이름을 몰라도 찾아갈 수 있어요.</p>
      {['미국', '한국'].map(mkt => {
        const row = chips.filter(c => (c.market || '미국') === mkt)
        if (!row.length) return null
        return (
          <div key={mkt}>
            <div className="tmkt">{mkt}</div>
            <div className="tchips">
              {row.map(c => (
                <button key={c.key} className={`chip${cur === c.key ? ' on' : ''}`}
                  onClick={() => onTheme(c.key)}>{c.short}</button>
              ))}
            </div>
          </div>
        )
      })}

      {busy && <p className="segnote dim">받아오는 중…</p>}

      {!busy && data && <>
        <div className="thead">
          <span className="tname">{data.name}</span>
          <span className="tdate">{data.date} 장</span>
        </div>

        {data.index && (
          <div className="tindex">
            <span className="tix-n">{data.index.name}</span>
            <span className="tix-v">{data.index.price.toLocaleString()}{data.index.unit || ''}</span>
            <span className={`tix-p ${data.index.pct > 0 ? 'up' : data.index.pct < 0 ? 'down' : ''}`}>
              {data.index.pct > 0 ? '+' : ''}{data.index.pct}%
            </span>
          </div>
        )}

        {st && <div className="tstat">
          <div className="tshape">{st.shape}</div>
          <div className="ttally">{st.tally} · 평균 {st.avg_pct > 0 ? '+' : ''}{st.avg_pct}%</div>
          {st.odd_note && <div className="todd">{st.odd_note}</div>}
        </div>}

        <div className="trows">
          {data.items.map(x => (
            <button key={x.symbol}
              className={`trow${picked === x.symbol ? ' on' : ''}`}
              onClick={() => onStock(x.symbol)}>
              <span className="tr-tk">{x.symbol}</span>
              <span className="tr-nm">{x.name}</span>
              <span className="tr-pr">
                {x.price.toLocaleString()}
                {x.unit === '원' && <span className="tr-u">원</span>}
                {x.stale && <span className="tr-old"> {x.date.slice(5)}</span>}
              </span>
              <span className={`tr-pc ${x.pct > 0 ? 'up' : x.pct < 0 ? 'down' : ''}`}>
                {x.pct > 0 ? '+' : ''}{x.pct}%
              </span>
            </button>
          ))}
        </div>
        <p className="segnote dim">종목을 누르면 왼쪽에서 자세히 볼 수 있어요.</p>
      </>}

      {!busy && !data && <p className="segnote dim">업종을 하나 골라보세요.</p>}
    </div>
  )
}

function StocksTab() {
  const [q, setQ] = useState('')
  const [found, setFound] = useState(null)
  const [brief, setBrief] = useState(null)
  const [busy, setBusy] = useState(false)
  const [sel, setSel] = useState(null)
  const [chips, setChips] = useState([])
  const [tchips, setTchips] = useState([])
  const [theme, setTheme] = useState(null)
  const [tcur, setTcur] = useState('반도체')
  const [tbusy, setTbusy] = useState(false)

  // 브리핑은 백그라운드로 만들고 몇 초마다 물어본다. 긴 HTTP 연결을 붙잡고
  // 있으면 nginx(60초)·브라우저·Funnel 중 어디선가 끊긴다 — 단어 검색에서
  // '유가' 가 실제로 60초에 끊겨 화면에 아무 일도 일어나지 않았다.
  useEffect(() => {
    if (!brief || brief.status !== 'working') return
    const t = setTimeout(() => {
      fetch(`${API}/api/stock/brief?q=${encodeURIComponent(brief.ticker)}`)
        .then(r => r.json()).then(setBrief)
        .catch(() => setBrief(b => ({ ...b, status: 'error', message: '서버에 연결하지 못했습니다' })))
    }, 3000)
    return () => clearTimeout(t)
  }, [brief])

  const run = (term) => {
    const word = (term ?? q).trim()
    if (!word) return
    setQ(word); setBusy(true); setFound(null); setBrief(null)
    fetch(`${API}/api/stock/find?q=${encodeURIComponent(word)}`)
      .then(r => r.json()).then(d => {
        setFound(d)
        if (d.popular) setChips(d.popular)
        if (d.status === 'ready') {
          return fetch(`${API}/api/stock/brief?q=${encodeURIComponent(d.ticker)}`)
            .then(r => r.json()).then(setBrief)
        }
        // 종목이 아니면 업종인지 본다. '유가' 는 회사가 아니라서 종목 검색으로는
        // 영원히 0건이지만, 사용자가 알고 싶은 것은 분명하다.
        return fetch(`${API}/api/theme/find?q=${encodeURIComponent(word)}`)
          .then(r => r.json()).then(t => {
            if (t.chips) setTchips(t.chips)
            if (t.status === 'ready') {
              setTcur(t.key); setTheme(t)
              setFound(f => ({ ...f, status: 'theme', theme: t.name }))
            }
          }).catch(() => {})
      })
      .catch(() => setFound({ status: 'failed', query: word }))
      .finally(() => setBusy(false))
  }

  const make = () => {
    setBrief(b => ({ ...b, status: 'working', elapsed: 0 }))
    fetch(`${API}/api/stock/brief?q=${encodeURIComponent(found.ticker)}&force=true`)
      .then(r => r.json()).then(setBrief)
      .catch(() => setBrief(b => ({ ...b, status: 'error', message: '브리핑을 시작하지 못했습니다' })))
  }

  const loadTheme = (key) => {
    setTcur(key); setTbusy(true)
    fetch(`${API}/api/theme/find?key=${encodeURIComponent(key)}`)
      .then(r => r.json()).then(d => {
        if (d.chips) setTchips(d.chips)
        setTheme(d.status === 'ready' ? d : null)
      })
      .catch(() => setTheme(null))
      .finally(() => setTbusy(false))
  }

  useEffect(() => { run('NVDA'); loadTheme('반도체') }, [])

  const days = (brief && brief.days) || []
  const hist = (found && found.history) || []
  const pts = hist.map(h => ({ t: h.date.slice(5), rate: h.close }))
  const rising = pts.length >= 2 && pts[pts.length - 1].rate >= pts[0].rate

  return (
    <div className="panel wide">
      <p className="lead">📈 <b>종목 이름이나 업종으로 찾는 주가와 AI 분석.</b></p>

      <div className="cols">
        <div className="main">
          <div className="search">
            <div className="search-row">
              <input className="search-in"
                placeholder="종목 이름이나 티커 — 엔비디아, TSLA, 코카콜라…"
                value={q}
                onChange={e => setQ(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') run() }} />
              <button className="search-btn" onClick={() => run()} disabled={busy}>
                {busy ? '찾는 중…' : '검색'}
              </button>
            </div>
            <div className="search-chips">
              {(chips.length ? chips : COMPANIES.map(c => ({ ticker: c.t, name: c.n }))).map(c => (
                <button key={c.ticker} className={`chip${found?.ticker === c.ticker ? ' on' : ''}`}
                  onClick={() => run(c.ticker)}>{c.name}</button>
              ))}
            </div>
          </div>

          {found?.status === 'theme' && (
            <div className="empty">
              <p className="lead">
                &lsquo;{found.query}&rsquo; 는 회사가 아니라 업종이에요.
                <br />오른쪽에 <b>{found.theme}</b> 종목들을 띄웠어요. 하나를 누르면 여기서 자세히 볼 수 있어요.
              </p>
            </div>
          )}
          {found?.status === 'none' && (
            <div className="empty">
              <p className="lead">
                &lsquo;{found.query}&rsquo; 가 어느 종목인지 몰랐어요.
                {found.hangul && <><br />지금은 미국에 상장된 종목만 찾을 수 있어요.</>}
                <br />오른쪽 업종 중에 있나 보세요.
              </p>
            </div>
          )}
          {found?.status === 'notfound' && (
            <div className="empty">
              <p className="lead">&lsquo;{found.ticker}&rsquo; 라는 종목이 없어요. 철자를 확인해 주세요.</p>
            </div>
          )}
          {found?.status === 'failed' && (
            <div className="empty"><p className="lead">서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.</p></div>
          )}

          {found?.status === 'ready' && <>
            <QuoteCard q={found.quote} ticker={found.ticker} name={found.name}
              volNote={found.volume_note} />

            <StockDay d={found.intraday} ticker={found.ticker} c={found.quote} />

            {pts.length >= 2 && (
              <div className="chartbox">
                <p className="chartcap">최근 {pts.length}거래일 종가 · 하루에 한 점 (주말·휴장일 제외)</p>
                <AxisChart pts={pts} baseline={pts[0].rate} baseName="시작"
                  color={rising ? '#4ade80' : '#f87171'}
                  fmt={v => money(v, found.quote)}
                  label={`${found.ticker} 최근 ${pts.length}거래일 종가 추이`} />
                {/* 주말·휴장일이 빠진 그래프라, 달력일로 읽으면 간격이 안 맞는다. */}
                <p className="dayaxis">x축: 거래일 · y축: 종가({found.quote?.unit}) · 점선: 첫날</p>
              </div>
            )}

            <div className="seg" />
            <div className="label">💬 AI 브리핑</div>

            {brief?.status === 'pending' && (
              <div className="segbox">
                <p className="segnote">
                  이 종목은 아직 설명이 없어요. 만드는 데 <b>5초에서 2분쯤</b> 걸립니다.
                </p>
                <button className="search-btn" onClick={make}>AI 브리핑 만들기</button>
              </div>
            )}
            {brief?.status === 'working' && (
              <div className="segbox">
                <p className="segnote">읽고 있어요… {brief.elapsed ? `${brief.elapsed}초` : ''}</p>
                <p className="segnote dim">다른 탭을 봐도 계속됩니다.</p>
              </div>
            )}
            {brief?.status === 'error' && (
              <div className="segbox">
                <p className="segnote">{brief.message || '브리핑을 만들지 못했습니다.'}</p>
                <button className="search-btn" onClick={make}>다시 시도</button>
              </div>
            )}

            {brief?.status === 'ready' && <>
              {!brief.precomputed && days.length === 1 && (
                <p className="segnote dim">이 종목은 오늘 하루만 있어요. 위 버튼의 종목들은 날짜별로 쌓입니다.</p>
              )}
              <div className="scroll">
                {days.map((x, i) => (
                  <button className={`day${i === 0 ? ' today' : ''}`} key={x.date} onClick={() => setSel(x)}>
                    <div className="day-top">{i === 0 && <span className="badge">최신</span>}<span>{x.date} ({dowOf(x.date)})</span></div>
                    <div className="day-metrics">
                      <div className="metric"><span className="k">종가</span><span className="v">{money(x.close, found?.quote)} {chgHtml(x.change_pct)}</span></div>
                      <div className="metric"><span className="k">거래량</span><span className="v">{fmtVol(x.volume)}</span></div>
                      <span className={`flow ${flowClass(x.change_pct)}`}>{flowLabel(x.change_pct)}</span>
                    </div>
                    <div className="day-sum">{(x.ai_summary || '').slice(0, 52)}…</div>
                    <div className="day-foot"><span>관련 뉴스 {(x.news || []).length}건</span><span className="arrow">그날 정보 보기 →</span></div>
                  </button>
                ))}
              </div>
            </>}
          </>}
        </div>

        <aside className="side">
          <ThemePanel chips={tchips} data={theme} cur={tcur} busy={tbusy}
            onTheme={loadTheme} onStock={run} picked={found?.ticker} />
        </aside>
      </div>

      {sel && <Modal onClose={() => setSel(null)}>
        <div className="m-date">{sel.date} ({dowOf(sel.date)})</div>
        <h2 className="m-title">{found?.ticker} · {found?.name}</h2>
        <div className="m-row">
          <div className="metric"><span className="k">종가</span><span className="v big">{money(sel.close, found?.quote)} {chgHtml(sel.change_pct)}</span></div>
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
// ===== 탭 3: 경제지표 =====
// 주가 카드를 걷어냈다. 검색도, 축도, 해설도 없는 7개 고정 카드였고
// 종목별 탭이 같은 일을 전부 더 잘한다. 남은 게 지표뿐이라 탭 이름도 바꿨다.
//
// 숫자 가공은 전부 백엔드(indicators.py)에 있다. 단위 규칙 — 지수는 비율(%),
// 금리·실업률은 차이(%p) — 을 화면에 흩어두면 또 틀린다.
function MarketTab() {
  const [items, setItems] = useState([])
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    fetch(`${API}/api/indicators`)
      .then(r => r.json())
      .then(d => setItems(Array.isArray(d) ? d : []))
      .catch(() => setFailed(true))
  }, [])
  return (
    <div className="panel">
      <p className="lead">물가, 금리, 일자리. 그리고 한국 수출입.</p>
      {failed && <p className="chartcap">지표를 불러오지 못했습니다.</p>}
      {[['US', '🇺🇸 미국'], ['KR', '🇰🇷 한국']].map(([cc, title]) => {
        const group = items.filter(d => d.country === cc)
        if (!group.length) return null
        return (
          <div key={cc}>
            <div className="clabel">{title}</div>
            <div className="igrid">
              {group.map(d => <IndCard key={d.name} d={d} />)}
            </div>
            {cc === 'KR' && (
              <p className="chartcap">
                원/달러 환율은 <b>환율 탭</b>에 있습니다 — 거기서는 5분마다 갱신되는
                장중 움직임까지 봅니다. 같은 걸 두 군데 두지 않았습니다.
              </p>
            )}
          </div>
        )
      })}
      <p className="chartcap">
        🔴🔵 뱃지는 <b>그래프에 보이는 기간 중 어디쯤인지</b>만 나타냅니다 — 좋고 나쁨이 아닙니다.
        금리가 낮은 게 좋은지는 대출자냐 예금자냐에 따라 다르고, 실업률도 너무 낮으면
        임금이 올라 물가를 밀어올립니다.
      </p>
      <p className="chartcap">미국 FRED 자료 · 발표될 때마다 갱신됩니다.</p>
    </div>
  )
}

// 금액이 아니라 변화량이다. 부호를 꼭 붙인다 — '0.21%p' 와 '-0.21%p' 는 반대다
function amount(a, sign = true) {
  if (!a) return ''
  return `${sign && a.value > 0 ? '+' : ''}${a.value.toFixed(a.decimals)}${a.unit}`
}

// 지표는 주가와 색 관습이 다르다. 주가는 올라서 좋지만 물가·금리·실업률은
// 셋 다 올라서 부담이다. 그래서 종목 탭의 초록(상승)/빨강(하락)이 아니라
// 빨강(상승)/파랑(하락) 을 쓴다. 기호(▲▼)를 같이 두는 건 색만으로 구분하면
// 색약인 사람에게 아무 정보가 아니기 때문이다.
function Delta({ a, pre }) {
  if (!a) return null
  const up = a.value > 0, down = a.value < 0
  return (
    <span className={`idelta${up ? ' iup' : down ? ' idown' : ''}`}>
      <span className="ipre">{pre}</span>
      {up ? '▲' : down ? '▼' : '─'}
      {Math.abs(a.value).toFixed(a.decimals)}{a.unit}
    </span>
  )
}

// 뱃지 색은 **높낮이만** 나타낸다. 좋고 나쁨이 아니다 — 금리가 낮은 게 좋은지는
// 대출자냐 예금자냐에 따라 다르고, 실업률도 너무 낮으면 임금이 올라 물가 압력이
// 된다. '안정·주의·경고' 로 쓰지 않은 이유이기도 하다. 경계를 내가 정하게 되고
// "왜 3.7% 가 경고인가" 에 답할 근거가 없다. 지난 3년 범위를 삼등분한 위치는
// 계산이라 "지난 3년을 삼등분했다" 고 답할 수 있다.
const BAND = {
  high: { dot: '🔴', text: '높은 쪽' },
  mid: { dot: '⚪', text: '중간' },
  low: { dot: '🔵', text: '낮은 쪽' },
}

function Band({ b, dec, unit }) {
  if (!b || !BAND[b.level]) return null
  const { dot, text } = BAND[b.level]
  return (
    <span className={`ibadge b-${b.level}`}>
      {dot} {text}
      <span className="ibrange">{b.lo.toFixed(dec)}~{b.hi.toFixed(dec)}{unit}</span>
    </span>
  )
}

function IndCard({ d }) {
  const pts = d.chart?.points || []
  if (pts.length < 2) return null
  // 기준선은 1년 전. 0 을 기준으로 잡으면 CPI 상승률(2~4%)이 바닥에 눌려
  // 모양이 안 보인다. 12칸 전이 없으면 가진 것의 처음을 쓴다.
  const bi = pts.length > 12 ? pts.length - 13 : 0
  const baseline = pts[bi].rate
  const baseName = pts.length > 12 ? '1년 전' : '시작'
  const chg = pts[pts.length - 1].rate - baseline
  const { decimals: dec, unit } = d.chart
  const index = d.unit === 'index'
  // ⚠️ 지표마다 세로축의 뜻이 다르다. 넷 다 눈금에 % 가 붙는데 의미가 둘로 갈린다.
  //   물가·수출입  작년 같은 달과 비교한 변화율
  //   금리·실업률  지표 값 그 자체
  // 안 적어두면 물가 그래프를 '물가 지수' 로 읽게 된다.
  const yLabel = d.unit === 'index' ? '작년 같은 달 대비 상승률'
    : d.unit === 'amount' ? '작년 같은 달 대비 증감률' : d.label
  // x 눈금을 index 로 4등분하면 달 간격이 어긋난다. CPI 는 결측이 한 달 있어서
  // 24.01 · 24.11 · 25.11 · 26.09 로 나왔다. 달력에서 1월·7월을 집는다.
  const ticks = pts.reduce((a, pt, i) =>
    (pt.t.endsWith('.01') || pt.t.endsWith('.07')) ? [...a, i] : a, [])
  const dir = index ? Math.sign(d.headline?.value || 0) : 0
  return (
    <div className="icard">
      <div className="ihead">
        <span className="iname">
          {d.label}
          {d.tip && <Info text={<>
            <p><b>뜻</b>{d.tip.term}</p>
            <p><b>의미</b>{d.tip.what}</p>
            <p><b>영향</b>{d.tip.effect}</p>
          </>} />}
        </span>
        <span className="iwhen">{d.month}{d.released && ` · ${d.released}`}</span>
      </div>
      {(d.band || d.tag) && (
        <div className="ihead2">
          <Band b={d.band} dec={dec} unit={unit} />
          {d.tag && <span className="itag">{d.tag}</span>}
        </div>
      )}
      <div className={`ibig${dir > 0 ? ' iup' : dir < 0 ? ' idown' : ''}`}>
        {amount(d.headline, index)}
      </div>
      <div className="isub">
        {index
          ? <span className="ipre">작년 같은 달 대비</span>
          : <Delta a={d.yoy} pre="작년보다" />}
        <Delta a={d.mom} pre="전월보다" />
      </div>
      {/* 색은 좋고 나쁨이 아니라 방향이다. 실업률이 내리면 좋지만 너무 낮으면
          금리 인상 우려가 되는 것처럼, 지표의 좋고 나쁨은 보는 쪽에 따라 다르다. */}
      <AxisChart pts={pts} baseline={baseline} baseName={baseName}
        color={dirColor(chg)} fmt={v => `${v.toFixed(dec)}${unit}`}
        headroom={1.6} xticks={ticks}
        label={`${d.label} ${d.chart.from}부터 ${d.chart.to}까지 추이`} />
      <p className="chartcap">{d.chart.from} ~ {d.chart.to} · {pts.length}개월</p>
      <p className="dayaxis">x축: 월 · y축: <b>{yLabel}({unit})</b> · 점선: {baseName}</p>
      {d.note && <p className="inote">{d.note}</p>}
      {/* 교과서에 나오는 방향이다. 지금 데이터에 대한 주장이 아니라서
          "오르면 보통" 이라고 머리를 달았다. */}
      {d.impact?.length > 0 && (
        <div className="iimpact">
          <span className="iimp-lbl">오르면 보통</span>
          {d.impact.map(x => (
            <span className="ichip" key={x.where}>
              {x.icon} <b>{x.where}</b> {x.text}
            </span>
          ))}
        </div>
      )}
      {/* 계산한 숫자만 보여주면 틀렸을 때 알 수가 없다. 원값을 남긴다. */}
      {d.raw != null && d.unit !== 'percent' && (
        <p className="iraw">
          {d.raw_name && `${d.raw_name} `}
          {d.raw.toLocaleString('ko-KR', { minimumFractionDigits: d.raw_decimals,
                                           maximumFractionDigits: d.raw_decimals })}
          {d.raw_unit}
        </p>
      )}
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

// 확정된 그날 종가 카드. 그래프는 위의 FxDay·FxTrend 가 맡는다.
function FxPair({ title, sub, rate, chg, main }) {
  const d = fxDir(chg)
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
    </div>
  )
}

function fxLine(rate, chg) {
  if (rate == null) return '-'
  const sign = chg > 0 ? '+' : ''
  return `${rate.toFixed(2)}원 ${chg != null ? `(${sign}${chg.toFixed(2)})` : ''}`
}

// 현재 시세의 '언제 기준인지'를 한 줄로.
//
// 값만 띄우면 거짓말이 된다. yfinance 는 야후 지연 시세이고, 쌍마다 신선도가
// 다르다 — 2026-10-31 실측으로 같은 순간에 받아도 달러는 32분 전, 유로는 396분
// 전 값이었다. 6시간 묵은 값을 '현재'라고 보여주지 않으려고 시각을 같이 쓴다.
function fxStamp(v) {
  const mt = v.market_time || ''
  if (!mt) return null
  const when = `${mt.slice(5, 10)} ${mt.slice(11, 16)} 기준`
  if (v.market_state !== 'REGULAR') return { text: `${when} · 장 마감`, warn: false }
  if (v.stale_min != null && v.stale_min > 30) return { text: `${when} · ${v.stale_min}분 전 값`, warn: true }
  return { text: when, warn: false }
}

// 오늘 하루 움직임 — 장 중 5분봉.
//
// 축을 반드시 적는다. 자동 스케일이라 보이는 구간의 최소~최대가 세로를 꽉 채우는데,
// 오늘처럼 0.06% 움직인 날도 그러면 산맥처럼 보인다. 그래서
//   · 시작가를 점선 기준선으로 그려서 '오른 쪽/내린 쪽'이 한눈에 보이게 하고
//   · 가로 눈금에 고가·시작가·저가의 실제 원화 값을 적고
//   · 두 축이 각각 무엇인지 그래프 아래에 쓴다
// 선 모양만으로는 "얼마나" 움직였는지 알 수 없다.
function AxisChart({ pts, baseline, baseName, color, label, fmt, headroom = 1, xticks }) {
  if (!pts || pts.length < 2) return null
  const W = 600, H = 172
  // padR 은 눈금 라벨("시작 1334.28")이 들어갈 자리다. 좁으면 글자가 잘린다.
  const padL = 8, padR = 100, padT = 14, padB = 26

  // 기준선이 항상 화면에 들어오게 범위에 포함시키고, 위아래로 여유를 둔다
  const vals = pts.map(x => x.rate)
  const high = Math.max(...vals), low = Math.min(...vals)
  let lo = Math.min(low, baseline), hi = Math.max(high, baseline)
  // headroom 은 위쪽만 더 띄우는 배수다. 아래위를 같이 늘리면 선이 납작해져서
  // 움직임이 안 보이는데, 꼭대기만 눌려 보일 때는 위쪽만 벌리면 된다.
  const room = (hi - lo) * 0.14 || 0.5
  lo -= room; hi += room * headroom
  const span = hi - lo || 1

  const px = i => padL + (i / (pts.length - 1)) * (W - padL - padR)
  const py = v => padT + (1 - (v - lo) / span) * (H - padT - padB)
  const line = pts.map((x, i) => `${px(i).toFixed(1)},${py(x.rate).toFixed(1)}`).join(' ')
  const base = (H - padB).toFixed(1)
  const area = `${px(0).toFixed(1)},${base} ${line} ${px(pts.length - 1).toFixed(1)},${base}`

  // 눈금은 임의의 값이 아니라 '읽을 가치가 있는 세 숫자'로 — 고·저·기준선.
  //
  // 겹침은 값이 아니라 픽셀로 판단해야 한다. 고 1334.51 / 시작 1334.28 은
  // 0.23원 차이지만 화면에서는 8px 밖에 안 떨어져서 글자가 겹친다.
  // 고·저를 먼저 남기고(그래프의 위아래 끝이라 눈금으로서 의미가 크다),
  // 기준선은 자리가 없으면 라벨을 접는다 — 점선과 아래 요약문에 이미 있다.
  const ticks = []
  for (const t of [{ v: high, name: '고' }, { v: low, name: '저' }, { v: baseline, name: baseName }]) {
    if (ticks.every(o => Math.abs(py(o.v) - py(t.v)) >= 15)) ticks.push(t)
  }

  // 기본은 index 를 4등분한 자리다. 달·분기처럼 달력으로 집어야 하는 자료는
  // 부르는 쪽이 ticks 로 넘긴다 — index 등분은 결측이 있으면 달 간격이 어긋난다.
  const last = pts.length - 1
  const xi = (xticks && xticks.length
    ? xticks
    : [0, Math.round(last / 3), Math.round(last * 2 / 3), last])
    .filter((v, i, a) => a.indexOf(v) === i && v >= 0 && v <= last)

  return (
    <svg className="daychart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label}>
      {/* 기준선 — 라벨이 겹쳐 접히더라도 선 자체는 항상 그린다.
          '오른 쪽인지 내린 쪽인지'를 한눈에 보여주는 것이 이 선의 일이다. */}
      <line x1={padL} y1={py(baseline)} x2={W - padR} y2={py(baseline)} className="gl open" />
      {ticks.map(t => (
        <g key={t.name}>
          {t.name !== baseName &&
            <line x1={padL} y1={py(t.v)} x2={W - padR} y2={py(t.v)} className="gl" />}
          <text x={W - padR + 7} y={py(t.v) + 4} className="axl">{t.name} {(fmt || (v => v.toFixed(2)))(t.v)}</text>
        </g>
      ))}
      <polygon points={area} fill={color} opacity="0.12" />
      <polyline points={line} fill="none" stroke={color} strokeWidth="2"
        vectorEffect="non-scaling-stroke" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={px(last)} cy={py(vals[last])} r="4" fill={color} stroke="#161a24" strokeWidth="1.5" />
      {xi.map((ix, i) => (
        <text key={ix} x={px(ix)} y={H - 8} className="axl"
          textAnchor={i === 0 ? 'start' : ix === last ? 'end' : 'middle'}>{pts[ix].t}</text>
      ))}
    </svg>
  )
}

// 환율은 좋/나쁨이 아니라 방향이다 — 오르면 원화 약세(노랑), 내리면 강세(파랑)
function dirColor(chg) {
  return chg > 0 ? '#fbbf24' : chg < 0 ? '#60a5fa' : '#8b93a1'
}

function FxDay({ d, name, unit }) {
  if (!d || !d.points || d.points.length < 2) return null
  const up = d.chg > 0
  return (
    <div className="daybox">
      <p className="daycap">
        <span><b>{name} 장중 움직임</b> · 5분마다 한 점</span>
        {/* 세션은 09:00 에 열려 다음날 02:00 에 닫히므로 자정을 넘어간다.
            창을 그대로 적어줘야 "09:00 ~ 01:55" 라는 시각 라벨이 안 헷갈린다. */}
        <span>{d.session}</span>
      </p>
      <AxisChart pts={d.points} baseline={d.open} baseName="개장" color={dirColor(d.chg)}
        fmt={v => `${v.toFixed(2)}원`}
        label={`${d.day} 장중 ${name} 움직임. 개장 ${d.open.toFixed(2)}원에서 ${d.last.toFixed(2)}원`} />
      <p className="daysum">
        {d.open_at || '09:00'} 개장 <b>{d.open.toFixed(2)}원</b> → <b>{d.last.toFixed(2)}원</b>
        <span className={`fxchg ${up ? 'up' : d.chg < 0 ? 'down' : ''}`}>
          {up ? '+' : ''}{d.chg.toFixed(2)}원{d.pct != null && ` (${up ? '+' : ''}${d.pct.toFixed(2)}%)`}
        </span>
        <br />이 장중 가장 높았을 때 {d.high.toFixed(2)}원 · 가장 낮았을 때 {d.low.toFixed(2)}원 · <b>변동폭 {d.span.toFixed(2)}원</b>
      </p>
      <p className="dayaxis">x축: 시각 · y축: {unit}(원) · 점선: 개장가</p>
    </div>
  )
}

// 최근 추이 — 하루에 점 하나. '요즘 오르는 추세인가'에 답한다.
// 오늘 그래프와 같은 엔진을 쓰고, 점선의 의미도 같다(구간 시작값).
function FxTrend({ series, name, unit }) {
  if (!series || series.length < 2) return null
  const asc = [...series].reverse()                       // API 는 최신순
  const pts = asc.map(x => ({ t: x.date.slice(5), rate: x.rate }))
  const base = pts[0].rate, last = pts[pts.length - 1].rate
  const chg = last - base
  const pct = base ? (chg / base) * 100 : null
  const vals = pts.map(x => x.rate)
  const up = chg > 0
  return (
    <div className="daybox">
      <p className="daycap">
        <span><b>{name} 최근 {pts.length}일</b> · 하루에 한 점(종가)</span>
        <span>{pts[0].t} ~ {pts[pts.length - 1].t}</span>
      </p>
      {/* baseName 은 짧게 — 눈금 라벨 자리가 93px 뿐이라 "15일 전 1340.84" 는 넘친다.
          점선이 무엇의 시작인지는 아래 설명문에 쓴다. */}
      <AxisChart pts={pts} baseline={base} baseName="시작" color={dirColor(chg)}
        fmt={v => `${v.toFixed(2)}원`}
        label={`${name} 최근 ${pts.length}일 추이. ${base.toFixed(2)}원에서 ${last.toFixed(2)}원`} />
      <p className="daysum">
        {pts.length}일 전 <b>{base.toFixed(2)}원</b> → 지금 <b>{last.toFixed(2)}원</b>
        <span className={`fxchg ${up ? 'up' : chg < 0 ? 'down' : ''}`}>
          {up ? '+' : ''}{chg.toFixed(2)}원{pct != null && ` (${up ? '+' : ''}${pct.toFixed(2)}%)`}
        </span>
        <br />이 기간 가장 높았을 때 {Math.max(...vals).toFixed(2)}원 · 가장 낮았을 때 {Math.min(...vals).toFixed(2)}원
      </p>
      <p className="dayaxis">x축: 날짜 · y축: {unit}(원) · 점선: {pts.length}일 전</p>
    </div>
  )
}

function FxNow({ live }) {
  const rows = [['USDKRW', '원/달러'], ['EURKRW', '원/유로']]
    .map(([k, label]) => [label, (live || {})[k]])
    .filter(([, v]) => v && v.rate != null)
  if (!rows.length) return null
  return (
    <div className="fxnow">
      <div className="fxnow-top">
        <span className="fxnow-t">지금 환율</span>
        <span className="fxnow-sub">야후 지연 시세 · 5분마다 갱신</span>
      </div>
      {rows.map(([label, v]) => {
        const st = fxStamp(v)
        return (
          <div className="fxnow-row" key={label}>
            <span className="fxnow-k">{label}</span>
            <span className="fxnow-v">{v.rate.toFixed(2)}<span className="won">원</span></span>
            {v.chg != null && <span className={`fxchg ${v.chg > 0 ? 'up' : v.chg < 0 ? 'down' : ''}`}>
              {v.chg > 0 ? '+' : ''}{v.chg.toFixed(2)}원{v.pct != null && ` (${v.pct > 0 ? '+' : ''}${v.pct.toFixed(2)}%)`}
            </span>}
            {st && <span className={`fxnow-when${st.warn ? ' warn' : ''}`}>{st.text}</span>}
          </div>
        )
      })}
      <p className="fxnow-note"><b>전일 종가 대비</b>입니다. 아래 <b>일자별 기록</b>은 장이 닫힌 뒤 확정된 종가예요 — 그래서 숫자가 다를 수 있습니다.</p>
    </div>
  )
}

function FxTab() {
  const [fx, setFx] = useState(null)
  const [sel, setSel] = useState(null)
  // 현재 시세가 5분마다 갱신되므로 화면도 주기적으로 다시 받아온다.
  // 새로고침을 눌러야 최신이 보이면 '실시간'이라고 할 수 없다.
  //
  // 폴링이 실패하면 화면을 비우지 않고 직전 값을 그대로 둔다. 네트워크가
  // 한 번 끊겼다고 보던 내용이 사라지면 고장으로 보인다.
  useEffect(() => {
    let alive = true
    const load = () => fetch(`${API}/api/fx`).then(r => r.json())
      .then(d => { if (alive) setFx(d) })
      .catch(() => { if (alive) setFx(prev => prev || { days: [], series: {}, live: {}, intraday: {} }) })
    load()
    const id = setInterval(load, 60000)
    return () => { alive = false; clearInterval(id) }
  }, [])
  if (!fx) return <div className="panel"><p className="lead">불러오는 중…</p></div>
  const days = fx.days || []
  const t = days[0]
  // 오늘 그래프가 보여주는 날짜 (서버 판정). 해설 날짜와 비교하는 데 쓴다.
  const liveDay = ((fx.intraday || {}).USDKRW || {}).day
  const past = days.slice(1)
  return (
    <div className="panel">
      <p className="lead">💱 <b>원/달러·원/유로 환율과 그 의미.</b> 환율은 한쪽만 좋은 게 아니라 <b>양면적</b>이에요 — 누구에게 유리하고 누구에게 불리한지 함께 봅니다.</p>
      {/* ── 지금 · 오늘 ───────────────────────────────────────────
          실시간을 붙이면서 한 화면에 시간대가 셋이 됐다(지금 / 오늘 / 확정된 하루).
          구역을 나누지 않으면 오늘 그래프 바로 아래 어제 숫자가 붙어서
          AI 가 틀린 것처럼 보인다. AI 해설은 15:40 에 쓰이므로 매일
          00:00~15:40 사이에는 실제로 하루 어긋나 있다. */}
      <div className="label">지금 · 장중</div>
      <FxNow live={fx.live} />
      <FxDay d={(fx.intraday || {}).USDKRW} name="원/달러" unit="1달러를 사는 데 드는 원화" />
      <FxDay d={(fx.intraday || {}).EURKRW} name="원/유로" unit="1유로를 사는 데 드는 원화" />
      <FxTrend series={(fx.series || {}).USDKRW} name="원/달러" unit="1달러를 사는 데 드는 원화" />

      <div className="seg" />

      {/* ── 확정된 하루 ─────────────────────────────────────────── */}
      {!t && <p className="lead">아직 환율 분석이 없습니다.</p>}
      {t && <>
        <div className="label">{t.date} ({dowOf(t.date)}) 하루</div>
        <p className="segnote">장이 닫힌 뒤 <b>확정된 값</b>이에요. 위쪽 <b>지금·오늘</b>과 숫자가 다를 수 있습니다.</p>
        <FxPair title="원/달러" sub="USD · 한국 경제에 가장 큰 영향" rate={t.usdkrw} chg={t.usdkrw_chg} main />
        <FxPair title="원/유로" sub="EUR · 보조 지표" rate={t.eurkrw} chg={t.eurkrw_chg} />
        <div className="sec-h">💬 {t.date} 환율 분석 (AI)</div>
        <div className="ai">{t.ai_summary}</div>
        {/* 그래프가 보여주는 날과 해설이 쓰인 날을 비교한다. 둘 다 서버가 준 값이라
            브라우저 시간대에 영향받지 않는다. */}
        {liveDay && liveDay !== t.date &&
          <p className="segnote">※ <b>{liveDay}</b> 분석은 한국장 마감 뒤(15:40)에 올라옵니다.
            확정된 종가로 분석해야 숫자가 바뀌지 않기 때문이에요.</p>}
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
        <div className="sec-h">💬 {sel.date} 환율 분석 (AI)</div>
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
        <button className={`tab${tab === 'market' ? ' active' : ''}`} onClick={() => setTab('market')}>📈 경제지표</button>
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
  .wrap { max-width:1120px; margin:0 auto; padding:0 18px 60px; }
/* 종목별 탭만 두 칼럼이라 넓다. 나머지 탭은 840px 그대로 보이게 묶어둔다 —
   .wrap 을 넓히면 헤더·탭바도 같이 넓어지는데, 탭마다 폭이 바뀌면 탭을
   누를 때 레이아웃이 튄다. 그래서 틀은 늘 1120px, 내용만 탭별로 정한다. */
.panel { max-width:840px; margin:0 auto; }
.panel.wide { max-width:none; }
  header { padding:24px 0 10px; }
  header h1 { margin:0; font-size:1.4rem; }
  header p { margin:5px 0 0; color:#8b93a1; font-size:.85rem; }
  .tabs { position:sticky; top:0; background:#0f1117; display:flex; gap:4px; border-bottom:1px solid #262c3a; z-index:10; padding-top:4px; }
  .tab { flex:1; background:none; border:none; color:#8b93a1; font:inherit; font-size:.82rem; font-weight:600; padding:13px 6px; cursor:pointer; border-bottom:2px solid transparent; border-radius:8px 8px 0 0; margin-bottom:-1px; white-space:nowrap; }
  /* 클릭한 뒤 브라우저 기본 포커스 테두리가 남으면 네모 박스처럼 보인다.
     키보드로 온 경우(:focus-visible)에만 테두리를 남긴다. */
  .tab:focus { outline:none; }
  .tab:focus-visible { outline:2px solid #4ade80; outline-offset:-3px; }
  @media (max-width:520px) { .tab { font-size:.7rem; padding:11px 2px; } }
  .tab:hover { color:#e6e8eb; }
  .tab.active { color:#4ade80; border-bottom-color:#4ade80; background:#151a26; }
  .panel { padding-top:16px; }
  .lead { color:#8b93a1; font-size:.84rem; margin:0 0 14px; line-height:1.5; }
  .label { font-size:.72rem; text-transform:uppercase; letter-spacing:.08em; color:#9ca3af; font-weight:700; margin:18px 0 10px; }
  .up { color:#4ade80; } .down { color:#f87171; }

  .chips { display:flex; gap:8px; overflow-x:auto; padding-bottom:6px; }
  .chip { flex:0 0 auto; background:#1a1e29; border:1px solid #262c3a; border-radius:10px; padding:9px 13px; cursor:pointer; font:inherit; color:#8b93a1; text-align:center; min-width:76px; }
  .chip:hover { border-color:#3a4358; color:#e6e8eb; }
  .chip.on { border-color:#1c4a2b; background:#12351f; color:#4ade80; }
  .ct { font-weight:700; font-size:.85rem; } .cn { font-size:.66rem; opacity:.85; margin-top:1px; }
  .cohead { display:flex; align-items:baseline; justify-content:space-between; gap:10px; margin:16px 0 4px; flex-wrap:wrap; }
  .coname { font-size:1.1rem; font-weight:700; } .coprice { font-weight:700; font-variant-numeric:tabular-nums; }

  .pickbox.err { border-color:#5b2a2f; background:#1d1316; }
  .pickbox.err .pickbox-t { color:#f87171; }
  .spin { display:inline-block; width:11px; height:11px; margin-right:7px; vertical-align:-1px;
          border:2px solid #2f6b45; border-top-color:#4ade80; border-radius:50%;
          animation:spin 0.8s linear infinite; }
  @keyframes spin { to { transform:rotate(360deg); } }
  @media (prefers-reduced-motion: reduce) { .spin { animation-duration:3s; } }

  .empty { background:#161b26; border:1px solid #262c3a; border-radius:13px; padding:16px; }
  .empty .lead { margin:0 0 4px; }
  .empty-h { font-size:.82rem; color:#8b93a1; margin:12px 0 8px; }

  .m-warn { margin:10px 0 2px; padding:9px 12px; border-radius:8px; font-size:.8rem; line-height:1.55;
            color:#d9c48a; background:#2a2415; border:1px solid #4a3f1d; }
  .livetag { display:inline-block; font-size:.68rem; color:#4ade80; background:#12351f; border-radius:20px; padding:2px 9px; margin-left:7px; vertical-align:1px; }

  /* 카드 겉면 기업 뱃지 · 범위 안내 · 접기 */
  .impbadges { display:flex; align-items:center; gap:6px; flex-wrap:wrap; margin-top:10px; }
  .impbadges-h { font-size:.78rem; opacity:.7; }
  .impbadge { font-size:.72rem; padding:3px 9px; border-radius:20px; background:#212734; color:#9aa4b2; white-space:nowrap; }
  .impbadge.pos { background:#12351f; color:#4ade80; }
  .impbadge.neg { background:#3a1518; color:#f87171; }
  .impbadge .est { font-style:normal; font-size:.62rem; opacity:.7; margin-left:4px; padding-left:5px; border-left:1px solid currentColor; }
  .aorig { font-size:.74rem; color:#9ca3af; margin-top:5px; line-height:1.4; }
  .m-orig { font-size:.78rem; color:#9ca3af; margin-top:3px; line-height:1.45; }
  .art.thin { padding:12px 14px; }
  .art.thin .atitle { font-size:.9rem; font-weight:600; }
  .foldbtn { width:100%; text-align:left; background:none; border:none; border-top:1px solid #262c3a; color:#8b93a1; font:inherit; font-size:.82rem; padding:12px 2px; margin-top:14px; cursor:pointer; }
  .foldbtn:hover { color:#e6e8eb; }
  .imp-kind { font-size:.76rem; color:#9ca3af; margin:10px 0 7px; }
  .imp-kind i { font-style:normal; color:#8b7a3a; }

  /* 기사 검색 — AI 선별 카드와 기업별 영향 */
  .pickcard { margin-bottom:14px; }
  .pickbox { background:#161b26; border:1px dashed #2f3646; border-radius:13px; padding:15px 16px; margin-bottom:14px; }
  .pickbox-t { font-size:.86rem; color:#8b93a1; margin-bottom:10px; }
  .search-btn.wide { width:100%; padding:13px; }
  .search-btn .dim { opacity:.7; font-weight:400; }
  .thinking { font-size:.9rem; color:#4ade80; line-height:1.5; }
  .thinking-sub { font-size:.78rem; color:#9ca3af; margin-top:5px; }
  .imps { display:flex; flex-direction:column; gap:9px; }
  .imp { background:#12151d; border:1px solid #262c3a; border-radius:11px; padding:11px 13px; }
  .imp-top { display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-bottom:6px; }
  .imp-tk { font-size:.66rem; color:#8b93a1; background:#212734; padding:2px 7px; border-radius:5px; font-variant-numeric:tabular-nums; }
  .imp-why { font-size:.84rem; color:#9aa4b2; line-height:1.55; }
  .imp-all { margin-top:9px; font-size:.8rem; color:#8b93a1; line-height:1.5; }
  .imp-none { font-size:.84rem; color:#9ca3af; line-height:1.55; }

  /* 기사 검색 */
  .search { margin:6px 0 18px; }
  .search-row { display:flex; gap:8px; }
  .search-in { flex:1; min-width:0; background:#12151d; border:1px solid #262c3a; border-radius:11px; padding:12px 14px; font:inherit; font-size:.95rem; color:#e6e8eb; }
  .search-in::placeholder { color:#5b6372; }
  .search-in:focus { outline:none; border-color:#2f6b45; }
  .search-btn { flex:0 0 auto; background:#12351f; border:1px solid #1c4a2b; color:#4ade80; border-radius:11px; padding:12px 18px; font:inherit; font-weight:700; cursor:pointer; }
  .search-btn:hover:not(:disabled) { background:#174227; }
  .search-btn:disabled { opacity:.55; cursor:default; }
  .search-clear { flex:0 0 auto; background:#1a1e29; border:1px solid #262c3a; color:#8b93a1; border-radius:11px; padding:12px 14px; font:inherit; cursor:pointer; }
  .search-clear:hover { border-color:#3a4358; color:#e6e8eb; }
  .search-chips { display:flex; gap:7px; flex-wrap:wrap; margin-top:9px; }
  .search-chips .chip { min-width:0; padding:6px 12px; font-size:.8rem; }
  .search-res { margin-top:15px; }
  .search-head { font-size:.84rem; color:#8b93a1; margin-bottom:9px; line-height:1.5; }
  .search-exp { color:#9ca3af; }
  .search-exp b { color:#8b93a1; font-weight:600; }
  .hit { background:#1d2a3d; color:#8fb4e8; font-size:.68rem; padding:2px 8px; border-radius:20px; }
  .asrc { margin-left:auto; color:#9ca3af; }
  a.art { text-decoration:none; }

  .scroll { display:flex; flex-direction:column; gap:10px; max-height:460px; overflow-y:auto; padding-right:4px; }
  .scroll::-webkit-scrollbar { width:8px; } .scroll::-webkit-scrollbar-thumb { background:#2f3646; border-radius:4px; }

  .day, .art { display:block; width:100%; text-align:left; font:inherit; color:inherit; cursor:pointer; background:#1a1e29; border:1px solid #262c3a; border-radius:13px; padding:15px 16px; }
  .day:hover, .art:hover { border-color:#3a4358; }
  .day.today, .art.today { border-color:#1c4a2b; background:linear-gradient(180deg,#16241b 0%,#1a1e29 60%); }
  .day-top, .atop { display:flex; align-items:center; gap:8px; font-size:.78rem; color:#8b93a1; margin-bottom:9px; font-variant-numeric:tabular-nums; }
  .badge { background:#4ade80; color:#06210f; font-weight:800; font-size:.64rem; padding:2px 7px; border-radius:5px; }
  .day-metrics { display:flex; gap:16px; flex-wrap:wrap; align-items:baseline; }
  .metric .v { font-weight:700; font-variant-numeric:tabular-nums; } .metric .v.big { font-size:1.05rem; }
  .metric .k { font-size:.68rem; color:#9ca3af; display:block; }
  .flow { font-size:.72rem; padding:2px 8px; border-radius:20px; background:#212734; color:#9aa4b2; }
  .flow.buy { background:#12351f; color:#4ade80; } .flow.sell { background:#3a1518; color:#f87171; }
  .day-sum { margin-top:10px; font-size:.78rem; color:#8b93a1; line-height:1.45; }
  .day-foot { margin-top:9px; font-size:.74rem; color:#9ca3af; display:flex; justify-content:space-between; }
  .arrow { color:#4ade80; }
  .atitle { font-size:.98rem; font-weight:650; line-height:1.45; }
  .sent { font-size:.68rem; padding:2px 8px; border-radius:20px; background:#212734; color:#9aa4b2; }
  .sent.pos { background:#12351f; color:#4ade80; } .sent.neg { background:#3a1518; color:#f87171; }

  .fxcard { background:#1a1e29; border:1px solid #262c3a; border-radius:13px; padding:15px 16px 10px; margin-bottom:12px; }
  .fxcard.main { border-color:#2b3a55; background:linear-gradient(180deg,#161d2b 0%,#1a1e29 60%); }
  .fxhead { display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap; }
  .fxname { font-size:1rem; font-weight:700; } .fxsub { font-size:.7rem; color:#9ca3af; }
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

  /* 지금 환율 — 확정 종가 카드와 구별되게 테두리를 파랗게 */
  .fxnow { background:linear-gradient(180deg,#131b2a 0%,#161a24 70%); border:1px solid #2b3a55;
           border-radius:13px; padding:13px 16px 11px; margin:4px 0 2px; }
  .fxnow-top { display:flex; align-items:baseline; justify-content:space-between; gap:10px;
               flex-wrap:wrap; margin-bottom:7px; }
  .fxnow-t { font-size:.78rem; font-weight:700; letter-spacing:.04em; color:#93c5fd; }
  .fxnow-sub { font-size:.68rem; color:#9ca3af; }
  .fxnow-row { display:flex; align-items:baseline; gap:9px; flex-wrap:wrap; padding:5px 0; }
  .fxnow-k { font-size:.72rem; color:#9ca3af; min-width:52px; }
  .fxnow-v { font-size:1.22rem; font-weight:700; font-variant-numeric:tabular-nums; }
  .fxnow-v .won { font-size:.8rem; font-weight:600; color:#8b93a1; margin-left:2px; }
  .fxnow-when { font-size:.68rem; color:#9ca3af; margin-left:auto; white-space:nowrap; }
  .fxnow-when.warn { color:#fbbf24; }
  .fxnow-note { font-size:.72rem; color:#9ca3af; line-height:1.55; margin:8px 0 0; }
  .fxnow-note b { color:#8b93a1; }

  /* 오늘 움직임 그래프 */
  .daybox { background:#161a24; border:1px solid #262c3a; border-radius:12px;
            padding:12px 14px 10px; margin:10px 0 2px; }
  .daycap { font-size:.72rem; color:#9ca3af; margin:0 0 6px;
            display:flex; justify-content:space-between; gap:10px; flex-wrap:wrap; }
  .daycap b { color:#c4cad4; }
  .daychart { width:100%; height:auto; display:block; }
  .daychart .gl { stroke:#262c3a; stroke-width:1; }
  .daychart .gl.open { stroke:#4b5563; stroke-dasharray:4 4; }   /* 시작가 기준선 */
  .daychart .axl { font-size:12px; fill:#9ca3af; font-variant-numeric:tabular-nums; }
  .daysum { font-size:.78rem; color:#8b93a1; line-height:1.75; margin:8px 0 0;
            font-variant-numeric:tabular-nums; }
  .daysum b { color:#e6e8eb; }
  /* 축 설명이 캡션보다 덜 중요할 이유가 없다. #4b5563 은 대비 2.2:1 로
     작은 글자 기준(4.5:1)의 절반도 안 됐다. .chartcap 과 같게 맞춘다. */
  .dayaxis { font-size:.72rem; color:#9ca3af; line-height:1.55; margin:7px 0 0; }

  /* 시간대가 다른 구역을 눈으로 가른다 — 위는 '지금·오늘', 아래는 '확정된 하루' */
  .seg { height:1px; margin:26px 0 2px;
         background:linear-gradient(90deg,transparent,#2b3a55 18%,#2b3a55 82%,transparent); }
  .segnote { font-size:.74rem; color:#9ca3af; line-height:1.6; margin:0 0 10px; }
  .segnote b { color:#8b93a1; }

  .chartbox { background:#161a24; border:1px solid #262c3a; border-radius:12px; padding:12px 14px 8px; margin:14px 0 4px; }
  .chartcap { font-size:.72rem; color:#9ca3af; margin:0 0 8px; }

  /* 한 줄에 하나씩 쌓는다. 2단으로 깔면 카드가 400px 쯤 되고, AxisChart 의
     viewBox 가 600 이라 12px 눈금 글자가 8px 로 줄어 안 읽힌다. */
  .igrid { display:grid; gap:14px; }
  .icard { background:#1a1e29; border:1px solid #262c3a; border-radius:12px; padding:16px; min-width:0; }
  .ihead { display:flex; justify-content:space-between; align-items:baseline; gap:10px; flex-wrap:wrap; }
  .iname { font-size:.9rem; font-weight:700; color:#e6e8eb; display:flex; align-items:center; }
  .iwhen { font-size:.72rem; color:#9ca3af; font-variant-numeric:tabular-nums; }
  .ibig { font-size:1.9rem; font-weight:700; margin-top:10px; letter-spacing:-.02em;
          font-variant-numeric:tabular-nums; }
  .isub { font-size:.76rem; color:#8b93a1; margin:4px 0 12px; font-variant-numeric:tabular-nums;
          display:flex; flex-wrap:wrap; align-items:center; gap:3px 14px; }
  .idelta { display:inline-flex; align-items:center; gap:4px; font-weight:600; }
  .ipre { color:#9ca3af; font-weight:400; }
  .clabel { font-size:.8rem; font-weight:700; color:#c9ced8; margin:18px 0 9px; }
  .ihead2 { display:flex; flex-wrap:wrap; align-items:center; gap:7px 10px; margin-top:10px; }
  .ibadge { display:inline-flex; align-items:center; gap:5px; font-size:.72rem; font-weight:700;
            padding:3px 9px; border-radius:999px; white-space:nowrap; }
  .ibrange { font-weight:400; opacity:.75; font-variant-numeric:tabular-nums; }
  .b-high { background:#2a1a1e; color:#f87171; border:1px solid #4a2630; }
  .b-low { background:#16212e; color:#60a5fa; border:1px solid #27405c; }
  .b-mid { background:#1e222b; color:#9ca3af; border:1px solid #333a4a; }
  .itag { font-size:.84rem; font-weight:600; color:#e6e8eb; }
  .iimpact { border-top:1px solid #262c3a; margin-top:11px; padding-top:9px;
             display:flex; flex-wrap:wrap; align-items:center; gap:6px 8px; }
  .iimp-lbl { font-size:.72rem; color:#9ca3af; font-weight:600; }
  .ichip { display:inline-flex; align-items:center; gap:5px; font-size:.74rem; color:#8b93a1;
           background:#161a24; border:1px solid #262c3a; border-radius:8px; padding:4px 8px; }
  .ichip b { color:#c9ced8; font-weight:600; }
  .iup { color:#f87171; }
  .idown { color:#60a5fa; }
  .icard .chartcap { margin:6px 0 0; }
  .inote { font-size:.82rem; color:#c9ced8; margin:6px 0 0; }
  .iraw { font-size:.72rem; color:#9ca3af; margin:4px 0 0; font-variant-numeric:tabular-nums; }
  .info { margin-left:6px; background:none; color:#9ca3af; font-size:.75rem; cursor:pointer; border:1px solid #4b5563; border-radius:50%; width:17px; height:17px; padding:0; line-height:1; }
  .tip { position:absolute; background:#0f1117; border:1px solid #4ade80; border-radius:8px; padding:10px 12px; font-size:.75rem; color:#cbd5e1; max-width:300px; margin-top:4px; z-index:5; line-height:1.6; }
  .tip p { margin:0 0 7px; }
  .tip p:last-child { margin:0; }
  .tip b { color:#4ade80; font-weight:700; margin-right:6px; }

  .modal-bg { position:fixed; inset:0; background:rgba(3,5,10,.72); display:flex; align-items:center; justify-content:center; padding:18px; z-index:50; }
  .modal { background:#1a1e29; border:1px solid #2f3646; border-radius:16px; padding:24px; max-width:540px; width:100%; max-height:86vh; overflow-y:auto; position:relative; }
  .mx { position:absolute; top:13px; right:15px; background:none; border:none; color:#8b93a1; font-size:1.5rem; cursor:pointer; line-height:1; }
  .mx:hover { color:#e6e8eb; }
  .m-date { font-size:.76rem; color:#4ade80; font-variant-numeric:tabular-nums; margin-bottom:6px; }
  .m-title { font-size:1.15rem; font-weight:700; margin:0 26px 6px 0; line-height:1.35; }
  .m-sub { font-size:.74rem; color:#9ca3af; margin-bottom:14px; }
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

/* ── 종목 시세 카드 ───────────────────────────────── */
.qcard { background:#161a24; border:1px solid #262c3a; border-radius:14px; padding:16px 16px 14px; margin:14px 0 4px; }
.qhead { display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:10px; }
.qtk { font-size:1.02rem; font-weight:700; color:#e6e8eb; letter-spacing:.02em; }
.qnm { font-size:.82rem; color:#8b93a1; margin-left:8px; }
.qstate { flex:0 0 auto; font-size:.7rem; font-weight:700; padding:4px 9px; border-radius:999px;
          background:#1f2430; color:#8b93a1; border:1px solid #2b3240; }
.qstate.on { background:#12351f; color:#4ade80; border-color:#1c4a2b; }
.qprice { display:flex; align-items:baseline; gap:10px; flex-wrap:wrap; }
.qnow { font-size:1.9rem; font-weight:700; color:#e6e8eb; font-variant-numeric:tabular-nums; }
.qchg { font-size:.92rem; font-weight:600; font-variant-numeric:tabular-nums; }
.qwhen { font-size:.72rem; color:#9ca3af; line-height:1.6; margin-top:6px; }
.qext { font-size:.76rem; color:#8b93a1; margin-top:7px; padding-top:7px; border-top:1px dashed #2b3240; }
.qgrid { display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin-top:14px;
         padding-top:13px; border-top:1px solid #222836; }
@media (max-width:560px) { .qgrid { grid-template-columns:repeat(2,1fr); } }

/* 52주 범위 막대 — 숫자 두 개보다 위치 하나가 빨리 읽힌다 */
.w52 { margin-top:16px; }
.w52-top, .w52-bot { display:flex; justify-content:space-between; font-size:.68rem; color:#9ca3af; }
.w52-bot { margin-top:5px; font-variant-numeric:tabular-nums; }
.w52-cur { color:#e6e8eb; font-weight:600; }
.w52-bar { position:relative; height:6px; margin-top:5px; border-radius:999px;
           background:linear-gradient(90deg,#1f3a4d,#2b3a55,#3a2b2b); }
.w52-dot { position:absolute; top:50%; width:11px; height:11px; margin-left:-5.5px;
           transform:translateY(-50%); border-radius:50%; background:#e6e8eb; border:2px solid #161a24; }

/* 브리핑 상태 상자 (없음 / 만드는 중 / 실패) */
.segbox { background:#161a24; border:1px solid #262c3a; border-radius:12px; padding:14px; margin:4px 0 10px; }
.segbox .search-btn { margin-top:4px; }
.segnote.dim { color:#565e6b; }
.qgrid .metric .sub { display:block; font-size:.66rem; color:#9ca3af; margin-top:2px; }

/* ── 두 칼럼 ───────────────────────────────────────── */
.cols { display:flex; gap:20px; align-items:flex-start; }
/* min-width:0 이 없으면 flex 항목이 내용 너비 밑으로 안 줄어들어 가로 스크롤이 생긴다 */
.cols > .main { flex:1 1 660px; min-width:0; }
.cols > .side { flex:0 0 384px; }
@media (max-width:980px) {
  .cols { flex-direction:column; }
  .cols > .main, .cols > .side { flex:none; width:100%; }
  /* 좁은 화면에서는 고르는 쪽이 먼저 */
  .cols > .side { order:-1; }
}

/* ── 업종 패널 ─────────────────────────────────────── */
.tpanel { background:#141821; border:1px solid #222836; border-radius:14px; padding:14px 14px 12px; }
.tpanel .label { margin-top:0; }
.tmkt { font-size:.66rem; font-weight:700; color:#565e6b; letter-spacing:.06em; margin:9px 0 5px; }
.tchips { display:flex; flex-wrap:wrap; gap:6px; margin:0 0 8px; }
.tchips .chip { padding:5px 10px; font-size:.76rem; }
.thead { display:flex; align-items:baseline; justify-content:space-between; gap:8px;
         padding-top:10px; border-top:1px solid #222836; }
.tname { font-size:.92rem; font-weight:700; color:#e6e8eb; }
.tdate { font-size:.68rem; color:#9ca3af; font-variant-numeric:tabular-nums; }
.tindex { display:flex; align-items:baseline; gap:8px; margin-top:9px; padding:8px 10px;
          background:#1a1f2b; border-radius:8px; }
.tix-n { flex:1 1 auto; font-size:.74rem; color:#8b93a1; }
.tix-v { font-size:.86rem; font-weight:600; color:#e6e8eb; font-variant-numeric:tabular-nums; }
.tix-p { font-size:.76rem; font-weight:600; font-variant-numeric:tabular-nums; }
.tstat { margin-top:11px; }
.tshape { font-size:.82rem; font-weight:600; color:#e6e8eb; }
.ttally { font-size:.72rem; color:#8b93a1; margin-top:3px; font-variant-numeric:tabular-nums; }
.todd { font-size:.72rem; color:#fbbf24; line-height:1.55; margin-top:7px;
        padding:7px 9px; background:#2a2310; border-radius:7px; }
.trows { display:flex; flex-direction:column; gap:3px; margin:12px 0 8px; }
.trow { display:flex; align-items:baseline; gap:7px; width:100%; padding:7px 8px;
        background:transparent; border:1px solid transparent; border-radius:7px;
        cursor:pointer; font:inherit; text-align:left; }
.trow:hover { background:#1a1f2b; border-color:#2b3240; }
.trow.on { background:#12351f; border-color:#1c4a2b; }
.tr-tk { flex:0 0 46px; font-size:.72rem; font-weight:700; color:#8b93a1; }
.tr-nm { flex:1 1 auto; font-size:.76rem; color:#e6e8eb; overflow:hidden;
         text-overflow:ellipsis; white-space:nowrap; }
.tr-pr { font-size:.76rem; color:#8b93a1; font-variant-numeric:tabular-nums; }
/* 그 줄만 거래일이 다를 때 — 지금은 미국 상장만 넣어서 안 나오지만,
   나중에 휴장일이 다른 시장을 넣으면 화면이 조용히 거짓말하는 것을 막는다 */
.tr-old { font-size:.64rem; color:#fbbf24; }
.tr-u { font-size:.64rem; color:#9ca3af; }
.tr-pc { flex:0 0 58px; text-align:right; font-size:.76rem; font-weight:600;
         font-variant-numeric:tabular-nums; }
.dayhead { display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:6px; }
.daylabel { font-size:.78rem; font-weight:600; color:#8b93a1; font-variant-numeric:tabular-nums; }
`

export default App
