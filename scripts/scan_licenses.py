#!/usr/bin/env python3
"""
Security and License Scanner for Repository Hygiene.
Generates comprehensive license report for all dependencies.
"""

import subprocess
import json
from collections import Counter
from pathlib import Path

def get_installed_packages():
    """Get list of installed packages with versions."""
    result = subprocess.run(
        ["pip", "list", "--format=json"],
        capture_output=True,
        text=True
    )
    return json.loads(result.stdout)

def classify_license(license_str):
    """Classify license into categories."""
    if not license_str:
        return "Unknown"

    license_lower = license_str.lower()

    # Open source licenses
    if any(x in license_lower for x in ['mit', 'bsd', 'apache', 'isc']):
        return "Permissive"
    elif any(x in license_lower for x in ['gpl', 'lgpl', 'agpl']):
        return "Copyleft"
    elif 'python' in license_lower or 'psf' in license_lower:
        return "Python"
    elif any(x in license_lower for x in ['proprietary', 'commercial']):
        return "Proprietary"
    else:
        return "Other"

def scan_licenses():
    """Scan all dependencies for licenses."""
    packages = get_installed_packages()

    # Common packages and their licenses (fallback for when pip show fails)
    known_licenses = {
        'numpy': 'BSD',
        'pandas': 'BSD',
        'scikit-learn': 'BSD',
        'streamlit': 'Apache 2.0',
        'fastapi': 'MIT',
        'uvicorn': 'BSD',
        'pydantic': 'MIT',
        'langchain': 'MIT',
        'langchain-community': 'MIT',
        'langchain-openai': 'MIT',
        'openai': 'MIT',
        'faiss-cpu': 'MIT',
        'sentence-transformers': 'Apache 2.0',
        'torch': 'BSD',
        'transformers': 'Apache 2.0',
        'click': 'BSD',
        'requests': 'Apache 2.0',
        'urllib3': 'MIT',
        'certifi': 'MPL-2.0',
        'jinja2': 'BSD',
        'markupsafe': 'BSD',
        'pytest': 'MIT',
        'black': 'MIT',
        'ruff': 'MIT',
        'mypy': 'MIT',
        'pre-commit': 'MIT',
        'python-dotenv': 'BSD',
        'pyyaml': 'MIT',
        'sqlalchemy': 'MIT',
        'alembic': 'MIT',
        'psutil': 'BSD',
        'tqdm': 'MIT/Apache 2.0',
        'rich': 'MIT',
        'httpx': 'BSD',
        'aiohttp': 'Apache 2.0',
        'boto3': 'Apache 2.0',
        'redis': 'MIT',
        'celery': 'BSD',
        'pillow': 'HPND',
        'matplotlib': 'PSF',
        'seaborn': 'BSD',
        'plotly': 'MIT',
        'opencv-python': 'MIT',
        'scipy': 'BSD',
        'sympy': 'BSD',
        'networkx': 'BSD',
        'beautifulsoup4': 'MIT',
        'lxml': 'BSD',
        'openpyxl': 'MIT',
        'xlrd': 'BSD',
        'cryptography': 'Apache 2.0/BSD',
        'pycryptodome': 'BSD/Public Domain',
        'jwt': 'MIT',
        'passlib': 'BSD',
        'flask': 'BSD',
        'django': 'BSD',
        'gunicorn': 'MIT',
        'nginx': 'BSD',
        'docker': 'Apache 2.0',
        'kubernetes': 'Apache 2.0',
    }

    licenses = []
    security_concerns = []

    for pkg in packages:
        name = pkg['name']
        version = pkg['version']

        # Try to get license info from pip show
        try:
            result = subprocess.run(
                ["pip", "show", name],
                capture_output=True,
                text=True,
                timeout=2
            )

            license_info = "Unknown"
            for line in result.stdout.split('\n'):
                if line.startswith('License:'):
                    license_info = line.replace('License:', '').strip()
                    break

            # Fallback to known licenses
            if (not license_info or license_info == "Unknown") and name in known_licenses:
                license_info = known_licenses[name]

        except:
            license_info = known_licenses.get(name, "Unknown")

        licenses.append({
            'name': name,
            'version': version,
            'license': license_info,
            'category': classify_license(license_info)
        })

        # Security checks
        # Check for known vulnerable versions (simplified)
        security_issues = []

        # Example checks (would need real CVE database in production)
        if name == 'urllib3' and version < '2.0.0':
            security_issues.append("Older version - consider upgrading")
        elif name == 'requests' and version < '2.31.0':
            security_issues.append("Older version - consider upgrading")
        elif name == 'cryptography' and version < '41.0.0':
            security_issues.append("Older version - security updates available")

        if security_issues:
            security_concerns.append({
                'package': name,
                'version': version,
                'issues': security_issues
            })

    return licenses, security_concerns

def generate_report():
    """Generate comprehensive license and security report."""
    print("🔍 Scanning licenses and security...")

    licenses, security_concerns = scan_licenses()

    # Count license categories
    license_counts = Counter(lic['category'] for lic in licenses)

    # Generate report
    report_lines = [
        "📦 License and Security Report",
        "=" * 60,
        f"Total packages: {len(licenses)}",
        f"Scan date: {subprocess.check_output(['date']).decode().strip()}",
        "",
        "📊 License Distribution:",
        "-" * 30
    ]

    for category, count in sorted(license_counts.items()):
        percentage = (count / len(licenses)) * 100
        report_lines.append(f"  {category:15s}: {count:3d} ({percentage:5.1f}%)")

    report_lines.extend([
        "",
        "📜 Package Licenses:",
        "-" * 30
    ])

    # Group by category
    for category in ['Permissive', 'Copyleft', 'Python', 'Other', 'Unknown']:
        packages_in_category = [p for p in licenses if p['category'] == category]
        if packages_in_category:
            report_lines.append(f"\n{category} Licenses:")
            for pkg in sorted(packages_in_category, key=lambda x: x['name'])[:20]:  # First 20
                report_lines.append(f"  • {pkg['name']:30s} {pkg['version']:15s} {pkg['license']}")
            if len(packages_in_category) > 20:
                report_lines.append(f"  ... and {len(packages_in_category) - 20} more")

    # Security section
    report_lines.extend([
        "",
        "🔒 Security Analysis:",
        "-" * 30
    ])

    if security_concerns:
        report_lines.append("⚠️ Packages with potential issues:")
        for concern in security_concerns:
            report_lines.append(f"  • {concern['package']} ({concern['version']})")
            for issue in concern['issues']:
                report_lines.append(f"    - {issue}")
    else:
        report_lines.append("✅ No immediate security concerns identified")

    # Compliance summary
    report_lines.extend([
        "",
        "📋 Compliance Summary:",
        "-" * 30,
        f"✅ Permissive licenses: {license_counts.get('Permissive', 0)} packages",
        f"⚠️  Copyleft licenses: {license_counts.get('Copyleft', 0)} packages",
        f"ℹ️  Unknown licenses: {license_counts.get('Unknown', 0)} packages",
        ""
    ])

    # Risk assessment
    copyleft_count = license_counts.get('Copyleft', 0)
    unknown_count = license_counts.get('Unknown', 0)

    if copyleft_count == 0 and unknown_count < 5:
        risk = "LOW"
        risk_icon = "✅"
    elif copyleft_count < 3 and unknown_count < 10:
        risk = "MEDIUM"
        risk_icon = "⚠️"
    else:
        risk = "HIGH"
        risk_icon = "🔴"

    report_lines.extend([
        f"Risk Level: {risk_icon} {risk}",
        ""
    ])

    # Recommendations
    report_lines.extend([
        "💡 Recommendations:",
        "-" * 30
    ])

    if copyleft_count > 0:
        report_lines.append("1. Review copyleft licensed packages for compliance")
    if unknown_count > 5:
        report_lines.append("2. Investigate packages with unknown licenses")
    if security_concerns:
        report_lines.append("3. Update packages with security concerns")
    if not copyleft_count and not unknown_count and not security_concerns:
        report_lines.append("1. Continue regular dependency updates")
        report_lines.append("2. Monitor for security advisories")

    # Save full report
    report_text = "\n".join(report_lines)

    # Save to file
    output_file = Path("reports/licenses_summary.txt")
    output_file.parent.mkdir(exist_ok=True)
    output_file.write_text(report_text)

    # Also save JSON for programmatic access
    json_report = {
        'total_packages': len(licenses),
        'license_distribution': dict(license_counts),
        'packages': licenses,
        'security_concerns': security_concerns,
        'risk_level': risk,
        'timestamp': subprocess.check_output(['date']).decode().strip()
    }

    json_file = Path("reports/licenses_detail.json")
    with open(json_file, 'w') as f:
        json.dump(json_report, f, indent=2)

    print(report_text)
    print("")
    print(f"📄 Reports saved:")
    print(f"   - {output_file}")
    print(f"   - {json_file}")

    return risk == "LOW" or risk == "MEDIUM"

if __name__ == "__main__":
    import sys
    success = generate_report()
    sys.exit(0 if success else 1)