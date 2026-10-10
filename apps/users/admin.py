from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import BaseUserCreationForm, UserChangeForm
from django.utils.html import format_html

from .models import Profile, User, UserStats


class UserCreationForm(BaseUserCreationForm):
    class Meta(BaseUserCreationForm.Meta):
        model = User
        fields = ("email", "full_name")
        field_classes = {}


class UserAdminChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User
        fields = "__all__"
        field_classes = {}


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    extra = 0


class UserStatsInline(admin.StackedInline):
    model = UserStats
    can_delete = False
    extra = 0


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    form = UserAdminChangeForm
    add_form = UserCreationForm

    ordering = ("-date_joined",)
    list_display = ("email", "full_name", "is_active", "is_staff", "date_joined")
    list_filter = ("is_active", "is_staff", "is_superuser", "date_joined")
    search_fields = ("email", "full_name")
    readonly_fields = ("last_login", "date_joined")
    inlines = [ProfileInline, UserStatsInline]

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("full_name",)}),
        (
            "Permissions",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "full_name", "password1", "password2")}),
    )


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "city", "picture_preview", "updated_at")
    search_fields = ("user__email", "user__full_name", "city")
    list_select_related = ("user",)
    readonly_fields = ("picture_preview", "created_at", "updated_at")

    @admin.display(description="Picture")
    def picture_preview(self, obj):
        if obj.profile_picture:
            return format_html(
                '<img src="{}" style="height:48px;width:48px;border-radius:50%;object-fit:cover;" />',
                obj.profile_picture.url,
            )
        return "-"


@admin.register(UserStats)
class UserStatsAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "points",
        "level",
        "current_streak",
        "longest_streak",
        "total_actions",
        "last_action_date",
    )
    list_select_related = ("user",)
    search_fields = ("user__email", "user__full_name")
    ordering = ("-points",)
