from datetime import datetime
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def now_kst():
    # Scheduling and daily limits are business rules in Korea time, not runner-local time.
    return datetime.now(KST)


def today_kst():
    return now_kst().date()
