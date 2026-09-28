import datetime
import re
import requests
import streamlit as st

# 1. API 키 불러오기
NICE_KEY = st.secrets.get("NICE_KEY", "177346823acb41daa7e14dd10ce3a065")

st.set_page_config(page_title="전국 고등학교 급식 조회", page_icon="🍱")
st.title("🍱 전국 고등학교 급식 정보 조회")

# ----------------------------------------------------
# Helper 함수: 학교 정보 검색 (학교코드, 교육청코드 조회)
# ----------------------------------------------------
def search_school(school_name):
    url = "https://open.neis.go.kr/hub/schoolInfo"
    params = {
        "KEY": NICE_KEY,
        "Type": "json",
        "pIndex": 1,
        "pSize": 100,
        "SCHUL_NM": school_name,
        "SCHUL_KND_SC_NM": "고등학교",  # 고등학교로 제한
    }
    res = requests.get(url, params=params).json()
    
    if "schoolInfo" in res:
        rows = res["schoolInfo"][1]["row"]
        return rows
    return []

# ----------------------------------------------------
# Helper 함수: 기간별 급식 목록 조회
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
    res = requests.get(url, params=params).json()
    
    if "mealServiceDietInfo" in res:
        return res["mealServiceDietInfo"][1]["row"]
    return []

# ----------------------------------------------------
# UI 구성
# ----------------------------------------------------
col1, col2 = st.columns([2, 1])

with col1:
    school_name_input = st.text_input("고등학교 이름을 입력하세요", value="휘문고등학교")

# 검색된 학교 선택
schools = []
if school_name_input.strip():
    schools = search_school(school_name_input.strip())

if not schools:
    st.warning("검색된 고등학교가 없습니다. 정확한 학교명을 입력해주세요.")
else:
    # 검색된 학교가 여러 개일 경우 선택 박스 제공
    school_options = {f"{s['SCHUL_NM']} ({s['LCTN_SC_NM']})": s for s in schools}
    selected_school_label = st.selectbox("학교 선택", list(school_options.keys()))
    selected_school = school_options[selected_school_label]

    st.markdown("---")
    
    # 날짜 범위 선택 (1일~30일 등 자유롭게 설정 가능)
    st.subheader("📅 조회 기간 선택")
    today = datetime.date.today()
    first_day = today.replace(day=1)
    
    date_range = st.date_input(
        "조회할 기간을 선택하세요 (시작일 ~ 종료일)",
        value=(first_day, today),
    )

    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
        
        # 급식 불러오기 버튼
        if st.button("급식 조회하기", type="primary"):
            with st.spinner("급식 정보를 불러오는 중..."):
                meals = get_meal_info(
                    selected_school["ATPT_OFCDC_SC_CODE"],
                    selected_school["SD_SCHUL_CODE"],
                    start_date,
                    end_date,
                )
            
            if not meals:
                st.info("해당 기간에는 급식 정보가 없습니다.")
            else:
                st.success(f"총 {len(meals)}건의 급식 정보를 찾았습니다!")
                
                # 일자별 표시
                for meal in meals:
                    # YYYYMMDD -> YYYY-MM-DD 변환
                    raw_date = meal["MLSV_YMD"]
                    formatted_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"
                    meal_type = meal.get("MMEAL_SC_NM", "중식")
                    
                    # HTML 태그 <br/> 및 알레르기 번호 제거 정제
                    dish_clean = meal["DDISH_NM"].replace("<br/>", "\n")
                    dish_clean = re.sub(r"\([0-9\.]+\)", "", dish_clean)  # 알레르기 번호 제거
                    
                    with st.expander(f"📌 {formatted_date} ({meal_type})"):
                        st.text(dish_clean)
                        if "CAL_INFO" in meal:
                            st.caption(f"🔥 칼로리: {meal['CAL_INFO']}")
