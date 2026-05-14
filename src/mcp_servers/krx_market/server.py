import os
import requests as _requests

from fastmcp import FastMCP
from pykrx import stock
from datetime import datetime, timedelta
import pandas as pd
from dotenv import load_dotenv

load_dotenv()  # ← 이 줄 추가


mcp = FastMCP("krx-market")


def get_recent_trading_date() -> str:
    """ 가장 최근 거래일 날짜를 YYYYMMDD 형식으로 반환 """

    today = datetime.now()

    if today.weekday == 5:
        today -= timedelta(days=1)

    elif today.weekday == 6:
        today -= timedelta(days=2)

    return today.strftime("%Y%m%d")



@mcp.tool()
def get_stock_price(ticker: str, days: int = 30) -> dict:
    """
    특정 종목의 최근 주가 데이터를 가져옵니다.

    Args:
        ticker: 종목 코드 (예:"005930" = 삼성전자)
        days: 조회할 기간 (기본값: 30일)

    Returns:
        종목명, 최근 종가, OHLCV 데이터
    """

    try:
        end_date = get_recent_trading_date()
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

        # OHLCV 데이터 수집
        df = stock.get_market_ohlcv(start_date, end_date, ticker)

        if df.empty:
            return {"error": f"ticker {ticker}에 대한 데이터가 없습니다."}

        # 종목명 조회
        ticker_name = stock.get_market_ticker_name(ticker)

        # 최근 종가
        latest = df.iloc[-1]


        return {
            "ticker": ticker,
            "name": ticker_name,
            "latest_close": int(latest["종가"]),
            "latest_volume": int(latest["거래량"]),
            "latest_date": df.index[-1].strftime("%Y-%m-%d"),
            "change_pct": round(float(latest["등락률"]), 2),
            "ohlcv": {k.strftime("%Y-%m-%d"): v for k, v in df.to_dict(orient="index").items()},
        }


    except Exception as e:
        return {"error": str(e)}



@mcp.tool()
def get_investor_trends(ticker: str, days: int = 10) -> dict:
    """외국인/기관 수급 데이터 조회 (네이버 증권 크롤링)"""
    try:
        import requests
        from bs4 import BeautifulSoup

        headers = {"User-Agent": "Mozilla/5.0"}
        url = f"https://finance.naver.com/item/main.naver?code={ticker}"
        resp = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")

        tables = soup.find_all("table")
        if len(tables) < 4:
            return {"error": "테이블 구조 변경됨"}

        table = tables[3]
        rows = table.find_all("tr")

        records = []
        for row in rows:
            cells = row.find_all("td")
            if not cells:
                continue
            texts = [c.get_text(strip=True) for c in cells]
            texts = [t for t in texts if t]

            # 첫 번째 셀이 종가(숫자+콤마)인 행만 처리
            if len(texts) >= 4:
                try:
                    close = int(texts[0].replace(",", ""))
                    foreign_net = int(texts[2].replace("+", "").replace(",", ""))
                    institution_net = int(texts[3].replace("+", "").replace(",", ""))
                    records.append({
                        "close": close,
                        "foreign_net": foreign_net,
                        "institution_net": institution_net,
                    })
                except ValueError:
                    continue

            if len(records) >= days:
                break

        return {"ticker": ticker, "count": len(records), "data": records}

    except Exception as e:
        return {"error": str(e)}





@mcp.tool()
def get_market_cap_ranking(market: str = "KOSPI", top_n: int = 10) -> dict:
    """
    시가총액 상위 종목 목록을 가져옵니다.
    
    Args:
        market: 시장 구분 ('KOSPI' 또는 'KOSDAQ')
        top_n: 상위 몇 개 (기본값: 10)
    
    Returns:
        시총 상위 종목 리스트
    """
    try:
        date = get_recent_trading_date()

        df = stock.get_market_cap_by_ticker(date, market=market)
        print(f"실제 컬럼명: {df.columns.tolist()}")  # ← 이 줄 추가
        df = df.sort_values("시가총액", ascending=False).head(top_n)
        
        result = []
        for ticker, row in df.iterrows():
            result.append({
                "ticker": ticker,
                "name": stock.get_market_ticker_name(ticker),
                "market_cap": int(row["시가총액"]),
                "close": int(row["종가"]),
            })
        
        return {
            "market": market,
            "date": date,
            "ranking": result,
        }
    except Exception as e:
        return {"error": str(e)}




@mcp.tool()
def get_analyst_reports(ticker: str, days: int = 90) -> dict:
    """증권사 리포트 목록 조회 (한경컨센서스 크롤링)"""
    try:
        import requests
        from bs4 import BeautifulSoup
        from datetime import datetime, timedelta

        headers = {"User-Agent": "Mozilla/5.0"}
        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        # 종목명 조회 (ticker → 검색어)
        ticker_name = stock.get_market_ticker_name(ticker)

        url = "https://consensus.hankyung.com/analysis/list"
        params = {
            "sdate": start,
            "edate": end,
            "report_type": "CO",
            "search_text": ticker_name,
            "pagenum": 20,
            "now_page": 1,
        }

        resp = requests.get(url, params=params, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        rows = soup.select("table tbody tr")

        reports = []
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 4:
                continue
            date = cols[0].get_text(strip=True)
            title = cols[1].get_text(strip=True)
            target_price = cols[2].get_text(strip=True)
            opinion = cols[3].get_text(strip=True)

            # 목표주가 숫자 변환
            try:
                tp = int(target_price.replace(",", "")) if target_price else None
            except ValueError:
                tp = None

            reports.append({
                "date": date,
                "title": title[:50],
                "target_price": tp,
                "opinion": opinion,
            })

        return {
            "ticker": ticker,
            "name": ticker_name,
            "count": len(reports),
            "reports": reports,
        }

    except Exception as e:
        return {"error": str(e)}





@mcp.tool()
def get_financials(ticker: str) -> dict:
    """
    종목의 PER/PBR/EPS/배당수익률을 조회합니다.
    pykrx get_market_fundamental() 사용 — API 키 불필요

    Args:
        ticker: 종목 코드 (예: "005930")

    Returns:
        PER, PBR, EPS, DPS, 배당수익률 (최근 거래일 기준)
    """
    try:
        date = get_recent_trading_date()
        # 최근 5거래일 조회 후 가장 최근 유효 데이터 사용
        start_date = (datetime.now() - timedelta(days=10)).strftime("%Y%m%d")

        df = stock.get_market_fundamental(start_date, date, ticker)

        if df.empty:
            return {"error": f"{ticker} 펀더멘털 데이터 없음"}

        # 마지막 유효 행
        latest = df.iloc[-1]
        ticker_name = stock.get_market_ticker_name(ticker)

        return {
            "ticker":       ticker,
            "name":         ticker_name,
            "date":         df.index[-1].strftime("%Y-%m-%d"),
            "per":          round(float(latest["PER"]), 2),
            "pbr":          round(float(latest["PBR"]), 2),
            "eps":          int(latest["EPS"]),
            "bps":          int(latest["BPS"]),
            "dps":          int(latest["DPS"]),
            "div_yield":    round(float(latest["DIV"]), 2),
        }

    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_consensus_estimates(ticker: str) -> dict:
    """
    종목의 실적 컨센서스(매출/영업이익/EPS 추정치)를 조회합니다.
    한경컨센서스 크롤링 — get_analyst_reports와 동일 소스

    Args:
        ticker: 종목 코드 (예: "005930")

    Returns:
        연간/분기 실적 추정치 + 컨센서스 방향 (상향/하향/유지)
    """
    try:
        import requests
        from bs4 import BeautifulSoup

        ticker_name = stock.get_market_ticker_name(ticker)
        headers = {"User-Agent": "Mozilla/5.0"}

        url = "https://consensus.hankyung.com/apps.analysis/analysis.list"
        params = {
            "report_type": "CO",
            "search_text": ticker_name,
            "pagenum": 5,
            "now_page": 1,
        }

        resp = requests.get(url, params=params, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        rows = soup.select("table tbody tr")

        # 목표주가 추이로 상향/하향 판단
        target_prices = []
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 3:
                continue
            tp_text = cols[2].get_text(strip=True).replace(",", "")
            try:
                tp = int(tp_text)
                if tp > 0:
                    target_prices.append(tp)
            except ValueError:
                continue

        # 컨센서스 방향: 최근 3건 평균 vs 이전 3건 평균
        revision_direction = "데이터 부족"
        if len(target_prices) >= 6:
            recent_avg = sum(target_prices[:3]) / 3
            prev_avg   = sum(target_prices[3:6]) / 3
            if recent_avg > prev_avg * 1.02:
                revision_direction = "상향"
            elif recent_avg < prev_avg * 0.98:
                revision_direction = "하향"
            else:
                revision_direction = "유지"
        elif len(target_prices) >= 2:
            if target_prices[0] > target_prices[-1]:
                revision_direction = "상향"
            elif target_prices[0] < target_prices[-1]:
                revision_direction = "하향"
            else:
                revision_direction = "유지"

        return {
            "ticker":               ticker,
            "name":                 ticker_name,
            "revision_direction":   revision_direction,
            "latest_tp":            target_prices[0] if target_prices else None,
            "tp_history":           target_prices[:10],
            "sample_count":         len(target_prices),
        }

    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_dart_disclosure(ticker: str, days: int = 30) -> dict:
    """
    DART OpenAPI로 기업 주요 공시를 조회합니다.
    자사주 매입, 유상증자, CB/BW 발행 등 주가 영향 공시 포함

    Args:
        ticker: 종목 코드 (예: "005930")
        days: 조회 기간 (기본 30일)

    Returns:
        최근 공시 목록 (날짜/제목/공시유형)
    """
    import os
    import requests

    dart_api_key = os.getenv("DART_API_KEY")
    if not dart_api_key:
        return {"error": "DART_API_KEY가 설정되지 않았습니다."}

    try:
        end_date   = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

        resp = requests.get(
            "https://opendart.fss.or.kr/api/list.json",
            params={
                "crtfc_key": dart_api_key,
                "stock_code": ticker,
                "bgn_de":    start_date,
                "end_de":    end_date,
                "page_count": 20,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != "000":
            return {
                "ticker": ticker,
                "disclosures": [],
                "count": 0,
                "note": f"DART 응답: {data.get('message', '데이터 없음')}",
            }

        # 주가 영향 공시만 필터링
        IMPORTANT_KEYWORDS = [
            "자기주식", "유상증자", "전환사채", "신주인수권",
            "합병", "분할", "최대주주", "대표이사", "영업정지",
        ]

        all_items = data.get("list", [])
        disclosures = []

        for item in all_items:
            title = item.get("report_nm", "")
            is_important = any(kw in title for kw in IMPORTANT_KEYWORDS)
            disclosures.append({
                "date":         item.get("rcept_dt", ""),
                "title":        title,
                "corp_name":    item.get("corp_name", ""),
                "is_important": is_important,
            })

        # 중요 공시 먼저 정렬
        disclosures.sort(key=lambda x: x["is_important"], reverse=True)

        return {
            "ticker":       ticker,
            "count":        len(disclosures),
            "disclosures":  disclosures[:15],
        }

    except Exception as e:
        return {"error": str(e)}



# ─────────────────────────────────────────────────────────────
# [v5.2 신규] 공통 유틸 — DART ticker → corp_code 변환
# ─────────────────────────────────────────────────────────────
import requests as _requests  # 이미 import된 경우 생략

def _get_corp_code(ticker: str) -> str | None:
    """
    종목코드(6자리) → DART 고유번호(8자리) 변환.
    DART corpCode.xml (전체 기업 목록 zip)을 받아서 stock_code로 검색.
    삼성전자(005930) → 00126380
    """
    import zipfile, io, xml.etree.ElementTree as ET

    api_key = os.getenv("DART_API_KEY")
    if not api_key:
        return None
    try:
        resp = _requests.get(
            "https://opendart.fss.or.kr/api/corpCode.xml",
            params={"crtfc_key": api_key},
            timeout=30,
        )
        with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
            with z.open("CORPCODE.xml") as f:
                root = ET.parse(f).getroot()
                for item in root.findall("list"):
                    if item.findtext("stock_code", "").strip() == ticker:
                        return item.findtext("corp_code", "").strip()
    except Exception as e:
        print(f"[_get_corp_code 오류] {type(e).__name__}: {e}")
    return None


# ─────────────────────────────────────────────────────────────
# [v5.2 신규] Tool: 배당 정보
# ─────────────────────────────────────────────────────────────

@mcp.tool()
def get_dividend_info(ticker: str) -> dict:
    """
    종목 배당 정보 조회 (DPS, 배당수익률).
    pykrx get_market_fundamental_by_ticker에서 DIV/DPS 컬럼 추출.
    KOSPI 조회 후 없으면 KOSDAQ 재시도.
    """
    from datetime import datetime, timedelta

    # 최근 영업일 기준으로 조회 (오늘이 휴장일일 수 있어 3일 전부터 시도)
    for days_back in range(0, 10):
        date = (datetime.now() - timedelta(days=days_back)).strftime("%Y%m%d")
        for market in ("KOSPI", "KOSDAQ"):
            try:
                df = stock.get_market_fundamental_by_ticker(date, market=market)
                if df.empty or ticker not in df.index:
                    continue
                row = df.loc[ticker]
                # pykrx 컬럼: BPS, PER, PBR, EPS, DIV(배당수익률%), DPS(주당배당금)
                dps = int(row.get("DPS", 0))
                div_yield = round(float(row.get("DIV", 0.0)), 2)
                if dps > 0 or div_yield > 0:
                    return {
                        "ticker": ticker,
                        "market": market,
                        "dps": dps,            # 주당배당금 (원)
                        "dividend_yield": div_yield,  # 배당수익률 (%)
                        "base_date": date,
                        "note": "DPS·DIV는 직전 사업연도 결산 기준 (한국 기업 대부분 12월 결산)",
                    }
            except Exception:
                continue

    return {
        "ticker": ticker,
        "dps": 0,
        "dividend_yield": 0.0,
        "note": "배당 데이터 없음 (무배당 종목이거나 데이터 조회 실패)",
    }


# ─────────────────────────────────────────────────────────────
# [v5.2 신규] Tool: 52주 신고가·신저가
# ─────────────────────────────────────────────────────────────

@mcp.tool()
def get_52week_range(ticker: str) -> dict:
    """
    52주 신고가·신저가 조회.
    pykrx get_market_ohlcv_by_date로 최근 380일 가져온 뒤
    마지막 252 거래일(≈1년) 윈도우에서 max/min 계산.
    """
    from datetime import datetime, timedelta

    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=380)).strftime("%Y%m%d")

    try:
        df = stock.get_market_ohlcv_by_date(start, end, ticker)
        if df.empty:
            return {"error": f"{ticker} 가격 데이터 없음"}

        df = df.tail(252)  # 최근 252 거래일
        high_52w = int(df["고가"].max())
        low_52w  = int(df["저가"].min())
        current  = int(df["종가"].iloc[-1])

        # 현재가가 신고가·신저가 대비 몇 % 위치인지
        pct_from_high = round((current - high_52w) / high_52w * 100, 1)  # 음수 = 고점 대비 하락
        pct_from_low  = round((current - low_52w)  / low_52w  * 100, 1)  # 양수 = 저점 대비 상승

        # 신고가/신저가 돌파 여부 (당일 종가 기준)
        is_52w_high = current >= high_52w
        is_52w_low  = current <= low_52w

        return {
            "ticker": ticker,
            "current": current,
            "high_52w": high_52w,
            "low_52w": low_52w,
            "pct_from_high": pct_from_high,   # 예: -5.2 → 신고가 대비 5.2% 아래
            "pct_from_low": pct_from_low,     # 예: +38.4 → 신저가 대비 38.4% 위
            "is_52w_high": is_52w_high,       # 신고가 돌파 여부
            "is_52w_low": is_52w_low,         # 신저가 갱신 여부
            "base_date": str(df.index[-1].date()),
            "window_days": len(df),
        }
    except Exception as e:
        return {"error": str(e)}


# ─────────────────────────────────────────────────────────────
# [v5.2 신규] Tool: 주주 구성 변화
# ─────────────────────────────────────────────────────────────

@mcp.tool()
def get_shareholder_changes(ticker: str, days: int = 90) -> dict:
    """
    주주 구성 변화 조회.
    - 5% 이상 대량보유 변동 공시 (DART majorstock 엔드포인트)
    대상 기간: 최근 days일 (기본 90일)
    """
    from datetime import datetime, timedelta

    api_key = os.getenv("DART_API_KEY")
    corp_code = _get_corp_code(ticker)
    if not corp_code:
        return {"error": f"{ticker} — DART 고유번호 조회 실패 (DART에 미등록 종목일 수 있음)"}

    end_de = datetime.now().strftime("%Y%m%d")
    bgn_de = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

    try:
        resp = _requests.get(
            "https://opendart.fss.or.kr/api/majorstock.json",
            params={
                "crtfc_key": api_key,
                "corp_code": corp_code,
                "bgn_de": bgn_de,
                "end_de": end_de,
            },
            timeout=10,
        )
        data = resp.json()
    except Exception as e:
        return {"error": str(e)}

    if data.get("status") not in ("000", "013"):  # 013 = 조회 결과 없음
        return {"error": f"DART API 오류: {data.get('message', '')}"}

    items = data.get("list", [])
    return {
        "ticker": ticker,
        "corp_code": corp_code,
        "period": f"{bgn_de}~{end_de}",
        "count": len(items),
        "holdings": [
            {
                "date": item.get("rcept_dt", ""),
                "holder": item.get("stkhldr_nm", ""),
                "shares": item.get("stkqy", ""),
                "ratio": item.get("stkrt", ""),
                "change_reason": item.get("change_reason", ""),
            }
            for item in items[:20]
        ],
    }


# ─────────────────────────────────────────────────────────────
# [v5.2 신규] Tool: CB·BW 공시
# ─────────────────────────────────────────────────────────────

@mcp.tool()
def get_convertible_bonds(ticker: str, days: int = 180) -> dict:
    """
    전환사채(CB)·신주인수권부사채(BW) 발행·전환 공시 조회.
    DART list 엔드포인트 — pblntf_detail_ty C001(CB), C002(BW).
    """
    from datetime import datetime, timedelta

    api_key = os.getenv("DART_API_KEY")
    corp_code = _get_corp_code(ticker)
    if not corp_code:
        return {"error": f"{ticker} — DART 고유번호 조회 실패"}

    bgn_de = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
    end_de = datetime.now().strftime("%Y%m%d")

    results = []
    type_map = {"C001": "CB(전환사채)", "C002": "BW(신주인수권부사채)"}

    for code, label in type_map.items():
        try:
            resp = _requests.get(
                "https://opendart.fss.or.kr/api/list.json",
                params={
                    "crtfc_key": api_key,
                    "corp_code": corp_code,
                    "bgn_de": bgn_de,
                    "end_de": end_de,
                    "pblntf_detail_ty": code,
                    "page_count": 10,
                },
                timeout=10,
            )
            data = resp.json()
            for item in data.get("list", []):
                results.append({
                    "type": label,
                    "date": item.get("rcept_dt", ""),
                    "title": item.get("report_nm", ""),
                    "rcept_no": item.get("rcept_no", ""),
                    "dart_url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={item.get('rcept_no', '')}",
                })
        except Exception:
            continue

    results.sort(key=lambda x: x["date"], reverse=True)
    return {
        "ticker": ticker,
        "period": f"{bgn_de}~{end_de}",
        "count": len(results),
        "items": results[:20],
        "signal": "⚠️ CB·BW 발행은 주식 희석 우려 → 주가 하락 압력 신호" if results else "이상 없음",
    }


# ─────────────────────────────────────────────────────────────
# [v5.2 신규] Tool: IPO·유상증자 이벤트
# ─────────────────────────────────────────────────────────────

@mcp.tool()
def get_equity_events(ticker: str, days: int = 180) -> dict:
    """
    유상증자 결정 공시 조회.
    DART list 엔드포인트 — pblntf_detail_ty C006(유상증자결정).
    향후 일정: days 이후 예정 건도 포함 (DART 공시 기준).
    """
    from datetime import datetime, timedelta

    api_key = os.getenv("DART_API_KEY")
    corp_code = _get_corp_code(ticker)
    if not corp_code:
        return {"error": f"{ticker} — DART 고유번호 조회 실패"}

    bgn_de = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
    end_de = datetime.now().strftime("%Y%m%d")

    try:
        resp = _requests.get(
            "https://opendart.fss.or.kr/api/list.json",
            params={
                "crtfc_key": api_key,
                "corp_code": corp_code,
                "bgn_de": bgn_de,
                "end_de": end_de,
                "pblntf_detail_ty": "C006",
                "page_count": 10,
            },
            timeout=10,
        )
        data = resp.json()
    except Exception as e:
        return {"error": str(e)}

    items = data.get("list", [])
    return {
        "ticker": ticker,
        "period": f"{bgn_de}~{end_de}",
        "count": len(items),
        "equity_events": [
            {
                "type": "유상증자",
                "date": item.get("rcept_dt", ""),
                "title": item.get("report_nm", ""),
                "rcept_no": item.get("rcept_no", ""),
                "dart_url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={item.get('rcept_no', '')}",
            }
            for item in items
        ],
        "signal": "⚠️ 유상증자는 주식 희석 → 단기 주가 하락 압력 신호" if items else "이상 없음",
    }


# ─────────────────────────────────────────────────────────────────
# [v5.3 신규] Tool: 실적 발표 캘린더
# ─────────────────────────────────────────────────────────────────

@mcp.tool()
def get_earnings_calendar(days_ahead: int = 14, market: str = "KOSPI") -> dict:
    """
    향후 실적 발표 예정 캘린더 조회.

    데이터 소스: DART API 정기보고서 제출 마감일 기준
    - 사업보고서 (연간): 12월 결산법인 → 3월 말 제출
    - 반기보고서 (6개월): 8월 말 제출
    - 분기보고서 (1분기/3분기): 5월 말 / 11월 말 제출

    DART 공시 일정이 아닌 '제출 마감일 기반 추정'입니다.
    정확한 발표일은 기업별로 다를 수 있습니다.

    Args:
        days_ahead: 앞으로 며칠 이내 실적 발표 (기본 14일)
        market: 시장 구분 (KOSPI / KOSDAQ, 기본 KOSPI)

    Returns:
        upcoming_deadlines: days_ahead일 이내 정기보고서 제출 마감일
        recent_disclosures: DART에서 최근 제출된 실적 관련 공시 (상위 20건)
    """
    from datetime import date, timedelta

    api_key = os.getenv("DART_API_KEY")
    today = date.today()
    cutoff = today + timedelta(days=days_ahead)

    # ── 정기보고서 제출 마감일 (12월 결산법인 기준) ─────────────────
    # 실제 마감일은 DART가 매년 공표하지만, 관례적 기준으로 산출
    year = today.year

    REPORT_DEADLINES = {
        f"{year}-03-31": f"{year-1}년 사업보고서 제출 마감 (12월 결산법인)",
        f"{year}-05-15": f"{year} 1분기 보고서 제출 마감",
        f"{year}-08-14": f"{year} 반기보고서 제출 마감",
        f"{year}-11-14": f"{year} 3분기 보고서 제출 마감",
        f"{year+1}-03-31": f"{year}년 사업보고서 제출 마감 (12월 결산법인)",
    }

    upcoming_deadlines = [
        {"date": d, "description": desc, "days_until": (date.fromisoformat(d) - today).days}
        for d, desc in REPORT_DEADLINES.items()
        if today <= date.fromisoformat(d) <= cutoff
    ]

    # ── DART 최근 실적 공시 (사업/반기/분기 보고서) ─────────────────
    recent_disclosures = []
    if api_key:
        try:
            end_de   = today.strftime("%Y%m%d")
            start_de = (today - timedelta(days=7)).strftime("%Y%m%d")  # 최근 7일

            resp = _requests.get(
                "https://opendart.fss.or.kr/api/list.json",
                params={
                    "crtfc_key":       api_key,
                    "bgn_de":          start_de,
                    "end_de":          end_de,
                    "pblntf_ty":       "A",        # A = 정기공시
                    "corp_cls":        "Y" if market == "KOSPI" else "K",
                    "page_count":      20,
                    "sort":            "date",
                    "sort_mth":        "desc",
                },
                timeout=10,
            )
            data = resp.json()

            # 실적 관련 보고서 필터
            EARNING_KEYWORDS = ["사업보고서", "반기보고서", "분기보고서"]
            for item in data.get("list", []):
                title = item.get("report_nm", "")
                if any(kw in title for kw in EARNING_KEYWORDS):
                    recent_disclosures.append({
                        "date":      item.get("rcept_dt", ""),
                        "corp_name": item.get("corp_name", ""),
                        "title":     title,
                        "dart_url":  f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={item.get('rcept_no', '')}",
                    })

        except Exception as e:
            recent_disclosures = [{"error": str(e)}]

    return {
        "market": market,
        "days_ahead": days_ahead,
        "upcoming_deadlines": upcoming_deadlines,
        "recent_disclosures": recent_disclosures[:20],
        "note": (
            "제출 마감일은 12월 결산법인 관례 기준 추정치입니다. "
            "실제 실적 발표일은 기업마다 다릅니다. "
            "정확한 일정은 DART(dart.fss.or.kr) 확인 권장."
        ),
    }


if __name__ == "__main__":
    mcp.run()