import pytest
from src.agents.base_agent import create_structured_agent
from langchain_core.messages import HumanMessage, SystemMessage


@pytest.mark.asyncio
async def test_structured_output():
    agent = create_structured_agent()

    messages = [
        SystemMessage(content="당신은 주식 시장 분석 ai 입니다. agent_name은 'test_agent'로 설정하세요."),
        HumanMessage(content="KOSPI 지수가 2500포인트입니다. 시장을 분석해주세요."),
    ]

    result = await agent.ainvoke(messages)

    assert result is not None
    assert result.recommendation in {"BUY", "SELL", "HOLD"}
    assert 0.0 <= result.confidence <= 1.0
    print(result)


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_structured_output())