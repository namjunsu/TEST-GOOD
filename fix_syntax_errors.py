#!/usr/bin/env python3
import ast
import sys

try:
    with open('perfect_rag.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Try to compile to check for syntax errors
    compile(content, 'perfect_rag.py', 'exec')
    print("✅ No syntax errors found!")
    
except SyntaxError as e:
    print(f"❌ Syntax error at line {e.lineno}: {e.msg}")
    print(f"   Text: {e.text}")
    print(f"   Offset: {' ' * (e.offset - 1) if e.offset else ''}^")
    
    # Try to provide context
    lines = content.split('\n')
    if e.lineno:
        start = max(0, e.lineno - 3)
        end = min(len(lines), e.lineno + 2)
        print("\nContext:")
        for i in range(start, end):
            marker = ">>> " if i == e.lineno - 1 else "    "
            print(f"{marker}{i+1:4}: {lines[i]}")
    sys.exit(1)

except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)
