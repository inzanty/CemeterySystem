from .moderation import is_moderator


def moderation_access(request):
    return {"can_moderate": is_moderator(request.user)}
