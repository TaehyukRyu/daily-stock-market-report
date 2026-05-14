import asyncio
import pytest
from fastmcp import Client

@pytest.mark.asyncio
async def test_us_market_server():
    async with Client("src/mcp_servers/us_market/server.py") as client:

        # Tool 1: 미국 개별 종목
        print("=== NVIDIA 주가 조회 ===")
        result = await client.call_tool("get_us_stock", {"symbol": "NVDA"})
        print(result.content[0].text)

        # Tool 2: S&P500
        print("\n=== S&P500 조회 ===")
        result = await client.call_tool("get_sp500_data", {"days": 10})
        print(result.content[0].text)

        # Tool 3: 국채 수익률
        print("\n=== 미국 국채 수익률 조회 ===")
        result = await client.call_tool("get_treasury_yields", {})
        print(result.content[0].text)

        # Tool 4: VIX
        print("\n=== VIX 공포지수 조회 ===")
        result = await client.call_tool("get_vix", {})
        print(result.content[0].text)

        # Tool 5: 원자재
        print("\n=== 원자재 가격 조회 ===")
        result = await client.call_tool("get_commodity_prices", {})
        print(result.content[0].text)

if __name__ == "__main__":
    asyncio.run(test_us_market_server())