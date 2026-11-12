"""담당자 화면 (내 PC). 접수 원문이 하자대장이 되기까지의 과정을 보여준다.

실행: streamlit run app.py
- 건별 과정: 원문 → AI 정리 → 규칙 판정 → 대장 한 줄
- 하자대장: data/하자대장.csv 보기, 전체 처리(AI 호출) 후 저장
- 기준 문서: 지침·업무설명 보기

원본(접수함, 공사정보)은 고치지 않는다. AI는 버튼을 눌렀을 때만 부른다.
"""
import json
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

import ai
import rules
import run

ROOT = Path(__file__).resolve().parent
접수함 = ROOT / "data" / "접수함"
대장_경로 = ROOT / "data" / "하자대장.csv"
지침_경로 = ROOT / "지침" / "접수정리.md"
업무설명_경로 = ROOT / "data" / "업무설명_하자보수.md"

st.set_page_config(page_title="하자보수 접수 → 하자대장", layout="wide")
st.title("하자보수 접수 → 하자대장")
st.caption("실습용 가상 업무 · 접수 원문이 하자대장이 되기까지의 과정")

# ---- 전체 흐름 -------------------------------------------------------------
흐름 = [
    ("① 접수 읽기", "코드", "접수함의 txt 원문을 읽는다"),
    ("② 내용 정리", "AI", "날짜·위치·공종·하자내용·긴급도를 뽑는다"),
    ("③ 규칙 판정", "코드", "접수번호·조치기한·공사 매칭·보증 판정"),
    ("④ 대장 기록", "코드", "16개 항목을 하자대장.csv에 적는다"),
    ("⑤ 확인·승인", "사람", "확인필요 건을 정하고 조치요청으로 넘긴다"),
]
for col, (이름, 담당, 설명) in zip(st.columns(len(흐름)), 흐름):
    with col:
        with st.container(border=True):
            st.markdown(f"**{이름}**")
            st.markdown({"AI": ":violet-badge[AI]", "코드": ":blue-badge[코드]", "사람": ":orange-badge[사람]"}[담당])
            st.caption(설명)


# ---- 읽기 도우미 -----------------------------------------------------------
def 대장_읽기() -> pd.DataFrame | None:
    if not 대장_경로.exists():
        return None
    return pd.read_csv(대장_경로, dtype=str, encoding="utf-8-sig").fillna("")


def 원문_파일들() -> list[Path]:
    return sorted(접수함.glob("*.txt"))


tab_건별, tab_대장, tab_기준 = st.tabs(["건별 과정", "하자대장", "기준 문서"])

# ---- 건별 과정 -------------------------------------------------------------
with tab_건별:
    파일들 = 원문_파일들()
    if not 파일들:
        st.warning(f"접수 원문이 없습니다: {접수함}")
        st.stop()

    선택 = st.selectbox("접수 원문 선택", 파일들, format_func=lambda p: p.name)
    대장 = 대장_읽기()
    저장행 = None
    if 대장 is not None:
        일치 = 대장[대장["원문파일"] == 선택.name]
        if len(일치):
            저장행 = 일치.iloc[0].to_dict()

    # ① 원문
    st.subheader("① 접수 원문  :blue-badge[코드]")
    st.code(선택.read_text(encoding="utf-8"), language=None)

    # ② AI 정리 — 버튼을 눌렀을 때만 AI를 부른다
    st.subheader("② AI 정리  :violet-badge[AI]")
    키 = f"ai_{선택.name}"
    if st.button("AI 호출해서 이 건 다시 정리하기", key=f"btn_{선택.name}"):
        with st.spinner("AI가 정리하는 중..."):
            try:
                st.session_state[키] = ai.접수정리(선택)
            except Exception as e:  # 키 없음·네트워크 등
                st.error(f"AI 호출에 실패했습니다: {e}")
    정리 = st.session_state.get(키)

    if 정리:
        st.caption("방금 AI가 돌려준 JSON (판단근거와 확인필요사유 포함)")
        st.json(정리)
    elif 저장행:
        st.caption("저장된 하자대장에서 가져온 값입니다. (AI는 부르지 않았습니다)")
        st.table(pd.DataFrame([{k: 저장행[k] for k in ["접수일", "위치", "공종", "하자내용", "긴급도"]}]))
    else:
        st.info("아직 정리된 결과가 없습니다. 위 버튼을 누르거나 하자대장 탭에서 전체 처리를 하세요.")

    # 판정에 쓸 값: 방금 AI 결과 > 저장된 대장
    값 = None
    if 정리:
        접수일 = 정리["접수일"] or run._파일명_날짜(선택.name)
        값 = {"접수일": 접수일, "위치": 정리["위치"], "공종": 정리["공종"], "긴급도": 정리["긴급도"]}
    elif 저장행:
        값 = {k: (저장행[k] or None) for k in ["접수일", "위치", "공종", "긴급도"]}

    # ③ 규칙 판정
    if 값 and 값["접수일"]:
        st.subheader("③ 규칙 판정  :blue-badge[코드]")
        공사목록 = rules.공사정보_읽기()
        판정 = rules.보증판정(값["접수일"], 값["위치"], 값["공종"], 공사목록)

        a, b = st.columns(2)
        with a:
            st.markdown("**조치기한**")
            일수 = rules.조치기한_일수[값["긴급도"]]
            기한 = rules.조치기한(값["접수일"], 값["긴급도"])
            st.write(f"긴급도 `{값['긴급도']}` → 접수일 {값['접수일']} + {일수}일 = **{기한}**")
        with b:
            st.markdown("**공사 매칭** (위치와 공종이 모두 같은 공사)")
            후보 = rules._후보_공사(값["위치"], 값["공종"], 공사목록)
            if 후보:
                표 = pd.DataFrame(후보)[["공사번호", "위치", "공종", "시공업체", "준공일", "하자보증기간(년)"]]
                표["보증만료일"] = [rules._만료일(c).isoformat() for c in 후보]
                st.dataframe(표, hide_index=True, width="stretch")
            else:
                st.write(f"위치 `{값['위치']}` · 공종 `{값['공종']}`에 맞는 공사가 없습니다.")

        판정값 = 판정["보증판정"]
        근거 = f"기준일은 오늘이 아니라 접수일({값['접수일']})입니다. "
        if 판정["보증만료일"]:
            근거 += f"보증만료일 {판정['보증만료일']} → "
        근거 += f"**{판정값}**" + (f" · 책임구분 **{판정['책임구분']}**" if 판정["책임구분"] else "")
        if 판정["비고"]:
            근거 += f" · {판정['비고']}"
        (st.warning if 판정값 == "확인필요" else st.success if 판정값 == "보증내" else st.info)(근거)

    # ④ 대장 한 줄
    if 저장행:
        st.subheader("④ 하자대장에 적힌 한 줄  :blue-badge[코드]")
        st.table(pd.DataFrame([저장행]).T.rename(columns={0: "값"}))

        # ⑤ 사람
        st.subheader("⑤ 담당자 확인  :orange-badge[사람]")
        if 저장행["상태"] == "확인필요":
            st.warning(f"확인필요 건입니다. {저장행['비고']}")
        else:
            st.success("판정완료 건입니다. 확인 후 조치요청으로 넘기면 됩니다.")

# ---- 하자대장 --------------------------------------------------------------
with tab_대장:
    대장 = 대장_읽기()
    if 대장 is None:
        st.info("하자대장.csv가 아직 없습니다. 아래 버튼으로 만들 수 있습니다.")
    else:
        수정시각 = datetime.fromtimestamp(대장_경로.stat().st_mtime)
        st.caption(f"{대장_경로.name} · 마지막 저장 {수정시각:%Y-%m-%d %H:%M}")
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("전체", len(대장))
        m2.metric("긴급", int((대장["긴급도"] == "긴급").sum()))
        m3.metric("업체 요청 (시공업체)", int((대장["책임구분"] == "시공업체").sum()))
        m4.metric("자체보수", int((대장["책임구분"] == "자체보수").sum()))
        m5.metric("확인필요", int((대장["상태"] == "확인필요").sum()))

        상태들 = st.multiselect("상태", sorted(대장["상태"].unique()), default=sorted(대장["상태"].unique()))
        st.dataframe(대장[대장["상태"].isin(상태들)], hide_index=True, width="stretch")

    st.divider()
    st.markdown("**전체 처리** — 접수함의 모든 원문을 AI로 정리하고 규칙을 적용해 하자대장.csv를 **다시 만듭니다.**")
    st.caption("AI를 건수만큼 호출합니다. 기존 하자대장.csv는 덮어씁니다.")
    if st.button("전체 처리 후 저장", type="primary"):
        with st.spinner("접수함을 처리하는 중..."):
            try:
                행들 = run.처리(접수함, 대장_경로)
                st.success(f"{len(행들)}건을 저장했습니다.")
                st.rerun()
            except Exception as e:
                st.error(f"처리에 실패했습니다: {e}")

# ---- 기준 문서 -------------------------------------------------------------
with tab_기준:
    st.caption("읽기 전용입니다.")
    with st.expander("AI에게 주는 지침 (지침/접수정리.md)"):
        st.markdown(지침_경로.read_text(encoding="utf-8"))
    with st.expander("업무 규칙 (data/업무설명_하자보수.md)"):
        st.markdown(업무설명_경로.read_text(encoding="utf-8"))
    with st.expander("공사정보 (data/공사정보.csv)"):
        st.dataframe(pd.DataFrame(rules.공사정보_읽기()), hide_index=True, width="stretch")
