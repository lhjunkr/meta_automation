import os

from dotenv import load_dotenv


def get_int_env(name, default):
    load_dotenv()

    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def is_dry_run():
    load_dotenv()
    return os.getenv("DRY_RUN", "false").lower() == "true"


def is_stories_enabled():
    load_dotenv()
    return os.getenv("ENABLE_STORIES", "true").lower() == "true"
