import io
import re

import pandas as pd
import requests
import streamlit as st
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ------------------------------------------------------------------
# 設定
# ------------------------------------------------------------------
URL = "https://apiservice.mol.gov.tw/OdService/download/A17000000J-030144-MKw"  # 換連結
COUNTIES = [
    "臺北市", "新北市", "桃園市", "臺中市", "臺南市", "高雄市",
    "基隆市", "新竹市", "嘉義市", "新竹縣", "苗栗縣", "彰化縣",
    "南投縣", "雲林縣", "嘉義縣", "屏東縣", "宜蘭縣", "花蓮縣",
    "臺東縣", "澎湖縣", "金門縣", "連江縣",
]
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/csv,application/octet-stream,*/*",
}
REGION_HINTS = ["縣市", "地區", "區域", "地點", "工作地", "地址", "城市", "區"]

st.set_page_config(page_title="求職職缺搜尋", page_icon="💼", layout="wide")


# ------------------------------------------------------------------
# 資料載入
# ------------------------------------------------------------------
def read_csv_bytes(content: bytes) -> pd.DataFrame:
    for enc in ("utf-8-sig", "utf-8", "big5", "cp950"):
        try:
            return pd.read_csv(io.BytesIO(content), encoding=enc)
        except UnicodeDecodeError:
            continue
    raise ValueError("無法判斷 CSV 編碼")


@st.cache_data(ttl=3600, show_spinner="資料載入中...")
def load_data(url: str) -> pd.DataFrame:
    resp = requests.get(url, headers=HEADERS, verify=False, timeout=30)
    resp.raise_for_status()
    return read_csv_bytes(resp.content)


def normalize(text: str) -> str:
    """台 / 臺 統一，方便比對"""
    return str(text).replace("台", "臺")


def guess_region_column(columns) -> str:
    for hint in REGION_HINTS:
        for c in columns:
            if hint in str(c):
                return c
    return columns[0]

JOB_TYPE_HINTS = ["工作性質", "僱用", "雇用", "全職", "職缺類型", "工時", "型態", "性質"]
EDU_HINTS = ["學歷", "教育", "程度"]
NONE_OPTION = "(不使用)"
 
 
def guess_column(columns, hints):
    for h in hints:
        for c in columns:
            if h in str(c):
                return c
    return None
 
 
def checkbox_filter(df, label, hints, key):
    """回傳 (欄位, 勾選的值)。選項 <= 30 個用勾選框，否則用多選選單。"""
    columns = list(df.columns)
    options = [NONE_OPTION] + columns
    guess = guess_column(columns, hints)
    col = st.selectbox(
        f"{label}欄位",
        options,
        index=options.index(guess) if guess else 0,
        key=f"{key}_col",
    )
    if col == NONE_OPTION:
        return col, []
 
    values = sorted(df[col].dropna().astype(str).str.strip().unique())
    if not values:
        st.caption("此欄位沒有資料")
        return col, []
 
    st.caption("勾選要保留的選項（全部不勾 = 不限）")
    if len(values) <= 30:
        chosen = [v for v in values if st.checkbox(v, key=f"{key}_chk_{v}")]
    else:
        chosen = st.multiselect("選項", values, key=f"{key}_multi")
    return col, chosen
# ------------------------------------------------------------------
# 側邊欄：資料來源
# ------------------------------------------------------------------
st.title("💼 求職職缺搜尋")

with st.sidebar:
    st.header("資料來源")
    source = st.radio("來源", ["線上下載", "上傳 CSV"], horizontal=True)
    url = st.text_input("資料網址", URL) if source == "線上下載" else None
    uploaded = st.file_uploader("上傳 CSV", type="csv") if source == "上傳 CSV" else None
    drop_na = st.checkbox("移除含空值的列（dropna）", value=False)

try:
    if source == "線上下載":
        df = load_data(url)
    elif uploaded is not None:
        df = read_csv_bytes(uploaded.getvalue())
    else:
        st.info("請在左側上傳 CSV 檔案。")
        st.stop()
except Exception as e:
    st.error(f"資料載入失敗：{e}")
    st.stop()

df = df.dropna() if drop_na else df.dropna(how="all")
df = df.reset_index(drop=True)
df.columns = [str(c).strip() for c in df.columns]
df = df.loc[:, ~pd.Index(df.columns).duplicated()]  # 移除重複欄位名稱

if df.empty:
    st.warning("資料是空的，請取消勾選「移除含空值的列」或更換資料來源。")
    st.stop()

columns = list(df.columns)

# ------------------------------------------------------------------
# 側邊欄：搜尋條件
# ------------------------------------------------------------------
with st.sidebar:
    st.header("搜尋條件")

    region_col = st.selectbox(
        "地區欄位", columns, index=columns.index(guess_region_column(columns))
    )
    selected_counties = st.multiselect("選擇地區（可複選）", COUNTIES)

    st.divider()
    keyword = st.text_input("關鍵字（空白分隔多個）", placeholder="例如：行政 助理")
    search_cols = st.multiselect(
        "要搜尋的欄位", columns, default=columns, help="預設搜尋全部欄位"
    )
    match_mode = st.radio("多關鍵字比對", ["全部符合 (AND)", "任一符合 (OR)"], horizontal=True)
    st.divider()
    st.subheader("進階篩選")
    with st.expander("工作性質（全職 / 兼職…）", expanded=True):
        job_col, job_chosen = checkbox_filter(df, "工作性質", JOB_TYPE_HINTS, "job")
    with st.expander("學歷", expanded=True):
        edu_col, edu_chosen = checkbox_filter(df, "學歷", EDU_HINTS, "edu")
# ------------------------------------------------------------------
# 篩選
# ------------------------------------------------------------------
result = df.copy()

if selected_counties:
    region_text = result[region_col].fillna("").astype(str).map(normalize)
    pattern = "|".join(re.escape(c) for c in selected_counties)
    result = result[region_text.str.contains(pattern, na=False)]
for col, chosen in [(job_col, job_chosen), (edu_col, edu_chosen)]:
    if col != NONE_OPTION and chosen:
        values = result[col].fillna("").astype(str).str.strip()
        result = result[values.isin(chosen)]
        
keywords = [k for k in normalize(keyword).split() if k]
if keywords and search_cols:
    blob = pd.Series("", index=result.index, dtype="object")
    for c in search_cols:
        blob = blob + " " + result[c].fillna("").astype(str)
    blob = blob.map(normalize)
    masks = [blob.str.contains(re.escape(k), case=False, na=False) for k in keywords] 
    combined = masks[0]
    for m in masks[1:]:
        combined = (combined & m) if match_mode.startswith("全部") else (combined | m)
    result = result[combined]

# ------------------------------------------------------------------
# 顯示結果
# ------------------------------------------------------------------
c1, c2 = st.columns(2)
c1.metric("全部資料筆數", f"{len(df):,}")
c2.metric("符合條件筆數", f"{len(result):,}")

show_cols = st.multiselect("顯示欄位", columns, default=columns)

# 網址欄位自動轉成可點擊連結
col_config = {}
for c in show_cols:
    sample = result[c].dropna().astype(str).head(20)
    if len(sample) and sample.str.startswith("http").mean() > 0.5:
        col_config[c] = st.column_config.LinkColumn(c)

st.dataframe(
    result[show_cols],
    use_container_width=True,
    hide_index=True,
    column_config=col_config,
)

st.download_button(
    "⬇️ 下載搜尋結果 (CSV)",
    data=result[show_cols].to_csv(index=False).encode("utf-8-sig"),
    file_name="job_search_result.csv",
    mime="text/csv",
    disabled=result.empty,
)

if result.empty:
    st.info("沒有符合的職缺，試試減少關鍵字或取消地區篩選。")
