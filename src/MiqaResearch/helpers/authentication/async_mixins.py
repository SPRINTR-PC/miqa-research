from django.contrib.auth.mixins import AccessMixin
from django.contrib.auth.views import redirect_to_login


class AsyncLoginRequiredMixin(AccessMixin):
    """Async compatible of LoginRequiredMixin."""

    async def dispatch(self, request, *args, **kwargs):
        if not (await request.auser()).is_authenticated:
            return self.handle_no_permission()

        return await super().dispatch(request, *args, **kwargs)

    def handle_no_permission(self):
        return redirect_to_login(self.request.get_full_path(), self.get_login_url(), self.get_redirect_field_name())
