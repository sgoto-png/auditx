"""
app.py - AuditX 就業規則チェックツール
Streamlit UIアプリ（リデザイン版）
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
# 定数
# ============================================================

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

PHASE_DESC = {
    "phase1": "助成金申請準備開始時　就業規則新規作成後の初回確認",
    "phase2": "制度導入・規定改訂時　導入内容・改訂内容の不備確認",
    "phase3": "支給申請提出前　全バージョン整合性の最終確認",
}

# ============================================================
# ページ設定
# ============================================================

st.set_page_config(
    page_title="AuditX | 就業規則チェックツール",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@300;400;500;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Noto Sans JP', sans-serif;
    background-color: #0f1117;
    color: #e8eaf0;
}
.block-container {
    padding: 2rem 2.5rem 4rem;
    max-width: 1100px;
}
section[data-testid="stSidebar"] {
    background: #0a0e1a;
    border-right: 1px solid #1e2640;
}
section[data-testid="stSidebar"] * { color: #c8cde0 !important; }

/* ヘッダー */
.auditx-header {
    background: linear-gradient(135deg, #0d1b3e 0%, #112354 40%, #0d2060 100%);
    border: 1px solid #1e3a8a;
    border-radius: 16px;
    padding: 2.5rem 3rem;
    margin-bottom: 2.5rem;
    position: relative;
    overflow: hidden;
}
.auditx-header::before {
    content: '';
    position: absolute;
    top: -50%; right: -10%;
    width: 400px; height: 400px;
    background: radial-gradient(circle, rgba(99,179,237,0.06) 0%, transparent 70%);
    pointer-events: none;
}
.auditx-header h1 {
    font-size: 2rem; font-weight: 700;
    color: #ffffff; margin: 0 0 0.5rem;
    letter-spacing: -0.5px;
}
.auditx-header .subtitle {
    color: #7ca3d4; font-size: 0.9rem;
    font-weight: 300; letter-spacing: 0.3px;
}
.auditx-header .badge-row {
    margin-top: 1.2rem;
    display: flex; gap: 0.6rem; flex-wrap: wrap;
}
.auditx-badge {
    background: rgba(255,255,255,0.07);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 99px; padding: 3px 12px;
    font-size: 0.75rem; color: #a8bdd4;
}

/* セクションヘッダー */
.section-header {
    display: flex; align-items: center;
    gap: 12px; margin: 2rem 0 1.2rem;
}
.step-circle {
    width: 32px; height: 32px; border-radius: 50%;
    background: linear-gradient(135deg, #1e40af, #2563eb);
    color: white; font-size: 0.8rem; font-weight: 700;
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0; box-shadow: 0 2px 8px rgba(37,99,235,0.4);
}
.section-title {
    font-size: 1rem; font-weight: 500;
    color: #e2e8f0; letter-spacing: 0.3px;
}

/* フェーズ説明 */
.phase-info {
    background: #0d1830;
    border: 1px solid #1a2d52;
    border-left: 3px solid #2563eb;
    border-radius: 0 8px 8px 0;
    padding: 0.8rem 1.2rem;
    font-size: 0.85rem; color: #7ca3d4;
    margin-bottom: 1rem;
}

/* 区切り線 */
.divider {
    border: none; border-top: 1px solid #1e2640;
    margin: 2rem 0;
}

/* ボタン */
.stButton > button {
    background: linear-gradient(135deg, #1e40af 0%, #2563eb 100%) !important;
    color: white !important; border: none !important;
    border-radius: 10px !important;
    font-family: 'Noto Sans JP', sans-serif !important;
    font-size: 0.95rem !important; font-weight: 500 !important;
    box-shadow: 0 4px 16px rgba(37,99,235,0.35) !important;
}
.stButton > button:hover {
    box-shadow: 0 6px 20px rgba(37,99,235,0.5) !important;
    transform: translateY(-1px) !important;
}
.stButton > button:disabled {
    background: #1e2640 !important;
    box-shadow: none !important; color: #4a5568 !important;
}

/* ダウンロードボタン */
.stDownloadButton > button {
    background: #141a2e !important;
    border: 1px solid #2563eb !important;
    color: #60a5fa !important; border-radius: 8px !important;
    font-family: 'Noto Sans JP', sans-serif !important;
}

/* 入力 */
.stTextInput > div > div > input {
    background: #0f1520 !important;
    border-color: #1e2a4a !important;
    color: #e2e8f0 !important; border-radius: 8px !important;
}

/* チェックボックス */
.stCheckbox > label {
    color: #c8cde0 !important; font-size: 0.88rem !important;
}

/* サイドバー */
.sidebar-logo { padding: 0.5rem 0 1rem; border-bottom: 1px solid #1e2640; margin-bottom: 1rem; }
.sidebar-logo h2 { font-size: 1.1rem; font-weight: 700; color: #e2e8f0; margin: 0; }
.sidebar-logo p { font-size: 0.75rem; color: #4a6080; margin: 2px 0 0; }
.rule-badge {
    background: #0d2040; border: 1px solid #1a3a6e;
    border-radius: 8px; padding: 6px 10px;
    font-size: 0.78rem; color: #60a5fa;
    margin-bottom: 6px; display: block;
}
.sidebar-footer {
    position: fixed; bottom: 1rem;
    font-size: 0.72rem; color: #2d3a52;
    text-align: center; width: 200px;
}
</style>
""", unsafe_allow_html=True)


# ============================================================
# ユーティリティ
# ============================================================

@st.cache_data
def load_rule_knowledge(course_id: str, year: str, date: str):
    local_path = Path(__file__).parent / "rule_knowledge" / f"{year}_{date}_{course_id}.json"
    if local_path.exists():
        with open(local_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def get_available_rules():
    rule_dir = Path(__file__).parent / "rule_knowledge"
    available = []
    if rule_dir.exists():
        for json_file in sorted(rule_dir.glob("*.json")):
            stem = json_file.stem
            parts = stem.split("_", 2)
            if len(parts) >= 3:
                year, date, course_id = parts[0], parts[1], parts[2]
                available.append({
                    "file": json_file, "year": year, "date": date,
                    "course_id": course_id,
                    "label": f"{year}年度（{date[:2]}月{date[2:]}日〜）{COURSE_OPTIONS.get(course_id, course_id)}",
                })
    return available


# ============================================================
# サイドバー
# ============================================================

with st.sidebar:
    st.markdown("""
    <div class="sidebar-logo">
        <h2>⚖️ AuditX</h2>
        <p>就業規則チェックツール</p>
    </div>
    """, unsafe_allow_html=True)

    available_rules = get_available_rules()

    st.markdown("**利用可能な判定ルール**")
    if available_rules:
        for rule in available_rules:
            st.markdown(f'<span class="rule-badge">✓ {rule["label"]}</span>', unsafe_allow_html=True)
    else:
        st.warning("判定ルールJSONがありません")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("**チェックフェーズの説明**")
    for key, desc in PHASE_DESC.items():
        phase_num = key.replace("phase", "Phase ")
        st.markdown(f"**{phase_num}**")
        st.caption(desc)

    st.markdown('<div class="sidebar-footer">AuditX v0.1 ／ Powered by Claude API</div>', unsafe_allow_html=True)


# ============================================================
# メイン
# ============================================================

st.markdown("""
<div class="auditx-header">
    <h1>⚖️ AuditX 就業規則チェックツール</h1>
    <div class="subtitle">助成金申請に特化した社労士法人向け就業規則監査システム ／ 不支給リスクをゼロに</div>
    <div class="badge-row">
        <span class="auditx-badge">13コース対応</span>
        <span class="auditx-badge">3フェーズ監査</span>
        <span class="auditx-badge">処方箋つきレポート</span>
        <span class="auditx-badge">PDF / Word 対応</span>
    </div>
</div>
""", unsafe_allow_html=True)


# STEP 1
st.markdown("""
<div class="section-header">
    <div class="step-circle">1</div>
    <div class="section-title">会社情報・申請情報を入力</div>
</div>
""", unsafe_allow_html=True)

col1, col2 = st.columns([3, 2])
with col1:
    company_name = st.text_input("会社名", placeholder="例：株式会社〇〇")
with col2:
    industry = st.text_input("業種", placeholder="例：小売業、サービス業")

col3, col4 = st.columns(2)
with col3:
    selected_year = st.selectbox("申請年度", options=YEAR_OPTIONS, format_func=lambda x: f"令和{x[1:]}年度")
with col4:
    date_options = DATE_OPTIONS.get(selected_year, ["0401"])
    selected_date = st.selectbox("施行日", options=date_options, format_func=lambda x: f"{x[:2]}月{x[2:]}日以降")

# フェーズ選択
st.markdown("**チェックフェーズ**")

if "selected_phase" not in st.session_state:
    st.session_state.selected_phase = "phase1"

phase_labels_short = {
    "phase1": ("Phase 1", "申請準備開始時"),
    "phase2": ("Phase 2", "制度導入・改訂時"),
    "phase3": ("Phase 3", "支給申請提出前"),
}

col_p1, col_p2, col_p3 = st.columns(3)
phase_cols = [col_p1, col_p2, col_p3]

for i, (phase_key, (phase_num, phase_short)) in enumerate(phase_labels_short.items()):
    with phase_cols[i]:
        is_active = st.session_state.selected_phase == phase_key
        bg = "#0f2a5e" if is_active else "#141a2e"
        border = "#2563eb" if is_active else "#1e2a4a"
        num_color = "#60a5fa" if is_active else "#4a6080"
        title_color = "#e2e8f0" if is_active else "#8a9ab8"

        st.markdown(f"""
        <div style="background:{bg};border:1px solid {border};border-radius:10px;
                    padding:1rem 1.2rem;margin-bottom:6px;">
            <div style="font-size:0.7rem;color:{num_color};text-transform:uppercase;
                        letter-spacing:0.1em;margin-bottom:4px;">{phase_num}</div>
            <div style="font-size:0.85rem;font-weight:500;color:{title_color};">{phase_short}</div>
        </div>
        """, unsafe_allow_html=True)

        if st.button(
            "✓ 選択中" if is_active else "選択する",
            key=f"phase_btn_{phase_key}",
            use_container_width=True,
        ):
            st.session_state.selected_phase = phase_key
            st.rerun()

selected_phase = st.session_state.selected_phase

st.markdown(f"""
<div class="phase-info">📋 {PHASE_DESC.get(selected_phase, '')}</div>
""", unsafe_allow_html=True)

# コース選択
available_course_ids = [
    r["course_id"] for r in available_rules
    if r["year"] == selected_year and r["date"] == selected_date
]

st.markdown("**申請予定の助成金コース**（複数選択可）")

selected_courses = []
if not available_course_ids:
    st.warning(f"令和{selected_year[1:]}年度（{selected_date[:2]}月{selected_date[2:]}日〜）の判定ルールJSONが見つかりません。")
else:
    cols = st.columns(2)
    for i, course_id in enumerate(available_course_ids):
        with cols[i % 2]:
            if st.checkbox(COURSE_OPTIONS.get(course_id, course_id), key=f"course_{course_id}"):
                selected_courses.append(course_id)

st.markdown('<hr class="divider">', unsafe_allow_html=True)


# STEP 2
st.markdown("""
<div class="section-header">
    <div class="step-circle">2</div>
    <div class="section-title">就業規則ファイルをアップロード</div>
</div>
""", unsafe_allow_html=True)

if selected_phase == "phase3":
    st.info("Phase 3 では複数バージョンの就業規則をまとめてアップロードしてください（導入前・導入後・改訂分すべて）")

uploaded_files = st.file_uploader(
    "PDF / Word ファイルを選択",
    type=["pdf", "docx", "doc"],
    accept_multiple_files=True,
    label_visibility="collapsed",
)

if uploaded_files:
    for f in uploaded_files:
        st.markdown(f"- 📄 **{f.name}**　{f.size/1024:.1f} KB")

with st.expander("補足情報（任意）"):
    memo = st.text_area(
        "担当者メモ・特記事項",
        placeholder="例：転換予定者は〇〇さん（入社3年目）。定年規定の確認が特に重要。",
        height=80,
    )

st.markdown('<hr class="divider">', unsafe_allow_html=True)


# 実行ボタン
can_run = bool(company_name) and bool(selected_courses) and bool(uploaded_files)

if not can_run:
    missing = []
    if not company_name: missing.append("会社名")
    if not selected_courses: missing.append("助成金コース")
    if not uploaded_files: missing.append("就業規則ファイル")
    st.caption(f"未入力の項目があります：{'　/　'.join(missing)}")

run_button = st.button(
    "🔍　就業規則チェックを開始する",
    disabled=not can_run,
    type="primary",
    use_container_width=True,
)


# ============================================================
# チェック実行
# ============================================================

if run_button and can_run:

    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    st.markdown("""
    <div class="section-header">
        <div class="step-circle">3</div>
        <div class="section-title">チェック結果</div>
    </div>
    """, unsafe_allow_html=True)

    # APIキー取得
    api_key = st.secrets.get("ANTHROPIC_API_KEY", os.getenv("ANTHROPIC_API_KEY"))
    if not api_key:
        env_path = Path(__file__).parent / ".env"
        if env_path.exists():
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("ANTHROPIC_API_KEY=") and "ここに" not in line:
                        api_key = line.split("=", 1)[1].strip()
                        break

    if not api_key:
        st.error("ANTHROPIC_API_KEY が設定されていません。Streamlit Cloud の Secrets を確認してください。")
        st.stop()

    os.environ["ANTHROPIC_API_KEY"] = api_key

    # テキスト抽出
    all_texts = []
    target_filenames = []

    with st.status("就業規則を読み込み中...", expanded=True) as status:
        for uploaded_file in uploaded_files:
            st.write(f"📄 {uploaded_file.name}")
            try:
                suffix = Path(uploaded_file.name).suffix
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(uploaded_file.read())
                    tmp_path = tmp.name
                text = extract_text(tmp_path)
                os.unlink(tmp_path)
                all_texts.append(f"=== {uploaded_file.name} ===\n{text}")
                target_filenames.append(uploaded_file.name)
                st.write(f"✅ {len(text):,} 文字を抽出")
            except Exception as e:
                st.error(f"❌ {uploaded_file.name}：{e}")
        status.update(label="読み込み完了", state="complete")

    if not all_texts:
        st.stop()

    combined_text = "\n\n".join(all_texts)
    all_reports = []

    for course_id in selected_courses:
        course_label = COURSE_OPTIONS.get(course_id, course_id)

        with st.status(f"判定中：{course_label}", expanded=True) as status:
            rule_knowledge = load_rule_knowledge(course_id, selected_year, selected_date)
            if not rule_knowledge:
                st.error(f"判定ルールJSONが見つかりません")
                status.update(label=f"エラー：{course_label}", state="error")
                continue

            st.write("📚 判定ルール読み込み完了")
            st.write("🤖 Claude API で判定中（30秒〜1分ほどかかります）...")

            try:
                other_courses = [COURSE_OPTIONS.get(c, c) for c in selected_courses if c != course_id]
                audit_result = run_audit(
                    combined_text, rule_knowledge, course_id,
                    selected_phase, other_courses if other_courses else None,
                )
                report = generate_report(
                    audit_result, company_name, course_id,
                    selected_phase, rule_knowledge, target_filenames,
                )
                all_reports.append({"course_id": course_id, "course_label": course_label, "report": report})
                status.update(label=f"✅ 完了：{course_label}", state="complete")
            except Exception as e:
                st.error(f"APIエラー：{e}")
                status.update(label=f"エラー：{course_label}", state="error")

    if all_reports:
        st.success(f"チェック完了 ／ {len(all_reports)} コース")

        if len(all_reports) == 1:
            rd = all_reports[0]
            st.markdown(rd["report"])
            now_str = datetime.now().strftime("%Y%m%d_%H%M")
            st.download_button(
                label="📥 レポートをダウンロード（Markdown）",
                data=rd["report"].encode("utf-8"),
                file_name=f"AuditX_{company_name}_{rd['course_id']}_{selected_phase}_{now_str}.md",
                mime="text/markdown",
                use_container_width=True,
            )
        else:
            tabs = st.tabs([r["course_label"] for r in all_reports])
            for tab, rd in zip(tabs, all_reports):
                with tab:
                    st.markdown(rd["report"])
                    now_str = datetime.now().strftime("%Y%m%d_%H%M")
                    st.download_button(
                        label="📥 このレポートをダウンロード",
                        data=rd["report"].encode("utf-8"),
                        file_name=f"AuditX_{company_name}_{rd['course_id']}_{selected_phase}_{now_str}.md",
                        mime="text/markdown",
                        key=f"dl_{rd['course_id']}",
                        use_container_width=True,
                    )

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
