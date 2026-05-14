# tests/check_pykrx.py
from pykrx.stock.market.core import MKD30040

date = "20260424"

print("=== KRX 원본 응답 컬럼명 확인 ===")
df = MKD30040().fetch(date, date, "005930")
print(f"컬럼명: {df.columns.tolist()}")
print(f"전체 데이터:\n{df.head()}")