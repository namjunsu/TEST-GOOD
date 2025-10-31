# RAG Pipeline QA Report

**Generated**: 2025-10-31T15:22:44.758035
**Total Tests**: 20
**Status**: ❌ FAILED

---

## 📊 Metrics Summary

| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| **Hit@3** | 0.600 | ≥0.90 | ❌ FAIL |
| **MRR@10** | 0.457 | ≥0.80 | ❌ FAIL |
| **Citation Rate** | 0.950 | ≥1.00 | ❌ FAIL |
| **Schema Failure** | 0.050 | ≤0.015 | ❌ FAIL |
| **Coverage Pass** | 0.900 | ≥0.90 | ✅ PASS |

---

## ⏱️ Performance

| Metric | Value |
|--------|-------|
| P50 Latency | 8950ms |
| P95 Latency | 9895ms |
| Avg Chunks Used | 4.8 |

---

## 🔍 Coverage Analysis

- **Chunks Used**: 4.8 avg
- **Coverage Pass Rate**: 90.0%

---

## 📋 Schema Validation

- **Schema Failure Rate**: 5.0%
- **Threshold**: ≤1.5%

---

## 📚 Citation Analysis

- **Citation Rate**: 95.0%
- **Target**: 100%

---

## ✅ Acceptance Criteria

❌ **SOME AC NOT MET**

1. Hit@3 ≥ 0.90: ❌
2. MRR@10 ≥ 0.80: ❌
3. Citation Rate = 1.00: ❌
4. JSON Schema Failure ≤ 1.5%: ❌
5. Parsing Coverage ≥ 90%: ✅

---

**Generated**: 20251031_152244
