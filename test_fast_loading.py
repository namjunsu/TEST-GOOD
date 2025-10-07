#!/usr/bin/env python3
"""
Test the fast loading function directly
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.absolute()
sys.path.insert(0, str(project_root))

# Import and test
from web_interface import load_documents
import time

print("🧪 Testing fast loading function...")

start_time = time.time()
df = load_documents(None)
end_time = time.time()

print(f"⏱️ Loading time: {end_time - start_time:.2f} seconds")
print(f"📊 Loaded {len(df)} documents")

if not df.empty:
    print("\n✅ Sample documents:")
    for i, row in df.head(3).iterrows():
        print(f"  - {row['filename']} ({row['category']}) - 기안자: {row['drafter']}")

print("\n🎉 Fast loading test completed!")