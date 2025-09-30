#!/usr/bin/env python3
import re

with open('perfect_rag.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Fix empty except blocks
for i in range(len(lines) - 1):
    if lines[i].strip().startswith('except') and lines[i].strip().endswith(':'):
        # Check if next non-empty line is not indented properly
        next_line_idx = i + 1
        while next_line_idx < len(lines) and lines[next_line_idx].strip() == '':
            next_line_idx += 1
        
        if next_line_idx < len(lines):
            next_line = lines[next_line_idx]
            # Check indentation
            current_indent = len(lines[i]) - len(lines[i].lstrip())
            next_indent = len(next_line) - len(next_line.lstrip())
            
            # If next line has same or less indentation, add pass
            if next_indent <= current_indent and next_line.strip():
                # Insert pass statement
                pass_indent = ' ' * (current_indent + 4)
                lines[i] = lines[i].rstrip() + '\n' + pass_indent + 'pass\n'

# Write back
with open('perfect_rag.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("✅ Fixed empty except blocks")
