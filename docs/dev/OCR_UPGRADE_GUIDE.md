# OCR 엔진 업그레이드 가이드

## 📋 개요
2017년 문서 45개의 메타데이터 추출 실패 문제를 해결하기 위한 Tesseract OCR 5.x 업그레이드 및 재처리 가이드

## 🎯 목표
- Tesseract 5.x 설치 및 한국어 인식 최적화
- 2017년 문서 OCR 품질 개선
- 메타데이터 추출 성공률 향상 (현재 3/45 → 목표 30+/45)

## 📊 현재 상황
```
- 전체 2017년 문서: 45개
- 메타데이터 추출 성공: 3개 (6.7%)
- 주요 문제: OCR 품질 저하로 인한 텍스트 인식 실패
- 특히 문제: 기안자 이름 인식 실패
```

## 🔧 Tesseract 5.x 설치

### 1. 시스템 요구사항
```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-kor \
    tesseract-ocr-eng \
    libtesseract-dev \
    libleptonica-dev

# 버전 확인
tesseract --version
# Expected: tesseract 5.3.0 or higher
```

### 2. Python 패키지 업그레이드
```bash
# 가상환경 활성화
source .venv/bin/activate

# OCR 관련 패키지 업그레이드
pip install --upgrade \
    pytesseract==0.3.10 \
    pdf2image==1.16.3 \
    Pillow==10.1.0 \
    opencv-python==4.8.1.78

# 추가 이미지 처리 도구
pip install --upgrade \
    scikit-image==0.22.0 \
    numpy==1.24.3
```

### 3. 한국어 학습 데이터 최적화
```bash
# 최신 한국어 학습 데이터 다운로드
cd /usr/share/tesseract-ocr/5/tessdata/
sudo wget https://github.com/tesseract-ocr/tessdata_best/raw/main/kor.traineddata -O kor_best.traineddata

# 기본 설정 변경
sudo ln -sf kor_best.traineddata kor.traineddata
```

## 📝 향상된 OCR 처리 스크립트

### scripts/enhanced_ocr_processor.py
```python
#!/usr/bin/env python3
"""향상된 OCR 처리기 - Tesseract 5.x 최적화"""

import pytesseract
from pdf2image import convert_from_path
from PIL import Image, ImageFilter, ImageEnhance
import cv2
import numpy as np
from pathlib import Path
import json
from typing import Dict, List, Optional
import re

class EnhancedOCRProcessor:
    """Tesseract 5.x 기반 향상된 OCR 처리기"""

    def __init__(self):
        # Tesseract 설정 최적화
        self.tesseract_config = r'--oem 3 --psm 6 -l kor+eng'
        self.preprocessing_enabled = True

    def preprocess_image(self, image: Image.Image) -> Image.Image:
        """이미지 전처리로 OCR 품질 향상"""

        # 1. 그레이스케일 변환
        img = image.convert('L')

        # 2. 해상도 향상 (DPI 300 이상)
        width, height = img.size
        if width < 2000:
            scale_factor = 2000 / width
            new_size = (int(width * scale_factor), int(height * scale_factor))
            img = img.resize(new_size, Image.LANCZOS)

        # 3. 노이즈 제거
        img = img.filter(ImageFilter.MedianFilter(size=3))

        # 4. 대비 향상
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2.0)

        # 5. 이진화 (Otsu's method)
        img_array = np.array(img)
        _, binary = cv2.threshold(img_array, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        img = Image.fromarray(binary)

        # 6. 기울기 보정
        img_array = np.array(img)
        coords = np.column_stack(np.where(img_array > 0))
        if len(coords) > 0:
            angle = cv2.minAreaRect(coords)[-1]
            if angle < -45:
                angle = 90 + angle
            if abs(angle) > 0.5:
                (h, w) = img_array.shape[:2]
                center = (w // 2, h // 2)
                M = cv2.getRotationMatrix2D(center, angle, 1.0)
                rotated = cv2.warpAffine(img_array, M, (w, h),
                                        flags=cv2.INTER_CUBIC,
                                        borderMode=cv2.BORDER_REPLICATE)
                img = Image.fromarray(rotated)

        return img

    def extract_text_from_pdf(self, pdf_path: Path) -> str:
        """PDF에서 향상된 텍스트 추출"""

        try:
            # PDF를 이미지로 변환 (고해상도)
            images = convert_from_path(
                pdf_path,
                dpi=300,  # 고해상도
                fmt='png'
            )

            all_text = []

            for i, image in enumerate(images):
                print(f"  - 페이지 {i+1}/{len(images)} 처리 중...")

                # 이미지 전처리
                if self.preprocessing_enabled:
                    processed_img = self.preprocess_image(image)
                else:
                    processed_img = image

                # OCR 수행 (다중 시도)
                text = ""

                # 첫 번째 시도: 기본 설정
                try:
                    text = pytesseract.image_to_string(
                        processed_img,
                        config=self.tesseract_config
                    )
                except Exception as e:
                    print(f"    OCR 1차 시도 실패: {e}")

                # 두 번째 시도: PSM 모드 변경
                if not text or len(text) < 50:
                    try:
                        config = r'--oem 3 --psm 3 -l kor+eng'  # PSM 3: 자동 페이지 분할
                        text = pytesseract.image_to_string(
                            processed_img,
                            config=config
                        )
                    except:
                        pass

                # 세 번째 시도: 영역별 OCR
                if not text or len(text) < 50:
                    text = self._extract_by_regions(processed_img)

                if text:
                    all_text.append(text)

            return "\n\n".join(all_text)

        except Exception as e:
            print(f"  ❌ PDF 처리 실패: {e}")
            return ""

    def _extract_by_regions(self, image: Image.Image) -> str:
        """영역별 OCR 수행 (표 등 복잡한 레이아웃 대응)"""

        img_array = np.array(image)

        # 영역 검출
        contours, _ = cv2.findContours(
            img_array,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )

        regions = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if w > 50 and h > 20:  # 너무 작은 영역 제외
                regions.append((x, y, w, h))

        # 영역 정렬 (위에서 아래, 왼쪽에서 오른쪽)
        regions.sort(key=lambda r: (r[1], r[0]))

        text_parts = []
        for x, y, w, h in regions[:20]:  # 최대 20개 영역
            region_img = image.crop((x, y, x+w, y+h))
            try:
                text = pytesseract.image_to_string(
                    region_img,
                    config=self.tesseract_config
                ).strip()
                if text:
                    text_parts.append(text)
            except:
                continue

        return "\n".join(text_parts)

    def extract_drafter(self, text: str) -> Optional[str]:
        """향상된 기안자 추출"""

        # 다양한 패턴 시도
        patterns = [
            # 표준 패턴
            r'기안자\s*[:|]?\s*([가-힣]{2,4})',
            r'기\s*안\s*자\s*[:|]?\s*([가-힣]{2,4})',

            # OCR 오류 보정 패턴
            r'기안[자지]\s*[:|]?\s*([가-힣]{2,4})',
            r'[기키][안간][자지]\s*[:|]?\s*([가-힣]{2,4})',

            # 작성자/담당자 패턴
            r'작성자\s*[:|]?\s*([가-힣]{2,4})',
            r'담당자\s*[:|]?\s*([가-힣]{2,4})',

            # 테이블 형식
            r'기안자\s*\|\s*([가-힣]{2,4})',
            r'([가-힣]{2,4})\s*\|\s*기안',

            # 영문 혼재
            r'Writer\s*[:|]?\s*([가-힣]{2,4})',
            r'Author\s*[:|]?\s*([가-힣]{2,4})',
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                drafter = match.group(1).strip()
                # 유효성 검사
                if 2 <= len(drafter) <= 4:
                    return drafter

        return None

def main():
    """2017년 문서 재처리"""

    processor = EnhancedOCRProcessor()

    # 2017년 문서 목록
    docs_dir = Path('docs/year_2017')
    pdf_files = list(docs_dir.glob('*.pdf'))

    print(f"📚 2017년 문서 {len(pdf_files)}개 재처리 시작")
    print("=" * 60)

    results = []
    success_count = 0

    for i, pdf_path in enumerate(pdf_files, 1):
        print(f"\n[{i}/{len(pdf_files)}] {pdf_path.name}")

        # OCR 수행
        text = processor.extract_text_from_pdf(pdf_path)

        if text:
            # 기안자 추출
            drafter = processor.extract_drafter(text)

            if drafter:
                print(f"  ✅ 기안자 추출 성공: {drafter}")
                success_count += 1

                # DB 업데이트
                # update_database(pdf_path.name, drafter)

                results.append({
                    'filename': pdf_path.name,
                    'drafter': drafter,
                    'text_length': len(text),
                    'status': 'success'
                })
            else:
                print(f"  ⚠️ 기안자 추출 실패")
                results.append({
                    'filename': pdf_path.name,
                    'drafter': None,
                    'text_length': len(text),
                    'status': 'no_drafter'
                })
        else:
            print(f"  ❌ OCR 실패")
            results.append({
                'filename': pdf_path.name,
                'drafter': None,
                'text_length': 0,
                'status': 'ocr_failed'
            })

    # 결과 저장
    output_path = Path('reports/ocr_reprocessing_2017.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({
            'total': len(pdf_files),
            'success': success_count,
            'success_rate': f"{(success_count/len(pdf_files)*100):.1f}%",
            'results': results
        }, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print(f"✅ 재처리 완료!")
    print(f"  - 전체: {len(pdf_files)}개")
    print(f"  - 성공: {success_count}개")
    print(f"  - 성공률: {(success_count/len(pdf_files)*100):.1f}%")
    print(f"  - 보고서: {output_path}")

if __name__ == "__main__":
    main()
```

## 🔄 재처리 실행 방법

### 1. 단계별 실행
```bash
# 1. OCR 엔진 업그레이드 확인
tesseract --version

# 2. 이미지 품질 테스트
python scripts/test_ocr_quality.py docs/year_2017/sample.pdf

# 3. 전체 재처리
python scripts/enhanced_ocr_processor.py

# 4. 결과 확인
cat reports/ocr_reprocessing_2017.json
```

### 2. 배치 처리 스크립트
```bash
#!/bin/bash
# scripts/reprocess_2017_docs.sh

echo "🔄 2017년 문서 OCR 재처리 시작"
echo "================================"

# 백업 생성
cp metadata.db metadata.db.backup_$(date +%Y%m%d_%H%M%S)

# OCR 재처리
python scripts/enhanced_ocr_processor.py

# DB 업데이트
python scripts/update_2017_metadata.py

# 인덱스 재생성
python scripts/reindex_atomic.py

echo "✅ 재처리 완료!"
```

## 📈 성능 비교

### 이전 (Tesseract 4.x + 기본 설정)
```
- OCR 품질: 낮음
- 기안자 인식률: 6.7% (3/45)
- 평균 처리 시간: 2초/페이지
- 주요 문제: 한글 인식 오류, 레이아웃 파싱 실패
```

### 개선 후 (Tesseract 5.x + 최적화)
```
- OCR 품질: 높음
- 기안자 인식률: 70%+ 예상 (30+/45)
- 평균 처리 시간: 3-4초/페이지
- 개선사항:
  - 이미지 전처리 (노이즈 제거, 대비 향상)
  - 기울기 자동 보정
  - 영역별 OCR 수행
  - 다중 패턴 매칭
```

## 🛠️ 문제 해결

### 1. 메모리 부족
```python
# 대용량 PDF 처리 시 페이지별 처리
def process_large_pdf(pdf_path, max_pages_batch=5):
    total_pages = get_pdf_page_count(pdf_path)

    for start in range(0, total_pages, max_pages_batch):
        end = min(start + max_pages_batch, total_pages)
        images = convert_from_path(
            pdf_path,
            first_page=start+1,
            last_page=end,
            dpi=300
        )
        # 처리...
```

### 2. OCR 속도 개선
```python
# 멀티프로세싱 활용
from multiprocessing import Pool

def process_pdfs_parallel(pdf_files, num_workers=4):
    with Pool(num_workers) as pool:
        results = pool.map(process_single_pdf, pdf_files)
    return results
```

### 3. 품질 검증
```python
# OCR 품질 자동 검증
def validate_ocr_quality(text):
    # 한글 비율 체크
    korean_chars = len(re.findall(r'[가-힣]', text))
    total_chars = len(text)
    korean_ratio = korean_chars / max(total_chars, 1)

    # 품질 판단
    if korean_ratio < 0.3:
        return "LOW"
    elif korean_ratio < 0.6:
        return "MEDIUM"
    else:
        return "HIGH"
```

## 📊 모니터링

### OCR 품질 대시보드 추가
```python
# metadata_dashboard.py에 추가할 섹션

def show_ocr_quality_metrics():
    """OCR 품질 메트릭 표시"""

    st.markdown("### 🔍 OCR 품질 현황")

    # 2017년 문서 상태
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "2017년 전체 문서",
            "45개",
            delta=None
        )

    with col2:
        st.metric(
            "메타데이터 추출 성공",
            "3개 → 30+개",
            delta="+27개 예상"
        )

    with col3:
        st.metric(
            "성공률",
            "6.7% → 70%+",
            delta="+63.3%p"
        )

    # OCR 재처리 진행률
    if Path('reports/ocr_reprocessing_2017.json').exists():
        with open('reports/ocr_reprocessing_2017.json', 'r') as f:
            data = json.load(f)

        progress = st.progress(data['success'] / data['total'])
        st.write(f"재처리 완료: {data['success']}/{data['total']} ({data['success_rate']})")
```

## 🎯 체크리스트

### 설치 완료
- [ ] Tesseract 5.x 설치
- [ ] 한국어 학습 데이터 업데이트
- [ ] Python 패키지 업그레이드
- [ ] 이미지 처리 라이브러리 설치

### 스크립트 준비
- [ ] enhanced_ocr_processor.py 생성
- [ ] test_ocr_quality.py 생성
- [ ] update_2017_metadata.py 생성
- [ ] reprocess_2017_docs.sh 생성

### 실행 및 검증
- [ ] 샘플 문서 테스트
- [ ] 전체 2017년 문서 재처리
- [ ] 메타데이터 DB 업데이트
- [ ] BM25 인덱스 재생성
- [ ] 결과 검증 (목표: 30+/45)

## 📚 참고 자료

- [Tesseract 5.x 공식 문서](https://github.com/tesseract-ocr/tesseract)
- [한국어 OCR 최적화 가이드](https://github.com/tesseract-ocr/tessdata_best)
- [이미지 전처리 기법](https://opencv.org/opencv-python-image-preprocessing/)
- [PyTesseract 고급 설정](https://pypi.org/project/pytesseract/)

## 💡 추가 개선 아이디어

1. **AI 기반 OCR**: Google Cloud Vision API, AWS Textract 등 클라우드 OCR 서비스 활용
2. **딥러닝 모델**: EasyOCR, PaddleOCR 등 딥러닝 기반 OCR 라이브러리 시도
3. **하이브리드 접근**: 여러 OCR 엔진 결과를 앙상블하여 최상의 결과 도출
4. **수동 보정 UI**: Streamlit 기반 수동 메타데이터 입력/수정 인터페이스

---

*작성일: 2025-11-20*
*작성자: AI-CHAT 개발팀*