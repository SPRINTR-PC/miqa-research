class PagePathConverter:
    """One or more ``[A-Za-z0-9_-]`` segments separated by ``/``: no dots, no empty segments."""

    regex = r"[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*"

    def to_python(self, value):
        return value

    def to_url(self, value):
        return value


class AssetFileConverter:
    """A single file name; dots allowed but not leading, so no ``.``/``..`` or hidden files."""

    regex = r"[A-Za-z0-9_-][A-Za-z0-9._-]*"

    def to_python(self, value):
        return value

    def to_url(self, value):
        return value


class DownloadHashConverter:
    """The hash directory Sphinx puts each download in."""

    regex = r"[0-9a-f]+"

    def to_python(self, value):
        return value

    def to_url(self, value):
        return value
