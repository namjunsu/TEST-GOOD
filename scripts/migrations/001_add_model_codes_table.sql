-- Migration: 001_add_model_codes_table
-- Purpose: 모델/부품 코드 전용 정확 매칭 테이블 생성
-- Date: 2025-10-31
-- Author: AI-CHAT System

-- ============================================================================
-- 1. model_codes 테이블 생성 (정확일치 조회용)
-- ============================================================================
CREATE TABLE IF NOT EXISTS model_codes (
    doc_id    INTEGER NOT NULL,                              -- documents.id FK
    code      TEXT    NOT NULL,                              -- 원문 코드 (예: "xrn-1620b2")
    norm_code TEXT    NOT NULL,                              -- 정규화 코드 (예: "XRN-1620B2")
    positions TEXT,                                           -- 코드 위치 (선택, 예: "p1:12-18;p3:221-228")
    source    TEXT    NOT NULL CHECK(source IN ('filename','content','metadata')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(doc_id, norm_code, source)                         -- 중복 방지
);

-- 인덱스: norm_code 기준 고속 검색
CREATE INDEX IF NOT EXISTS idx_model_codes_norm ON model_codes(norm_code);
CREATE INDEX IF NOT EXISTS idx_model_codes_doc_id ON model_codes(doc_id);

-- ============================================================================
-- 2. FTS5 테이블 재구성 (하이픈/슬래시/언더스코어/점 보존)
-- ============================================================================
-- 주의: 기존 documents_fts를 삭제하고 재생성해야 합니다.
-- 실행 전 백업 필수!

-- 기존 FTS 테이블 백업
-- CREATE TABLE documents_fts_backup AS SELECT * FROM documents_fts;

-- 기존 FTS 테이블 삭제 (트리거도 함께 삭제됨)
DROP TABLE IF EXISTS documents_fts;

-- 새 FTS5 테이블 생성 (커스텀 토크나이저)
-- tokenchars '-/_.' : 하이픈, 슬래시, 언더스코어, 점을 토큰 내부 문자로 인식
CREATE VIRTUAL TABLE documents_fts USING fts5(
    path UNINDEXED,
    title,
    filename,                                                 -- 파일명 추가 (중요!)
    text_preview,
    keywords,
    content=documents,
    content_rowid=id,
    tokenize = "unicode61 remove_diacritics 2 tokenchars '-/_.'"
);

-- FTS 동기화 트리거 재생성
CREATE TRIGGER IF NOT EXISTS documents_ai
AFTER INSERT ON documents
BEGIN
    INSERT INTO documents_fts(rowid, path, title, filename, text_preview, keywords)
    VALUES (new.id, new.path, new.title, new.filename, new.text_preview, new.keywords);
END;

CREATE TRIGGER IF NOT EXISTS documents_au
AFTER UPDATE ON documents
BEGIN
    UPDATE documents_fts
    SET title = new.title,
        filename = new.filename,
        text_preview = new.text_preview,
        keywords = new.keywords
    WHERE rowid = new.id;
END;

CREATE TRIGGER IF NOT EXISTS documents_ad
AFTER DELETE ON documents
BEGIN
    DELETE FROM documents_fts WHERE rowid = old.id;
END;

-- ============================================================================
-- 3. 재색인 (기존 데이터 FTS로 복사)
-- ============================================================================
-- 이 부분은 Python 스크립트에서 실행
-- INSERT INTO documents_fts(rowid, path, title, filename, text_preview, keywords)
-- SELECT id, path, title, filename, text_preview, keywords FROM documents;

-- ============================================================================
-- 4. 검증 쿼리
-- ============================================================================
-- 테이블 존재 확인
-- SELECT name FROM sqlite_master WHERE type='table' AND name IN ('model_codes', 'documents_fts');

-- 토크나이저 확인
-- SELECT * FROM documents_fts WHERE documents_fts MATCH 'XRN-1620B2';

-- 코드 검색 테스트
-- SELECT * FROM model_codes WHERE norm_code IN ('XRN-1620B2', 'XRN1620B2', 'XRN 1620B2');
