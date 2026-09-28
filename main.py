import datetime
import re
import pandas as pd
import requests
import streamlit as st

# 1. API 키 설정 (secrets 사용)
NICE_KEY = st.secrets.get("NICE_KEY", "177346823acb41daa7e14dd10ce3a065")

st.set_page_config(page_title="고등학교 급식 & 단백질 비교", page_icon="🍱", layout="wide")
st.title("🍱 전국 고등학교 급식 조회 & 단백질량 비교 분석")

# ----------------------------------------------------
# Helper 함수: 학교 목록 검색 (고등학교)
# ----------------------------------------------------
def search_school(school_name):
    if not school_name.strip():
        return []
    url = "https://open.neis.go.kr/hub/schoolInfo"
    params = {
        "KEY": NICE_KEY,
        "Type": "json",
        "pIndex": 1,
        "pSize": 100,
        "SCHUL_NM": school_name.strip(),
        "SCHUL_KND_SC_NM": "고등학교",
    }
    try:
        res = requests.get(url, params=params).json()
        if "schoolInfo" in res:
            return res["schoolInfo"][1]["row"]
    except Exception as e:
        st.error(f"학교 검색 중 오류 발생: {e}")
    return []

# ----------------------------------------------------
# Helper 함수: 기간별 급식 정보 조회
# ----------------------------------------------------
def get_meal_info(office_code, school_code, start_date, end_date):
    url = "https://open.neis.go.kr/hub/mealServiceDietInfo"
    params = {
        "KEY": NICE_KEY,
        "Type": "json",
        "pIndex": 1,
        "pSize": 100,
        "ATPT_OFCDC_SC_CODE": office_code,
        "SD_SCHUL_CODE": school_code,
        "MLSV_FROM_YMD": start_date.strftime("%Y%m%d"),
        "MLSV_TO_YMD": end_date.strftime("%Y%m%d"),
    }
    try:
        res = requests.get(url, params=params).json()
        if "mealServiceDietInfo" in res:
            return res["mealServiceDietInfo"][1]["row"]
    except Exception as e:
        st.error(f"급식 데이터 조회 중 오류 발생: {e}")
    return []

# ----------------------------------------------------
# Helper 함수: 영양정보(NTR_INFO) 텍스트에서 단백질(g) 추출
# 예: "탄수화물(g) : 100.5 <br/>단백질(g) : 35.2 <br/>지방(g) : 12.0..."
# ----------------------------------------------------
def parse_protein(ntr_info_str):
    if not ntr_info_str:
        return None
    # "단백질(g) : 32.5" 또는 "단백질 : 32.5" 패턴 탐색
    match = re.search(r"단백질(?:\(g\))?\s*:\s*([\d\.]+)", ntr_info_str)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None

# ----------------------------------------------------
# Sidebar: 조회 기간 및 조건 설정
# ----------------------------------------------------
st.sidebar.header("⚙️ 검색 설정")

today = datetime.date.today()
first_day = today.replace(day=1)

date_range = st.sidebar.date_input(
    "📅 조회 기간 선택 (1일~30일 자유 설정)",
    value=(first_day, today),
)

# ----------------------------------------------------
# 메인 화면: 학교 검색 및 다중 선택
# ----------------------------------------------------
st.subheader("1. 비교 및 조회할 고등학교 검색")

search_kw = st.text_input("고등학교 이름을 입력하고 엔터를 누르세요 (예: 휘문고, 경기고, 상산고)", value="휘문고")

# 세션 상태로 비교할 학교 데이터 저장
if "selected_schools" not in st.session_state:
    st.session_state["selected_schools"] = {}

searched_schools = search_school(search_kw)

if searched_schools:
    school_options = {f"{s['SCHUL_NM']} ({s['LCTN_SC_NM']})": s for s in searched_schools}
    chosen_label = st.selectbox("검색 결과에서 학교를 선택하여 목록에 추가하세요", list(school_options.keys()))
    
    if st.button("➕ 비교 목록에 학교 추가"):
        school_data = school_options[chosen_label]
        s_key = f"{school_data['SCHUL_NM']}_{school_data['SD_SCHUL_CODE']}"
        st.session_state["selected_schools"][s_key] = school_data
        st.success(f"'{school_data['SCHUL_NM']}' 학교가 비교 목록에 추가되었습니다!")

# 추가된 학교 목록 보여주기 및 삭제
if st.session_state["selected_schools"]:
    st.markdown("### 🏫 선택된 학교 목록")
    cols = st.columns(len(st.session_state["selected_schools"]))
    
    # 목록 지우기 버튼
    if st.button("🧹 전체 목록 초기화"):
        st.session_state["selected_schools"] = {}
        st.experimental_rerun()

    for idx, (s_key, s_info) in enumerate(list(st.session_state["selected_schools"].items())):
        st.info(f"**{s_info['SCHUL_NM']}** ({s_info['LCTN_SC_NM']})")

# ----------------------------------------------------
# 급식 데이터 조회 및 분석 처리
# ----------------------------------------------------
if isinstance(date_range, tuple) and len(date_range) == 2:
    start_date, end_date = date_range

    if st.button("🚀 선택한 학교 급식 & 단백질 데이터 비교 분석", type="primary"):
        if not st.session_state["selected_schools"]:
            st.warning("최소 1개 이상의 학교를 검색하여 목록에 추가해주세요!")
        else:
            summary_list = []
            detailed_meals_by_school = {}

            with st.spinner("학교별 급식 및 영양 성분을 분석하는 중..."):
                for s_key, s_info in st.session_state["selected_schools"].items():
                    school_name = s_info["SCHUL_NM"]
                    meals = get_meal_info(
                        s_info["ATPT_OFCDC_SC_CODE"],
                        s_info["SD_SCHUL_CODE"],
                        start_date,
                        end_date,
                    )
                    
                    protein_values = []
                    meal_records = []

                    for m in meals:
                        p_val = parse_protein(m.get("NTR_INFO", ""))
                        m_type = m.get("MMEAL_SC_NM", "중식")
                        
                        # 메뉴 정제
                        dish_clean = m["DDISH_NM"].replace("<br/>", "\n")
                        dish_clean = re.sub(r"\([0-9\.]+\)", "", dish_clean)
                        
                        if p_val is not None:
                            protein_values.append(p_val)

                        meal_records.append({
                            "날짜": m["MLSV_YMD"],
                            "식사": m_type,
                            "메뉴": dish_clean,
                            "칼로리": m.get("CAL_INFO", "-"),
                            "단백질(g)": p_val if p_val is not None else 0.0
                        })

                    detailed_meals_by_school[school_name] = meal_records
                    
                    avg_protein = sum(protein_values) / len(protein_values) if protein_values else 0.0
                    summary_list.append({
                        "학교명": school_name,
                        "총 제공 횟수": len(meals),
                        "평균 단백질(g)": round(avg_protein, 2),
                        "최대 단백질(g)": max(protein_values) if protein_values else 0.0,
                        "최소 단백질(g)": min(protein_values) if protein_values else 0.0,
                    })

            st.markdown("---")
            st.header("📊 학교별 단백질 제공량 비교")

            df_summary = pd.DataFrame(summary_list)
            
            # 요약 지표 (Metric Card)
            m_cols = st.columns(len(summary_list))
            for i, row in enumerate(summary_list):
                with m_cols[i]:
                    st.metric(
                        label=f"🏫 {row['학교명']}",
                        value=f"{row['평균 단백질(g)']} g",
                        delta=f"총 {row['총 제공 횟수']}회 식단"
                    )

            # 단백질 비교 차트
            st.subheader("📈 한 달 평균 단백질량(g) 비교 차트")
            st.bar_chart(df_summary.set_index("학교명")["평균 단백질(g)"])

            # 상세 요약 표
            st.subheader("📋 상세 통계 데이터")
            st.dataframe(df_summary, use_container_width=True)

            # ----------------------------------------------------
            # 학교별 상세 식단 탭 (Tab)
            # ----------------------------------------------------
            st.markdown("---")
            st.header("🍱 학교별 상세 식단 & 일별 단백질량")
            
            tabs = st.tabs(list(detailed_meals_by_school.keys()))
            
            for idx, (sch_name, records) in enumerate(detailed_meals_by_school.items()):
                with tabs[idx]:
                    if not records:
                        st.info("해당 기간의 급식 정보가 없습니다.")
                    else:
                        for rec in records:
                            raw_date = rec["날짜"]
                            f_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"
                            
                            with st.expander(f"📌 {f_date} ({rec['식사']}) | 💪 단백질: {rec['단백질(g)']}g | 🔥 {rec['칼로리']}"):
                                st.text(rec["메뉴"])
                                st.caption(f"단백질 제공량: {rec['단백질(g)']}g")
