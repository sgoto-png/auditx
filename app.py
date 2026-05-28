"""
app.py - AuditX 就業規則チェックツール v0.4
"""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

import streamlit as st
from audit_engine import PHASE_LABELS, extract_text, generate_report, run_audit

# ============================================================
# 定数
# ============================================================

COURSES = [
    {"id": "CA_seishain",  "group": "キャリアアップ助成金",   "name": "正社員化コース"},
    {"id": "CA_shoyo",     "group": "キャリアアップ助成金",   "name": "賞与・退職金制度導入コース"},
    {"id": "KO65_keizoku", "group": "65歳超雇用推進助成金",   "name": "65歳超継続雇用促進コース"},
    {"id": "KO65_tenkan",  "group": "65歳超雇用推進助成金",   "name": "高年齢者無期雇用転換コース"},
    {"id": "JK_kanri",     "group": "人材確保等支援助成金",   "name": "雇用管理制度・雇用環境整備助成コース"},
    {"id": "JK_hyoka",     "group": "人材確保等支援助成金",   "name": "人事評価改善等助成コース"},
    {"id": "JH_kyuka",     "group": "人材開発支援助成金",     "name": "教育訓練休暇等付与コース"},
    {"id": "RY_funin",     "group": "両立支援等助成金",       "name": "不妊治療及び女性の健康課題対応両立支援コース"},
    {"id": "RY_juman",     "group": "両立支援等助成金",       "name": "柔軟な働き方選択制度等支援コース"},
    {"id": "RY_shussei",   "group": "両立支援等助成金",       "name": "出生時両立支援コース"},
    {"id": "RY_kaigo",     "group": "両立支援等助成金",       "name": "介護離職防止支援コース"},
    {"id": "RY_ikukyu",    "group": "両立支援等助成金",       "name": "育児休業等支援コース"},
    {"id": "RY_daitai",    "group": "両立支援等助成金",       "name": "育休中等業務代替支援コース"},
]

YEAR_OPTIONS = ["R08", "R07", "R06"]
DATE_OPTIONS = {"R08": ["0408", "0401"], "R07": ["0401"], "R06": ["0401"]}

PHASE_ITEMS = {
    "phase1": ("Phase 1", "申請準備開始時", "就業規則新規作成後の初回確認"),
    "phase2": ("Phase 2", "制度導入・改訂時", "導入内容・改訂内容の不備確認"),
    "phase3": ("Phase 3", "支給申請提出前", "全バージョン整合性の最終確認"),
}

# ============================================================
# ページ設定
# ============================================================

st.set_page_config(
    page_title="就業規則チェックツール | Humax",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@300;400;500;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Noto Sans JP', sans-serif;
    background-color: #f0f2f7;
    color: #1e293b;
}
.block-container { padding: 2.5rem 3rem 5rem; max-width: 1000px; }

/* サイドバー */
section[data-testid="stSidebar"] { background: #ffffff; border-right: 1px solid #e8ecf2; }
section[data-testid="stSidebar"] * { color: #334155 !important; }

/* ページタイトルエリア */
.page-eyebrow {
    font-size: 0.7rem; font-weight: 600; letter-spacing: 0.15em;
    color: #94a3b8; text-transform: uppercase; margin-bottom: 0.4rem;
}
.page-title {
    font-size: 2rem; font-weight: 700; color: #0f172a;
    margin: 0 0 0.3rem; letter-spacing: -0.5px; line-height: 1.2;
}
.page-subtitle {
    font-size: 0.85rem; color: #64748b; font-weight: 300;
    margin: 0 0 2rem;
}
.page-divider {
    border: none; border-top: 1px solid #dde3ee; margin: 0 0 2rem;
}

/* セクションラベル */
.sec-label {
    font-size: 0.72rem; font-weight: 700; letter-spacing: 0.12em;
    color: #94a3b8; text-transform: uppercase; margin: 2rem 0 0.8rem;
}

/* カード */
.card {
    background: #ffffff; border: 1px solid #e8ecf2;
    border-radius: 12px; padding: 1.4rem 1.6rem;
    margin-bottom: 0.8rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04), 0 1px 8px rgba(0,0,0,0.03);
}

/* フェーズボタン */
.stButton > button {
    font-family: 'Noto Sans JP', sans-serif !important;
    border-radius: 7px !important;
    font-size: 0.83rem !important;
    font-weight: 500 !important;
    transition: all 0.15s !important;
    border: 1.5px solid #dde3ee !important;
    background: #ffffff !important;
    color: #64748b !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.05) !important;
}
.stButton > button:hover {
    border-color: #3b82f6 !important;
    color: #1d4ed8 !important;
    background: #f0f7ff !important;
    box-shadow: 0 2px 6px rgba(59,130,246,0.15) !important;
}
.btn-selected > button {
    background: #1d4ed8 !important;
    color: #ffffff !important;
    border-color: #1d4ed8 !important;
    box-shadow: 0 2px 8px rgba(29,78,216,0.25) !important;
}
.btn-selected > button:hover {
    background: #1e40af !important;
    color: #ffffff !important;
    border-color: #1e40af !important;
}

/* 実行ボタン */
.run-btn > button {
    background: #1d4ed8 !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 10px !important;
    font-size: 0.95rem !important;
    font-weight: 600 !important;
    padding: 0.7rem 2rem !important;
    box-shadow: 0 3px 12px rgba(29,78,216,0.3) !important;
    letter-spacing: 0.3px !important;
}
.run-btn > button:hover {
    background: #1e40af !important;
    box-shadow: 0 5px 16px rgba(29,78,216,0.4) !important;
    transform: translateY(-1px) !important;
}
.run-btn > button:disabled {
    background: #e2e8f0 !important;
    color: #94a3b8 !important;
    box-shadow: none !important;
    transform: none !important;
    border: none !important;
}

/* ダウンロードボタン */
.stDownloadButton > button {
    background: #ffffff !important;
    border: 1.5px solid #3b82f6 !important;
    color: #1d4ed8 !important;
    border-radius: 8px !important;
    font-family: 'Noto Sans JP', sans-serif !important;
    font-size: 0.85rem !important;
}

/* フェーズ説明 */
.phase-hint {
    background: #f0f7ff; border-left: 3px solid #3b82f6;
    border-radius: 0 8px 8px 0;
    padding: 0.7rem 1rem; font-size: 0.82rem; color: #1e40af;
    margin-top: 0.8rem; margin-bottom: 1.2rem;
}

/* コースグループラベル */
.group-label {
    font-size: 0.72rem; font-weight: 700; letter-spacing: 0.1em;
    color: #94a3b8; text-transform: uppercase;
    padding: 0.6rem 0 0.3rem;
    border-top: 1px solid #e8ecf2; margin-top: 0.8rem;
}
.group-label:first-child { border-top: none; margin-top: 0; }

/* コース選択展開エリア */
.course-expand {
    background: #f8fafc; border: 1px solid #e2e8f0;
    border-radius: 8px; padding: 0.7rem 1rem;
    margin: 0.3rem 0 0.6rem 1.5rem;
}

/* 入力フィールド */
.stTextInput > div > div > input {
    background: #ffffff !important; border-color: #dde3ee !important;
    color: #1e293b !important; border-radius: 8px !important;
    font-family: 'Noto Sans JP', sans-serif !important;
}
.stSelectbox > div > div {
    background: #ffffff !important; border-color: #dde3ee !important;
    color: #1e293b !important;
    font-family: 'Noto Sans JP', sans-serif !important;
}
.stCheckbox > label {
    color: #334155 !important; font-size: 0.88rem !important;
    font-family: 'Noto Sans JP', sans-serif !important;
}

/* サイドバー内装飾 */
.sb-brand {
    padding: 0.8rem 0 1.2rem;
    border-bottom: 1px solid #e8ecf2;
    margin-bottom: 1.2rem;
}
.sb-brand-eye {
    font-size: 0.65rem; font-weight: 700; letter-spacing: 0.15em;
    color: #94a3b8; text-transform: uppercase; margin-bottom: 4px;
}
.sb-brand-title {
    font-size: 1rem; font-weight: 700; color: #0f172a; margin: 0;
}
.sb-brand-sub {
    font-size: 0.72rem; color: #94a3b8; margin: 2px 0 0;
}
.sb-rule-item {
    background: #f8fafc; border: 1px solid #e2e8f0;
    border-radius: 7px; padding: 5px 9px;
    font-size: 0.76rem; color: #3b82f6;
    margin-bottom: 5px; display: block;
}
.sb-footer {
    position: fixed; bottom: 1.2rem;
    font-size: 0.68rem; color: #cbd5e1; text-align: center; width: 200px;
}
.divider { border: none; border-top: 1px solid #dde3ee; margin: 2rem 0; }
</style>
""", unsafe_allow_html=True)


# ============================================================
# ユーティリティ
# ============================================================

@st.cache_data
def load_rule_knowledge(course_id, year, date):
    p = Path(__file__).parent / "rule_knowledge" / f"{year}_{date}_{course_id}.json"
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

def get_available_keys():
    rule_dir = Path(__file__).parent / "rule_knowledge"
    keys = set()
    if rule_dir.exists():
        for jf in rule_dir.glob("*.json"):
            parts = jf.stem.split("_", 2)
            if len(parts) == 3:
                keys.add(tuple(parts))
    return keys


# ============================================================
# サイドバー
# ============================================================

with st.sidebar:
    st.markdown(
        '<div class="sb-brand">'
        '<div class="sb-brand-eye">HUMAX | AUDIT SYSTEM</div>'
        '<div class="sb-brand-title">就業規則チェックツール</div>'
        '<div class="sb-brand-sub">社会保険労務士法人ヒューマックス</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    available_keys = get_available_keys()

    st.markdown("**利用可能な判定ルール**")
    if available_keys:
        for year, date, cid in sorted(available_keys):
            c = next((x for x in COURSES if x["id"] == cid), None)
            label = f"{year}年度 {date[:2]}月{date[2:]}日〜　{c['name'] if c else cid}"
            st.markdown(f'<span class="sb-rule-item">&#10003;&#160;{label}</span>', unsafe_allow_html=True)
    else:
        st.warning("判定ルールJSONがありません")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("**チェックフェーズ**")
    for pk, (pnum, pshort, pdesc) in PHASE_ITEMS.items():
        st.markdown(f"**{pnum}　{pshort}**")
        st.caption(pdesc)

    st.markdown('<div class="sb-footer">AuditX v0.4　Powered by Claude API</div>', unsafe_allow_html=True)


# ============================================================
# メイン：ページヘッダー
# ============================================================

st.markdown(
    '<div class="page-eyebrow">HUMAX | LABOR REGULATION AUDIT SYSTEM</div>'
    '<div class="page-title">就業規則チェックツール（Humax）</div>'
    '<div class="page-subtitle">社会保険労務士法人ヒューマックス向け就業規則チェックシステム'
    '　— 業務効率の最大化のために</div>',
    unsafe_allow_html=True,
)
st.markdown('<hr class="page-divider">', unsafe_allow_html=True)


# ============================================================
# STEP 1 : 会社情報
# ============================================================

st.markdown('<div class="sec-label">STEP 1　会社情報</div>', unsafe_allow_html=True)

col1, col2 = st.columns([3, 2])
with col1:
    company_name = st.text_input("会社名", placeholder="例：株式会社〇〇", label_visibility="collapsed")
with col2:
    industry = st.text_input("業種（任意）", placeholder="例：小売業、サービス業", label_visibility="collapsed")

st.markdown('<hr class="divider">', unsafe_allow_html=True)


# ============================================================
# STEP 2 : フェーズ選択
# ============================================================

st.markdown('<div class="sec-label">STEP 2　チェックフェーズ</div>', unsafe_allow_html=True)

if "selected_phase" not in st.session_state:
    st.session_state.selected_phase = "phase1"

cols_p = st.columns(3)
for col, (pk, (pnum, pshort, pdesc)) in zip(cols_p, PHASE_ITEMS.items()):
    with col:
        is_active = st.session_state.selected_phase == pk
        bg    = "#eff6ff" if is_active else "#ffffff"
        border = "1.5px solid #1d4ed8" if is_active else "1px solid #dde3ee"
        ncolor = "#1d4ed8" if is_active else "#94a3b8"
        lcolor = "#1e3a8a" if is_active else "#334155"
        st.markdown(
            f'<div style="background:{bg};border:{border};border-radius:10px;'
            f'padding:0.85rem 1rem;margin-bottom:6px;'
            f'box-shadow:{"0 0 0 3px #bfdbfe" if is_active else "none"};">'
            f'<div style="font-size:0.68rem;color:{ncolor};text-transform:uppercase;'
            f'letter-spacing:0.12em;font-weight:700;margin-bottom:3px;">{pnum}</div>'
            f'<div style="font-size:0.84rem;font-weight:600;color:{lcolor};margin-bottom:2px;">{pshort}</div>'
            f'<div style="font-size:0.74rem;color:#94a3b8;">{pdesc}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        css_class = "btn-selected" if is_active else ""
        st.markdown(f'<div class="stButton {css_class}">', unsafe_allow_html=True)
        if st.button(
            "選択中 ✓" if is_active else "選択する",
            key=f"pb_{pk}",
            use_container_width=True,
        ):
            st.session_state.selected_phase = pk
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

selected_phase = st.session_state.selected_phase
_, pshort, pdesc = PHASE_ITEMS[selected_phase]
st.markdown(
    f'<div class="phase-hint">&#128203;&#160;<strong>{pshort}</strong>　{pdesc}</div>',
    unsafe_allow_html=True,
)

st.markdown('<hr class="divider">', unsafe_allow_html=True)


# ============================================================
# STEP 3 : コース選択（コースごとに年度・施行日）
# ============================================================

st.markdown('<div class="sec-label">STEP 3　申請予定の助成金コース　（コースごとに年度・施行日を設定）</div>', unsafe_allow_html=True)

selected_courses = []
prev_group = None

for course in COURSES:
    if course["group"] != prev_group:
        st.markdown(f'<div class="group-label">{course["group"]}</div>', unsafe_allow_html=True)
        prev_group = course["group"]

    checked = st.checkbox(course["name"], key=f"chk_{course['id']}")

    if checked:
        c1, c2, c3 = st.columns([2, 2, 3])
        with c1:
            year = st.selectbox(
                "年度",
                YEAR_OPTIONS,
                format_func=lambda x: f"令和{x[1:]}年度",
                key=f"y_{course['id']}",
            )
        with c2:
            date_opts = DATE_OPTIONS.get(year, ["0401"])
            date = st.selectbox(
                "施行日",
                date_opts,
                format_func=lambda x: f"{x[:2]}月{x[2:]}日以降",
                key=f"d_{course['id']}",
            )
        with c3:
            rule_exists = (year, date, course["id"]) in available_keys
            if rule_exists:
                st.success("判定ルール：あり", icon="✓")
            else:
                st.warning(f"令和{year[1:]}年度（{date[:2]}月{date[2:]}日〜）の判定ルールJSONがありません")

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

st.markdown('<div class="sec-label">STEP 4　就業規則ファイルをアップロード</div>', unsafe_allow_html=True)

if selected_phase == "phase3":
    st.info("Phase 3 では導入前・導入後・その他改訂分すべての就業規則をまとめてアップロードしてください。")

col_upload1, col_upload2 = st.columns(2)
with col_upload1:
    st.markdown("**就業規則**（必須・複数可）")
    st.caption("就業規則・賃金規程・育児介護休業規程 等")
    uploaded_files = st.file_uploader(
        "就業規則",
        type=["pdf", "docx", "doc"],
        accept_multiple_files=True,
        label_visibility="collapsed",
        key="main_files",
    )

with col_upload2:
    st.markdown("**補足書類**（任意）")
    st.caption("賃金台帳・労働条件通知書・労使協定書 等")
    supplementary_files = st.file_uploader(
        "補足書類",
        type=["pdf", "docx", "doc", "txt"],
        accept_multiple_files=True,
        label_visibility="collapsed",
        key="sup_files",
    )

if uploaded_files:
    for f in uploaded_files:
        st.caption(f"&#128196;&#160;{f.name}　({f.size/1024:.1f} KB)")

with st.expander("担当者メモ（任意）"):
    st.text_area(
        "メモ",
        placeholder="例：転換予定者は〇〇さん（入社3年目）。定年規定の確認が特に重要。",
        height=70,
        label_visibility="collapsed",
    )

st.markdown('<hr class="divider">', unsafe_allow_html=True)


# ============================================================
# 実行ボタン
# ============================================================

valid_courses = [c for c in selected_courses if c["rule_exists"]]
can_run = bool(company_name) and bool(valid_courses) and bool(uploaded_files)

missing = []
if not company_name:   missing.append("会社名")
if not valid_courses:  missing.append("助成金コース（判定ルールが存在するもの）")
if not uploaded_files: missing.append("就業規則ファイル")
if missing:
    st.caption("未入力の項目：" + "　/　".join(missing))

st.markdown('<div class="run-btn">', unsafe_allow_html=True)
run_button = st.button(
    "チェック開始",
    disabled=not can_run,
    use_container_width=True,
)
st.markdown("</div>", unsafe_allow_html=True)

if not can_run:
    st.caption("就業規則ファイルをアップロードすると「チェック開始」が有効になります。")


# ============================================================
# チェック実行
# ============================================================

if run_button and can_run:

    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    st.markdown('<div class="sec-label">チェック結果</div>', unsafe_allow_html=True)

    # APIキー
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
    all_texts, target_filenames = [], []
    all_upload = list(uploaded_files) + (list(supplementary_files) if supplementary_files else [])

    with st.status("ファイルを読み込み中...", expanded=True) as status:
        for uf in all_upload:
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

    for ci in valid_courses:
        with st.status(f"判定中：{ci['name']}", expanded=True) as status:
            rk = load_rule_knowledge(ci["course_id"], ci["year"], ci["date"])
            if not rk:
                st.error("判定ルールJSONの読み込みに失敗しました")
                status.update(label=f"エラー：{ci['name']}", state="error")
                continue
            st.write("判定ルール読み込み完了")
            st.write("Claude API で判定中（30秒〜1分ほどかかります）...")
            try:
                others = [f"{c['group']}　{c['name']}" for c in valid_courses if c["course_id"] != ci["course_id"]]
                result = run_audit(combined_text, rk, ci["course_id"], selected_phase, others or None)
                report = generate_report(result, company_name, ci["course_id"], selected_phase, rk, target_filenames)
                all_reports.append({"course_id": ci["course_id"], "label": f"{ci['group']}　{ci['name']}", "report": report})
                status.update(label=f"完了：{ci['name']}", state="complete")
            except Exception as e:
                st.error(f"APIエラー：{e}")
                status.update(label=f"エラー：{ci['name']}", state="error")

    if all_reports:
        st.success(f"チェック完了　{len(all_reports)} コース")
        now_str = datetime.now().strftime("%Y%m%d_%H%M")

        if len(all_reports) == 1:
            rd = all_reports[0]
            st.markdown(rd["report"])
            st.download_button(
                "レポートをダウンロード（Markdown）",
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
                    st.download_button(
                        "このレポートをダウンロード",
                        data=rd["report"].encode("utf-8"),
                        file_name=f"AuditX_{company_name}_{rd['course_id']}_{selected_phase}_{now_str}.md",
                        mime="text/markdown",
                        key=f"dl_{rd['course_id']}",
                        use_container_width=True,
                    )
            all_combined = "\n\n---\n\n".join(r["report"] for r in all_reports)
            st.download_button(
                "全レポートをまとめてダウンロード",
                data=all_combined.encode("utf-8"),
                file_name=f"AuditX_{company_name}_全コース_{selected_phase}_{now_str}.md",
                mime="text/markdown",
                type="primary",
                use_container_width=True,
            )

    # フッター
    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    st.caption("就業規則チェックツール（ヒューマックス）　v1.1　|　キャリアアップ助成金 正社員化コース対応")
    st.caption("※ 本ツールは実務補助用です。最終判断は必ず担当社会保険労務士が行ってください。")
