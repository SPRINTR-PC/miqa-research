# Sent when a session ends (logout, expiry) so the browser drops cached WADO frames/metadata (#276).
# Only "cache": viewer drafts in IndexedDB ("storage") must survive.
CLEAR_SITE_DATA_CACHE = '"cache"'


def get_client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
