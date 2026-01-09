#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.year_utils import safe_year_to_int

test_values = ["2022", "2018", "", None, "연도없음", 2022]

print("year_utils.safe_year_to_int() 테스트:")
for val in test_values:
    result = safe_year_to_int(val)
    print(f"  {repr(val):20} → {result}")
