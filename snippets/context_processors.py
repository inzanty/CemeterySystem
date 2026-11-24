from .moderation import is_moderator


def moderation_access(request):
    match = request.resolver_match
    page = (match.url_name or "") if match else ""
    if page.startswith("moderator-") or page == "record-history" or (match and match.namespace == "admin"):
        category = "management"
    elif page in {"saved-graves", "request-list", "request-detail", "register", "login"}:
        category = "account"
    else:
        category = "discover"
    return {"can_moderate": is_moderator(request.user),
            "navigation_category": category, "navigation_page": page}
