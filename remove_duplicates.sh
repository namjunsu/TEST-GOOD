#!/bin/bash
#
# 중복 파일 제거 스크립트
#

echo "=================================="
echo "🧹 중복 파일 정리"
echo "=================================="
echo ""

# 통계
TOTAL_BEFORE=$(find docs -type f -name "*.pdf" | wc -l)
DUPLICATES=0

# archive 폴더의 중복 파일 제거
echo "📁 archive 폴더 중복 제거 중..."
for file in docs/archive/*.pdf; do
    if [ -f "$file" ]; then
        basename=$(basename "$file")
        # year_2014~2016 폴더에 같은 파일이 있는지 확인
        for year in 2014 2015 2016; do
            year_file="docs/year_${year}/${basename}"
            if [ -f "$year_file" ]; then
                echo "  삭제: archive/${basename} (year_${year}에 원본 존재)"
                rm "$file"
                DUPLICATES=$((DUPLICATES + 1))
                break
            fi
        done
    fi
done

# recent 폴더의 중복 파일 제거
echo ""
echo "📁 recent 폴더 중복 제거 중..."
for file in docs/recent/*.pdf; do
    if [ -f "$file" ]; then
        basename=$(basename "$file")
        # year_2023~2025 폴더에 같은 파일이 있는지 확인
        for year in 2023 2024 2025; do
            year_file="docs/year_${year}/${basename}"
            if [ -f "$year_file" ]; then
                echo "  삭제: recent/${basename} (year_${year}에 원본 존재)"
                rm "$file"
                DUPLICATES=$((DUPLICATES + 1))
                break
            fi
        done
    fi
done

# category 폴더들의 실제 파일 확인
echo ""
echo "📁 category 폴더 중복 확인 중..."
for category in purchase repair review disposal consumables; do
    cat_dir="docs/category_${category}"
    if [ -d "$cat_dir" ]; then
        for file in "$cat_dir"/*.pdf; do
            if [ -f "$file" ] && [ ! -L "$file" ]; then
                basename=$(basename "$file")
                # year 폴더에서 원본 찾기
                original_found=false
                for year_dir in docs/year_*; do
                    year_file="${year_dir}/${basename}"
                    if [ -f "$year_file" ]; then
                        echo "  삭제: category_${category}/${basename}"
                        rm "$file"
                        DUPLICATES=$((DUPLICATES + 1))
                        original_found=true
                        break
                    fi
                done
            fi
        done
    fi
done

TOTAL_AFTER=$(find docs -type f -name "*.pdf" | wc -l)

echo ""
echo "=================================="
echo "✅ 정리 완료!"
echo "=================================="
echo "📊 결과:"
echo "  • 이전 파일 수: $TOTAL_BEFORE개"
echo "  • 삭제된 중복: $DUPLICATES개"
echo "  • 현재 파일 수: $TOTAL_AFTER개"
echo ""