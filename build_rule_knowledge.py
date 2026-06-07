"""
build_rule_knowledge.py - Gemini API版
支給要領・Q&A・パンフレットのPDFを読み込み、就業規則チェック用の
判定ルールJSONを自動生成するスクリプト。

使い方:
    python build_rule_knowledge.py --course CA_seishain --year R08 --date 0408
"""

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path

import fitz  # PyMuPDF
import google.generativeai as genai

# ============================================================
# 定数
# ============================================================

COURSE_NAMES = {
    "CA_seishain": "キャリアアップ助成金（正社員化コース）",
    "CA_shoyo": "キャリアアップ助成金（賞与・退職金制度導入コース）",
    "KO65_keizoku": "65歳超雇用推進助成金（65歳超継続雇用促進コース）",
    "KO65_tenkan": "65歳超雇用推進助成金（高年齢者無期雇用転換コース）",
    "JK_kanri": "人材確保等支援助成金（雇用管理制度・雇用環境整備助成コース）",
    "JK_hyoka": "人材確保等支援助成金（人事評価改善等助成コース）",
    "JH_kyuka": "人材開発支援助成金（教育訓練休暇等付与コース）",
    "RY_funin": "両立支援等助成金（不妊治療及び女性の健康課題対応両立支援コース）",
    "RY_juman": "両立支援等助成金（柔軟な働き方選択制度等支援コース）",
    "RY_shussei": "両立支援等助成金（出生時両立支援コース）",
    "RY_kaigo": "両立支援等助成金（介護離職防止支援コース）",
    "RY_ikukyu": "両立支援等助成金（育児休業等支援コース）",
    "RY_daitai": "両立支援等助成金（育休中等業務代替支援コース）",
}

PDF_PATTERNS = {
    "shikyo_yori": ["shikyo_yori", "支給要領", "要領"],
    "qa": ["qa", "Q&A", "QA", "よくある"],
    "pamphlet": ["pamphlet", "パンフレット", "案内"],
}

MODEL = "gemini-2.5-flash-lite"
MAX_TOKENS = 8192
PAGE_BATCH_SIZE = 15

# ============================================================
# PDFユーティリティ
# ============================================================

def find_pdf_files(folder_path: str) -> dict:
    if not os.path.exists(folder_path):
        return {}
    found = {}
    pdf_files = [f for f in os.listdir(folder_path) if f.lower().endswith(".pdf")]
    for pdf_file in pdf_files:
        pdf_lower = pdf_file.lower()
        matched = False
        for doc_type, patterns in PDF_PATTERNS.items():
            if any(p.lower() in pdf_lower for p in patterns):
                found[doc_type] = os.path.join(folder_path, pdf_file)
                matched = True
                break
        if not matched:
            keys = ['shikyo_yori', 'qa', 'pamphlet']
            for k in keys:
                if k not in found:
                    found[k] = os.path.join(folder_path, pdf_file)
                    break
    return found

def extract_page_range_bytes(pdf_path: str, start: int, end: int) -> bytes:
    doc = fitz.open(pdf_path)
    sub = fitz.open()
    sub.insert_pdf(doc, from_page=start, to_page=min(end - 1, len(doc) - 1))
    data = sub.tobytes()
    doc.close()
    sub.close()
    return data

def get_total_pages(pdf_path: str) -> int:
    doc = fitz.open(pdf_path)
    pages = len(doc)
    doc.close()
    return pages

# ============================================================
# Gemini API 呼び出し
# ============================================================

def extract_rules_from_pdf_batch(
    model,
    pdf_bytes: bytes,
    source_filename: str,
    course_name: str,
    doc_type: str,
    batch_label: str,
) -> str:
    doc_type_label = {
        "shikyo_yori": "支給要領",
        "qa": "Q&A",
        "pamphlet": "パンフレット",
    }.get(doc_type, "資料")

    prompt = f"""
あなたは雇用関係助成金の専門家です。
添付している「{source_filename}」（{doc_type_label}の{batch_label}）を精読し、
「{course_name}」の就業規則チェックに必要な判定ルールをすべて抽出してください。

【抽出してほしい情報】
1. 用語の定義（正規雇用労働者・有期雇用労働者・重点支援対象者 等）
2. 就業規則に必ず記載が必要な事項（必須条文・記載内容の要件）
3. 就業規則に書いてはいけないパターン（NG例・不支給になる書き方）
4. 数値ルール（金額・割合・期間・日数等の具体的な数字）
5. 申請タイムライン（取組前・取組後・申請期間の時系列）
6. 添付書類の要件
7. よくある落とし穴・不支給事例
8. 他の助成金との併給調整・注意事項

【出力形式】
抽出した情報をJSONとして出力してください。
キー名は日本語で構いません。
情報が見つからなかった項目は省略して構いません。

【重要な制約】
- 資料の記載内容のみを根拠とすること
- 推測で補完しないこと
- 曖昧な場合は「要確認」と記載すること
"""

    pdf_part = {
        "mime_type": "application/pdf",
        "data": base64.b64encode(pdf_bytes).decode(),
    }

    response = model.generate_content(
        [prompt, pdf_part],
        generation_config=genai.types.GenerationConfig(
            max_output_tokens=MAX_TOKENS,
            temperature=0.1,
        ),
    )
    return response.text


def merge_and_finalize(
    model,
    raw_extractions: list,
    course_name: str,
    course_id: str,
    year: str,
    date: str,
    source_files: list,
) -> dict:
    raw_json = json.dumps(raw_extractions, ensure_ascii=False, indent=2)

    prompt = f"""
あなたは雇用関係助成金の専門家です。
以下は「{course_name}」の支給要領・Q&A・パンフレットから抽出した判定ルールの生データです。

【生データ】
{raw_json}

【作業内容】
上記の生データを統合・整理して、就業規則チェックツールで使用する最終的なJSONを作成してください。

【最終JSONの構造】
{{
  "meta": {{
    "title": "...",
    "course_id": "{course_id}",
    "course_name": "{course_name}",
    "year": "{year}",
    "effective_date": "{year}年{date[:2]}月{date[2:]}日",
    "source": {json.dumps(source_files, ensure_ascii=False)},
    "generated_at": "（自動生成日時）"
  }},
  "definitions": {{ }},
  "common_requirements": {{ }},
  "courses": {{ }},
  "just_rule_checklist": {{
    "必須記載事項": [],
    "NG記載パターン": [],
    "OK記載パターン": [],
    "人間確認が必要な項目": []
  }},
  "determination_checklist": {{ }},
  "timeline": {{ }},
  "required_documents": {{ }},
  "pitfalls": []
}}

【重要な制約】
- 重複する情報は統合・整理すること
- 推測・補完は一切しないこと
- 情報が不足している場合は「要確認」とすること
- JSONのみ出力すること（前後の説明文は不要）
"""

    response = model.generate_content(
        prompt,
        generation_config=genai.types.GenerationConfig(
            max_output_tokens=MAX_TOKENS,
            temperature=0.1,
        ),
    )

    raw_text = response.text
    if "```json" in raw_text:
        raw_text = raw_text.split("```json")[1].split("```")[0].strip()
    elif "```" in raw_text:
        raw_text = raw_text.split("```")[1].split("```")[0].strip()

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as e:
        print(f"   [WARN] JSON解析エラー: {e}")
        return {"_raw_text": raw_text, "_error": str(e)}

# ============================================================
# メイン処理
# ============================================================

def build_rule_knowledge(course_id: str, year: str, date: str):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    folder_key = f"{year}_{date}"
    pdf_folder = os.path.join(script_dir, "knowledge", folder_key, course_id)
    output_dir = os.path.join(script_dir, "rule_knowledge")
    output_path = os.path.join(output_dir, f"{folder_key}_{course_id}.json")
    os.makedirs(output_dir, exist_ok=True)

    course_name = COURSE_NAMES.get(course_id, course_id)

    print(f"\n{'='*60}")
    print(f"  就業規則チェックツール - ルール知識ビルダー（Gemini版）")
    print(f"{'='*60}")
    print(f"  コース    : {course_name}")
    print(f"  年度      : {year}")
    print(f"  施行日    : {date}")
    print(f"  PDFフォルダ: {pdf_folder}")
    print(f"  出力先    : {output_path}")
    print(f"{'='*60}\n")

    pdf_files = find_pdf_files(pdf_folder)
    if not pdf_files:
        print(f" [NG] エラー: '{pdf_folder}' にPDFファイルが見つかりません。")
        sys.exit(1)

    print(" [PDF] 検出されたPDF:")
    source_files = []
    for doc_type, path in pdf_files.items():
        filename = os.path.basename(path)
        print(f"  [{doc_type}] {filename}")
        source_files.append(filename)

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        env_path = os.path.join(script_dir, ".env")
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("GOOGLE_API_KEY="):
                        api_key = line.split("=", 1)[1].strip()
                        break
    if not api_key:
        print(" [NG] エラー: GOOGLE_API_KEY が設定されていません。")
        sys.exit(1)

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(MODEL)

    all_extractions = []
    for doc_type, pdf_path in pdf_files.items():
        filename = os.path.basename(pdf_path)
        total_pages = get_total_pages(pdf_path)
        batch_ranges = list(range(0, total_pages, PAGE_BATCH_SIZE))
        doc_label = {"shikyo_yori": "支給要領", "qa": "Q&A", "pamphlet": "パンフレット"}.get(doc_type, doc_type)

        print(f"\n [READ] [{doc_label}] {filename} を処理中... (全{total_pages}ページ / {len(batch_ranges)}バッチ)")

        file_extractions = []
        for i, batch_start in enumerate(batch_ranges):
            batch_end = min(batch_start + PAGE_BATCH_SIZE, total_pages)
            batch_label = f"p.{batch_start + 1}〜{batch_end}"
            print(f"  バッチ {i+1}/{len(batch_ranges)}: {batch_label} を抽出中...", end="", flush=True)

            try:
                pdf_bytes = extract_page_range_bytes(pdf_path, batch_start, batch_end)
                result = extract_rules_from_pdf_batch(model, pdf_bytes, filename, course_name, doc_type, batch_label)

                try:
                    if "```json" in result:
                        result = result.split("```json")[1].split("```")[0].strip()
                    elif "```" in result:
                        result = result.split("```")[1].split("```")[0].strip()
                    parsed = json.loads(result)
                    file_extractions.append({"source": filename, "doc_type": doc_type, "pages": batch_label, "data": parsed})
                    print(f"  [OK]")
                except json.JSONDecodeError:
                    file_extractions.append({"source": filename, "doc_type": doc_type, "pages": batch_label, "data": result})
                    print(f"  [OK] (テキスト形式)")

                time.sleep(2)  # レート制限対策

            except Exception as e:
                print(f"  [NG] エラー: {e}")
                time.sleep(5)

        all_extractions.extend(file_extractions)
        print(f"  → [{doc_label}] 完了")

    print(f"\n [MERGE] 全{len(all_extractions)}バッチのデータを統合中...")
    final_json = merge_and_finalize(model, all_extractions, course_name, course_id, year, date, source_files)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(final_json, f, ensure_ascii=False, indent=2)

    print(f"\n [OK] 完了！")
    print(f"  出力ファイル: {output_path}")
    print(f"  ファイルサイズ: {os.path.getsize(output_path):,} バイト")
    print(f"\n [WARN] 生成されたJSONは必ず社労士スタッフが内容を確認・修正してください。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--course", required=True)
    parser.add_argument("--year", required=True)
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    build_rule_knowledge(args.course, args.year, args.date)
