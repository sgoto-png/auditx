"""
app.py - 就業規則チェックツール AuditX
Streamlit UIアプリ

起動方法:
    streamlit run app.py

GitHub + Streamlit Cloud でのデプロイ:
    1. GitHubにpushする
    2. Streamlit Cloudでリポジトリを連携する
    3. Secrets に ANTHROPIC_API_KEY を設定する
"""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

import streamlit as st

from audit_engine import (
    PHASE_LABELS,
    extract_text,
    generate_report,
    run_audit,
)

# ============================================================
# 定数・設定
# ============================================================

# コースID → 表示名
COURSE_OPTIONS = {
    "CA":           "キャリアアップ助成金（正社員化・賞与退職金）",
    "KO65_keizoku": "65歳超雇用推進助成金（継続雇用促進）",
    "KO65_tenkan":  "65歳超雇用推進助成金（無期雇用転換）",
    "JK_kanri":     "人材確保等支援助成金（雇用管理制度）",
    "JK_hyoka":     "人材確保等支援助成金（人事評価改善）",
    "JH_kyuka":     "人材開発支援助成金（教育訓練休暇）",
    "RY_funin":     "両立支援等助成金（不妊治療・女性健康）",
    "RY_juman":     "両立支援等助成金（柔軟な働き方選択）",
    "RY_shussei":   "両立支援等助成金（出生時両立支援）",
    "RY_kaigo":     "両立支援等助成金（介護離職防止）",
    "RY_ikukyu":    "両立支援等助成金（育児休業等支援）",
    "RY_daitai":    "両立支援等助成金（育休中等業務代替）",
}

YEAR_OPTIONS = ["R08", "R07", "R06"]
DATE_OPTIONS = {
    "R08": ["0408", "0401"],
    "R07": ["0401"],
    "R06": ["0401"],
}


# ============================================================
# ルール知識JSONの読み込み
# ============================================================

@st.cache_data
def load_rule_knowledge(course_id: str, year: str, date: str) -> dict | None:
    """指定されたコース・年度・施行日のルール知識JSONを読み込む。"""
    # ローカル実行時のパス
    local_path = Path(__file__).parent / "rule_knowledge" / f"{year}_{date}_{course_id}.json"

    if local_path.exists():
        with open(local_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def get_available_rules() -> list[dict]:
    """利用可能なルール知識JSONの一覧を返す。"""
    rule_dir = Path(__file__).parent / "rule_knowledge"
    available = []
    if rule_dir.exists():
        for json_file in sorted(rule_dir.glob("*.json")):
            stem = json_file.stem  # 例: R08_0408_CA
            parts = stem.split("_", 2)
            if len(parts) >= 3:
                year, date, course_id = parts[0], parts[1], parts[2]
                available.append({
                    "file": json_file,
                    "year": year,
                    "date": date,
                    "course_id": course_id,
                    "label": f"{year}年度（{date[:2]}月{date[2:]}日～）{COURSE_OPTIONS.get(course_id, course_id)}",
                })
    return available


# ============================================================
# ページ設定
# ============================================================

st.set_page_config(
    page_title="AuditX - 就業規則チェックツール",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# カスタムCSS
st.markdown("""
<style>
    /* フォント・カラー設定 */
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&family=JetBrains+Mono&display=swap');

    html, body, [class*="css"] {
        font-family: 'Noto Sans JP', sans-serif;
    }

    /* ヘッダー */
    .main-header {
        background: linear-gradient(135deg, #1a237e 0%, #283593 50%, #1565c0 100%);
        padding: 2rem 2.5rem;
        border-radius: 12px;
        margin-bottom: 2rem;
        color: white;
    }
    .main-header h1 {
        font-size: 2rem;
        font-weight: 700;
        margin: 0;
        letter-spacing: -0.5px;
    }
    .main-header p {
        margin: 0.5rem 0 0;
        opacity: 0.85;
        font-size: 0.95rem;
    }

    /* カード */
    .info-card {
        background: #f8f9ff;
        border: 1px solid #e3e8f0;
        border-left: 4px solid #1a237e;
        border-radius: 8px;
        padding: 1rem 1.25rem;
        margin-bottom: 1rem;
    }

    /* アラートバッジ */
    .badge-critical { background: #ffebee; color: #b71c1c; padding: 3px 10px; border-radius: 99px; font-size: 0.8rem; font-weight: 700; }
    .badge-warning  { background: #fff8e1; color: #e65100; padding: 3px 10px; border-radius: 99px; font-size: 0.8rem; font-weight: 700; }
    .badge-ok       { background: #e8f5e9; color: #1b5e20; padding: 3px 10px; border-radius: 99px; font-size: 0.8rem; font-weight: 700; }

    /* ステップ表示 */
    .step-label {
        background: #1a237e;
        color: white;
        width: 28px;
        height: 28px;
        border-radius: 50%;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-weight: 700;
        font-size: 0.85rem;
        margin-right: 8px;
    }

    /* フッター */
    .footer {
        text-align: center;
        color: #9e9e9e;
        font-size: 0.8rem;
        margin-top: 3rem;
        padding-top: 1rem;
        border-top: 1px solid #e0e0e0;
    }

    /* レポート表示エリア */
    .report-area {
        background: white;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 1.5rem;
    }

    /* Streamlitデフォルトの余白調整 */
    .block-container {
        padding-top: 2rem;
        max-width: 1200px;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================
# サイドバー
# ============================================================

with st.sidebar:
    st.markdown("### ⚖️ AuditX")
    st.markdown("就業規則チェックツール")
    st.divider()

    # 利用可能なルール一覧
    available_rules = get_available_rules()
    if available_rules:
        st.markdown("**📚 利用可能な判定ルール**")
        for rule in available_rules:
            st.markdown(f"- ✅ {rule['label']}")
    else:
        st.warning("判定ルールJSONがありません。\n`rule_knowledge/` フォルダを確認してください。")

    st.divider()
    st.markdown("**📋 チェックフェーズの説明**")
    st.markdown("""
**Phase1** 就業規則新規作成後の初回確認

**Phase2** 制度導入・規定改訂時の確認

**Phase3** 支給申請提出前の最終確認
""")
    st.divider()
    st.markdown('<div class="footer">AuditX v0.1<br>Powered by Claude API</div>', unsafe_allow_html=True)


# ============================================================
# メインコンテンツ
# ============================================================

# ヘッダー
st.markdown("""
<div class="main-header">
    <h1>⚖️ AuditX 就業規則チェックツール</h1>
    <p>助成金申請に特化した社労士法人向け就業規則監査システム ／ 不支給リスクをゼロに</p>
</div>
""", unsafe_allow_html=True)

# ============================================================
# STEP 1: 会社情報・申請情報の入力
# ============================================================

st.markdown("#### STEP 1　会社情報・申請情報を入力")

col1, col2 = st.columns(2)

with col1:
    company_name = st.text_input(
        "会社名 *",
        placeholder="例：株式会社〇〇",
        help="顧問先の会社名を入力してください"
    )

with col2:
    industry = st.text_input(
        "業種",
        placeholder="例：小売業、サービス業、製造業",
    )

col3, col4, col5 = st.columns(3)

with col3:
    selected_year = st.selectbox(
        "申請年度 *",
        options=YEAR_OPTIONS,
        format_func=lambda x: f"令和{x[1:]}年度",
        help="申請する助成金の対象年度を選択してください"
    )

with col4:
    date_options = DATE_OPTIONS.get(selected_year, ["0401"])
    selected_date = st.selectbox(
        "施行日 *",
        options=date_options,
        format_func=lambda x: f"{x[:2]}月{x[2:]}日以降",
        help="取組開始日が該当する施行日を選択してください"
    )

with col5:
    selected_phase = st.selectbox(
        "チェックフェーズ *",
        options=list(PHASE_LABELS.keys()),
        format_func=lambda x: PHASE_LABELS[x].split("：")[0],
        help="今回のチェックのタイミングを選択してください"
    )

# フェーズの説明
st.markdown(f"""
<div class="info-card">
    📋 <strong>{PHASE_LABELS.get(selected_phase, '')}</strong>
</div>
""", unsafe_allow_html=True)

# コース選択
st.markdown("**申請予定の助成金コース *（複数選択可）**")

# 利用可能なコースのみ選択肢に表示
available_course_ids = [r["course_id"] for r in available_rules if r["year"] == selected_year and r["date"] == selected_date]

if not available_course_ids:
    st.warning(f"令和{selected_year[1:]}年度（{selected_date[:2]}月{selected_date[2:]}日～）の判定ルールJSONが見つかりません。先に `build_rule_knowledge.py` を実行してJSONを生成してください。")
    selected_courses = []
else:
    course_cols = st.columns(2)
    selected_courses = []
    for i, course_id in enumerate(available_course_ids):
        col = course_cols[i % 2]
        if col.checkbox(COURSE_OPTIONS.get(course_id, course_id), key=f"course_{course_id}"):
            selected_courses.append(course_id)

st.divider()

# ============================================================
# STEP 2: 就業規則ファイルのアップロード
# ============================================================

st.markdown("#### STEP 2　就業規則ファイルをアップロード")

if selected_phase == "phase3":
    st.info("Phase3では複数バージョンの就業規則をまとめてアップロードしてください（導入前・導入後・改訂分すべて）")

uploaded_files = st.file_uploader(
    "就業規則ファイルを選択（PDF / Word）",
    type=["pdf", "docx", "doc"],
    accept_multiple_files=True,
    help="複数ファイルを同時にアップロードできます"
)

if uploaded_files:
    st.markdown(f"**{len(uploaded_files)}件のファイルが選択されています：**")
    for f in uploaded_files:
        size_kb = f.size / 1024
        st.markdown(f"- 📄 {f.name}（{size_kb:.1f} KB）")

st.divider()

# ============================================================
# STEP 3: メモ・補足情報
# ============================================================

with st.expander("STEP 3　補足情報（任意）"):
    memo = st.text_area(
        "担当者メモ・特記事項",
        placeholder="例：転換予定者は〇〇さん（入社3年目）。定年規定の確認が特に重要。",
        height=100,
    )

    if len(selected_courses) > 1:
        st.info("複数コースが選択されています。コース間の整合性チェックも自動で実行します。")

st.divider()

# ============================================================
# チェック実行ボタン
# ============================================================

# バリデーション
can_run = (
    bool(company_name)
    and bool(selected_courses)
    and bool(uploaded_files)
)

if not can_run:
    missing = []
    if not company_name:
        missing.append("会社名")
    if not selected_courses:
        missing.append("助成金コース")
    if not uploaded_files:
        missing.append("就業規則ファイル")
    st.warning(f"以下の項目を入力・選択してください：{' / '.join(missing)}")

run_button = st.button(
    "🔍　チェックを開始する",
    disabled=not can_run,
    type="primary",
    use_container_width=True,
)

# ============================================================
# チェック実行
# ============================================================

if run_button and can_run:

    st.divider()
    st.markdown("### 📊 チェック結果")

    # APIキーの確認
    api_key = st.secrets.get("ANTHROPIC_API_KEY", os.getenv("ANTHROPIC_API_KEY"))
    if not api_key:
        # .envファイルから読み込みを試みる
        env_path = Path(__file__).parent / ".env"
        if env_path.exists():
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("ANTHROPIC_API_KEY="):
                        api_key = line.split("=", 1)[1].strip()
                        break

    if not api_key:
        st.error("ANTHROPIC_API_KEY が設定されていません。Streamlit CloudのSecretsまたは.envファイルを確認してください。")
        st.stop()

    os.environ["ANTHROPIC_API_KEY"] = api_key

    # 就業規則テキストの抽出
    all_texts = []
    target_filenames = []
    extract_error = False

    with st.status("就業規則を読み込み中...", expanded=True) as status:
        for uploaded_file in uploaded_files:
            st.write(f"📄 {uploaded_file.name} を処理中...")
            try:
                # 一時ファイルに保存してテキスト抽出
                suffix = Path(uploaded_file.name).suffix
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(uploaded_file.read())
                    tmp_path = tmp.name

                text = extract_text(tmp_path)
                os.unlink(tmp_path)  # 一時ファイルを削除

                all_texts.append(f"=== {uploaded_file.name} ===\n{text}")
                target_filenames.append(uploaded_file.name)
                st.write(f"✅ {uploaded_file.name}：{len(text):,}文字を抽出")

            except Exception as e:
                st.error(f"❌ {uploaded_file.name} の読み込みに失敗しました：{e}")
                extract_error = True

        if not extract_error:
            status.update(label="読み込み完了", state="complete")
        else:
            status.update(label="一部ファイルの読み込みに失敗しました", state="error")

    if extract_error or not all_texts:
        st.stop()

    combined_text = "\n\n".join(all_texts)

    # 各コースのチェック実行
    all_reports = []

    for course_id in selected_courses:
        course_label = COURSE_OPTIONS.get(course_id, course_id)

        with st.status(f"チェック実行中：{course_label}...", expanded=True) as status:
            # ルール知識JSONの読み込み
            rule_knowledge = load_rule_knowledge(course_id, selected_year, selected_date)

            if not rule_knowledge:
                st.error(f"❌ {course_label} の判定ルールJSONが見つかりません")
                status.update(label=f"エラー：{course_label}", state="error")
                continue

            st.write(f"📚 判定ルール読み込み完了")
            st.write(f"🔍 Claude APIで判定中（30秒〜1分かかる場合があります）...")

            try:
                # 他のコースを「同時申請中」として渡す
                other_courses = [
                    COURSE_OPTIONS.get(c, c)
                    for c in selected_courses
                    if c != course_id
                ]

                audit_result = run_audit(
                    combined_text,
                    rule_knowledge,
                    course_id,
                    selected_phase,
                    other_courses if other_courses else None,
                )

                report = generate_report(
                    audit_result,
                    company_name,
                    course_id,
                    selected_phase,
                    rule_knowledge,
                    target_filenames,
                )

                all_reports.append({
                    "course_id": course_id,
                    "course_label": course_label,
                    "report": report,
                })

                status.update(label=f"✅ チェック完了：{course_label}", state="complete")

            except Exception as e:
                st.error(f"❌ APIエラー：{e}")
                status.update(label=f"エラー：{course_label}", state="error")

    # ============================================================
    # レポート表示
    # ============================================================

    if all_reports:
        st.success(f"✅ チェック完了（{len(all_reports)}コース）")

        if len(all_reports) == 1:
            # 1コースの場合はそのまま表示
            report_data = all_reports[0]
            st.markdown(report_data["report"])

            # ダウンロードボタン
            now_str = datetime.now().strftime("%Y%m%d_%H%M")
            filename = f"AuditX_{company_name}_{report_data['course_id']}_{selected_phase}_{now_str}.md"
            st.download_button(
                label="📥 レポートをダウンロード（Markdown）",
                data=report_data["report"].encode("utf-8"),
                file_name=filename,
                mime="text/markdown",
                use_container_width=True,
            )

        else:
            # 複数コースの場合はタブで表示
            tab_labels = [r["course_label"] for r in all_reports]
            tabs = st.tabs(tab_labels)

            for tab, report_data in zip(tabs, all_reports):
                with tab:
                    st.markdown(report_data["report"])

                    now_str = datetime.now().strftime("%Y%m%d_%H%M")
                    filename = f"AuditX_{company_name}_{report_data['course_id']}_{selected_phase}_{now_str}.md"
                    st.download_button(
                        label="📥 このレポートをダウンロード",
                        data=report_data["report"].encode("utf-8"),
                        file_name=filename,
                        mime="text/markdown",
                        key=f"dl_{report_data['course_id']}",
                        use_container_width=True,
                    )

            # 全レポートを1ファイルにまとめてダウンロード
            all_combined = "\n\n---\n\n".join(r["report"] for r in all_reports)
            now_str = datetime.now().strftime("%Y%m%d_%H%M")
            st.download_button(
                label="📥 全レポートをまとめてダウンロード",
                data=all_combined.encode("utf-8"),
                file_name=f"AuditX_{company_name}_全コース_{selected_phase}_{now_str}.md",
                mime="text/markdown",
                type="primary",
                use_container_width=True,
            )
