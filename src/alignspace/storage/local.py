import hashlib
import os
from pathlib import Path


class LocalStorage:
    """Content-addressed local filesystem storage.

    Keys are ``<sha256>.<extension>`` and never contain caller-supplied paths,
    so a key can never escape the configured root.
    """

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)

    def save(self, data: bytes, extension: str) -> str:
        key = f"{hashlib.sha256(data).hexdigest()}.{extension.lstrip('.').lower()}"
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".tmp")
        temporary.write_bytes(data)
        os.replace(temporary, target)
        return key

    def open(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def _path(self, key: str) -> Path:
        valid = (
            key
            and key[0] not in ".\\"
            and "/" not in key
            and "\\" not in key
        )
        if not valid:
            raise ValueError("invalid storage key")
        return self._root / key
