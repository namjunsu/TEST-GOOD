# License Information

## Project License

This project is proprietary and internal use only.

## Dependency Licenses Summary

Last Updated: 2025-10-29
Total Dependencies: 109 packages

### License Distribution

| License Type | Count | Percentage | Risk Level |
|--------------|-------|------------|------------|
| **Permissive** (MIT, BSD, Apache) | 57 | 52.3% | ✅ Low |
| **Copyleft** (GPL, LGPL) | 9 | 8.3% | ⚠️ Medium |
| **Unknown** | 24 | 22.0% | 🔴 High |
| **Other** | 19 | 17.4% | ℹ️ Variable |

## License Categories

### ✅ Permissive Licenses (Allowed)

These licenses allow use in proprietary software with minimal restrictions:

| Package | Version | License |
|---------|---------|---------|
| fastapi | Latest | MIT |
| streamlit | Latest | Apache 2.0 |
| pydantic | Latest | MIT |
| numpy | 2.3.4 | BSD |
| pandas | Latest | BSD |
| scikit-learn | Latest | BSD |
| uvicorn | Latest | BSD |
| click | 8.1.6 | BSD-3-Clause |
| requests | Latest | Apache 2.0 |
| pytest | Latest | MIT |
| black | Latest | MIT |
| ruff | Latest | MIT |
| python-dotenv | Latest | BSD |
| pyyaml | 6.0.1 | MIT |
| jinja2 | 3.1.2 | BSD-3-Clause |
| markupsafe | 2.1.5 | BSD-3-Clause |
| cryptography | 41.0.7 | Apache-2.0 OR BSD-3-Clause |
| faiss-cpu | 1.12.0 | MIT |
| transformers | Latest | Apache 2.0 |
| sentence-transformers | Latest | Apache 2.0 |

### ⚠️ Copyleft Licenses (Review Required)

These licenses require careful consideration for distribution:

| Package | Version | License | Risk | Action Required |
|---------|---------|---------|------|-----------------|
| PyGObject | 3.48.2 | GNU LGPL | Medium | Dynamic linking OK |
| chardet | 5.2.0 | LGPL | Medium | Library use OK |
| launchpadlib | 1.11.0 | LGPL v3 | Medium | API client only |
| lazr.restfulclient | 0.14.6 | LGPL v3 | Medium | API client only |
| lazr.uri | 1.0.6 | LGPL v3 | Medium | API client only |
| python-apt | 2.7.7 | GNU GPL | **High** | System package, not redistributed |
| systemd-python | 235 | LGPLv2+ | Medium | System integration only |
| ubuntu-pro-client | 8001 | GPLv3 | **High** | System tool, not bundled |
| wadllib | 1.3.6 | LGPL v3 | Medium | API support library |

**Note**: GPL packages are system tools and not redistributed with the application.

### 🔴 Unknown Licenses (Investigation Required)

These packages need license clarification:

| Package | Action |
|---------|--------|
| PyPDF2 | Verify - likely BSD/MIT |
| attrs | Verify - likely MIT |
| blinker | Verify - likely MIT |
| colorama | Verify - likely BSD |
| filelock | Verify - likely Unlicense |
| fsspec | Verify - likely BSD |
| packaging | Verify - likely BSD/Apache |
| pdfminer.six | Verify - likely MIT |
| pdfplumber | Verify - likely MIT |
| regex | Verify - likely Apache/PSF |
| tokenizers | Verify - likely Apache |
| (and 13 others) | Contact maintainers |

### ℹ️ Other Licenses

| Package | License | Notes |
|---------|---------|-------|
| certifi | MPL-2.0 | Mozilla Public License - Compatible |
| numpy | Copyright notice | BSD-style |
| scipy | Copyright notice | BSD-style |
| pillow | HPND | Historical Permission Notice |
| zope.interface | ZPL 2.1 | Zope Public License |

## Compliance Requirements

### For Internal Use
- ✅ Current configuration is acceptable
- ⚠️ Document GPL components are system-level only
- 📝 Maintain this license inventory

### For Distribution/Deployment
1. **Replace or Remove GPL packages**:
   - python-apt → Use subprocess calls instead
   - ubuntu-pro-client → Not needed for deployment

2. **Clarify Unknown Licenses**:
   - Run `pip show <package>` for each
   - Check package repositories
   - Document findings

3. **LGPL Compliance**:
   - Ensure dynamic linking only
   - Provide LGPL license text
   - Enable users to replace LGPL libraries

## CI/CD License Policy

### Automated Checks

```yaml
# .github/workflows/license-check.yml
allowed_licenses:
  - MIT
  - BSD*
  - Apache*
  - ISC
  - MPL-2.0
  - Python
  - PSF

warning_licenses:
  - LGPL*  # Requires review

blocked_licenses:
  - GPL-2.0
  - GPL-3.0
  - AGPL*

fail_on_unknown: true
```

### Implementation

1. **Pre-commit Hook**: Check licenses before commit
2. **PR Gate**: Block merges with unapproved licenses
3. **Weekly Audit**: Scan for license changes
4. **SBOM Generation**: Create Software Bill of Materials

## License Texts

Full license texts for all dependencies are available in:
- `THIRD_PARTY_NOTICES.md` - Complete license texts
- `reports/licenses_detail.json` - Machine-readable format

## Contact

For license questions or compliance concerns:
- Internal: Legal/Compliance Team
- External: See individual package repositories

---

*This document is automatically generated. Do not edit manually.*
*Last scan: 2025-10-29 via scripts/scan_licenses.py*