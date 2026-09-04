from asgiref.sync import async_to_sync, iscoroutinefunction, markcoroutinefunction
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
    Middleware to automatically resolve request.auser() so templates and
    views don't throw a SynchronousOnlyOperation error when they touch
    request.user from inside an async view.

    Whether get_response ends up sync or async depends on the *handler*
    serving the request (ASGI vs WSGI), not on whether the matched view is
    async — under WSGI, Django presents the whole middleware chain as
    synchronous even though an async view is invoked further down via
    async_to_sync. So both branches below resolve request.user explicitly,
    rather than skipping it whenever this middleware happens to run in sync
    mode.
    """
    sync_capable = True
    async_capable = True

    def __init__(self, get_response):
        self.get_response = get_response
        # Determine if the subsequent view/middleware is async
        self.is_async = iscoroutinefunction(self.get_response)
        if self.is_async:
            # __call__ is a plain (non-async-def) method that only *returns*
            # a coroutine conditionally, so Django/asgiref can't infer
            # async-ness from its signature. Whatever middleware wraps us
            # next (e.g. Django's MiddlewareMixin-based ones) checks
            # iscoroutinefunction(self) directly, so mark it explicitly -
            # otherwise it misdetects us as sync and calls us without
            # awaiting, blowing up with "'coroutine' object has no
            # attribute ..." under a real ASGI server.
            markcoroutinefunction(self)

    def __call__(self, request):
        if self.is_async:
            # If it's an async request path, route to the async handler
            return self.__acall__(request)

        if hasattr(request, 'auser'):
            request.user = async_to_sync(request.auser)()

        return self.get_response(request)

    async def __acall__(self, request):
        # Await the user and overwrite the SimpleLazyObject
        if hasattr(request, 'auser'):
            request.user = await request.auser()

        # Proceed with the response asynchronously
        return await self.get_response(request)
