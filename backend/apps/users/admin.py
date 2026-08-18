"""Django admin for User.

Spec §2 leans on the built-in admin as the taxonomy configuration tool, so it is
a first-class surface here rather than a debug convenience.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from simple_history.admin import SimpleHistoryAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin, SimpleHistoryAdmin):
    list_display = ["username", "full_name", "role", "partner", "account_status", "last_login"]
    list_filter = ["role", "account_status", "is_staff"]
    search_fields = ["username", "full_name", "work_email", "personal_email"]
    ordering = ["full_name"]
    list_select_related = ["partner"]
    autocomplete_fields = ["partner"]

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Identity", {"fields": ("full_name",)}),
        ("Contact", {"fields": ("work_email", "personal_email", "work_phone", "personal_phone")}),
        ("Role and scope", {"fields": ("role", "woreda_assignment", "partner", "account_status")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "full_name", "role", "woreda_assignment", "password1", "password2"),
            },
        ),
    )
