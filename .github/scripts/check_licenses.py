#!/usr/bin/env python3
"""
CI License Gate - Enforces license policy for dependencies.
"""

import json
import sys

# License Policy Configuration
ALLOWED_LICENSES = {
    "MIT", "MIT License",
    "BSD", "BSD License", "BSD-2-Clause", "BSD-3-Clause", "BSD 2-Clause", "BSD 3-Clause",
    "Apache", "Apache 2.0", "Apache-2.0", "Apache License 2.0", "Apache Software License",
    "ISC", "ISC License",
    "MPL-2.0", "Mozilla Public License 2.0",
    "Python", "Python Software Foundation License", "PSF",
    "Unlicense", "Public Domain", "CC0",
    "HPND", "Historical Permission Notice and Disclaimer",
    "Zope", "ZPL", "Zope Public License",
}

WARNING_LICENSES = {
    "LGPL", "LGPL-2.1", "LGPL-3.0", "LGPLv2", "LGPLv3",
    "GNU LGPL", "GNU Lesser General Public License",
}

BLOCKED_LICENSES = {
    "GPL", "GPL-2.0", "GPL-3.0", "GPLv2", "GPLv3",
    "GNU GPL", "GNU General Public License",
    "AGPL", "AGPL-3.0", "AGPLv3",
    "Proprietary", "Commercial",
}

# System packages that are allowed despite GPL license
SYSTEM_PACKAGE_EXCEPTIONS = {
    "python-apt",          # System package manager
    "ubuntu-pro-client",   # Ubuntu system tool
    "cloud-init",         # System initialization
    "command-not-found",  # System utility
    "distro-info",       # System information
    "systemd-python",    # System integration
}

# Packages with known but acceptable licenses
KNOWN_ACCEPTABLE = {
    "numpy": "BSD",
    "scipy": "BSD",
    "cryptography": "Apache/BSD",
}


def normalize_license(license_str: str) -> str:
    """Normalize license string for comparison."""
    if not license_str:
        return "UNKNOWN"
    return license_str.strip().upper()


def check_license_compliance(license_str: str, package_name: str) -> tuple[str, str]:
    """
    Check if a license is compliant with policy.

    Returns: (status, message)
    status: 'allowed', 'warning', 'blocked', 'unknown'
    """
    # Handle system package exceptions
    if package_name in SYSTEM_PACKAGE_EXCEPTIONS:
        return "allowed", f"System package exception for {package_name}"

    # Handle known acceptable packages
    if package_name in KNOWN_ACCEPTABLE:
        return "allowed", f"Known acceptable: {KNOWN_ACCEPTABLE[package_name]}"

    # Normalize for comparison
    norm_license = normalize_license(license_str)

    # Check for blocked licenses
    for blocked in BLOCKED_LICENSES:
        if blocked in norm_license:
            return "blocked", f"BLOCKED license: {license_str}"

    # Check for warning licenses
    for warning in WARNING_LICENSES:
        if warning in norm_license:
            return "warning", f"Warning - copyleft license: {license_str}"

    # Check for allowed licenses
    for allowed in ALLOWED_LICENSES:
        if normalize_license(allowed) in norm_license:
            return "allowed", f"Allowed: {license_str}"

    # Handle dual licenses (e.g., "MIT OR BSD")
    if " OR " in norm_license or "/" in license_str:
        parts = license_str.replace(" OR ", "/").split("/")
        for part in parts:
            for allowed in ALLOWED_LICENSES:
                if normalize_license(allowed) in normalize_license(part):
                    return "allowed", f"Dual license with allowed option: {license_str}"

    # Unknown license
    if license_str and license_str.lower() not in ["unknown", "", "none"]:
        return "unknown", f"Unknown license: {license_str}"

    return "unknown", "No license information found"


def main():
    """Main license checking function."""
    # Load license data
    try:
        with open("licenses.json", "r") as f:
            licenses_data = json.load(f)
    except FileNotFoundError:
        print("❌ Error: licenses.json not found. Run 'pip-licenses --format=json' first.")
        sys.exit(1)

    # Initialize counters
    results = {
        "allowed": [],
        "warning": [],
        "blocked": [],
        "unknown": []
    }

    # Check each package
    for package in licenses_data:
        name = package.get("Name", "Unknown")
        version = package.get("Version", "Unknown")
        license_str = package.get("License", "Unknown")

        status, message = check_license_compliance(license_str, name)
        results[status].append({
            "name": name,
            "version": version,
            "license": license_str,
            "message": message
        })

    # Generate report
    report_lines = [
        "=" * 60,
        "LICENSE COMPLIANCE REPORT",
        "=" * 60,
        "",
        f"Total packages analyzed: {len(licenses_data)}",
        f"✅ Allowed: {len(results['allowed'])}",
        f"⚠️  Warnings: {len(results['warning'])}",
        f"🚫 Blocked: {len(results['blocked'])}",
        f"❓ Unknown: {len(results['unknown'])}",
        ""
    ]

    # Report warnings
    if results["warning"]:
        report_lines.extend([
            "⚠️  WARNING - Copyleft Licenses (Review Required)",
            "-" * 40
        ])
        for pkg in results["warning"]:
            report_lines.append(f"  • {pkg['name']} ({pkg['version']}): {pkg['license']}")
        report_lines.append("")

    # Report blocked licenses
    if results["blocked"]:
        report_lines.extend([
            "🚫 BLOCKED - Prohibited Licenses",
            "-" * 40
        ])
        for pkg in results["blocked"]:
            report_lines.append(f"  • {pkg['name']} ({pkg['version']}): {pkg['license']}")
        report_lines.extend([
            "",
            "Action Required:",
            "1. Remove or replace blocked packages",
            "2. Or add to SYSTEM_PACKAGE_EXCEPTIONS if it's a system tool",
            ""
        ])

    # Report unknown licenses
    if results["unknown"]:
        report_lines.extend([
            "❓ UNKNOWN - Requires Investigation",
            "-" * 40
        ])
        for pkg in results["unknown"][:10]:  # Show first 10
            report_lines.append(f"  • {pkg['name']} ({pkg['version']})")
        if len(results["unknown"]) > 10:
            report_lines.append(f"  ... and {len(results['unknown']) - 10} more")
        report_lines.extend([
            "",
            "Action Required:",
            "1. Investigate package licenses",
            "2. Update KNOWN_ACCEPTABLE dict if acceptable",
            ""
        ])

    # Determine pass/fail
    fail_build = False

    # Fail on blocked licenses
    if results["blocked"]:
        report_lines.append("❌ BUILD FAILED: Blocked licenses detected")
        fail_build = True

    # Fail on too many unknown licenses
    elif len(results["unknown"]) > 30:
        report_lines.append(f"❌ BUILD FAILED: Too many unknown licenses ({len(results['unknown'])} > 30)")
        fail_build = True

    # Pass with warnings
    elif results["warning"] or results["unknown"]:
        report_lines.append("⚠️  BUILD PASSED with warnings - Review required")

    # Clean pass
    else:
        report_lines.append("✅ BUILD PASSED - All licenses compliant")

    # Write report
    report_text = "\n".join(report_lines)

    with open("license-check-report.txt", "w") as f:
        f.write(report_text)

    # Print to console
    print(report_text)

    # Exit with appropriate code
    sys.exit(1 if fail_build else 0)


if __name__ == "__main__":
    main()
