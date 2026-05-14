# tests/test_krx_mcp.py
import asyncio
import pytest
from fastmcp import Client

@pytest.mark.asyncio
async def test_krx_server():
    async with Client("src/mcp_servers/krx_market/server.py") as client:

        print("\n=== 삼성전자 주가 조회 ===")
        result = await client.call_tool(
            "get_stock_price",
            {"ticker": "005930", "days": 5}
        )
        data = result.data
        if "error" in data:
            print(f"❌ 실패: {data['error']}")
        else:
            print(f"✅ 종목명: {data['name']}")
            print(f"✅ 최근 종가: {data['latest_close']:,}원")
            print(f"✅ 등락률: {data['change_pct']}%")
            print(f"✅ 날짜: {data['latest_date']}")

        print("\n=== 삼성전자 수급 조회 ===")
        result = await client.call_tool(
            "get_investor_trends",
            {"ticker": "005930", "days": 30}
        )
        data = result.data
        if "error" in data:
            print(f"❌ 실패: {data['error']}")

        else:
            print(f"✅ 데이터 수: {data['count']}건")
            latest = data['data'][0]
            print(f"✅ 최근 종가: {latest['close']:,}원")
            print(f"✅ 외국인 순매수: {latest['foreign_net']:,}주")
            print(f"✅ 기관 순매수: {latest['institution_net']:,}주")


        print("\n=== 삼성전자 증권사 리포트 ===")
        result = await client.call_tool(
            "get_analyst_reports",
            {"ticker": "005930", "days": 90}
        )
        data = result.data
        if "error" in data:
            print(f"❌ 실패: {data['error']}")
        else:
            print(f"✅ 리포트 수: {data['count']}건")
            for r in data['reports'][:3]:
                print(f"  {r['date']} | {r['opinion']} | TP:{r['target_price']:,} | {r['title'][:30]}")

                

if __name__ == "__main__":
    asyncio.run(test_krx_server())