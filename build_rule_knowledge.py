"""
build_rule_knowledge.py - Claude API版
支給要領・Q&A・パンフレットのPDFを読み込み、就業規則チェック用の
判定ルールJSONを自動生成するスクリプト。

使い方:
    python build_rule_knowledge.py --course CA --year R08 --date 0408

引数:
    --course : コースID (例: CA, RY_ikukyu, KO65_keizoku)
    --year   : 年度 (例: R06, R07, R08)
    --date   : 施行日 (例: 0401, 0408) ※同一年度内で複数バージョンがある場合

出力:
    rule_knowledge/{year}_{date}_{course}.json

必要なPDFの配置場所:
    knowledge/{year}_{date}/{course}/
        ├── shikyo_yori.pdf   (支給要領)
        ├── qa.pdf            (Q&A)
        └── pamphlet.pdf      (パンフレット) ※任意
"""

import argparse
import json
import os
import sys
import time

import anthropic
import fitz  # PyMuPDF

# ============================================================
# 定数・設定
# ============================================================

# コースIDと正式名称のマッピング
COURSE_NAMES = {
    "CA":            "キャリアアップ助成金（正社員化コース・賞与退職金制度導入コース）",
    "CA_seishain":   "キャリアアップ助成金（正社員化コース）",
    "CA_shoyo":      "キャリアアップ助成金（賞与・退職金制度導入コース）",
    "KO65_keizoku":  "65歳超雇用推進助成金（65歳超継続雇用促進コース）",
    "KO65_tenkan":   "65歳超雇用推進助成金（高年齢者無期雇用転換コース）",
    "JK_kanri":      "人材確保等支援助成金（雇用管理制度・雇用環境整備助成コース）",
    "JK_hyoka":      "人材確保等支援助成金（人事評価改善等助成コース）",
    "JH_kyuka":      "人材開発支援助成金（教育訓練休暇等付与コース）",
    "RY_funin":      "両立支援等助成金（不妊治療及び女性の健康課題対応両立支援コース）",
    "RY_juman":      "両立支援等助成金（柔軟な働き方選択制度等支援コース）",
    "RY_shussei":    "両立支援等助成金（出生時両立支援コース）",
    "RY_kaigo":      "両立支援等助成金（介護離職防止支援コース）",
    "RY_ikukyu":     "両立支援等助成金（育児休業等支援コース）",
    "RY_daitai":     "両立支援等助成金（育休中等業務代替支援コース）",
}

# PDFファイル名のパターン（フォルダ内で自動検出する際のヒント）
PDF_PATTERNS = {
    "shikyo_yori": ["shikyo_yori", "支給要領", "要領"],
    "qa":          ["qa", "Q&A", "QA", "よくある"],
    "pamphlet":    ["pamphlet", "パンフレット", "案内"],
}

# Claude APIの設定
MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 8192

# 1バッチあたりのPDFページ数（大きすぎるとトークン上限超過）
PAGE_BATCH_SIZE = 15


# ============================================================
# PDFユーティリティ
# ============================================================

def find_pdf_files(folder_path: str) -> dict:
    """
    フォルダ内のPDFを種別（支給要領・Q&A・パンフレット）に分類して返す。
    """
    if not os.path.exists(folder_path):
        return {}

    found = {}
    pdf_files = [f for f in os.listdir(folder_path) if f.lower().endswith(".pdf")]

    for pdf_file in pdf_files:
        pdf_lower = pdf_file.lower()
        for doc_type, patterns in PDF_PATTERNS.items():
            if any(p.lower() in pdf_lower for p in patterns):
                found[doc_type] = os.path.join(folder_path, pdf_file)
                break

    return found


def extract_page_range_bytes(pdf_path: str, start: int, end: int) -> bytes:
    """PDFから指定ページ範囲を抽出してbytesで返す。"""
    doc = fitz.open(pdf_path)
    sub = fitz.open()
    sub.insert_pdf(doc, from_page=start, to_page=min(end - 1, len(doc) - 1))
    data = sub.tobytes()
    doc.close()
    sub.close()
    return data


def get_total_pages(pdf_path: str) -> int:
    """PDFのページ数を返す。"""
    doc = fitz.open(pdf_path)
    pages = len(doc)
    doc.close()
    return pages


# ============================================================
# Claude API 呼び出し
# ============================================================

def extract_rules_from_pdf_batch(
    client: anthropic.Anthropic,
    pdf_bytes: bytes,
    source_filename: str,
    course_name: str,
    doc_type: str,
    batch_label: str,
) -> str:
    """
    PDFの1バッチ分をClaudeに読ませてルールを抽出する。
    戻り値はJSON文字列またはテキスト。
    """
    doc_type_label = {
        "shikyo_yori": "支給要領",
        "qa":          "Q&A",
        "pamphlet":    "パンフレット",
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
7. よくある落とし穴・不支給事例（Q&Aの場合は特に重点的に）
8. 他の助成金との併給調整・注意事項

【出力形式】
抽出した情報をJSONとして出力してください。
キー名は日本語で構いません。
情報が見つからなかった項目は省略して構いません。
このバッチで見つかった情報だけを出力してください。

【重要な制約】
- 厚生労働省が公表する上記資料の記載内容のみを根拠とすること
- インターネット上の他の情報や推測を含めないこと
- 曖昧な場合は「要確認」と記載し、推測で補完しないこと
"""

    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": __import__("base64").b64encode(pdf_bytes).decode(),
                        },
                    },
                    {
                        "type": "text",
                        "text": prompt,
                    },
                ],
            }
        ],
    )

    return response.content[0].text


def merge_and_finalize(
    client: anthropic.Anthropic,
    raw_extractions: list[dict],
    course_name: str,
    course_id: str,
    year: str,
    date: str,
    source_files: list[str],
) -> dict:
    """
    複数バッチ・複数ファイルから抽出した生データを統合・整理して最終JSONを生成する。
    """
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
  "definitions": {{
    // 用語定義。正規雇用労働者・有期雇用労働者・重点支援対象者 等
  }},
  "common_requirements": {{
    // 全コース共通の要件（キャリアアップ計画・受給不可条件・中小企業判定等）
  }},
  "courses": {{
    // コース別の詳細ルール
    // 支給対象事業主の要件、対象労働者の要件、支給額、申請期間、添付書類 等
  }},
  "just_rule_checklist": {{
    // 就業規則チェック専用：以下の観点でまとめること
    "必須記載事項": [
      // 就業規則に必ず書かなければいけない条文・内容
    ],
    "NG記載パターン": [
      // 書いてはいけない表現・不支給になる書き方（具体例付き）
    ],
    "OK記載パターン": [
      // 認められる書き方（具体例付き）
    ],
    "人間確認が必要な項目": [
      // AIでは判定できず、担当者が実態を確認する必要がある項目
    ]
  }},
  "determination_checklist": {{
    // 申請要件の確認用チェックリスト（STEP別）
  }},
  "timeline": {{
    // 取組のタイムライン（取組前・制度導入・取組後・申請期間）
  }},
  "required_documents": {{
    // 添付書類一覧と各書類の確認ポイント
  }},
  "pitfalls": [
    // よくある落とし穴・不支給事例（具体的に）
  ]
}}

【重要な制約】
- 重複する情報は統合・整理すること
- 矛盾する情報は支給要領の記載を優先し、Q&Aで補足すること
- 「就業規則チェック」の観点から実用的な形に整理すること
- 推測・補完は一切しないこと
- 情報が不足している場合は該当フィールドを「要確認」とすること
"""

    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )

    raw_text = response.content[0].text

    # JSON部分を抽出（コードブロックで囲まれている場合に対応）
    if "```json" in raw_text:
        raw_text = raw_text.split("```json")[1].split("```")[0].strip()
    elif "```" in raw_text:
        raw_text = raw_text.split("```")[1].split("```")[0].strip()

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as e:
        print(f"  ⚠️ JSON解析エラー: {e}")
        print("  生テキストをそのまま保存します。")
        return {"_raw_text": raw_text, "_error": str(e)}


# ============================================================
# メイン処理
# ============================================================

def build_rule_knowledge(course_id: str, year: str, date: str):
    """メイン処理：PDFを読み込み、判定ルールJSONを生成する。"""

    # パスの設定
    script_dir   = os.path.dirname(os.path.abspath(__file__))
    project_root = script_dir  # このスクリプトをprojectルートに置く想定

    folder_key   = f"{year}_{date}"
    pdf_folder   = os.path.join(project_root, "knowledge", folder_key, course_id)
    output_dir   = os.path.join(project_root, "rule_knowledge")
    output_path  = os.path.join(output_dir, f"{folder_key}_{course_id}.json")

    os.makedirs(output_dir, exist_ok=True)

    # コース名の取得
    course_name = COURSE_NAMES.get(course_id, course_id)

    print(f"\n{'='*60}")
    print(f"  就業規則チェックツール - ルール知識ビルダー")
    print(f"{'='*60}")
    print(f"  コース  : {course_name}")
    print(f"  年度    : {year}")
    print(f"  施行日  : {date}")
    print(f"  PDFフォルダ: {pdf_folder}")
    print(f"  出力先  : {output_path}")
    print(f"{'='*60}\n")

    # PDFファイルの検索
    pdf_files = find_pdf_files(pdf_folder)

    if not pdf_files:
        print(f"❌ エラー: '{pdf_folder}' にPDFファイルが見つかりません。")
        print("  以下のファイル名パターンで配置してください:")
        print("    支給要領: shikyo_yori.pdf または ファイル名に「支給要領」を含むPDF")
        print("    Q&A    : qa.pdf または ファイル名に「Q&A」を含むPDF")
        print("    パンフ  : pamphlet.pdf または ファイル名に「パンフレット」を含むPDF")
        sys.exit(1)

    print(f"📄 検出されたPDF:")
    source_files = []
    for doc_type, path in pdf_files.items():
        filename = os.path.basename(path)
        print(f"  [{doc_type}] {filename}")
        source_files.append(filename)

    # Claude APIクライアントの初期化
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("\n❌ エラー: ANTHROPIC_API_KEY 環境変数が設定されていません。")
        print("  .env ファイルに ANTHROPIC_API_KEY=sk-ant-... を記載してください。")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    # 各PDFから情報を抽出
    all_extractions = []

    for doc_type, pdf_path in pdf_files.items():
        filename = os.path.basename(pdf_path)
        total_pages = get_total_pages(pdf_path)
        batch_ranges = list(range(0, total_pages, PAGE_BATCH_SIZE))

        doc_label = {"shikyo_yori": "支給要領", "qa": "Q&A", "pamphlet": "パンフレット"}.get(doc_type, doc_type)
        print(f"\n📖 [{doc_label}] {filename} を処理中... (全{total_pages}ページ / {len(batch_ranges)}バッチ)")

        file_extractions = []

        for i, batch_start in enumerate(batch_ranges):
            batch_end   = min(batch_start + PAGE_BATCH_SIZE, total_pages)
            batch_label = f"p.{batch_start + 1}〜{batch_end}"

            print(f"  バッチ {i+1}/{len(batch_ranges)}: {batch_label} を抽出中...", end="", flush=True)

            try:
                pdf_bytes = extract_page_range_bytes(pdf_path, batch_start, batch_end)
                result    = extract_rules_from_pdf_batch(
                    client, pdf_bytes, filename, course_name, doc_type, batch_label
                )

                # JSON文字列の場合はパースを試みる
                try:
                    if "```json" in result:
                        result = result.split("```json")[1].split("```")[0].strip()
                    elif "```" in result:
                        result = result.split("```")[1].split("```")[0].strip()
                    parsed = json.loads(result)
                    file_extractions.append({
                        "source": filename,
                        "doc_type": doc_type,
                        "pages": batch_label,
                        "data": parsed,
                    })
                    print(f" ✅ ({len(str(parsed))}文字)")
                except json.JSONDecodeError:
                    file_extractions.append({
                        "source": filename,
                        "doc_type": doc_type,
                        "pages": batch_label,
                        "data": result,  # テキストのまま保存
                    })
                    print(f" ✅ (テキスト形式)")

                time.sleep(1)  # APIレート制限対策

            except Exception as e:
                print(f" ❌ エラー: {e}")
                time.sleep(3)

        all_extractions.extend(file_extractions)
        print(f"  → [{doc_label}] 完了: {len(file_extractions)}バッチ分抽出")

    # 抽出結果を統合・整理して最終JSONを生成
    print(f"\n🔄 全{len(all_extractions)}バッチのデータを統合中...")
    print("  (この処理には1〜2分かかることがあります)")

    final_json = merge_and_finalize(
        client,
        all_extractions,
        course_name,
        course_id,
        year,
        date,
        source_files,
    )

    # 出力
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(final_json, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 完了！")
    print(f"   出力ファイル: {output_path}")
    print(f"   ファイルサイズ: {os.path.getsize(output_path):,} バイト")
    print(f"\n⚠️  生成されたJSONは必ず社労士スタッフが内容を確認・修正してください。")
    print(f"   AIの自動抽出のため、漏れや誤りが含まれる可能性があります。")


# ============================================================
# エントリポイント
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="支給要領・Q&A・パンフレットPDFから就業規則チェック用のルールJSONを自動生成します"
    )
    parser.add_argument(
        "--course",
        required=True,
        help=f"コースID。選択肢: {', '.join(COURSE_NAMES.keys())}",
    )
    parser.add_argument(
        "--year",
        required=True,
        help="年度（例: R06, R07, R08）",
    )
    parser.add_argument(
        "--date",
        required=True,
        help="施行日（例: 0401, 0408）※同一年度内で複数バージョンがある場合",
    )
    args = parser.parse_args()

    build_rule_knowledge(args.course, args.year, args.date)
