# Company Valuation Tools

미국(NYSE/NASDAQ 등) · 한국(KRX) 상장사 기업가치를 에이전트 툴로 조회하는 스켈레톤입니다.

## 구성

| 툴 | 역할 |
|----|------|
| `resolve_company` | 회사명/티커 → US/KR 식별자 |
| `get_company_valuation` | 시총, EV, 주가, PER/PBR 등 |
| `get_company_fundamentals` | 매출·영업이익·자산/부채 등 |

### 데이터 소스

- **미국**: [Financial Modeling Prep](https://site.financialmodelingprep.com/)
- **한국 시세/시총**: KRX (`pykrx` / FinanceDataReader)
- **한국 재무/공시**: [OpenDART](https://opendart.fss.or.kr/)

## 설치

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# .env 에 FMP_API_KEY, OPENDART_API_KEY 입력
```

## CLI

```bash
python -m company_valuation.cli schemas
python -m company_valuation.cli resolve AAPL
python -m company_valuation.cli resolve 삼성전자
python -m company_valuation.cli valuation AAPL
python -m company_valuation.cli valuation 005930 --market KR
python -m company_valuation.cli fundamentals 삼성전자 --market KR
```

## Python

```python
from company_valuation import resolve_company, get_company_valuation

print(resolve_company("Apple"))
print(get_company_valuation(query="005930", market="KR"))
```

에이전트 function calling용 JSON 스키마는 `company_valuation.tools.TOOL_SCHEMAS`에 있습니다.

## 참고

- OpenDART는 시가총액을 제공하지 않습니다. 한국 시총은 KRX 경로를 사용합니다.
- 한국 EV는 `시총 + 이자부채(추정) − 현금`으로 계산하며, `notes`에 근거를 남깁니다.
- API 키 없이 라우팅/스키마 단위 테스트는 가능합니다: `pytest -q`
