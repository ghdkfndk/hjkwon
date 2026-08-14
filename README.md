# 📊 종목 분석기

티커만 입력하면 주가·PER·실적·투자 스코어를 한눈에 볼 수 있는 분석 도구입니다.

## 설치 (Mac)

```bash
# Python 설치
brew install python3

# 코드 다운로드
git clone https://github.com/ghdkfndk/hjkwon.git
cd hjkwon

# 의존성 설치
pip3 install flask yfinance matplotlib
```

## 실행

```bash
python3 app.py
```

실행하면 자동으로 브라우저가 열립니다.

## 기능

### 🔍 종목 분석기 (웹 앱)
- 아무 티커나 입력하면 즉시 분석
- 투자 스코어 (0~100점, A~F 등급)
- 주가·PER 추이, 분기별 매출/순이익/이익률 차트
- 성장률 기반 고평가 이유 분석

### 📧 매일 자동 리포트
| 시각 | 내용 |
|---|---|
| 오전 9시 | 결론 + 스코어 요약 이메일 |
| 오후 10시 | 전체 상세 리포트 이메일 + GitHub Issue |

### 분석 항목
- **밸류에이션**: PER, Forward PER, PBR, PEG
- **성장성**: 매출/이익 성장률, 이익률
- **안정성**: 일간 변동성
- **52주 위치**: 현재가의 52주 최고/최저 대비 위치
- **뉴스 감성**: 증시 뉴스 키워드 기반 긍정/부정/중립 판정
- **Motley Fool**: 종목별 투자 분석 기사 (한국어 번역)
