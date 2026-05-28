"""
audit_engine.py - 就業規則チェックエンジン
就業規則PDF/WordをClaude APIで判定し、処方箋つき監査レポートを生成する。

使い方（単体テスト用）:
    python audit_engine.py \
        --rules rule_knowledge/R08_0408_CA.json \
        --target 就業規則.pdf \
        --course CA \
        --phase phase1 \
        --output outputs/report.md
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import anthropic
import fitz  # PyMuPDF

# python-docx（Wordファイル対応）
try:
    import docx
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

# ============================================================
# 定数
# ============================================================

MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 8192

PHASE_LABELS = {
    "phase1": "Phase1：助成金申請準備開始時（就業規則新規作成後）",
    "phase2": "Phase2：制度導入・規定改訂時",
    "phase3": "Phase3：支給申請提出前（全バージョン整合性確認）",
}

ALERT_ICONS = {
    "CRITICAL":    "🔴",
    "WARNING":     "🟡",
    "CAUTION":     "🟠",
    "HUMAN_CHECK": "👤",
    "OK":          "🟢",
    "INFO":        "ℹ️",
}


# ============================================================
# テキスト抽出
# ============================================================

def extract_text_from_pdf(pdf_path: str) -> str:
    """PDFからテキストを抽出する。"""
    doc = fitz.open(pdf_path)
    text_parts = []
    for page_num, page in enumerate(doc, 1):
        text = page.get_text()
        if text.strip():
            text_parts.append(f"--- {page_num}ページ ---\n{text}")
    doc.close()
    return "\n".join(text_parts)


def extract_text_from_docx(docx_path: str) -> str:
    """WordファイルからテキストをExtractする。"""
    if not DOCX_AVAILABLE:
        raise ImportError("python-docx がインストールされていません。pip install python-docx を実行してください。")

    document = docx.Document(docx_path)
    text_parts = []

    for para in document.paragraphs:
        if para.text.strip():
            text_parts.append(para.text)

    # テーブルも抽出
    for table in document.tables:
        for row in table.rows:
            row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
            if row_text:
                text_parts.append(row_text)

    return "\n".join(text_parts)


def extract_text(file_path: str) -> str:
    """ファイル種別に応じてテキストを抽出する。"""
    ext = Path(file_path).suffix.lower()
    if ext == ".pdf":
        return extract_text_from_pdf(file_path)
    elif ext in (".docx", ".doc"):
        return extract_text_from_docx(file_path)
    else:
        raise ValueError(f"対応していないファイル形式です: {ext}（PDF または Word ファイルを使用してください）")


# ============================================================
# プロンプト生成
# ============================================================

def build_system_prompt(rule_knowledge: dict, course_id: str, phase: str) -> str:
    """システムプロンプトを生成する。"""

    course_name = rule_knowledge.get("meta", {}).get("course_name", course_id)
    year        = rule_knowledge.get("meta", {}).get("year", "")
    eff_date    = rule_knowledge.get("meta", {}).get("effective_date", "")

    # 判定に必要な知識をJSONから抽出してプロンプトに注入
    rule_json = json.dumps(rule_knowledge, ensure_ascii=False, indent=2)

    return f"""あなたは雇用関係助成金の申請業務に特化した社会保険労務士法人のベテラン監査官AIです。
就業規則を助成金の支給要領・Q&A・パンフレットに照らして厳格にチェックし、
不支給リスクをゼロにするための実務的な監査レポートを作成します。

【チェック対象の助成金】
{course_name}（{year}年度 {eff_date}施行版）

【チェックフェーズ】
{PHASE_LABELS.get(phase, phase)}

【判定の根拠知識】
以下のJSONが、このチェックで使用する支給要領・Q&A・パンフレットから抽出した判定ルールです。
このJSON以外の情報（インターネット上の情報等）は一切使用しないこと。

{rule_json}

【監査の姿勢】
- 「たぶん大丈夫」という曖昧な判断は絶対にしない
- 1円・1日・1文字でもズレていたら必ずアラートを出す
- グレーゾーンは「グレーゾーン」として明示し、人間確認を促す
- 不支給になった実例・審査官の目線で生々しく指摘する
- 修正案は条文レベルで具体的に提示する（コピペで使えるレベル）

【出力の制約】
- 問題がない項目も「OK」として明示すること（確認済みの証跡として重要）
- 推測や補完は行わない。就業規則に記載がない場合は「記載なし」として指摘する
- アラートレベルは必ず以下のいずれかを使用すること：
  CRITICAL（不支給確定リスク）/ WARNING（不支給リスクあり）/ CAUTION（グレーゾーン）/ HUMAN_CHECK（人間確認必要）/ OK（問題なし）
"""


def build_user_prompt(rules_text: str, phase: str, additional_courses: list = None) -> str:
    """ユーザープロンプトを生成する。"""

    phase_instruction = {
        "phase1": """
【Phase1 チェック内容】
以下の観点で就業規則をチェックしてください。

A. 全コース共通チェック
   1. 従業員の呼称が全規程で統一されているか
   2. 雇用形態の定義が全規程で矛盾がないか
   3. 全従業員に適用される規程があるか（「別に定める」があるのに規程が存在しない場合はNG）
   4. 支給されている手当が全て定義されているか・定義もれ・記載箇所による順番の相違がないか
   5. 手当の定義（残業代算定含否・固定/変動の別）が明確か
   6. 雇用形態別の給与形態規定に誤りがないか
   7. 最新の労働基準法に抵触する内容がないか
   8. 誤字脱字

B. 助成金コース別チェック
   - 今後申請予定の助成金の要件を満たすための規定が存在するか、または将来の妨げになる規定がないかを確認する
   - 定年規定が助成金申請の妨げになっていないか
   - 昇給・賞与・退職金の規定が助成金要件と矛盾しないか
""",
        "phase2": """
【Phase2 チェック内容】
以下の観点で就業規則をチェックしてください。

A. 全コース共通チェック（Phase1と同様）

B. 導入・改訂内容のチェック
   - 今回新たに導入・改訂した規定の内容が支給要領の要件を満たしているか
   - 必須記載事項が全て含まれているか
   - NG記載パターンが含まれていないか
   - 改訂前後で意図しない変更が生じていないか

C. タイムライン確認
   - 制度導入のタイミングが支給要領の要件を満たしているか（アラート指示を出す）
""",
        "phase3": """
【Phase3 チェック内容】
以下の観点で就業規則の全バージョンをチェックしてください。

A. 全コース共通チェック（Phase1と同様）

B. 全バージョン間の整合性チェック
   - 導入前規則が「取組前要件」を満たしているか
   - 導入後規則が「取組後要件」を満たしているか
   - バージョン間で意図しない矛盾・変更がないか
   - 支給申請対象期間中に有効だった全バージョンに抵触がないか

C. 支給申請書類との整合性（アラート指示）
   - 賃金台帳・労働条件通知書との照合が必要な項目を明示する
   - 過去の助成金申請条文との矛盾確認を促す
""",
    }.get(phase, "")

    additional_info = ""
    if additional_courses:
        additional_info = f"""
【同時申請中の他コース】
{', '.join(additional_courses)}
上記コースとの規定の矛盾・整合性も確認すること。
"""

    return f"""以下の就業規則をチェックしてください。

{phase_instruction}
{additional_info}

【出力形式】
必ず以下の構造でMarkdownレポートを出力してください。

---

# 就業規則チェックレポート

## サマリー
- 🔴 CRITICAL（即時修正必須）: X件
- 🟡 WARNING（要修正）: X件
- 🟠 CAUTION（要確認）: X件
- 👤 HUMAN_CHECK（人間確認）: X件
- 🟢 OK（問題なし）: X件

---

## 詳細チェック結果

### [チェック項目名]

**判定：[アラートレベル] [アイコン]**

**該当箇所：**
（就業規則の条文番号・規程名・具体的な文言を引用）

**問題の内容：**
（何が問題なのか、なぜ不支給になるのかを具体的に説明）

**審査官の目線：**
（労働局の審査官がどのような観点で落とすかを実務的に説明）

**修正案：**
（そのままコピペできる条文案、または人間への確認指示）

**根拠：**
（支給要領・Q&Aの該当箇所）

---

（以降、全チェック項目を同じ形式で出力）

---

## 人間確認が必要な項目一覧
（HUMAN_CHECKの項目をまとめて再掲。担当者が実態確認すべき内容を具体的に指示）

---

【就業規則本文】
{rules_text}
"""


# ============================================================
# チェック実行
# ============================================================

def run_audit(
    rules_text: str,
    rule_knowledge: dict,
    course_id: str,
    phase: str,
    additional_courses: list = None,
) -> str:
    """就業規則チェックを実行してレポートを返す。"""

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        # .envファイルを手動で読み込む
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("ANTHROPIC_API_KEY="):
                        api_key = line.split("=", 1)[1].strip()
                        break

    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY が設定されていません。.env ファイルを確認してください。")

    client = anthropic.Anthropic(api_key=api_key)

    system_prompt = build_system_prompt(rule_knowledge, course_id, phase)
    user_prompt   = build_user_prompt(rules_text, phase, additional_courses)

    print("  Claude API にリクエスト送信中...", end="", flush=True)

    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    print(" 完了")
    return response.content[0].text


# ============================================================
# レポート生成
# ============================================================

def generate_report(
    audit_result: str,
    company_name: str,
    course_id: str,
    phase: str,
    rule_knowledge: dict,
    target_files: list,
) -> str:
    """最終レポートを生成する（ヘッダー情報を付加）。"""

    course_name = rule_knowledge.get("meta", {}).get("course_name", course_id)
    year        = rule_knowledge.get("meta", {}).get("year", "")
    eff_date    = rule_knowledge.get("meta", {}).get("effective_date", "")
    now         = datetime.now().strftime("%Y年%m月%d日 %H:%M")

    header = f"""# 就業規則チェックレポート

| 項目 | 内容 |
|------|------|
| 会社名 | {company_name} |
| チェック日時 | {now} |
| 対象助成金 | {course_name} |
| 適用支給要領 | {year}年度 {eff_date}施行版 |
| チェックフェーズ | {PHASE_LABELS.get(phase, phase)} |
| チェック対象ファイル | {', '.join(target_files)} |

---

"""
    # audit_resultの最初の「# 就業規則チェックレポート」見出しを除去（ヘッダーで代替）
    result_body = audit_result
    if result_body.startswith("# 就業規則チェックレポート"):
        lines = result_body.split("\n")
        result_body = "\n".join(lines[1:]).lstrip("\n")

    return header + result_body


# ============================================================
# メイン処理（単体テスト用）
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="就業規則チェックエンジン（単体テスト用）")
    parser.add_argument("--rules",   required=True, help="判定ルールJSONのパス")
    parser.add_argument("--target",  required=True, nargs="+", help="チェック対象の就業規則ファイル（複数可）")
    parser.add_argument("--course",  required=True, help="コースID（例: CA）")
    parser.add_argument("--phase",   required=True, choices=["phase1", "phase2", "phase3"])
    parser.add_argument("--company", default="テスト会社", help="会社名")
    parser.add_argument("--output",  default=None, help="レポート出力先（省略時は標準出力）")
    parser.add_argument("--additional-courses", nargs="*", default=None, help="同時申請中の他コースID")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  就業規則チェックツール - AuditX")
    print(f"{'='*60}")

    # ルール知識JSONの読み込み
    print(f"\n📚 判定ルールを読み込み中: {args.rules}")
    with open(args.rules, "r", encoding="utf-8") as f:
        rule_knowledge = json.load(f)
    print(f"  ✅ 読み込み完了")

    # 就業規則テキストの抽出
    all_texts = []
    target_filenames = []

    for target_path in args.target:
        print(f"\n📄 就業規則を読み込み中: {target_path}")
        try:
            text = extract_text(target_path)
            filename = os.path.basename(target_path)
            all_texts.append(f"=== {filename} ===\n{text}")
            target_filenames.append(filename)
            print(f"  ✅ {len(text):,}文字を抽出")
        except Exception as e:
            print(f"  ❌ エラー: {e}")
            sys.exit(1)

    combined_text = "\n\n".join(all_texts)

    # チェック実行
    print(f"\n🔍 チェック実行中...")
    print(f"  コース  : {args.course}")
    print(f"  フェーズ: {PHASE_LABELS.get(args.phase, args.phase)}")

    try:
        audit_result = run_audit(
            combined_text,
            rule_knowledge,
            args.course,
            args.phase,
            args.additional_courses,
        )
    except Exception as e:
        print(f"  ❌ APIエラー: {e}")
        sys.exit(1)

    # レポート生成
    report = generate_report(
        audit_result,
        args.company,
        args.course,
        args.phase,
        rule_knowledge,
        target_filenames,
    )

    # 出力
    if args.output:
        os.makedirs(os.path.dirname(args.output) if os.path.dirname(args.output) else ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\n✅ レポートを保存しました: {args.output}")
    else:
        print(f"\n{'='*60}")
        print(report)

    print(f"\n{'='*60}")
    print(f"  チェック完了")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
