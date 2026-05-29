"""
audit_engine.py - 就業規則チェックエンジン（Gemini API版）
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import google.generativeai as genai
import fitz  # PyMuPDF

try:
    import docx
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

# ============================================================
# 定数
# ============================================================

MODEL = "gemini-1.5-pro"
MAX_TOKENS = 8192

PHASE_LABELS = {
    "phase1": "Phase1：助成金申請準備開始時（就業規則新規作成後）",
    "phase2": "Phase2：制度導入・規定改訂時",
    "phase3": "Phase3：支給申請提出前（全バージョン整合性確認）",
}

ALERT_ICONS = {
    "CRITICAL": "🔴",
    "WARNING": "🟡",
    "CAUTION": "🟠",
    "HUMAN_CHECK": "👤",
    "OK": "🟢",
    "INFO": "ℹ️",
}

# ============================================================
# テキスト抽出
# ============================================================

def extract_text_from_pdf(pdf_path: str) -> str:
    doc = fitz.open(pdf_path)
    text_parts = []
    for page_num, page in enumerate(doc, 1):
        text = page.get_text()
        if text.strip():
            text_parts.append(f"--- {page_num}ページ ---\n{text}")
    doc.close()
    return "\n".join(text_parts)

def extract_text_from_docx(docx_path: str) -> str:
    if not DOCX_AVAILABLE:
        raise ImportError("python-docx がインストールされていません。")
    document = docx.Document(docx_path)
    text_parts = []
    for para in document.paragraphs:
        if para.text.strip():
            text_parts.append(para.text)
    for table in document.tables:
        for row in table.rows:
            row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
            if row_text:
                text_parts.append(row_text)
    return "\n".join(text_parts)

def extract_text(file_path: str) -> str:
    ext = Path(file_path).suffix.lower()
    if ext == ".pdf":
        return extract_text_from_pdf(file_path)
    elif ext in (".docx", ".doc"):
        return extract_text_from_docx(file_path)
    else:
        raise ValueError(f"対応していないファイル形式です: {ext}")

# ============================================================
# プロンプト生成
# ============================================================

def build_prompt(rule_knowledge: dict, course_id: str, phase: str,
                 rules_text: str, additional_courses: list = None) -> str:
    course_name = rule_knowledge.get("meta", {}).get("course_name", course_id)
    year = rule_knowledge.get("meta", {}).get("year", "")
    eff_date = rule_knowledge.get("meta", {}).get("effective_date", "")
    rule_json = json.dumps(rule_knowledge, ensure_ascii=False, indent=2)

    phase_instruction = {
        "phase1": """
【Phase1 チェック内容】
A. 全コース共通チェック
1. 従業員の呼称が全規程で統一されているか
2. 雇用形態の定義が全規程で矛盾がないか
3. 全従業員に適用される規程があるか
4. 支給されている手当が全て定義されているか
5. 手当の定義（残業代算定含否・固定/変動の別）が明確か
6. 雇用形態別の給与形態規定に誤りがないか
7. 最新の労働基準法に抵触する内容がないか
8. 誤字脱字

B. 助成金コース別チェック
- 申請予定の助成金の要件を満たすための規定が存在するか
- 定年規定が助成金申請の妨げになっていないか
- 昇給・賞与・退職金の規定が助成金要件と矛盾しないか
""",
        "phase2": """
【Phase2 チェック内容】
A. 全コース共通チェック（Phase1と同様）
B. 導入・改訂内容のチェック
- 今回新たに導入・改訂した規定の内容が支給要領の要件を満たしているか
- 必須記載事項が全て含まれているか
- NG記載パターンが含まれていないか
C. タイムライン確認
- 制度導入のタイミングが支給要領の要件を満たしているか
""",
        "phase3": """
【Phase3 チェック内容】
A. 全コース共通チェック（Phase1と同様）
B. 全バージョン間の整合性チェック
- 導入前規則が「取組前要件」を満たしているか
- 導入後規則が「取組後要件」を満たしているか
- バージョン間で意図しない矛盾・変更がないか
C. 支給申請書類との整合性
- 賃金台帳・労働条件通知書との照合が必要な項目を明示
""",
    }.get(phase, "")

    additional_info = ""
    if additional_courses:
        additional_info = f"""
【同時申請中の他コース】
{', '.join(additional_courses)}
上記コースとの規定の矛盾・整合性も確認すること。
"""

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
- 問題がない項目も「OK」として明示すること
- 推測や補完は行わない。記載がない場合は「記載なし」として指摘する
- アラートレベルは必ず以下のいずれかを使用すること：
  CRITICAL（不支給確定リスク）/ WARNING（不支給リスクあり）/ CAUTION（グレーゾーン）/ HUMAN_CHECK（人間確認必要）/ OK（問題なし）

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
（HUMAN_CHECKの項目をまとめて再掲）

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
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("GOOGLE_API_KEY="):
                        api_key = line.split("=", 1)[1].strip()
                        break
    if not api_key:
        raise ValueError("GOOGLE_API_KEY が設定されていません。")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(MODEL)

    prompt = build_prompt(rule_knowledge, course_id, phase, rules_text, additional_courses)

    response = model.generate_content(
        prompt,
        generation_config=genai.types.GenerationConfig(
            max_output_tokens=MAX_TOKENS,
            temperature=0.1,
        ),
    )
    return response.text

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
    course_name = rule_knowledge.get("meta", {}).get("course_name", course_id)
    year = rule_knowledge.get("meta", {}).get("year", "")
    eff_date = rule_knowledge.get("meta", {}).get("effective_date", "")
    now = datetime.now().strftime("%Y年%m月%d日 %H:%M")

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
    result_body = audit_result
    if result_body.startswith("# 就業規則チェックレポート"):
        lines = result_body.split("\n")
        result_body = "\n".join(lines[1:]).lstrip("\n")

    return header + result_body
