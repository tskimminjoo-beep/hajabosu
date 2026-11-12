"""저장은 이 파일에서만 한다. 연결 정보는 .env의 DATABASE_URL (웹 배포는 Streamlit Secrets).

테이블 2개 (처음 실행하면 만들고, 둘 다 RLS를 켠다)
  접수     : 매장·현장에서 들어온 접수 (id 자동 번호)
  하자대장 : data/하자대장.csv와 같은 열, 접수번호가 기본키

RLS(행 수준 보안)를 켜고 정책은 만들지 않으므로 Supabase의 공개 API 키(anon)로는
읽고 쓸 수 없다. 이 코드가 쓰는 DATABASE_URL의 postgres 역할은 RLS를 우회한다.

연결 정보와 비밀번호는 어디에도 출력하지 않는다.
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import (
    CheckConstraint, Column, Date, DateTime, Integer, MetaData, Table, Text,
    create_engine, func, select, text,
)
from sqlalchemy.dialects.postgresql import insert as pg_insert

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env", encoding="utf-8")

# 업무설명 2. 하자대장 항목 (이 순서). data/하자대장.csv의 열과 같다.
대장_항목 = [
    "접수번호", "접수일", "원문파일", "위치", "공종", "하자내용", "긴급도",
    "조치기한", "공사번호", "시공업체", "준공일", "보증만료일", "보증판정",
    "책임구분", "상태", "비고",
]

_meta = MetaData()

접수_테이블 = Table(
    "접수", _meta,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("접수일시", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Column("발견일", Date),
    Column("접수자", Text),
    Column("부서", Text),
    Column("위치", Text),
    Column("내용", Text),
    Column("처리상태", Text, nullable=False, server_default="미처리"),
    Column("접수번호", Text),
    CheckConstraint("\"처리상태\" in ('미처리', '처리완료')", name="접수_처리상태_check"),
)

# 값은 CSV와 같이 문자열(날짜도 'YYYY-MM-DD')로 둔다.
대장_테이블 = Table(
    "하자대장", _meta,
    *[Column(이름, Text, primary_key=(이름 == "접수번호")) for 이름 in 대장_항목],
)

_엔진 = None


def _접속_주소() -> str:
    주소 = os.getenv("DATABASE_URL", "").strip()
    if not 주소:
        raise RuntimeError(".env에 DATABASE_URL이 없습니다.")
    if "YOUR-PASSWORD" in 주소:
        raise RuntimeError("DATABASE_URL의 [YOUR-PASSWORD]를 DB 비밀번호로 바꿔야 합니다.")
    # SQLAlchemy가 psycopg(3)을 쓰도록 스킴을 맞춘다.
    for 앞 in ("postgresql://", "postgres://"):
        if 주소.startswith(앞):
            return "postgresql+psycopg://" + 주소[len(앞):]
    return 주소


def 엔진():
    global _엔진
    if _엔진 is None:
        _엔진 = create_engine(_접속_주소(), pool_pre_ping=True)
    return _엔진


def 초기화() -> None:
    """테이블이 없으면 만들고, 두 테이블 모두 RLS를 켠다. 여러 번 불러도 안전하다."""
    _meta.create_all(엔진())
    with 엔진().begin() as conn:
        for 이름 in ("접수", "하자대장"):
            conn.execute(text(f'ALTER TABLE "{이름}" ENABLE ROW LEVEL SECURITY'))


def 대장_읽기() -> list[dict]:
    """하자대장 전체를 접수번호 순으로. 값은 문자열, 비어 있으면 ''."""
    초기화()
    with 엔진().connect() as conn:
        행들 = conn.execute(select(대장_테이블).order_by(대장_테이블.c.접수번호)).mappings().all()
    return [{k: ("" if v is None else str(v)) for k, v in 행.items()} for 행 in 행들]


def 대장_저장(행들: list[dict]) -> int:
    """접수번호가 같으면 갈아 쓰고, 없으면 추가한다. 저장한 건수를 돌려준다."""
    초기화()
    if not 행들:
        return 0
    값들 = [{k: (행.get(k) or None) for k in 대장_항목} for 행 in 행들]
    구문 = pg_insert(대장_테이블).values(값들)
    구문 = 구문.on_conflict_do_update(
        index_elements=["접수번호"],
        set_={k: 구문.excluded[k] for k in 대장_항목 if k != "접수번호"},
    )
    with 엔진().begin() as conn:
        conn.execute(구문)
    return len(값들)


def 건수() -> dict[str, int]:
    """테이블별 행 수."""
    초기화()
    with 엔진().connect() as conn:
        return {
            t.name: conn.execute(select(func.count()).select_from(t)).scalar_one()
            for t in (접수_테이블, 대장_테이블)
        }


def rls_상태() -> dict[str, bool]:
    """테이블별 RLS 켜짐 여부."""
    with 엔진().connect() as conn:
        행들 = conn.execute(text(
            "select relname, relrowsecurity from pg_class "
            "where relname in ('접수', '하자대장') and relkind = 'r'"
        )).all()
    return {이름: bool(켜짐) for 이름, 켜짐 in 행들}
