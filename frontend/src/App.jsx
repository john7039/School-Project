import { useState, useEffect } from 'react'

function App() {
  const [prices, setPrices] = useState([])
  const [indicators, setIndicators] = useState([])

  useEffect(() => {
    fetch('http://100.121.62.50:8000/api/prices')
      .then(res => res.json())
      .then(data => setPrices(data))
    fetch('http://100.121.62.50:8000/api/indicators')
      .then(res => res.json())
      .then(data => setIndicators(data))
  }, [])

  return (
    <div style={{ padding: 40, fontFamily: 'sans-serif' }}>
      <h1>경제 지표 · 주가 대시보드</h1>
      <h2>주가 (AAPL)</h2>
      <ul>
        {prices.map(p => (
          <li key={p.id}>{p.date} — 종가 {p.close}</li>
        ))}
      </ul>
      <h2>CPI 지표</h2>
      <ul>
        {indicators.map(i => (
          <li key={i.id}>{i.date} — {i.value}</li>
        ))}
      </ul>
    </div>
  )
}

export default App
