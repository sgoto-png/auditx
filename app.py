"""
app.py - AuditX 就業規則チェックツール
Streamlit UIアプリ v0.3
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

# コース正式名称（個別管理）
COURSES = [
    {"id": "CA_seishain",   "group": "キャリアアップ助成金",        "name": "正社員化コース"},
    {"id": "CA_shoyo",      "group": "キャリアアップ助成金",        "name": "賞与・退職金制度導入コース"},
    {"id": "KO65_keizoku",  "group": "65歳超雇用推進助成金",        "name": "65歳超継続雇用促進コース"},
    {"id": "KO65_tenkan",   "group": "65歳超雇用推進助成金",        "name": "高年齢者無期雇用転換コース"},
    {"id": "JK_kanri",      "group": "人材確保等支援助成金",        "name": "雇用管理制度・雇用環境整備助成コース"},
    {"id": "JK_hyoka",      "group": "人材確保等支援助成金",        "name": "人事評価改善等助成コース"},
    {"id": "JH_kyuka",      "group": "人材開発支援助成金",          "name": "教育訓練休暇等付与コース"},
    {"id": "RY_funin",      "group": "両立支援等助成金",            "name": "不妊治療及び女性の健康課題対応両立支援コース"},
    {"id": "RY_juman",      "group": "両立支援等助成金",            "name": "柔軟な働き方選択制度等支援コース"},
    {"id": "RY_shussei",    "group": "両立支援等助成金",            "name": "出生時両立支援コース"},
    {"id": "RY_kaigo",      "group": "両立支援等助成金",            "name": "介護離職防止支援コース"},
    {"id": "RY_ikukyu",     "group": "両立支援等助成金",            "name": "育児休業等支援コース"},
    {"id": "RY_daitai",     "group": "両立支援等助成金",            "name": "育休中等業務代替支援コース"},
]

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
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@300;400;500;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Noto Sans JP', sans-serif;
    background-color: #f4f6fb;
    color: #1a2340;
}
.block-container {
    padding: 2rem 2.5rem 4rem;
    max-width: 1100px;
}

/* サイドバー */
section[data-testid="stSidebar"] {
    background: #1a2340;
    border-right: none;
}
section[data-testid="stSidebar"] * { color: #c8d4e8 !important; }
section[data-testid="stSidebar"] .stMarkdown p { color: #8a9dc0 !important; }

/* ヘッダー */
.auditx-header {
    background: linear-gradient(135deg, #1a2f6e 0%, #1e3a8a 50%, #1d4ed8 100%);
    border-radius: 16px;
    padding: 2.2rem 2.8rem;
    margin-bottom: 2rem;
    position: relative;
    overflow: hidden;
    box-shadow: 0 4px 24px rgba(30,58,138,0.18);
}
.auditx-header::after {
    content: '';
    position: absolute;
    top: -60px; right: -40px;
    width: 300px; height: 300px;
    background: radial-gradient(circle, rgba(255,255,255,0.07) 0%, transparent 70%);
    pointer-events: none;
}
.auditx-header-title {
    font-size: 1.75rem;
    font-weight: 700;
    color: #ffffff;
    margin: 0 0 0.4rem;
    letter-spacing: -0.3px;
    line-height: 1.3;
}
.auditx-header-sub {
    color: #93c5fd;
    font-size: 0.88rem;
    font-weight: 300;
}
.auditx-header .badge-row {
    margin-top: 1.1rem;
    display: flex; gap: 0.5rem; flex-wrap: wrap;
}
.auditx-badge {
    background: rgba(255,255,255,0.12);
    border: 1px solid rgba(255,255,255,0.2);
    border-radius: 99px;
    padding: 3px 11px;
    font-size: 0.73rem;
    color: #dbeafe;
}

/* セクションヘッダー */
.section-header {
    display: flex; align-items: center;
    gap: 10px; margin: 1.8rem 0 1rem;
}
.step-circle {
    width: 30px; height: 30px; border-radius: 50%;
    background: #1d4ed8;
    color: white; font-size: 0.78rem; font-weight: 700;
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0;
    box-shadow: 0 2px 8px rgba(29,78,216,0.35);
}
.section-title {
    font-size: 1rem; font-weight: 600;
    color: #1a2340; letter-spacing: 0.2px;
}

/* カード */
.card {
    background: #ffffff;
    border: 1px solid #e2e8f4;
    border-radius: 12px;
    padding: 1.4rem 1.6rem;
    margin-bottom: 1rem;
    box-shadow: 0 1px 4px rgba(0,0,0,0.05);
}

/* フェーズカード */
.phase-card {
    background: #ffffff;
    border: 2px solid #e2e8f4;
    border-radius: 10px;
    padding: 0.9rem 1.1rem;
    margin-bottom: 6px;
    transition: all 0.15s;
}
.phase-card.active {
    background: #eff6ff;
    border-color: #1d4ed8;
    box-shadow: 0 0 0 1px #1d4ed8;
}
.phase-num {
    font-size: 0.68rem; color: #94a3b8;
    text-transform: uppercase; letter-spacing: 0.1em;
    margin-bottom: 3px;
}
.phase-card.active .phase-num { color: #1d4ed8; }
.phase-label {
    font-size: 0.83rem; font-weight: 500; color: #475569;
}
.phase-card.active .phase-label { color: #1e3a8a; }

/* フェーズ説明 */
.phase-info {
    background: #eff6ff;
    border: 1px solid #bfdbfe;
    border-left: 3px solid #1d4ed8;
    border-radius: 0 8px 8px 0;
    padding: 0.75rem 1.1rem;
    font-size: 0.83rem; color: #1e40af;
    margin-bottom: 1.2rem;
}

/* コース選択カード */
.course-group-label {
    font-size: 0.75rem; font-weight: 600;
    color: #64748b; text-transform: uppercase;
    letter-spacing: 0.08em; margin: 1rem 0 0.4rem;
}
.course-card {
    background: #ffffff;
    border: 1.5px solid #e2e8f4;
    border-radius: 10px;
    padding: 0.9rem 1.1rem 0.7rem;
    margin-bottom: 0.5rem;
    transition: border-color 0.15s;
}
.course-card.selected {
    border-color: #1d4ed8;
    background: #f0f7ff;
}

/* ボタン */
.stButton > button {
    background: #1d4ed8 !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    font-family: 'Noto Sans JP', sans-serif !important;
    font-weight: 500 !important;
    box-shadow: 0 2px 8px rgba(29,78,216,0.25) !important;
    transition: all 0.15s !important;
}
.stButton > button:hover {
    background: #1e40af !important;
    box-shadow: 0 4px 12px rgba(29,78,216,0.35) !important;
    transform: translateY(-1px) !important;
}
.stButton > button:disabled {
    background: #e2e8f4 !important;
    color: #94a3b8 !important;
    box-shadow: none !important;
    transform: none !important;
}

/* 選択中ボタン（アクティブフェーズ） */
.btn-active > .stButton > button {
    background: #1d4ed8 !important;
    color: white !important;
    font-weight: 600 !important;
}
.btn-inactive > .stButton > button {
    background: #f1f5f9 !important;
    color: #64748b !important;
    border: 1.5px solid #cbd5e1 !important;
    box-shadow: none !important;
}
.btn-inactive > .stButton > button:hover {
    background: #e2e8f0 !important;
    border-color: #94a3b8 !important;
    transform: none !important;
    box-shadow: none !important;
}

/* ダウンロードボタン */
.stDownloadButton > button {
    background: #ffffff !important;
    border: 1.5px solid #1d4ed8 !important;
    color: #1d4ed8 !important;
    border-radius: 8px !important;
    font-family: 'Noto Sans JP', sans-serif !important;
}

/* 区切り */
.divider { border: none; border-top: 1px solid #e2e8f4; margin: 1.8rem 0; }

/* サイドバー */
.sb-logo { padding: 0.5rem 0 1.2rem; border-bottom: 1px solid #2a3a5c; margin-bottom: 1rem; }
.sb-logo h2 { font-size: 1.05rem; font-weight: 700; color: #e2e8f0; margin: 0; }
.sb-logo p { font-size: 0.73rem; color: #64748b; margin: 2px 0 0; }
.rule-badge {
    background: #111c35; border: 1px solid #2a3a5c;
    border-radius: 7px; padding: 5px 9px;
    font-size: 0.76rem; color: #60a5fa;
    margin-bottom: 5px; display: block;
}
.sb-footer {
    position: fixed; bottom: 1rem;
    font-size: 0.7rem; color: #334155;
    text-align: center; width: 200px;
}

/* 入力フィールド */
.stTextInput > div > div > input {
    background: #ffffff !important;
    border-color: #cbd5e1 !important;
    color: #1a2340 !important;
    border-radius: 8px !important;
}
.stSelectbox > div > div {
    background: #ffffff !important;
    border-color: #cbd5e1 !important;
    color: #1a2340 !important;
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


def get_available_rule_keys():
    """利用可能なJSONのキーセット {(year, date, course_id)} を返す"""
    rule_dir = Path(__file__).parent / "rule_knowledge"
    keys = set()
    if rule_dir.exists():
        for json_file in rule_dir.glob("*.json"):
            parts = json_file.stem.split("_", 2)
            if len(parts) == 3:
                keys.add(tuple(parts))
    return keys


# ============================================================
# サイドバー
# ============================================================

with st.sidebar:
    st.markdown("""
    <div class="sb-logo">
        <h2>AuditX</h2>
        <p>就業規則チェックツール</p>
    </div>
    """, unsafe_allow_html=True)

    available_keys = get_available_rule_keys()

    st.markdown("**利用可能な判定ルール**")
    if available_keys:
        for year, date, course_id in sorted(available_keys):
            course = next((c for c in COURSES if c["id"] == course_id), None)
            label = f"{year}年度 {date[:2]}月{date[2:]}日〜 {course['name'] if course else course_id}"
            st.markdown(f'<span class="rule-badge">&#10003; {label}</span>', unsafe_allow_html=True)
    else:
        st.warning("判定ルールJSONがありません")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("**チェックフェーズ**")
    for key, desc in PHASE_DESC.items():
        st.markdown(f"**{key.replace('phase','Phase ')}**")
        st.caption(desc)

    st.markdown('<div class="sb-footer">AuditX v0.1<br>Powered by Claude API</div>', unsafe_allow_html=True)


# ============================================================
# メイン
# ============================================================

st.markdown(
    '<div class="auditx-header">'
    '<div class="auditx-header-title">AuditX 就業規則チェックツール</div>'
    '<div class="auditx-header-sub">社会保険労務士法人ヒューマックス向け就業規則チェックシステム'
    ' ／ 業務効率の最大化のために</div>'
    '<div class="badge-row">'
    '<span class="auditx-badge">13コース対応</span>'
    '<span class="auditx-badge">3フェーズ監査</span>'
    '<span class="auditx-badge">処方箋つきレポート</span>'
    '<span class="auditx-badge">PDF / Word 対応</span>'
    '</div>'
    '</div>',
    unsafe_allow_html=True,
)


# ============================================================
# STEP 1 : 会社情報
# ============================================================

st.markdown(
    '<div class="section-header">'
    '<div class="step-circle">1</div>'
    '<div class="section-title">会社情報を入力</div>'
    '</div>',
    unsafe_allow_html=True,
)

col1, col2 = st.columns([3, 2])
with col1:
    company_name = st.text_input("会社名", placeholder="例：株式会社〇〇")
with col2:
    industry = st.text_input("業種", placeholder="例：小売業、サービス業")

st.markdown('<hr class="divider">', unsafe_allow_html=True)


# ============================================================
# STEP 2 : フェーズ選択
# ============================================================

st.markdown(
    '<div class="section-header">'
    '<div class="step-circle">2</div>'
    '<div class="section-title">チェックフェーズを選択</div>'
    '</div>',
    unsafe_allow_html=True,
)

if "selected_phase" not in st.session_state:
    st.session_state.selected_phase = "phase1"

phase_defs = {
    "phase1": ("Phase 1", "申請準備開始時"),
    "phase2": ("Phase 2", "制度導入・改訂時"),
    "phase3": ("Phase 3", "支給申請提出前"),
}

col_p1, col_p2, col_p3 = st.columns(3)
for col, (pk, (pnum, plabel)) in zip([col_p1, col_p2, col_p3], phase_defs.items()):
    is_active = st.session_state.selected_phase == pk
    with col:
        bg    = "#eff6ff" if is_active else "#ffffff"
        border = "#1d4ed8" if is_active else "#e2e8f4"
        bwidth = "2px" if is_active else "1.5px"
        ncolor = "#1d4ed8" if is_active else "#94a3b8"
        lcolor = "#1e3a8a" if is_active else "#475569"
        st.markdown(
            f'<div style="background:{bg};border:{bwidth} solid {border};border-radius:10px;'
            f'padding:0.9rem 1.1rem;margin-bottom:6px;">'
            f'<div style="font-size:0.68rem;color:{ncolor};text-transform:uppercase;'
            f'letter-spacing:0.1em;margin-bottom:3px;">{pnum}</div>'
            f'<div style="font-size:0.83rem;font-weight:500;color:{lcolor};">{plabel}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        btn_class = "btn-active" if is_active else "btn-inactive"
        st.markdown(f'<div class="{btn_class}">', unsafe_allow_html=True)
        if st.button(
            "選択中" if is_active else "選択する",
            key=f"phase_btn_{pk}",
            use_container_width=True,
        ):
            st.session_state.selected_phase = pk
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

selected_phase = st.session_state.selected_phase
st.markdown(
    f'<div class="phase-info">&#128203; {PHASE_DESC.get(selected_phase,"")}</div>',
    unsafe_allow_html=True,
)

st.markdown('<hr class="divider">', unsafe_allow_html=True)


# ============================================================
# STEP 3 : コース選択（コースごとに年度・施行日を選択）
# ============================================================

st.markdown(
    '<div class="section-header">'
    '<div class="step-circle">3</div>'
    '<div class="section-title">申請予定の助成金コースを選択（コースごとに年度・施行日を設定）</div>'
    '</div>',
    unsafe_allow_html=True,
)

# グループ別に表示
selected_courses = []  # [{course_id, year, date, name}]

prev_group = None
for course in COURSES:
    if course["group"] != prev_group:
        st.markdown(
            f'<div class="course-group-label">{course["group"]}</div>',
            unsafe_allow_html=True,
        )
        prev_group = course["group"]

    checked = st.checkbox(
        course["name"],
        key=f"check_{course['id']}",
    )

    if checked:
        c1, c2 = st.columns([1, 1])
        with c1:
            year = st.selectbox(
                "申請年度",
                options=YEAR_OPTIONS,
                format_func=lambda x: f"令和{x[1:]}年度",
                key=f"year_{course['id']}",
                label_visibility="collapsed",
            )
        with c2:
            date_opts = DATE_OPTIONS.get(year, ["0401"])
            date = st.selectbox(
                "施行日",
                options=date_opts,
                format_func=lambda x: f"{x[:2]}月{x[2:]}日以降",
                key=f"date_{course['id']}",
                label_visibility="collapsed",
            )

        # 判定ルールJSONの存在確認
        rule_exists = (year, date, course["id"]) in available_keys
        if not rule_exists:
            st.caption(
                f"⚠️ 令和{year[1:]}年度（{date[:2]}月{date[2:]}日〜）の判定ルールJSONが見つかりません。"
            )

        selected_courses.append({
            "course_id":   course["id"],
            "name":        course["name"],
            "group":       course["group"],
            "year":        year,
            "date":        date,
            "rule_exists": rule_exists,
        })

st.markdown('<hr class="divider">', unsafe_allow_html=True)


# ============================================================
# STEP 4 : ファイルアップロード
# ============================================================

st.markdown(
    '<div class="section-header">'
    '<div class="step-circle">4</div>'
    '<div class="section-title">就業規則ファイルをアップロード</div>'
    '</div>',
    unsafe_allow_html=True,
)

if selected_phase == "phase3":
    st.info(
        "Phase 3 では複数バージョンの就業規則をまとめてアップロードしてください"
        "（制度導入前・導入後・その他改訂分すべて）"
    )

uploaded_files = st.file_uploader(
    "PDF / Word ファイルを選択",
    type=["pdf", "docx", "doc"],
    accept_multiple_files=True,
    label_visibility="collapsed",
)

if uploaded_files:
    for f in uploaded_files:
        st.markdown(f"- **{f.name}**　{f.size/1024:.1f} KB")

with st.expander("担当者メモ（任意）"):
    memo = st.text_area(
        "メモ",
        placeholder="例：転換予定者は〇〇さん（入社3年目）。定年規定の確認が特に重要。",
        height=80,
        label_visibility="collapsed",
    )

st.markdown('<hr class="divider">', unsafe_allow_html=True)


# ============================================================
# 実行ボタン
# ============================================================

valid_courses = [c for c in selected_courses if c["rule_exists"]]
can_run = (
    bool(company_name)
    and bool(valid_courses)
    and bool(uploaded_files)
)

if not can_run:
    missing = []
    if not company_name:    missing.append("会社名")
    if not valid_courses:   missing.append("有効な助成金コース（判定ルールJSONが存在するもの）")
    if not uploaded_files:  missing.append("就業規則ファイル")
    if missing:
        st.caption("未入力・未選択の項目があります：" + "　/　".join(missing))

run_button = st.button(
    "就業規則チェックを開始する",
    disabled=not can_run,
    type="primary",
    use_container_width=True,
)


# ============================================================
# チェック実行
# ============================================================

if run_button and can_run:

    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-header">'
        '<div class="step-circle">5</div>'
        '<div class="section-title">チェック結果</div>'
        '</div>',
        unsafe_allow_html=True,
    )

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
        st.error(
            "ANTHROPIC_API_KEY が設定されていません。"
            "Streamlit Cloud の Secrets を確認してください。"
        )
        st.stop()

    os.environ["ANTHROPIC_API_KEY"] = api_key

    # テキスト抽出
    all_texts = []
    target_filenames = []

    with st.status("就業規則を読み込み中...", expanded=True) as status:
        for uf in uploaded_files:
            st.write(f"読み込み中：{uf.name}")
            try:
                suffix = Path(uf.name).suffix
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(uf.read())
                    tmp_path = tmp.name
                text = extract_text(tmp_path)
                os.unlink(tmp_path)
                all_texts.append(f"=== {uf.name} ===\n{text}")
                target_filenames.append(uf.name)
                st.write(f"完了：{uf.name}（{len(text):,} 文字）")
            except Exception as e:
                st.error(f"エラー：{uf.name}　{e}")
        status.update(label="読み込み完了", state="complete")

    if not all_texts:
        st.stop()

    combined_text = "\n\n".join(all_texts)
    all_reports = []

    for course_info in valid_courses:
        cid    = course_info["course_id"]
        cname  = course_info["name"]
        cgroup = course_info["group"]
        year   = course_info["year"]
        date   = course_info["date"]
        label  = f"{cgroup}　{cname}"

        with st.status(f"判定中：{cname}", expanded=True) as status:
            rule_knowledge = load_rule_knowledge(cid, year, date)
            if not rule_knowledge:
                st.error("判定ルールJSONの読み込みに失敗しました")
                status.update(label=f"エラー：{cname}", state="error")
                continue

            st.write("判定ルール読み込み完了")
            st.write("Claude API で判定中（30秒〜1分ほどかかります）...")

            try:
                other_courses = [
                    f"{c['group']}　{c['name']}"
                    for c in valid_courses if c["course_id"] != cid
                ]
                audit_result = run_audit(
                    combined_text, rule_knowledge, cid,
                    selected_phase,
                    other_courses if other_courses else None,
                )
                report = generate_report(
                    audit_result, company_name, cid,
                    selected_phase, rule_knowledge, target_filenames,
                )
                all_reports.append({
                    "course_id": cid,
                    "label": label,
                    "report": report,
                })
                status.update(label=f"完了：{cname}", state="complete")
            except Exception as e:
                st.error(f"APIエラー：{e}")
                status.update(label=f"エラー：{cname}", state="error")

    # レポート表示
    if all_reports:
        st.success(f"チェック完了　{len(all_reports)} コース")

        if len(all_reports) == 1:
            rd = all_reports[0]
            st.markdown(rd["report"])
            now_str = datetime.now().strftime("%Y%m%d_%H%M")
            st.download_button(
                label="レポートをダウンロード（Markdown）",
                data=rd["report"].encode("utf-8"),
                file_name=f"AuditX_{company_name}_{rd['course_id']}_{selected_phase}_{now_str}.md",
                mime="text/markdown",
                use_container_width=True,
            )
        else:
            tabs = st.tabs([r["label"] for r in all_reports])
            for tab, rd in zip(tabs, all_reports):
                with tab:
                    st.markdown(rd["report"])
                    now_str = datetime.now().strftime("%Y%m%d_%H%M")
                    st.download_button(
                        label="このレポートをダウンロード",
                        data=rd["report"].encode("utf-8"),
                        file_name=f"AuditX_{company_name}_{rd['course_id']}_{selected_phase}_{now_str}.md",
                        mime="text/markdown",
                        key=f"dl_{rd['course_id']}",
                        use_container_width=True,
                    )

            all_combined = "\n\n---\n\n".join(r["report"] for r in all_reports)
            now_str = datetime.now().strftime("%Y%m%d_%H%M")
            st.download_button(
                label="全レポートをまとめてダウンロード",
                data=all_combined.encode("utf-8"),
                file_name=f"AuditX_{company_name}_全コース_{selected_phase}_{now_str}.md",
                mime="text/markdown",
                type="primary",
                use_container_width=True,
            )
