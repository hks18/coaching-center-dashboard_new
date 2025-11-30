# accounts/activity_logic.py

from datetime import timedelta

from django.utils import timezone
from django.db.models import Count

from .models import DailyCustomer


def daily_counts_for_user(user, days=30):
    """
    Helper: returns lists of dates and counts for the last `days` days.
    Oldest → newest.
    """
    today = timezone.localdate()
    start_date = today - timedelta(days=days - 1)

    qs = (
        DailyCustomer.objects
        .filter(user=user, date__range=(start_date, today))
        .values("date")
        .annotate(count=Count("id"))
    )

    count_map = {row["date"]: row["count"] for row in qs}
    dates = [start_date + timedelta(days=i) for i in range(days)]
    counts = [count_map.get(d, 0) for d in dates]
    return dates, counts


def compute_activity_status(user):
    """
    Activity logic with RESTART:

    - A day is valid only if 3 <= count < 25.
    - Streak can RESTART after a bad day (count < 3 or >= 25).
    - Once user increases, that becomes the new limit.
    - If they go BELOW the current limit, the old streak breaks and a NEW streak starts from that day.
    - If they stay on the SAME limit > 7 days in a row, that long streak is treated as broken
      (they must increase at some point).
    - Final ACTIVE / INACTIVE is decided only from the **last valid streak segment**.
    """
    dates, counts = daily_counts_for_user(user, days=30)

    started = False
    streak_dates = []
    streak_counts = []
    current_limit = None
    run_length = 0  # consecutive days at current_limit

    for d, c in zip(dates, counts):
        # 1) Bad day → reset streak (allow restart later)
        if c < 3 or c >= 25:
            started = False
            streak_dates = []
            streak_counts = []
            current_limit = None
            run_length = 0
            continue

        # 2) No active streak yet → start new one
        if not started:
            started = True
            current_limit = c
            run_length = 1
            streak_dates = [d]
            streak_counts = [c]
            continue

        # 3) We are inside a streak
        streak_dates.append(d)
        streak_counts.append(c)

        if c < current_limit:
            # Dropped below previous limit → old streak broken,
            # start a NEW streak from this day with smaller limit.
            started = True
            current_limit = c
            run_length = 1
            streak_dates = [d]
            streak_counts = [c]

        elif c > current_limit:
            # Increased limit → reset run_length for this new limit
            current_limit = c
            run_length = 1
        else:
            # Same as current_limit
            run_length += 1

        # 4) If we stayed on SAME limit > 7 days → that streak is invalid,
        #    user must increase; treat as broken and wait for a new streak later.
        if run_length > 7:
            started = False
            streak_dates = []
            streak_counts = []
            current_limit = None
            run_length = 0

    # After processing all days:
    if not started:
        # No valid streak at the end
        return False, [], [], 3  # default limit 3

    # We have a valid final streak segment
    return True, streak_dates, streak_counts, current_limit
