from asgiref.sync import iscoroutinefunction


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