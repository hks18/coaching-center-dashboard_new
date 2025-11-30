from datetime import date, timedelta

from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Count
from django.shortcuts import render, redirect
from django.utils import timezone

from .models import Profile, DailyCustomer
from django.views.decorators.csrf import csrf_exempt
from .activity_logic import compute_activity_status

@csrf_exempt
def signup_view(request):
    """
    Signup page for new users/center owners.
    Center list is dynamic:
      - base centers: balasore, bbsr, basta
      - plus any centers already used in Profile.center
    """

    # Build dynamic center list for dropdown
    base_centers = ["balasore", "bbsr", "basta"]
    existing_centers = Profile.objects.values_list("center", flat=True).distinct()
    centers = sorted({c for c in existing_centers if c} | set(base_centers))

    if request.method == "POST":
        username_raw = request.POST.get("username")
        email = request.POST.get("email") or ""
        password = request.POST.get("password")
        confirm_password = request.POST.get("confirm_password")
        role = request.POST.get("role")
        center_from_dropdown = request.POST.get("center")  # selected option
        new_center_name = (request.POST.get("new_center_name") or "").strip()

        # extract username from email
        email_name = email.split("@")[0]
        username = email_name.lower().strip()

        if not username:
            return render(request, "signup.html", {
                "error": "Invalid email. Username extracted from email is empty.",
                "centers": centers,
            })

        # basic checks
        if password != confirm_password:
            return render(request, "signup.html", {
                "error": "Passwords do not match!",
                "centers": centers,
            })

        if not role:
            return render(request, "signup.html", {
                "error": "Select role",
                "centers": centers,
            })

        # decide final center value
        center_value = None

        if role == "centerowner":
            # center owner can either pick existing OR add new
            if new_center_name:
                center_value = new_center_name
            else:
                center_value = center_from_dropdown

            if not center_value:
                return render(request, "signup.html", {
                    "error": "Select a center or add a new one.",
                    "centers": centers,
                })
        else:
            # normal user must choose from dropdown only
            center_value = center_from_dropdown
            if not center_value:
                return render(request, "signup.html", {
                    "error": "Select a center",
                    "centers": centers,
                })

        # rule: only one owner per center
        if role == "centerowner" and Profile.objects.filter(role="centerowner", center=center_value).exists():
            return render(request, "signup.html", {
                "error": "Center owner already exists for this center!",
                "centers": centers,
            })

        # rule: username must be unique across all centers
        if User.objects.filter(username=username).exists():
            return render(request, "signup.html", {
                "error": "This email already has an account! Please login instead.",
                "centers": centers,
            })

        name_part = username[:3]  # first 3 letters of name

        # password rules
        if role == "user":
            required_password = f"{name_part}@{center_value}"
        else:
            required_password = f"{name_part}"

        if password != required_password:
            return render(request, "signup.html", {
                "error": f"Password must be: {required_password}",
                "centers": centers,
            })

        # create user + profile
        user = User.objects.create_user(username=username, email=email, password=password)
        Profile.objects.create(user=user, role=role, center=center_value)

        login(request, user)
        return redirect("home")

    # GET request: just show empty signup form
    return render(request, "signup.html", {"centers": centers})

@csrf_exempt
def login_view(request):
    """
    Login:
      - Superuser  -> admin dashboard
      - Centerowner -> blocked here, must use /center-login/
      - Normal user -> home
    """
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)
        if user is None:
            return render(request, "login.html", {"error": "Invalid username or password"})

        # 1) If this is the Django superuser (admin) -> go to admin dashboard
        if user.is_superuser:
            login(request, user)
            return redirect("admin_dashboard")

        # 2) For all others, check profile
        try:
            profile = user.profile
        except Profile.DoesNotExist:
            profile = None

        # Center owner should not log in here
        if profile and profile.role == "centerowner":
            return render(
                request,
                "login.html",
                {"error": "This account is a Center Owner. Please use the Center Owner login page."},
            )

        # 3) Normal user
        login(request, user)
        return redirect("home")

    return render(request, "login.html")


def center_login_view(request):
    """Center owner login."""
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)
        if user:
            try:
                profile = user.profile
            except Profile.DoesNotExist:
                profile = None

            if not profile or profile.role != "centerowner":
                return render(
                    request,
                    "center_login.html",
                    {"error": "This account is not a Center Owner. Please use the normal User login page."},
                )

            login(request, user)
            return redirect("home")
        else:
            return render(request, "center_login.html", {"error": "Invalid username or password"})

    return render(request, "center_login.html")


# ---------- helper functions ----------


def _daily_counts_for_user(user, days=30):
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


def _is_active_user(user):
    """
    Dynamic streak logic:

    - Look at last 7 days (including today).
    - If ANY day has < 3 customers  -> Inactive (limit = 3).
    - Otherwise -> Active, with 'current_limit' = minimum daily count in those 7 days.
      Example last 7 days: [5, 5, 5, 5, 5, 5, 5] -> current_limit = 5
      Example last 7 days: [3, 4, 3, 5, 3, 4, 3] -> current_limit = 3
    """
    dates, counts = _daily_counts_for_user(user, days=7)

    if not counts:
        # No data at all -> Inactive, limit = 3
        return False, dates, counts, 3

    # If any day below 3 -> streak broken -> Inactive
    if any(c < 3 for c in counts):
        return False, dates, counts, 3

    # All last 7 days have at least 3 calls -> Active
    # current_limit = smallest daily count in last 7-day window
    current_limit = min(counts)

    return True, dates, counts, current_limit


@login_required
def home_view(request):
    """
    Normal user home:
      - If center owner logs in and hits /home → redirect to center dashboard.
      - For users: show today's customers + streak info + calendar.
    """
    # 1) Center owner? → send to center dashboard
    try:
        profile = request.user.profile
        if profile.role == "centerowner":
            return redirect("center_dashboard")
    except Profile.DoesNotExist:
        profile = None

    # 2) Normal user behaviour
    today = timezone.localdate()
    date_str = request.GET.get("date")
    try:
        if date_str:
            selected_date = date.fromisoformat(date_str)
        else:
            selected_date = today
    except ValueError:
        selected_date = today

    message = None
    error = None

    if request.method == "POST":
        # only allow adding for today
        if selected_date != today:
            error = "You can only add customers for today."
        else:
            names = request.POST.getlist("customer_name")
            phones = request.POST.getlist("customer_phone")

            customers_to_add = []
            for n, p in zip(names, phones):
                n = (n or "").strip()
                p = (p or "").strip()
                if n and p:
                    customers_to_add.append((n, p))

            existing_count = DailyCustomer.objects.filter(user=request.user, date=today).count()
            new_count = len(customers_to_add)
            total_after = existing_count + new_count

            if existing_count == 0 and total_after < 3:
                error = "You must add at least 3 customers for a new day."
            elif total_after > 25:
                error = "You cannot have more than 25 customers in one day."
            else:
                for n, p in customers_to_add:
                    DailyCustomer.objects.create(user=request.user, date=today, name=n, phone=p)
                message = f"Saved! Total customers for today: {total_after}"

    customers = DailyCustomer.objects.filter(user=request.user, date=selected_date).order_by("id")

    try:
        profile = request.user.profile
        role_code = profile.role
        center_label = profile.center

    except Profile.DoesNotExist:
        role_code = "user"
        center_label = ""

    role_label = "User" if role_code == "user" else "Center Owner"

    # --- streak / active logic using dynamic rule ---
    is_active, streak_dates, streak_counts, current_limit = compute_activity_status(request.user)
    streak_status_text = "Active user" if is_active else "Inactive user"

    context = {
        "role_label": role_label,
        "center_label": center_label,
        "selected_date": selected_date,
        "today": today,
        "customers": customers,
        "message": message,
        "error": error,
        "streak_status_text": streak_status_text,
        "streak_dates_counts": list(zip(streak_dates, streak_counts)),
        "current_limit": current_limit,   # current daily target (min in last 7 active days)
    }
    return render(request, "home.html", context)


@login_required
def center_dashboard_view(request):
    """
    Center owner dashboard:
      - Only centerowner role
      - Shows each user of that center in a table
      - Date filter (calendar) to see customers on that date
      - Search bar to filter by username
      - Shows for that date: count + list of customers (name + phone)
    """
    try:
        profile = request.user.profile
    except Profile.DoesNotExist:
        return redirect("home")

    if profile.role != "centerowner":
        return redirect("home")

    center = profile.center
    today = timezone.localdate()

    # --- filters from query params ---
    date_str = request.GET.get("date")
    search = (request.GET.get("q") or "").strip()

    # selected date (default: today)
    try:
        if date_str:
            selected_date = date.fromisoformat(date_str)
        else:
            selected_date = today
    except ValueError:
        selected_date = today

    # base queryset: all users in this center
    user_qs = (
        Profile.objects
        .filter(center=center, role="user")
        .select_related("user")
    )

    # filter by username if search provided
    if search:
        user_qs = user_qs.filter(user__username__icontains=search)

    users_data = []

    for up in user_qs:
        user = up.user

        # Use same dynamic streak logic as home_view
        is_active, _, _, _ = compute_activity_status(user)
        status = "Active" if is_active else "Inactive"


        # customers for selected date
        customers_qs = (
            DailyCustomer.objects
            .filter(user=user, date=selected_date)
            .order_by("id")
        )
        customers = [{"name": c.name, "phone": c.phone} for c in customers_qs]
        count_for_date = len(customers)

        users_data.append({
            "username": user.username,
            "status": status,
            "count": count_for_date,
            "customers": customers,
            # optional: use in template if you like
        })

    context = {
        "center_label": profile.center,
        "users_data": users_data,
        "today": today,
        "selected_date": selected_date,
        "search": search,
    }
    return render(request, "center_dashboard.html", context)
@login_required
def admin_dashboard_view(request):
    """
    Admin dashboard (local only):
      - Only Django superuser
      - Shows dynamic list of centers based on Profile.center
    """
    if not request.user.is_superuser:
        return redirect("home")

    # dynamic list of centers: all distinct Profile.center values
    centers_qs = Profile.objects.values_list("center", flat=True).distinct()
    centers = sorted(c for c in centers_qs if c)  # remove None / empty

    return render(request, "admin_dashboard.html", {"centers": centers})



@login_required
def admin_center_dashboard_view(request, center_code):
    """
    Admin view of a single center's dashboard.
    Same data as center_owner's dashboard, but admin can choose any center.
    """
    if not request.user.is_superuser:
        return redirect("home")

    today = timezone.localdate()

    # filters from query params (same as center_dashboard_view)
    date_str = request.GET.get("date")
    search = (request.GET.get("q") or "").strip()

    try:
        if date_str:
            selected_date = date.fromisoformat(date_str)
        else:
            selected_date = today
    except ValueError:
        selected_date = today

    # all users in the selected center
    user_qs = (
        Profile.objects
        .filter(center=center_code, role="user")
        .select_related("user")
    )

    if search:
        user_qs = user_qs.filter(user__username__icontains=search)

    users_data = []

    for up in user_qs:
        user = up.user

        # use same dynamic streak logic
        is_active, _, _, _ = compute_activity_status(user)
        status = "Active" if is_active else "Inactive"


        customers_qs = (
            DailyCustomer.objects
            .filter(user=user, date=selected_date)
            .order_by("id")
        )
        customers = [{"name": c.name, "phone": c.phone} for c in customers_qs]
        count_for_date = len(customers)

        users_data.append({
            "username": user.username,
            "status": status,
            "count": count_for_date,
            "customers": customers,
            
        })

    center_label = center_code  # or center_code.title() if you want it pretty


    context = {
        "center_label": center_label,
        "users_data": users_data,
        "today": today,
        "selected_date": selected_date,
        "search": search,
        "is_admin_view": True,  # if you ever want to show 'Admin view' badge in template
    }
    return render(request, "center_dashboard.html", context)
