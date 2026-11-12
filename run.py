"""입력 폴더의 접수 원문을 일괄 처리해 하자대장 테이블(DB)에 저장한다.

사용: python run.py [입력폴더]
기본: data/접수함

AI 정리(ai.py) → 번호·기한·보증 판정(rules.py) → 대장 16개 항목으로 기록(db.py).
원본(접수함, 공사정보)은 고치지 않는다.
"""
import re
import sys
from collections import defaultdict
from pathlib import Path

import ai
import db
import rules

ROOT = Path(__file__).resolve().parent
기본_입력 = ROOT / "data" / "접수함"


def _파일명_날짜(이름: str):
    """파일명에서 YYYYMMDD를 찾아 YYYY-MM-DD로. 없으면 None."""
    m = re.search(r"(20\d{2})(\d{2})(\d{2})", 이름)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def _합치기(*메모) -> str | None:
    글 = [m for m in 메모 if m]
    return " / ".join(글) if 글 else None


def 행_만들기(파일명: str, 정리: dict, 접수일: str, 순번: int, 공사목록: list[dict]):
    """AI 정리 결과 1건 → 대장 1행. (행, 보증판정 결과)를 돌려준다. app.py도 쓴다."""
    판정 = rules.보증판정(접수일, 정리["위치"], 정리["공종"], 공사목록)
    확인필요 = 판정["보증판정"] == "확인필요" or 정리["확인필요사유"]
    행 = {
        "접수번호": rules.접수번호(접수일, 순번),
        "접수일": 접수일,
        "원문파일": 파일명,
        "위치": 정리["위치"],
        "공종": 정리["공종"],
        "하자내용": 정리["하자내용"],
        "긴급도": 정리["긴급도"],
        "조치기한": rules.조치기한(접수일, 정리["긴급도"]).isoformat(),
        "공사번호": 판정["공사번호"],
        "시공업체": 판정["시공업체"],
        "준공일": 판정["준공일"],
        "보증만료일": 판정["보증만료일"],
        "보증판정": 판정["보증판정"],
        "책임구분": 판정["책임구분"],
        "상태": "확인필요" if 확인필요 else "판정완료",
        "비고": _합치기(판정["비고"], 정리["확인필요사유"]),
    }
    return 행, 판정


def 처리(입력폴더: Path) -> list[dict]:
    파일들 = sorted(입력폴더.glob("*.txt"))
    if not 파일들:
        raise SystemExit(f"접수 원문이 없습니다: {입력폴더}")

    공사목록 = rules.공사정보_읽기()
    순번 = defaultdict(int)  # 접수일별 순번
    행들 = []

    for 파일 in 파일들:
        정리 = ai.접수정리(파일)

        # 접수일: 원문(AI) → 없으면 파일명 날짜 (업무설명 2)
        접수일 = 정리["접수일"] or _파일명_날짜(파일.name)
        if not 접수일:
            raise SystemExit(f"접수일을 알 수 없습니다: {파일.name}")

        순번[접수일] += 1
        행, _ = 행_만들기(파일.name, 정리, 접수일, 순번[접수일], 공사목록)
        행들.append(행)
        print(f"  {행['접수번호']}  {파일.name}  →  {행['보증판정']}")

    # 저장은 db.py에서만 한다. 접수번호가 같으면 갈아 쓴다.
    db.대장_저장(행들)
    return 행들


if __name__ == "__main__":
    입력 = Path(sys.argv[1]) if len(sys.argv) > 1 else 기본_입력
    print(f"처리 시작: {입력}")
    행들 = 처리(입력)
    print(f"{len(행들)}건 하자대장 테이블에 저장")
