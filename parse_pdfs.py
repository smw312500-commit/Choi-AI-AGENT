"""
JUSTEM 제품 PDF 자동 파싱 스크립트
- PDF 폴더 경로 지정 → Claude API로 스펙 추출 → products_db.json 생성
- 생성된 JSON을 앱에서 'DB JSON 복원' 버튼으로 불러오기
"""

import json
import os
import re
import time
import requests
from pathlib import Path

# ============================================================
# 설정
# ============================================================
API_KEY   = ""   # Claude API Key (없으면 실행 시 입력)
PDF_FOLDER = ""  # PDF 폴더 경로 (없으면 실행 시 입력)
OUTPUT_FILE = "products_db.json"
PROGRESS_FILE = "parse_progress.json"  # 중간 저장 (오류 시 이어서 가능)
DELAY_SEC = 0.5  # API 호출 간격 (초)

# ============================================================
# PDF 텍스트 추출
# ============================================================
def extract_text(pdf_path):
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(pdf_path))
        text = ""
        for page in doc[:6]:  # 앞 6페이지만 (스펙은 보통 앞부분)
            text += page.get_text()
        doc.close()
        return text[:4000]  # 토큰 절약
    except ImportError:
        print("  PyMuPDF 없음 → pip install pymupdf")
        raise
    except Exception as e:
        return ""

# ============================================================
# Claude API로 스펙 추출
# ============================================================
def extract_spec(text, filename, api_key):
    prompt = f"""다음은 전기/전자 제품 PDF에서 추출한 텍스트입니다.
파일명: {filename}

아래 JSON 형식으로 제품 스펙을 추출해주세요. 없는 값은 null로 하세요.
모델이 여러 개면 대표 모델 1개만 추출하세요.

{{
  "brand": "제조사명",
  "cat": "카테고리 (MCCB/CP/ELB/SMPS/Chiller/Motor/PLC/HMI/Terminal/Controller/Laser/Cooling/Pump/Safety/Motion/LED/Other 중 하나)",
  "model": "모델명",
  "rated_A": AC정격전류숫자또는null,
  "v": AC입력전압숫자또는null,
  "ph": 위상수(1또는3)또는null,
  "ow": 출력W숫자또는null,
  "dv": DC출력전압숫자또는null,
  "da": DC출력전류숫자또는null,
  "mul": 1.25
}}

텍스트:
{text}

JSON만 출력하세요. 다른 설명 없이 JSON만."""

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 512,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=30
        )
        result = resp.json()
        if "error" in result:
            print(f"  API 오류: {result['error']['message']}")
            return None
        raw = result["content"][0]["text"]
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception as e:
        print(f"  오류: {e}")
    return None

# ============================================================
# 메인
# ============================================================
def main():
    global API_KEY, PDF_FOLDER

    if not API_KEY:
        API_KEY = input("Claude API Key 입력 (sk-ant-...): ").strip()
    if not PDF_FOLDER:
        PDF_FOLDER = input("PDF 폴더 경로 입력 (예: C:\\Users\\me\\Manuals): ").strip()

    folder = Path(PDF_FOLDER)
    if not folder.exists():
        print(f"폴더가 없습니다: {folder}")
        return

    pdfs = sorted(folder.rglob("*.pdf"))
    print(f"\nPDF {len(pdfs)}개 발견\n")

    # 이전 진행 기록 불러오기
    progress = {}
    if Path(PROGRESS_FILE).exists():
        with open(PROGRESS_FILE, encoding="utf-8") as f:
            progress = json.load(f)
        print(f"이전 기록 {len(progress)}개 불러옴 → 이어서 진행\n")

    products = list(progress.values())
    skipped = 0

    for i, pdf_path in enumerate(pdfs):
        key = str(pdf_path)

        if key in progress:
            skipped += 1
            continue

        print(f"[{i+1}/{len(pdfs)}] {pdf_path.name}")
        text = extract_text(pdf_path)

        if not text.strip():
            print("  ✗ 텍스트 없음 (스캔 이미지 PDF이거나 암호화)")
            progress[key] = None
            continue

        spec = extract_spec(text, pdf_path.name, API_KEY)

        if spec and spec.get("model"):
            spec["id"] = f"p{len([p for p in products if p])+1:03d}"
            products.append(spec)
            progress[key] = spec
            print(f"  ✓ {spec.get('brand','')} {spec.get('model','')} [{spec.get('cat','')}]")
        else:
            progress[key] = None
            print(f"  ✗ 스펙 추출 실패")

        # 중간 저장
        with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(progress, f, ensure_ascii=False, indent=2)

        time.sleep(DELAY_SEC)

    # 최종 저장
    valid = [p for p in products if p]
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(valid, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*50}")
    print(f"완료: {len(valid)}개 제품 추출 ({skipped}개 스킵)")
    print(f"저장: {OUTPUT_FILE}")
    print(f"{'='*50}")
    print(f"\n앱에서 'DB JSON 복원' 버튼으로 불러오세요.")

if __name__ == "__main__":
    main()
