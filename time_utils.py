from datetime import datetime
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def now_kst():
    # 예약 실행과 일일 제한은 runner 로컬 시간이 아니라 한국 시간 기준의 운영 규칙입니다.
    return datetime.now(KST)


def today_kst():
    return now_kst().date()
