# Trigger type sets used by worker/task routing.
USER_TRIGGER_TYPES = {"mention"}

AUTO_TRIGGER_TYPES = {
    "silence",
    "time_progress",
    "monopoly",
    "committee",
}


def is_user_trigger(trigger_type: str | None) -> bool:
    return str(trigger_type or "").strip().lower() in USER_TRIGGER_TYPES


def is_auto_trigger(trigger_type: str | None) -> bool:
    return str(trigger_type or "").strip().lower() in AUTO_TRIGGER_TYPES
