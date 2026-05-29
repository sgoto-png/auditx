"""
app.py - AuditX 就業規則チェックツール v0.5
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
    "phase1": ("PHASE 1", "申請準備開始時", "就業規則新規作成後の初回確認"),
    "phase2": ("PHASE 2", "制度導入・改訂時", "導入内容・改訂内容の不備確認"),
    "phase3": ("PHASE 3", "支給申請提出前", "全バージョン整合性の最終確認"),
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
    background-color: #f5f6f9;
    color: #1e293b;
}
.block-container { padding: 2.5rem 3rem 5rem; max-width: 1000px; }

section[data-testid="stSidebar"] {
    background: #0d1b30;
    border-right: none;
}
section[data-testid="stSidebar"] * { color: #b0bec5 !important; }
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3,
section[data-testid="stSidebar"] strong { color: #e8dfc0 !important; }

.page-eyebrow {
    font-size: 0.68rem; font-weight: 700; letter-spacing: 0.18em;
    color: #c8a84a; text-transform: uppercase; margin-bottom: 0.5rem;
}
.page-title {
    font-size: 2.1rem; font-weight: 700; color: #0f172a;
    margin: 0 0 0.4rem; letter-spacing: -0.5px; line-height: 1.2;
}
.page-subtitle {
    font-size: 0.85rem; color: #64748b; font-weight: 400; margin: 0 0 2rem;
}
.page-divider { border: none; border-top: 2px solid #dde2ea; margin: 0 0 2rem; }

.sec-label {
    font-size: 0.72rem; font-weight: 700; letter-spacing: 0.16em;
    color: #c8a84a; text-transform: uppercase;
    display: flex; align-items: center; gap: 12px;
    margin: 2rem 0 1rem;
}
.sec-label::after {
    content: '';
    flex: 1;
    height: 1.5px;
    background: linear-gradient(to right, #c8a84a55, transparent);
}

.card {
    background: #ffffff; border: 1px solid #dde2ea;
    border-radius: 12px; padding: 1.4rem 1.6rem;
    margin-bottom: 0.8rem;
    box-shadow: 0 2px 6px rgba(0,0,0,0.05);
}

.phase-active {
    background: #ffffff;
    border: 1.5px solid #c8a84a;
    border-radius: 10px; padding: 0.9rem 1rem; margin-bottom: 6px;
    box-shadow: 0 4px 14px rgba(200,168,74,0.18);
}
.phase-inactive {
    background: #ffffff; border: 1.5px solid #dde2ea;
    border-radius: 10px; padding: 0.9rem 1rem; margin-bottom: 6px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}
.phase-num-active {
    font-size: 0.68rem; font-weight: 700; color: #c8a84a;
    text-transform: uppercase; letter-spacing: 0.14em; margin-bottom: 3px;
}
.phase-num-inactive {
    font-size: 0.68rem; font-weight: 700; color: #94a3b8;
    text-transform: uppercase; letter-spacing: 0.14em; margin-bottom: 3px;
}
.phase-title-active {
    font-size: 0.9rem; font-weight: 700; color: #0f172a; margin-bottom: 2px;
}
.phase-title-inactive {
    font-size: 0.9rem; font-weight: 600; color: #64748b; margin-bottom: 2px;
}
.phase-desc-active  { font-size: 0.75rem; color: #475569; }
.phase-desc-inactive { font-size: 0.75rem; color: #94a3b8; }

.phase-hint {
    background: #faf7ee;
    border: 1px solid #e8dfc0;
    border-left: 4px solid #c8a84a;
    border-radius: 0 8px 8px 0;
    padding: 0.75rem 1.1rem;
    font-size: 0.85rem; color: #5a4a1a; font-weight: 500;
    margin: 0.8rem 0 1.5rem;
}

.group-label {
    font-size: 0.73rem; font-weight: 700; letter-spacing: 0.1em;
    color: #64748b; text-transform: uppercase;
    background: #f0f1f4; border-radius: 4px;
    display: inline-block; padding: 2px 8px;
    margin: 1rem 0 0.5rem;
}

.stButton > button {
    font-family: 'Noto Sans JP', sans-serif !important;
    border-radius: 8px !important;
    font-size: 0.85rem !important;
    font-weight: 500 !important;
    transition: all 0.15s !important;
}

.btn-inactive > div > button {
    background: #f1f3f7 !important;
    color: #64748b !important;
    border: 1.5px solid #dde2ea !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.05) !important;
}
.btn-inactive > div > button:hover {
    background: #e8eaf0 !important;
    border-color: #c8a84a !important;
    color: #a07a28 !important;
}

.btn-active > div > button {
    background: #0d1b30 !important;
    color: #c8a84a !important;
    border: 1.5px solid #c8a84a !important;
    box-shadow: 0 3px 10px rgba(13,27,48,0.25) !important;
    font-weight: 700 !important;
}
.btn-active > div > button:hover {
    background: #162540 !important;
}

.stButton > button[kind="primary"] {
    background: #0d1b30 !important;
    color: #c8a84a !important;
    border: 1.5px solid #c8a84a !important;
    border-radius: 10px !important;
    font-size: 1rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.5px !important;
    box-shadow: 0 4px 14px rgba(13,27,48,0.25) !important;
}
.stButton > button[kind="primary"]:hover {
    background: #162540 !important;
    box-shadow: 0 6px 18px rgba(13,27,48,0.35) !important;
    transform: translateY(-1px) !important;
}
.stButton > button:disabled {
    background: #f0f1f4 !important;
    color: #a0aab8 !important;
    box-shadow: none !important;
    border: 1px solid #dde2ea !important;
    transform: none !important;
}

.stDownloadButton > button {
    background: #ffffff !important;
    border: 1.5px solid #c8a84a !important;
    color: #a07a28 !important;
    border-radius: 8px !important;
    font-family: 'Noto Sans JP', sans-serif !important;
    font-weight: 600 !important;
}
.stDownloadButton > button:hover {
    background: #faf7ee !important;
}

.stTextInput > div > div > input {
    background: #ffffff !important;
    border-color: #dde2ea !important;
    border-bottom: 1.5px solid #c8a84a !important;
    color: #1e293b !important;
    border-radius: 8px !important;
    font-family: 'Noto Sans JP', sans-serif !important;
    font-size: 0.9rem !important;
}
.stTextInput > div > div > input:focus {
    border-color: #c8a84a !important;
    box-shadow: 0 0 0 2px rgba(200,168,74,0.15) !important;
}
.stSelectbox > div > div {
    background: #ffffff !important;
    border-color: #dde2ea !important;
    color: #1e293b !important;
    font-family: 'Noto Sans JP', sans-serif !important;
}
.stCheckbox > label {
    color: #1e293b !important; font-size: 0.9rem !important;
    font-family: 'Noto Sans JP', sans-serif !important;
    font-weight: 500 !important;
}

.divider { border: none; border-top: 1.5px solid #dde2ea; margin: 2rem 0; }

.sb-brand {
    padding: 0.8rem 0 1.2rem;
    border-bottom: 1px solid #1e3050; margin-bottom: 1.2rem;
}
.sb-brand-eye {
    font-size: 0.63rem; font-weight: 700; letter-spacing: 0.18em;
    color: #c8a84a; text-transform: uppercase; margin-bottom: 5px;
}
.sb-brand-title {
    font-size: 1rem; font-weight: 700; color: #e8dfc0; margin: 0;
}
.sb-brand-sub { font-size: 0.72rem; color: #607080; margin: 3px 0 0; }
.sb-rule-item {
    background: #0a1525;
    border: 1px solid #c8a84a44;
    border-radius: 7px; padding: 6px 10px;
    font-size: 0.77rem; color: #c8a84a;
    margin-bottom: 5px; display: block;
}
.sb-footer {
    position: fixed; bottom: 1.2rem;
    font-size: 0.68rem; color: #3d5068; text-align: center; width: 200px;
}
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
            st.markdown(
                f'<span class="sb-rule-item">&#10003;&#160;{label}</span>',
                unsafe_allow_html=True,
            )
    else:
        st.warning("判定ルールJSONがありません")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("**チェックフェーズ**")
    for pk, (pnum, pshort, pdesc) in PHASE_ITEMS.items():
        st.markdown(f"**{pnum}　{pshort}**")
        st.caption(pdesc)

    st.markdown(
        '<div class="sb-footer">AuditX v0.5　Powered by Gemini API</div>',
        unsafe_allow_html=True,
    )


# ============================================================
# メイン：ページヘッダー
# ============================================================

st.markdown(
    '<div class="page-eyebrow">HUMAX | LABOR REGULATION AUDIT SYSTEM</div>'
    '<div class="page-title">就業規則チェックツール（Humax）</div>'
    '<div class="page-subtitle">'
    '社会保険労務士法人ヒューマックス向け就業規則チェックシステム'
    '　— 業務効率の最大化のために'
    '</div>',
    unsafe_allow_html=True,
)
st.markdown('<hr class="page-divider">', unsafe_allow_html=True)


# ============================================================
# STEP 1 : 会社情報
# ============================================================

st.markdown('<div class="sec-label">STEP 1　会社情報</div>', unsafe_allow_html=True)

col1, col2 = st.columns([3, 2])
with col1:
    company_name = st.text_input(
        "会社名", placeholder="例：株式会社〇〇", label_visibility="collapsed"
    )
with col2:
    industry = st.text_input(
        "業種（任意）", placeholder="例：小売業、サービス業", label_visibility="collapsed"
    )

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
        card_cls  = "phase-active" if is_active else "phase-inactive"
        num_cls   = "phase-num-active" if is_active else "phase-num-inactive"
        ttl_cls   = "phase-title-active" if is_active else "phase-title-inactive"
        dsc_cls   = "phase-desc-active" if is_active else "phase-desc-inactive"

        st.markdown(
            f'<div class="{card_cls}">'
            f'<div class="{num_cls}">{pnum}</div>'
            f'<div class="{ttl_cls}">{pshort}</div>'
            f'<div class="{dsc_cls}">{pdesc}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        btn_wrap = "btn-active" if is_active else "btn-inactive"
        st.markdown(f'<div class="{btn_wrap}">', unsafe_allow_html=True)
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

st.markdown(
    '<div class="sec-label">STEP 3　申請予定の助成金コース（コースごとに年度・施行日を設定）</div>',
    unsafe_allow_html=True,
)

selected_courses = []
prev_group = None

for course in COURSES:
    if course["group"] != prev_group:
        st.markdown(
            f'<div class="group-label">{course["group"]}</div>',
            unsafe_allow_html=True,
        )
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
                st.success("判定ルール：あり ✓")
            else:
                st.warning(
                    f"令和{year[1:]}年度（{date[:2]}月{date[2:]}日〜）の"
                    "判定ルールJSONがありません"
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
    '<div class="sec-label">STEP 4　就業規則ファイルをアップロード</div>',
    unsafe_allow_html=True,
)

if selected_phase == "phase3":
    st.info(
        "Phase 3 では導入前・導入後・その他改訂分すべての就業規則を"
        "まとめてアップロードしてください。"
    )

col_u1, col_u2 = st.columns(2)
with col_u1:
    st.markdown("**就業規則**（必須・複数可）")
    st.caption("就業規則・賃金規程・育児介護休業規程 等")
    uploaded_files = st.file_uploader(
        "就業規則",
        type=["pdf", "docx", "doc"],
        accept_multiple_files=True,
        label_visibility="collapsed",
        key="main_files",
    )
with col_u2:
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
if not valid_courses:  missing.append("助成金コース")
if not uploaded_files: missing.append("就業規則ファイル")
if missing:
    st.caption("未入力の項目：" + "　/　".join(missing))

run_button = st.button(
    "チェック開始",
    disabled=not can_run,
    type="primary",
    use_container_width=True,
)

if not can_run:
    st.caption("就業規則ファイルをアップロードすると「チェック開始」が有効になります。")


# ============================================================
# チェック実行
# ============================================================

if run_button and can_run:

    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    st.markdown('<div class="sec-label">チェック結果</div>', unsafe_allow_html=True)

    # APIキー
    api_key = st.secrets.get("GOOGLE_API_KEY", os.getenv("GOOGLE_API_KEY"))
    if not api_key:
        env_path = Path(__file__).parent / ".env"
        if env_path.exists():
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("GOOGLE_API_KEY=") and "ここに" not in line:
                        api_key = line.split("=", 1)[1].strip()
                        break
    if not api_key:
        st.error("GOOGLE_API_KEY が設定されていません。Streamlit Cloud の Secrets を確認してください。")
        st.stop()
    os.environ["GOOGLE_API_KEY"] = api_key

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
            st.write("Gemini API で判定中（30秒〜1分ほどかかります）...")
            try:
                others = [
                    f"{c['group']}　{c['name']}"
                    for c in valid_courses if c["course_id"] != ci["course_id"]
                ]
                result = run_audit(
                    combined_text, rk, ci["course_id"],
                    selected_phase, others or None,
                )
                report = generate_report(
                    result, company_name, ci["course_id"],
                    selected_phase, rk, target_filenames,
                )
                all_reports.append({
                    "course_id": ci["course_id"],
                    "label":     f"{ci['group']}　{ci['name']}",
                    "report":    report,
                })
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

    st.markdown('<hr class="divider">', unsafe_allow_html=True)
    st.caption(
        "就業規則チェックツール（ヒューマックス）　v0.5　|　"
        "キャリアアップ助成金 正社員化・賞与退職金制度導入コース対応"
    )
    st.caption(
        "※ 本ツールは実務補助用です。最終判断は必ず担当社会保険労務士が行ってください。"
    )
