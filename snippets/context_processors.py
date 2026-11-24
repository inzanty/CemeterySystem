from .moderation import is_moderator
from datetime import timedelta
from django.utils import timezone
from .models import GraveFee


def moderation_access(request):
    match = request.resolver_match
    page = (match.url_name or "") if match else ""
    if page.startswith("moderator-") or page == "record-history" or (match and match.namespace == "admin"):
        category = "management"
    elif page in {"fee-reminders", "saved-graves", "request-list", "request-detail", "register", "login"}:
        category = "account"
    else:
        category = "discover"
    due_count = 0
    if request.user.is_authenticated:
        due_count = GraveFee.objects.filter(grave__saved_entries__user=request.user,
            valid_until__lte=timezone.localdate() + timedelta(days=30)).count()
    return {"fee_reminder_count": due_count, "can_moderate": is_moderator(request.user),
            "navigation_category": category, "navigation_page": page}
