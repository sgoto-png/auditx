"""
build_law_knowledge.py - 労働法令PDFからJSONを生成するスクリプト

使い方:
    python build_law_knowledge.py --law rodo_kijunho --pdf knowledge/rodo_kijun/rodo_kijunho.pdf
    python build_law_knowledge.py --law ikukyu_ho   --pdf knowledge/rodo_kijun/ikukyu_ho.pdf

生成先:
    rule_knowledge/humax_knowledge/law_rodo_kijunho.json
"""

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path

import fitz  # PyMuPDF
from google import genai
from google.genai import types

# ============================================================
# 定数
# ============================================================

MODEL = "gemini-2.5-flash-lite"
MAX_TOKENS = 65536
PAGE_BATCH_SIZE = 20

LAW_NAMES = {
    "rodo_kijunho":   "労働基準法",
    "ikukyu_ho":      "育児介護休業法",
    "part_yuuki_ho":  "パートタイム・有期雇用労働法",
    "rodo_keiyaku_ho":"労働契約法",
    "chingin_shiharai":"賃金の支払の確保等に関する法律",
}

# ============================================================
# PDFユーティリティ
# ============================================================

def get_total_pages(pdf_path: str) -> int:
    doc = fitz.open(pdf_path)
    pages = len(doc)
    doc.close()
    return pages

def extract_page_range_bytes(pdf_path: str, start: int, end: int) -> bytes:
    doc = fitz.open(pdf_path)
    sub = fitz.open()
    sub.insert_pdf(doc, from_page=start, to_page=min(end - 1, len(doc) - 1))
    data = sub.tobytes()
    doc.close()
    sub.close()
    return data

# ============================================================
# Gemini API 呼び出し
# ============================================================

def extract_rules_from_batch(client, pdf_bytes: bytes, law_name: str, batch_label: str) -> dict:
    prompt = f"""あなたは就業規則の専門家です。
添付している「{law_name}」の{batch_label}を精読し、
就業規則チェックの観点から重要な条文・要件を抽出してください。

【抽出してほしい情報】
1. 就業規則に必ず記載が必要な事項（法定記載事項）
2. 就業規則に記載してはいけない内容（法令違反になるパターン）
3. 数値ルール（労働時間・割増率・日数等の具体的な数字）
4. 罰則・制裁に関する規定
5. 就業規則でよく見られる法令違反のパターン
6. 法改正で変わった重要なポイント

【出力形式】
JSONのみで出力。説明文不要。

{{
  "mandatory_provisions": [
    {{"条文": "第●条", "内容": "就業規則への必須記載事項", "alert_level": "CRITICAL"}}
  ],
  "prohibited_patterns": [
    {{"パターン": "違反になる書き方", "理由": "理由", "alert_level": "CRITICAL"}}
  ],
  "numeric_rules": [
    {{"項目": "項目名", "条文": "第●条", "数値": "具体的な数値・割合"}}
  ],
  "common_violations": [
    {{"違反パターン": "よくある違反", "正しい書き方": "正しい記載例", "alert_level": "WARNING"}}
  ]
}}
"""

    pdf_part = {
        "inline_data": {
            "mime_type": "application/pdf",
            "data": base64.b64encode(pdf_bytes).decode(),
        }
    }

    response = client.models.generate_content(
        model=MODEL,
        contents=[prompt, pdf_part],
        config=types.GenerateContentConfig(
            max_output_tokens=MAX_TOKENS,
            temperature=0.0,
        ),
    )

    raw = response.text.strip()
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0].strip()
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0].strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw": raw}


def merge_and_finalize(client, extractions: list, law_name: str, law_id: str) -> dict:
    raw_json = json.dumps(extractions, ensure_ascii=False, indent=2)

    prompt = f"""以下は「{law_name}」から抽出した就業規則チェック用ルールの生データです。

【生データ】
{raw_json}

【作業】
上記を統合・整理して、就業規則チェックツール用の最終JSONを作成してください。
重複を削除し、重要度順に並べてください。

【出力形式】JSONのみ。説明文不要。

{{
  "_meta": {{
    "law_name": "{law_name}",
    "law_id": "{law_id}",
    "description": "就業規則チェック用 {law_name}ルール知識",
    "generated_at": "自動生成"
  }},
  "mandatory_provisions": [],
  "prohibited_patterns": [],
  "numeric_rules": [],
  "common_violations": [],
  "check_instructions": "このJSONを使って就業規則が{law_name}に違反していないかチェックすること。違反が明確な場合はCRITICAL、グレーゾーンはCAUTION、人間確認が必要な場合はHUMAN_CHECKで指摘する。"
}}
"""

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            max_output_tokens=MAX_TOKENS,
            temperature=0.0,
        ),
    )

    raw = response.text.strip()
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0].strip()
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0].strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw": raw, "_error": "JSON解析失敗"}


# ============================================================
# メイン処理
# ============================================================

def build_law_knowledge(law_id: str, pdf_path: str):
    law_name = LAW_NAMES.get(law_id, law_id)
    script_dir = Path(__file__).parent
    output_dir = script_dir / "rule_knowledge" / "humax_knowledge"
    output_path = output_dir / f"law_{law_id}.json"
    output_dir.mkdir(parents=True, exist_ok=True)

    if not Path(pdf_path).exists():
        print(f"❌ PDFが見つかりません: {pdf_path}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  法令知識ビルダー")
    print(f"{'='*60}")
    print(f"  法令名  : {law_name}")
    print(f"  PDF     : {pdf_path}")
    print(f"  出力先  : {output_path}")
    print(f"{'='*60}\n")

    # APIキー取得
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        env_path = script_dir / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("GOOGLE_API_KEY="):
                    api_key = line.split("=", 1)[1].strip()
                    break
    if not api_key:
        print("❌ GOOGLE_API_KEY が設定されていません。")
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    total_pages = get_total_pages(pdf_path)
    batch_ranges = list(range(0, total_pages, PAGE_BATCH_SIZE))
    print(f"📄 全{total_pages}ページ / {len(batch_ranges)}バッチで処理します\n")

    extractions = []
    for i, batch_start in enumerate(batch_ranges):
        batch_end = min(batch_start + PAGE_BATCH_SIZE, total_pages)
        batch_label = f"p.{batch_start+1}〜{batch_end}"
        print(f"  バッチ {i+1}/{len(batch_ranges)}: {batch_label} を抽出中...", end="", flush=True)

        for attempt in range(5):
            try:
                pdf_bytes = extract_page_range_bytes(pdf_path, batch_start, batch_end)
                result = extract_rules_from_batch(client, pdf_bytes, law_name, batch_label)
                extractions.append({"pages": batch_label, "data": result})
                print(" ✅")
                time.sleep(5)
                break
            except Exception as e:
                err_str = str(e)
                if "503" in err_str or "UNAVAILABLE" in err_str or "429" in err_str:
                    wait = 30 * (attempt + 1)
                    print(f" ⏳ サーバー混雑（{attempt+1}回目）{wait}秒待機...")
                    time.sleep(wait)
                else:
                    print(f" ❌ エラー: {e}")
                    time.sleep(10)
                    break
        else:
            print(f" ❌ {batch_label} は5回試行後も失敗しました。スキップします。")

    print(f"\n🔄 {len(extractions)}バッチのデータを統合中...")
    final = None
    for attempt in range(5):
        try:
            final = merge_and_finalize(client, extractions, law_name, law_id)
            break
        except Exception as e:
            err_str = str(e)
            if "503" in err_str or "UNAVAILABLE" in err_str or "429" in err_str:
                wait = 30 * (attempt + 1)
                print(f"  ⏳ サーバー混雑（{attempt+1}回目）{wait}秒待機...")
                time.sleep(wait)
            else:
                print(f"  ❌ 統合エラー: {e}")
                break
    if final is None:
        print("❌ 統合ステップが5回試行後も失敗しました。")
        sys.exit(1)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(final, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 完了！")
    print(f"  出力: {output_path}")
    print(f"  サイズ: {output_path.stat().st_size:,} バイト")
    print(f"\n⚠️ 生成されたJSONは必ず社労士スタッフが確認・修正してください。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--law",  required=True, help=f"法令ID: {list(LAW_NAMES.keys())}")
    parser.add_argument("--pdf",  required=True, help="PDFファイルのパス")
    args = parser.parse_args()
    build_law_knowledge(args.law, args.pdf)
