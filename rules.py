"""번호·기한·판정 규칙. 기준은 data/업무설명_하자보수.md.

AI를 부르지 않는다. 같은 입력이면 항상 같은 결과가 나온다.
"""
import csv
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
공사정보_경로 = ROOT / "data" / "공사정보.csv"

# 업무설명 4. 긴급도와 조치기한
조치기한_일수 = {"긴급": 1, "높음": 3, "보통": 7}

# 업무설명 5. 보증내인데 보증만료일까지 이 일수 이내면 만료임박
만료임박_일수 = 30


def _날짜(값) -> date:
    """'YYYY-MM-DD' 문자열 또는 date를 date로 맞춘다."""
    if isinstance(값, datetime):  # datetime은 date의 하위 클래스라 먼저 검사
        return 값.date()
    if isinstance(값, date):
        return 값
    return datetime.strptime(str(값).strip(), "%Y-%m-%d").date()


def 접수번호(접수일, 순번: int) -> str:
    """HJ-접수일(YYYYMMDD)-순번(01부터). 예) HJ-20261102-01"""
    if 순번 < 1:
        raise ValueError("순번은 1부터 시작합니다.")
    return f"HJ-{_날짜(접수일):%Y%m%d}-{순번:02d}"


def 조치기한(접수일, 긴급도: str) -> date:
    """긴급 +1일, 높음 +3일, 보통 +7일."""
    if 긴급도 not in 조치기한_일수:
        raise ValueError(f"긴급도는 긴급/높음/보통 중 하나여야 합니다: {긴급도!r}")
    return _날짜(접수일) + timedelta(days=조치기한_일수[긴급도])


def 공사정보_읽기(경로=공사정보_경로) -> list[dict]:
    """공사정보.csv를 읽는다. 원본은 고치지 않는다."""
    with open(경로, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def 보증만료일(준공일, 보증기간_년) -> date:
    """보증만료일 = 준공일 + 하자보증기간(년)."""
    준공 = _날짜(준공일)
    연 = 준공.year + int(보증기간_년)
    try:
        return 준공.replace(year=연)
    except ValueError:  # 2월 29일 준공 → 평년이면 2월 28일
        return 준공.replace(year=연, day=28)


def _만료일(공사: dict) -> date:
    return 보증만료일(공사["준공일"], 공사["하자보증기간(년)"])


def _만료임박(접수: date, 만료: date) -> bool:
    return 0 <= (만료 - 접수).days <= 만료임박_일수


def _후보_공사(위치, 공종, 공사목록) -> list[dict]:
    """위치와 공종이 모두 같은 공사. 공종이 '설비/타일'이면 후보 공종 각각으로 찾는다."""
    if not 위치 or not 공종:
        return []
    후보_공종 = {x.strip() for x in str(공종).split("/")}
    return [
        c for c in 공사목록
        if c["위치"].strip() == str(위치).strip() and c["공종"].strip() in 후보_공종
    ]


def 보증판정(접수일, 위치, 공종, 공사목록=None) -> dict:
    """접수일 기준 보증 판정. 오늘 날짜는 쓰지 않는다.

    - 위치·공종이 모두 같은 공사가 정확히 1건, 공종이 하나로 정해짐
      - 접수일 ≤ 보증만료일 → 보증내 / 시공업체  (30일 이내면 비고에 만료임박)
      - 접수일 > 보증만료일 → 보증만료 / 자체보수
    - 공사가 없거나 2건 이상, 공종 미정·후보 여러 개 → 확인필요
      (후보 공사가 만료임박이면 비고에 함께 적는다)
    """
    접수 = _날짜(접수일)
    공사목록 = 공사정보_읽기() if 공사목록 is None else 공사목록

    결과 = {
        "공사번호": None, "시공업체": None, "준공일": None, "보증만료일": None,
        "보증판정": "확인필요", "책임구분": None, "비고": None,
    }

    후보 = _후보_공사(위치, 공종, 공사목록)
    공종_확정 = bool(공종) and "/" not in str(공종)

    if len(후보) == 1 and 공종_확정:
        공사 = 후보[0]
        만료 = _만료일(공사)
        결과.update(
            공사번호=공사["공사번호"], 시공업체=공사["시공업체"],
            준공일=공사["준공일"], 보증만료일=만료.isoformat(),
        )
        if 접수 <= 만료:
            결과.update(보증판정="보증내", 책임구분="시공업체")
            if _만료임박(접수, 만료):
                결과["비고"] = "만료임박"
        else:
            결과.update(보증판정="보증만료", 책임구분="자체보수")
        return 결과

    # 확인필요: 후보 공사 중 만료임박이 있으면 함께 적는다.
    임박 = [
        f"{c['공사번호']} 보증만료일 {_만료일(c).isoformat()}"
        for c in 후보
        if 접수 <= _만료일(c) and _만료임박(접수, _만료일(c))
    ]
    if 임박:
        결과["비고"] = "만료임박 (" + ", ".join(임박) + ")"
    return 결과
