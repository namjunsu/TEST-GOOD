#!/usr/bin/env python3
"""
Convert DOT file to HTML-based graph visualization.
Alternative to graphviz when dot binary is not available.
"""

import re
from pathlib import Path

def dot_to_html_svg(dot_file: str, output_file: str):
    """Convert DOT file to HTML with embedded SVG-like visualization."""

    # Parse DOT file
    with open(dot_file, 'r') as f:
        dot_content = f.read()

    # Extract nodes and edges
    nodes = set()
    edges = []
    entry_nodes = set()

    # Find entry nodes (highlighted in green)
    for match in re.finditer(r'"([^"]+)"\s*\[.*fillcolor=lightgreen.*\]', dot_content):
        entry_nodes.add(match.group(1))
        nodes.add(match.group(1))

    # Find all edges
    for match in re.finditer(r'"([^"]+)"\s*->\s*"([^"]+)"', dot_content):
        source, target = match.groups()
        nodes.add(source)
        nodes.add(target)
        edges.append((source, target))

    # Create HTML with embedded visualization
    html_content = """<!DOCTYPE html>
<html>
<head>
    <title>Module Dependency Graph</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        h1 { color: #333; }
        .graph-container {
            border: 1px solid #ccc;
            padding: 20px;
            background: #f9f9f9;
            overflow: auto;
        }
        .stats {
            background: #fff;
            padding: 15px;
            margin: 20px 0;
            border-left: 4px solid #4CAF50;
        }
        .node-list {
            columns: 3;
            column-gap: 20px;
        }
        .node {
            break-inside: avoid;
            margin-bottom: 10px;
            padding: 5px;
            background: #fff;
            border-left: 3px solid #ddd;
        }
        .entry-node {
            border-left-color: #4CAF50;
            font-weight: bold;
        }
        .edge-list {
            max-height: 400px;
            overflow-y: auto;
            background: #fff;
            padding: 10px;
            border: 1px solid #ddd;
        }
        .edge {
            padding: 3px;
            margin: 2px 0;
            font-family: monospace;
            font-size: 12px;
        }
    </style>
</head>
<body>
    <h1>📊 Module Dependency Graph - RAG System</h1>

    <div class="stats">
        <h2>Statistics</h2>
        <ul>
            <li><strong>Total Modules:</strong> """ + str(len(nodes)) + """</li>
            <li><strong>Total Dependencies:</strong> """ + str(len(edges)) + """</li>
            <li><strong>Entry Points:</strong> """ + str(len(entry_nodes)) + """</li>
        </ul>
    </div>

    <div class="graph-container">
        <h2>🟢 Entry Points</h2>
        <ul>"""

    for node in sorted(entry_nodes):
        html_content += f"\n            <li><code>{node}</code></li>"

    html_content += """
        </ul>

        <h2>📦 All Modules</h2>
        <div class="node-list">"""

    for node in sorted(nodes):
        if node in entry_nodes:
            html_content += f'\n            <div class="node entry-node">🟢 {node}</div>'
        else:
            html_content += f'\n            <div class="node">⚪ {node}</div>'

    html_content += """
        </div>

        <h2>🔗 Dependencies</h2>
        <div class="edge-list">"""

    for source, target in sorted(edges):
        html_content += f'\n            <div class="edge">{source} → {target}</div>'

    html_content += """
        </div>
    </div>

    <div style="margin-top: 20px; color: #666; font-size: 12px;">
        <p>Generated from: """ + dot_file + """</p>
        <p>Note: For better visualization, install graphviz and run: <code>dot -Tsvg """ + dot_file + """ -o graph.svg</code></p>
    </div>
</body>
</html>"""

    # Write HTML file
    with open(output_file, 'w') as f:
        f.write(html_content)

    print(f"Generated HTML visualization: {output_file}")

if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print("Usage: python dot_to_svg_html.py <input.dot> <output.html>")
        sys.exit(1)

    dot_to_html_svg(sys.argv[1], sys.argv[2])