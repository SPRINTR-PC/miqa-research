class PagePathConverter:
    """One or more ``[A-Za-z0-9_-]`` segments separated by ``/``: no dots, no empty segments."""

    regex = r"[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*"

    def to_python(self, value):
        return value

    def to_url(self, value):
        return value
