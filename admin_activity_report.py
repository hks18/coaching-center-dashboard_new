import os
import django
import csv
from datetime import timedelta

from django.utils import timezone
from django.db.models import Count

# 1) Point to your Django settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mysite.settings")
django.setup()

from accounts.models import Profile, DailyCustomer  # noqa: E402


def daily_counts_for_user(user, days=30):
    """
    Returns:
      - dates: list of dates (oldest → newest)
      - counts: list of customer counts per date
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


def is_active_and_limit(user):
    """
    Same logic as your site:

    - Look at last 7 days (including today).
    - If any day < 3 -> Inactive, limit = 3
    - Else Active, limit = minimum count in last 7 days.
    """
    today = timezone.localdate()
    start_7 = today - timedelta(days=6)

    # counts for last 7 days
    qs = (
        DailyCustomer.objects
        .filter(user=user, date__range=(start_7, today))
        .values("date")
        .annotate(count=Count("id"))
    )
    count_map = {row["date"]: row["count"] for row in qs}
    dates_7 = [start_7 + timedelta(days=i) for i in range(7)]
    counts_7 = [count_map.get(d, 0) for d in dates_7]

    if not counts_7:
        return False, 3  # no data -> inactive, base limit 3

    if any(c < 3 for c in counts_7):
        return False, 3

    # all >= 3 => active, limit is smallest
    current_limit = min(counts_7)
    return True, current_limit


def build_admin_report():
    today = timezone.localdate()
    start_30 = today - timedelta(days=29)

    rows = []

    # all normal users from all centres
    profiles = Profile.objects.filter(role="user").select_related("user")

    for p in profiles:
        user = p.user
        center_name = p.get_center_display()
        username = user.username

        # last 30 days counts
        dates_30, counts_30 = daily_counts_for_user(user, days=30)
        date_to_count = {d: c for d, c in zip(dates_30, counts_30)}

        # active + limit from last 7 days
        active, current_limit = is_active_and_limit(user)
        status = "Active" if active else "Inactive"

        # one row per date (for Excel-style layout)
        for d in dates_30:
            count_for_date = date_to_count.get(d, 0)

            rows.append({
                "Center": center_name,
                "Username": username,
                "Date": d.isoformat(),
                "CallsThatDay": count_for_date,
                "StatusLast7Days": status,
                "CurrentLimit": current_limit,
            })

    filename = "admin_activity_report.csv"
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "Center",
                "Username",
                "Date",
                "CallsThatDay",
                "StatusLast7Days",
                "CurrentLimit",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"✅ Admin report created: {filename}")
    print("   Open this file in Excel to view all centres' activity.")


if __name__ == "__main__":
    build_admin_report()
