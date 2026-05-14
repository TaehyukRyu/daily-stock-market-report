import asyncio
from src.agents.quant_analyst import run_quant_analyst

async def test():
    report = await run_quant_analyst()
    print('recommendation:', report.recommendation)
    print('confidence:', report.confidence)
    print('selection_rationale:', report.selection_rationale)
    for i, r in enumerate(report.reasoning, 1):
        print(f'  {i}. {r}')

asyncio.run(test())