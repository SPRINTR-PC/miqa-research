from asgiref.sync import iscoroutinefunction
from django.conf import settings
from django.contrib.auth import logout
from django.utils import timezone

from contract.constants.audit_log import EVENT_TYPE_SESSION_EXPIRED
from helpers.http import get_client_ip

_CREATED_AT_KEY = "_mires_session_created_at"
_LAST_ACTIVITY_KEY = "_mires_session_last_activity"


class SessionTimeoutMiddleware:
    """Enforces the session's absolute max lifetime and sliding idle timeout.

    Django's SESSION_COOKIE_AGE alone can't express both an absolute cap and
    an independent sliding idle timeout at once, so both are tracked here via
    timestamps stored in the session itself. Skipped entirely in DEBUG.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not settings.DEBUG and getattr(request.user, "is_authenticated", False):
            self._enforce_timeout(request)
        return self.get_response(request)

    def _enforce_timeout(self, request):
        from MiqaResearch.data.models import AuditLog

        now = timezone.now().timestamp()
        created_at = request.session.get(_CREATED_AT_KEY)
        last_activity = request.session.get(_LAST_ACTIVITY_KEY)

        if created_at is None:
            request.session[_CREATED_AT_KEY] = now
            request.session[_LAST_ACTIVITY_KEY] = now
            return

        reason = None
        if now - created_at > settings.SESSION_COOKIE_AGE:
            reason = "max_lifetime"
        elif last_activity is not None and now - last_activity > settings.SESSION_IDLE_TIMEOUT:
            reason = "idle_timeout"

        if reason:
            user = request.user
            ip_address = get_client_ip(request)
            session_key = request.session.session_key
            logout(request)
            AuditLog.objects.record(
                EVENT_TYPE_SESSION_EXPIRED,
                user=user,
                ip_address=ip_address,
                session_key=session_key,
                metadata={"reason": reason},
            )
            return

        request.session[_LAST_ACTIVITY_KEY] = now


class AsyncUserMiddleware:
    """
    Middleware to automatically resolve request.auser() in async views
    so templates don't throw a SynchronousOnlyOperation error.
    """
    sync_capable = True
    async_capable = True

    def __init__(self, get_response):
        self.get_response = get_response
        # Determine if the subsequent view/middleware is async
        self.is_async = iscoroutinefunction(self.get_response)

    def __call__(self, request):
        if self.is_async:
            # If it's an async request path, route to the async handler
            return self.__acall__(request)

        # If it's a standard synchronous request, do nothing and pass it along
        return self.get_response(request)

    async def __acall__(self, request):
        # Await the user and overwrite the SimpleLazyObject
        if hasattr(request, 'auser'):
            request.user = await request.auser()

        # Proceed with the response asynchronously
        return await self.get_response(request)