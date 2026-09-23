import hashlib


def sha256_of_upload(uploaded_file) -> str:
    """Hashes an uploaded file's bytes without reading it all into memory at once, then rewinds it
    so the caller can still hand it to `FileField.save()`."""
    digest = hashlib.sha256()
    for chunk in uploaded_file.chunks():
        digest.update(chunk)
    uploaded_file.seek(0)
    return digest.hexdigest()
