# 증권사 리포트 분석기

국내 증권사 리포트 PDF를 업로드하면 종목·투자의견·목표주가·투자근거를 자동 추출하고, Buy Signal Score 랭킹과 투자근거 클러스터링을 제공하는 Streamlit 대시보드입니다.

## 빠른 시작

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 기능

| 탭 | 설명 |
|---|---|
| PDF Upload | PDF 여러 개 업로드 → 자동 파싱·저장 |
| Extracted Reports | 전체 리포트 목록 (필터링 지원) |
| Buy Stocks | Buy Signal Score 랭킹 + 투자의견 분포 |
| Thesis Clusters | TF-IDF + KMeans 투자근거 클러스터링 |
| Company Detail | 종목별 목표주가 추이·증권사별 의견 |

## Buy Signal Score 산식

```
score = buy_count + tp_up_count + firm_count + avg_upside_score
        - hold_sell_count - tp_down_count
```

- `avg_upside_score` = `min(평균 업사이드% / 10, 10)`

## 스택

- **UI**: Streamlit
- **PDF 파싱**: PyMuPDF (fitz)
- **저장소**: DuckDB
- **데이터**: pandas
- **클러스터링**: scikit-learn (TF-IDF + KMeans)
- **시각화**: Plotly

## LLM 교체 포인트

`src/extractor.py`의 `extract_report_data()` 함수 본문만 LLM 기반 구현으로 교체하면 나머지 파이프라인은 그대로 작동합니다. 반환 딕셔너리 스키마만 유지하면 됩니다.

```python
# src/extractor.py
def extract_report_data(pdf_data: dict) -> dict:
    # 여기를 Claude / GPT-4o 호출로 교체
    ...
```

## 파일 구조

```
securities-analyzer/
├── app.py                        # Streamlit 진입점
├── requirements.txt
├── data/
│   ├── uploads/                  # 업로드된 PDF 저장
│   └── securities.duckdb         # 자동 생성 DB
└── src/
    ├── pdf_parser.py             # PyMuPDF 텍스트 추출
    ├── extractor.py              # 정규식 필드 추출 (LLM 교체 포인트)
    ├── rating_normalizer.py      # Buy/Hold/Sell 정규화
    ├── database.py               # DuckDB CRUD
    ├── scoring.py                # Buy Signal Score 계산
    ├── clustering.py             # TF-IDF + KMeans 클러스터링
    └── dashboard_components.py   # Streamlit 탭별 컴포넌트
```
