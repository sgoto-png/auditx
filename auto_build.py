"""
auto_build.py - 就業規則チェックツール 自動ビルドスクリプト

PDFを所定のフォルダに置いておけば自動でJSONを生成してgit pushまで行う。
PCの前にいなくても実行可能。

【使い方】
    python auto_build.py

【PDFの配置場所】
    助成金コース:  knowledge\{年度}_{日付}\{コースID}\  例: knowledge\R08_0408\CA_seishain\
    労働法令:      knowledge\rodo_kijun\

【対応コースID】
    CA_seishain / CA_shoyo / KO65_keizoku / KO65_tenkan
    JK_kanri / JK_hyoka / JH_kyuka
    RY_funin / RY_juman / RY_shussei / RY_kaigo / RY_ikukyu / RY_daitai

【ログ】
    auto_build.log に進捗が記録される
"""

import os
import sys
import json
import time
import logging
import subprocess
from pathlib import Path
from datetime import datetime

# ============================================================
# 設定
# ============================================================

SCRIPT_DIR = Path(__file__).parent

# 助成金コースID一覧
COURSE_IDS = [
    "CA_seishain", "CA_shoyo",
    "KO65_keizoku", "KO65_tenkan",
    "JK_kanri", "JK_hyoka",
    "JH_kyuka",
    "RY_funin", "RY_juman", "RY_shussei",
    "RY_kaigo", "RY_ikukyu", "RY_daitai",
]

# 共通PDFフォルダの定義
# _フォルダ名: [対応するコースIDリスト]
COMMON_PDF_FOLDERS = {
    "_CA_common": ["CA_seishain", "CA_shoyo"],
    "_RY_common": ["RY_funin", "RY_juman", "RY_shussei", "RY_kaigo", "RY_ikukyu", "RY_daitai"],
    "_KO65_common": ["KO65_keizoku", "KO65_tenkan"],
    "_JK_common": ["JK_kanri", "JK_hyoka"],
}

def get_common_pdf_folder(year_date_dir: Path, course_id: str) -> Path:
    """コースIDに対応する共通PDFフォルダを返す。なければNone。"""
    for folder_name, course_ids in COMMON_PDF_FOLDERS.items():
        if course_id in course_ids:
            common_path = year_date_dir / folder_name
            if common_path.exists():
                pdfs = list(common_path.glob("*.pdf"))
                if pdfs:
                    return common_path
    return None

# 法令PDFの法令ID（ファイル名から自動判定）
LAW_PDF_TO_ID = {
    "rodo_kijunho.pdf":        "rodo_kijunho",
    "rodo_kijunho_qa.pdf":     "rodo_kijunho_qa",
    "ikukyu_ho.pdf":           "ikukyu_ho",
    "ikukyu_detail.pdf":       "ikukyu_detail",
    "dotsu_chingin.pdf":       "dotsu_chingin",
    "dotsu_chingin_leaf.pdf":  "dotsu_chingin_leaf",
    "hatarakikata.pdf":        "hatarakikata",
}

RETRY_WAIT_BASE = 60   # 秒（503時の待機時間ベース）
RETRY_MAX       = 5    # 最大リトライ回数
BETWEEN_WAIT    = 10   # タスク間の待機秒数

# ============================================================
# ログ設定
# ============================================================

log_path = SCRIPT_DIR / "auto_build.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_path, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# ============================================================
# タスク検出
# ============================================================

def find_course_tasks() -> list:
    """未処理の助成金コースPDFを検出してタスクリストを返す"""
    tasks = []
    knowledge_dir = SCRIPT_DIR / "knowledge"
    rule_dir      = SCRIPT_DIR / "rule_knowledge"

    if not knowledge_dir.exists():
        return tasks

    for year_date_dir in sorted(knowledge_dir.iterdir()):
        if not year_date_dir.is_dir():
            continue
        # フォルダ名を年度_日付に分解 例: R08_0408
        parts = year_date_dir.name.split("_")
        if len(parts) != 2:
            continue
        year, date = parts

        for course_dir in sorted(year_date_dir.iterdir()):
            if not course_dir.is_dir():
                continue
            course_id = course_dir.name
            if course_id not in COURSE_IDS:
                continue

            # 出力JSONが既に存在するか確認（先にチェック）
            output_json = rule_dir / f"{year}_{date}_{course_id}.json"
            if output_json.exists():
                log.info(f"  スキップ（既存）: {year}_{date}_{course_id}")
                continue

            # PDFがあるか確認（コース専用フォルダ優先、なければ共通フォルダ）
            pdfs = list(course_dir.glob("*.pdf"))
            pdf_folder = course_dir
            if not pdfs:
                common_folder = get_common_pdf_folder(year_date_dir, course_id)
                if common_folder:
                    pdfs = list(common_folder.glob("*.pdf"))
                    pdf_folder = common_folder
                    log.info(f"  共通PDFフォルダを使用: {common_folder.name} → {course_id}")
                else:
                    continue

            tasks.append({
                "type":      "course",
                "course_id": course_id,
                "year":      year,
                "date":      date,
                # 実際にPDFが入っているフォルダ（共通フォルダの場合もある）を保存する。
                # course_dir ではなく解決済みの pdf_folder を渡すのが重要。
                "folder":    str(pdf_folder),
                "output":    str(output_json),
            })

    return tasks


def find_law_tasks() -> list:
    """未処理の法令PDFを検出してタスクリストを返す"""
    tasks = []
    law_dir    = SCRIPT_DIR / "knowledge" / "rodo_kijun"
    output_dir = SCRIPT_DIR / "rule_knowledge" / "humax_knowledge"

    if not law_dir.exists():
        return tasks

    for pdf_file in sorted(law_dir.glob("*.pdf")):
        law_id = LAW_PDF_TO_ID.get(pdf_file.name)
        if not law_id:
            # ファイル名から推測
            law_id = pdf_file.stem
            log.info(f"  法令ID自動推測: {pdf_file.name} → {law_id}")

        output_json = output_dir / f"law_{law_id}.json"
        if output_json.exists():
            log.info(f"  スキップ（既存）: law_{law_id}")
            continue

        tasks.append({
            "type":    "law",
            "law_id":  law_id,
            "pdf":     str(pdf_file),
            "output":  str(output_json),
        })

    return tasks


# ============================================================
# タスク実行
# ============================================================

def run_with_retry(cmd: list, task_name: str) -> bool:
    """コマンドをリトライ付きで実行。成功したらTrue。"""
    for attempt in range(1, RETRY_MAX + 1):
        log.info(f"  実行中（{attempt}回目）: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        output = result.stdout + result.stderr

        if result.returncode == 0:
            log.info(f"  [OK] 完了: {task_name}")
            return True

        # 503/429/UNAVAILABLE エラーの場合はリトライ
        if any(x in output for x in ["503", "UNAVAILABLE", "429", "high demand"]):
            wait = RETRY_WAIT_BASE * attempt
            log.warning(f"  [WAIT] サーバー混雑（{attempt}回目）。{wait}秒後にリトライ...")
            time.sleep(wait)
            continue

        # その他のエラーはスキップ
        log.error(f"  [ERROR] エラー（スキップ）: {task_name}")
        log.error(f"     {output[-500:]}")
        return False

    log.error(f"  [ERROR] {RETRY_MAX}回試行後も失敗: {task_name}")
    return False


def execute_course_task(task: dict) -> bool:
    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "build_rule_knowledge.py"),
        "--course", task["course_id"],
        "--year",   task["year"],
        "--date",   task["date"],
        # 検出時に解決したPDFフォルダ（共通フォルダの場合もある）を明示的に渡す
        "--pdf-folder", task["folder"],
    ]
    return run_with_retry(cmd, f"{task['year']}_{task['date']}_{task['course_id']}")


def execute_law_task(task: dict) -> bool:
    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "build_law_knowledge.py"),
        "--law", task["law_id"],
        "--pdf", task["pdf"],
    ]
    return run_with_retry(cmd, f"law_{task['law_id']}")


# ============================================================
# Git push
# ============================================================

def git_push(completed_tasks: list):
    """完了したタスクをgit add/commit/pushする"""
    if not completed_tasks:
        return

    log.info("\n[PUSH] GitHubにpush中...")

    # git add
    subprocess.run(["git", "add", "."], cwd=SCRIPT_DIR, capture_output=True)

    # git commit
    names = ", ".join(
        t.get("course_id") or t.get("law_id") for t in completed_tasks
    )
    msg = f"Auto build: {names} [{datetime.now().strftime('%Y-%m-%d %H:%M')}]"
    result = subprocess.run(
        ["git", "commit", "-m", msg],
        cwd=SCRIPT_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if "nothing to commit" in result.stdout + result.stderr:
        log.info("  変更なし（pushスキップ）")
        return

    # git push（リトライあり）
    for attempt in range(1, 4):
        result = subprocess.run(
            ["git", "push"],
            cwd=SCRIPT_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if result.returncode == 0:
            log.info(f"  [OK] push完了: {msg}")
            return
        log.warning(f"  push失敗（{attempt}回目）。30秒後にリトライ...")
        time.sleep(30)

    log.error("  [ERROR] pushに失敗しました。手動でpushしてください。")


# ============================================================
# メイン
# ============================================================

def main():
    log.info("=" * 60)
    log.info("  AuditX 自動ビルドスクリプト 開始")
    log.info(f"  開始時刻: {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}")
    log.info("=" * 60)

    # タスク収集
    course_tasks = find_course_tasks()
    law_tasks    = find_law_tasks()
    all_tasks    = course_tasks + law_tasks

    if not all_tasks:
        log.info("\n[OK] 処理対象のPDFが見つかりませんでした。")
        log.info("   以下のフォルダにPDFを配置してから再実行してください:")
        log.info("   助成金: knowledge\\{年度}_{日付}\\{コースID}\\")
        log.info("   法令:   knowledge\\rodo_kijun\\")
        return

    log.info(f"\n[LIST] 処理対象: {len(all_tasks)}件")
    for t in all_tasks:
        if t["type"] == "course":
            log.info(f"  [助成金] {t['year']}_{t['date']}_{t['course_id']}")
        else:
            log.info(f"  [法令]   law_{t['law_id']}")

    log.info("")

    # タスク実行
    completed = []
    failed    = []

    for i, task in enumerate(all_tasks, 1):
        name = (task.get("course_id") or task.get("law_id"))
        log.info(f"\n[{i}/{len(all_tasks)}] 処理中: {name}")

        if task["type"] == "course":
            ok = execute_course_task(task)
        else:
            ok = execute_law_task(task)

        if ok:
            completed.append(task)
            # 5件ごとにpush
            if len(completed) % 5 == 0:
                git_push(completed[-5:])
        else:
            failed.append(task)

        # タスク間の待機
        if i < len(all_tasks):
            log.info(f"  {BETWEEN_WAIT}秒待機中...")
            time.sleep(BETWEEN_WAIT)

    # 最終push
    remaining = [t for t in completed if t not in completed[::5]]
    git_push(completed)

    # 結果サマリー
    log.info("\n" + "=" * 60)
    log.info("  処理完了")
    log.info(f"  [OK] 成功: {len(completed)}件")
    log.info(f"  [ERROR] 失敗: {len(failed)}件")
    if failed:
        log.info("  失敗したタスク:")
        for t in failed:
            name = t.get("course_id") or t.get("law_id")
            log.info(f"    - {name}")
    log.info(f"  終了時刻: {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}")
    log.info("=" * 60)
    log.info(f"\n[LOG] ログファイル: {log_path}")


if __name__ == "__main__":
    main()
