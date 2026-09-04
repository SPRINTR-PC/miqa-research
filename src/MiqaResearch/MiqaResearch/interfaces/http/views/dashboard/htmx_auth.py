from functools import wraps

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django_htmx.http import HttpResponseClientRedirect


def htmx_login_required(view_func):
    """
    Like django.contrib.auth.decorators.login_required, but an htmx request
    from an anonymous/expired session gets an HX-Redirect header instead of a
    normal 302, so the login page isn't swapped into the requesting element.
    """

    @wraps(view_func)
    async def wrapped(request, *args, **kwargs):
        if (await request.auser()).is_authenticated:
            return await view_func(request, *args, **kwargs)
        if request.htmx:
            return HttpResponseClientRedirect(settings.LOGIN_URL)
        return redirect_to_login(request.get_full_path())

    return wrapped
