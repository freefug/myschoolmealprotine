import streamlit as st
import pandas as pd
import requests
import re
import datetime
import plotly.express as px

# -------------------------------------------------------------------
# 1. 페이지 기본 설정 및 스타일 정의
# -------------------------------------------------------------------
st.set_page_config(
    page_title="학교별 요일별 단백질 함량 분석",
    page_icon="🍱",
    layout="wide"
)

st.title("🍱 학교별 요일별 평균 단백질 함량 비교 분석")
st.caption("나이스(NEIS) 급식 API의 반정형 데이터(JSON)를 활용하여 학교별/요일별 영양 성분을 분석합니다.")

# Secrets 키 불러오기 (없는 경우 예외 처리)
API_KEY = st.secrets.get("NEIS_API_KEY", "")

if not API_KEY:
    st.warning("⚠️ `.streamlit/secrets.toml` 파일에 `NEIS_API_KEY`가 설정되어 있지 않습니다.")

# -------------------------------------------------------------------
# 2. 기본 비교 학교 데이터 및 API 호출 함수
# -------------------------------------------------------------------
DEFAULT_SCHOOLS = [
    {"SCHUL_NM": "송탄고등학교", "ATPT_OFCDC_SC_CODE": "J10", "SD_SCHUL_CODE": "7530480"},
    {"SCHUL_NM": "평택고등학교", "ATPT_OFCDC_SC_CODE": "J10", "SD_SCHUL_CODE": "7530864"},
    {"SCHUL_NM": "효명고등학교", "ATPT_OFCDC_SC_CODE": "J10", "SD_SCHUL_CODE": "7530176"}
]

DAYS_KR = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]

def parse_protein(ntr_info_str):
    """
    NTR_INFO 문자열에서 '단백질(g)' 함량 숫자를 정규표현식으로 추출
    예: "단백질(g) : 34.5" -> 34.5
    """
    if not ntr_info_str:
        return None
    match = re.search(r'단백질\s*\(g\)\s*:\s*([\d.]+)', ntr_info_str)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None

@st.cache_data(ttl=3600)
def fetch_meal_data(api_key, ofcdc_code, schul_code, from_ymd, to_ymd):
    """나이스 급식식단정보 API 호출 함수"""
    url = "https://open.neis.go.kr/hub/mealServiceDietInfo"
    params = {
        "KEY": api_key,
        "Type": "json",
        "pIndex": 1,
        "pSize": 1000,
        "ATPT_OFCDC_SC_CODE": ofcdc_code,
        "SD_SCHUL_CODE": schul_code,
        "MMEAL_SC_CODE": "2",  # 중식
        "MLSV_FROM_YMD": from_ymd,
        "MLSV_TO_YMD": to_ymd
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        if "mealServiceDietInfo" in data:
            return data["mealServiceDietInfo"][1]["row"]
        else:
            return []
    except Exception as e:
        st.error(f"API 호출 중 오류 발생: {e}")
        return []

# -------------------------------------------------------------------
# 3. 사이드바 (조회 기간 및 학교 선택)
# -------------------------------------------------------------------
st.sidebar.header("🔍 분석 조건 설정")

# 기간 선택 (기본값: 최근 1개월)
today = datetime.date.today()
first_day_of_month = today.replace(day=1)
date_range = st.sidebar.date_input(
    "조회 기간 선택",
    value=(first_day_of_month, today),
    max_value=today
)

# 학교 선택
selected_school_names = st.sidebar.multiselect(
    "비교할 학교 선택 (최소 3개교 권장)",
    options=[s["SCHUL_NM"] for s in DEFAULT_SCHOOLS],
    default=[s["SCHUL_NM"] for s in DEFAULT_SCHOOLS]
)

# -------------------------------------------------------------------
# 4. 데이터 수집 및 처리
# -------------------------------------------------------------------
if len(date_range) == 2:
    start_date, end_date = date_range
    from_ymd = start_date.strftime("%Y%m%d")
    to_ymd = end_date.strftime("%Y%m%d")

    parsed_rows = []

    if selected_school_names:
        with st.spinner("나이스 API에서 급식 데이터를 가져오는 중..."):
            for school in DEFAULT_SCHOOLS:
                if school["SCHUL_NM"] in selected_school_names:
                    raw_meals = fetch_meal_data(
                        API_KEY,
                        school["ATPT_OFCDC_SC_CODE"],
                        school["SD_SCHUL_CODE"],
                        from_ymd,
                        to_ymd
                    )
                    
                    for row in raw_meals:
                        ymd_str = row.get("MLSV_YMD", "")
                        if not ymd_str:
                            continue
                        
                        date_obj = datetime.datetime.strptime(ymd_str, "%Y%m%d").date()
                        weekday_num = date_obj.weekday()
                        
                        # 평일(월~금) 데이터만 추출
                        if weekday_num < 5:
                            ntr_str = row.get("NTR_INFO", "")
                            protein = parse_protein(ntr_str)
                            
                            if protein is not None:
                                parsed_rows.append({
                                    "학교명": school["SCHUL_NM"],
                                    "날짜": date_obj,
                                    "요일": DAYS_KR[weekday_num],
                                    "요일순서": weekday_num,
                                    "단백질(g)": protein,
                                    "메뉴": row.get("DDISH_NM", "").replace("<br/>", ", "),
                                    "칼로리": row.get("CAL_INFO", "")
                                })

        df = pd.DataFrame(parsed_rows)

        # -------------------------------------------------------------------
        # 5. 분석 결과 시각화 (Main 화면)
        # -------------------------------------------------------------------
        if not df.empty:
            # 요일별/학교별 단백질 평균 집계
            avg_df = df.groupby(["학교명", "요일", "요일순서"])["단백질(g)"].mean().reset_index()
            avg_df = avg_df.sort_values(by="요일순서")

            # 가장 단백질이 풍부한 요일 계산
            overall_day_avg = avg_df.groupby("요일")["단백질(g)"].mean()
            best_day = overall_day_avg.idxmax()
            best_val = overall_day_avg.max()

            # 핵심 결론 메트릭 강조
            st.success(f"💡 **분석 결과**: 선택한 학교들의 평균 단백질 함량이 가장 높은 요일은 **[{best_day}]** 입니다! (평균 **{best_val:.1f}g**)")

            # Plotly 막대 그래프 생성
            fig = px.bar(
                avg_df,
                x="요일",
                y="단백질(g)",
                color="학교명",
                barmode="group",
                title="<b>학교별 요일별 평균 단백질 함량 비교</b>",
                text_auto=".1f",
                category_orders={"요일": ["월요일", "화요일", "수요일", "목요일", "금요일"]}
            )
            fig.update_layout(xaxis_title="요일", yaxis_title="평균 단백질 (g)", legend_title="학교")
            
            st.plotly_chart(fig, use_container_width=True)

            # 상세 요약 표
            st.subheader("📊 요일별/학교별 단백질 평균 요약표")
            pivot_df = avg_df.pivot(index="학교명", columns="요일", values="단백질(g)")[["월요일", "화요일", "수요일", "목요일", "금요일"]]
            st.dataframe(pivot_df.style.highlight_max(axis=1, color="#d4edda"), use_container_width=True)

            # 상세 raw 데이터 보기
            with st.expander("📄 전체 조회 데이터 상세 보기"):
                st.dataframe(df[["학교명", "날짜", "요일", "단백질(g)", "칼로리", "메뉴"]], use_container_width=True)

        else:
            st.warning("지정한 기간에 해당하는 급식 영양 데이터가 없거나, API 요청 건수를 초과했습니다.")
    else:
        st.info("사이드바에서 비교할 학교를 선택해 주세요.")
else:
    st.info("조회 기간을 선택해 주세요.")
