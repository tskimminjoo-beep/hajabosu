"""접수 화면 (웹에 배포, 매장·현장용). 접수를 DB의 접수 테이블에 저장한다.

실행: streamlit run intake.py
- 접수자·부서·발견일·위치·내용을 받아 접수 테이블에 저장한다.
- 이 화면은 저장만 한다. 정리·판정은 run.py가 한다. AI·하자대장은 이 화면에서 쓰지 않는다.
- 공개 화면이므로 다른 사람의 접수 내용을 보여주지 않는다.
- DB 연결 정보는 .env(내 PC) 또는 Streamlit Secrets(웹 배포)의 DATABASE_URL.
"""
from datetime import datetime, timedelta, timezone

import streamlit as st

import db

한국시간 = timezone(timedelta(hours=9))  # 웹 서버는 UTC일 수 있어서 한국 날짜로 맞춘다
오늘 = datetime.now(한국시간).date()

st.set_page_config(page_title="하자 접수", layout="centered")
st.title("하자 접수")
st.caption("발견한 하자를 적어 주세요. 시설관리팀이 확인합니다.")

with st.form("접수", clear_on_submit=False):
    접수자 = st.text_input("접수자", max_chars=50)
    부서 = st.text_input("부서 또는 매장", max_chars=50)
    발견일 = st.date_input("발견일", value=오늘, max_value=오늘)
    위치 = st.text_input("위치", max_chars=100, placeholder="예: 2F 화장실, B1 푸드코트 3번 매장 앞")
    내용 = st.text_area(
        "내용", max_chars=1000, height=160,
        placeholder="무엇이 어떻게 되어 있는지 적어 주세요. 다치거나 미끄러질 위험이 있으면 함께 적어 주세요.",
    )
    제출 = st.form_submit_button("접수하기", type="primary")

if 제출:
    입력 = {"접수자": 접수자, "부서 또는 매장": 부서, "위치": 위치, "내용": 내용}
    빈칸 = [이름 for 이름, 값 in 입력.items() if not 값.strip()]
    if 빈칸:
        st.error("다음 칸을 적어 주세요: " + ", ".join(빈칸))
    else:
        try:
            접수_id = db.접수_저장(접수자.strip(), 부서.strip(), 발견일, 위치.strip(), 내용.strip())
        except Exception:  # 연결 정보가 화면에 나오지 않도록 내용은 감춘다
            st.error("접수를 저장하지 못했습니다. 잠시 뒤에 다시 시도해 주세요.")
        else:
            st.success(f"접수되었습니다. (접수 번호 {접수_id})")
            st.info("같은 내용을 다시 누르면 중복 접수됩니다.")
