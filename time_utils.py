from datetime import datetime
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def now_kst():
    return datetime.now(KST)


def today_kst():
    return now_kst().date()
