# backend/scripts

한 번 쓰고 끝났거나, 사람이 필요할 때만 손으로 돌리는 스크립트.
배치(systemd)와 API 서버는 여기 있는 파일을 부르지 않는다.

지우지 않고 모아둔 이유 — 데이터를 어떻게 고쳤는지가 여기 남아 있다.
같은 문제가 다시 생기면 이걸 보고 고친다.

실행은 `backend/` 에서:

```bash
cd ~/School-Project/backend
.venv/bin/python scripts/uptime_stats.py 30
```

각 파일 맨 위에서 `backend/` 로 이동하고 거기 있는 모듈을 불러오므로,
`econ.db` 는 언제나 `backend/econ.db` 를 쓴다.

⚠️ `setup_db.py` 는 `prices`·`indicators` 테이블을 **지우고** 새로 만든다.
운영 DB 에서 돌리면 시세와 지표가 전부 사라진다. 처음 설치할 때만 쓴다.

| 파일 | 하는 일 | 지금 쓰는가 |
|---|---|---|
| uptime_stats.py | 아침 점검 통과율·문제 있던 날 (읽기만) | 발표 수치 낼 때 |
| check_groq.py | Groq 키·모델 이름 확인 | 모델 바꿀 때 |
| setup_db.py | prices·indicators 테이블 새로 만들기 | 처음 설치 때만 |
| add_news.py | news 테이블 만들기 (이 테이블을 만드는 코드는 여기뿐) | 처음 설치 때만 |
| backfill_kr.py | 한국 수출·수입·콜금리 처음 적재 (FRED) | 끝남 — collect 가 매일 받는다 |
| fx_backfill.py | 환율 해설 과거치 | 끝남 — `fx_curate.py --backfill` 로 흡수 |
| migrate_daily.py | daily 의 분석을 article_analysis 로 옮기기 | 끝남 |
| redo_daily.py | 지난 추천 기사에 기업별 영향 다시 만들기 | 끝남 |
| redo_titleonly.py | 제목만으로 분석된 기사 다시 분석 | 끝남 |
| clean_impacts.py | 저장된 기업별 영향에 이름 정리 규칙 다시 적용 (LLM 없이) | 규칙 고칠 때 |
| refresh_company_sentiment.py | company_daily 요약·뉴스 감정 다시 채우기 | 끝남 |
