from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from alignspace.storage.local import LocalStorage


@pytest.fixture
def storage(tmp_path):
    return LocalStorage(tmp_path / "assets")


def test_save_is_content_addressed_and_round_trips(storage):
    key = storage.save(b"hello world", "jpg")
    assert key.endswith(".jpg")
    assert storage.exists(key) is True
    assert storage.open(key) == b"hello world"


def test_saving_identical_bytes_reuses_one_key(storage):
    assert storage.save(b"same", "png") == storage.save(b"same", "png")


def test_concurrent_identical_saves_use_independent_temporary_files(storage, monkeypatch):
    import alignspace.storage.local as module

    barrier = Barrier(2)
    replace = module.os.replace

    def concurrent_replace(source, destination):
        barrier.wait(timeout=5)
        replace(source, destination)

    monkeypatch.setattr(module.os, "replace", concurrent_replace)
    with ThreadPoolExecutor(max_workers=2) as pool:
        keys = list(pool.map(lambda _: storage.save(b"same", "png"), range(2)))
    assert keys[0] == keys[1]
    assert storage.open(keys[0]) == b"same"
    assert len(list(storage._root.iterdir())) == 1


def test_delete_removes_bytes_and_is_idempotent(storage):
    key = storage.save(b"bye", "webp")
    storage.delete(key)
    storage.delete(key)
    assert storage.exists(key) is False


@pytest.mark.parametrize("key", ["", "../escape.jpg", "nested/key.jpg", ".hidden"])
def test_traversal_like_keys_are_rejected(storage, key):
    with pytest.raises(ValueError):
        storage.open(key)
