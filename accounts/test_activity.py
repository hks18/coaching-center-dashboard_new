# # accounts/test_activity.py

# from datetime import date, timedelta
# from django.contrib.auth.models import User
# from django.utils import timezone
# from accounts.models import DailyCustomer
# from accounts.activity_logic import compute_activity_status


# def test_pattern(username, pattern):
#     """
#     pattern example: [3,3,4,4,4,4,4,4]
#     This simulates the LAST len(pattern) days of activity.
#     """
#     try:
#         user = User.objects.get(username=username)
#     except User.DoesNotExist:
#         print(f"❌ User '{username}' not found")
#         return

#     print(f"\n--- Testing streak for user: {username} ---")
#     print("Pattern (old -> new):", pattern)

#     # clear old data for last 30 days
#     DailyCustomer.objects.filter(
#         user=user,
#         date__gte=timezone.localdate() - timedelta(days=30)
#     ).delete()

#     today = timezone.localdate()

#     # insert simulated daily counts
#     for i, c in enumerate(pattern[::-1]):  # newest last
#         d = today - timedelta(days=i)
#         for _ in range(c):
#             DailyCustomer.objects.create(
#                 user=user,
#                 date=d,
#                 name=f"Test{i}",
#                 phone="000"
#             )

#     is_active, dates, counts, limit = compute_activity_status(user)

#     print("Dates:", [str(d) for d in dates])
#     print("Counts:", counts)
#     print("💡 Current Limit:", limit)
#     print("🔍 Status:", "ACTIVE 🟢" if is_active else "INACTIVE 🔴")
#     print("---------------------------------\n")
