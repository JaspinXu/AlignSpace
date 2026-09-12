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


def test_delete_removes_bytes_and_is_idempotent(storage):
    key = storage.save(b"bye", "webp")
    storage.delete(key)
    storage.delete(key)
    assert storage.exists(key) is False


@pytest.mark.parametrize("key", ["", "../escape.jpg", "nested/key.jpg", ".hidden"])
def test_traversal_like_keys_are_rejected(storage, key):
    with pytest.raises(ValueError):
        storage.open(key)
