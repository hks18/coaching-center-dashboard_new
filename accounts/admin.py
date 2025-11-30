from django.contrib import admin
from .models import Profile, DailyCustomer


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "center")
    list_filter = ("role", "center")
    search_fields = ("user__username", "user__email")


@admin.register(DailyCustomer)
class DailyCustomerAdmin(admin.ModelAdmin):
    list_display = ("user", "date", "name", "phone")
    list_filter = ("date", "user__profile__center")
    search_fields = ("user__username", "name", "phone")
