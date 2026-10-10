from django.contrib import admin, messages
from django.utils.html import format_html

from .models import Action, Proof, ProofStatus
from .services import approve_proof, reject_proof


def _thumbnail(proof, size=60):
    if proof and proof.image:
        return format_html(
            '<a href="{0}" target="_blank"><img src="{0}" style="height:{1}px;border-radius:4px;" /></a>',
            proof.image.url,
            size,
        )
    return "-"


class ProofInline(admin.StackedInline):
    model = Proof
    extra = 0
    can_delete = False
    # Status changes go through the "Approve/Reject" actions so points stay consistent.
    readonly_fields = (
        "thumbnail",
        "image_hash",
        "status",
        "verification_note",
        "ai_confidence",
        "uploaded_at",
        "reviewed_at",
    )
    fields = readonly_fields

    @admin.display(description="Preview")
    def thumbnail(self, obj):
        return _thumbnail(obj, 160)

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Action)
class ActionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "action_type",
        "points",
        "points_awarded",
        "proof_status",
        "created_at",
    )
    list_filter = ("action_type", "points_awarded", "proof__status", "created_at")
    search_fields = ("user__email", "user__full_name", "description")
    list_select_related = ("user", "proof")
    readonly_fields = ("points_awarded", "created_at")
    date_hierarchy = "created_at"
    inlines = [ProofInline]

    @admin.display(description="Proof", ordering="proof__status")
    def proof_status(self, obj):
        return obj.proof.status if hasattr(obj, "proof") else "-"


@admin.register(Proof)
class ProofAdmin(admin.ModelAdmin):
    list_display = ("id", "thumbnail", "action", "owner", "status", "ai_confidence", "uploaded_at")
    list_filter = ("status", "uploaded_at")
    search_fields = ("action__user__email", "action__user__full_name", "verification_note")
    list_select_related = ("action", "action__user")
    readonly_fields = (
        "action",
        "thumbnail",
        "image_hash",
        "status",
        "ai_confidence",
        "uploaded_at",
        "reviewed_at",
    )
    fields = ("action", "thumbnail", "image", "image_hash", "status", "verification_note",
              "ai_confidence", "uploaded_at", "reviewed_at")
    actions = ["approve_selected", "reject_selected"]
    date_hierarchy = "uploaded_at"

    @admin.display(description="Preview")
    def thumbnail(self, obj):
        return _thumbnail(obj)

    @admin.display(description="User", ordering="action__user__email")
    def owner(self, obj):
        return obj.action.user

    @admin.action(description="Approve selected proofs (awards points)")
    def approve_selected(self, request, queryset):
        count = 0
        for proof in queryset.exclude(status=ProofStatus.APPROVED):
            approve_proof(proof, note="Approved by moderator.")
            count += 1
        self.message_user(request, f"{count} proof(s) approved.", messages.SUCCESS)

    @admin.action(description="Reject selected proofs (revokes points if awarded)")
    def reject_selected(self, request, queryset):
        count = 0
        for proof in queryset.exclude(status=ProofStatus.REJECTED):
            reject_proof(proof, note="Rejected by moderator.")
            count += 1
        self.message_user(request, f"{count} proof(s) rejected.", messages.SUCCESS)
