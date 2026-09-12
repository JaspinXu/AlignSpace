from io import BytesIO

import pytest
from PIL import Image

from alignspace.storage.images import MAX_BYTES, ImageValidationError, prepare_image


def encode(image: Image.Image, fmt: str, **kwargs) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format=fmt, **kwargs)
    return buffer.getvalue()


@pytest.mark.parametrize(
    ("fmt", "media_type", "extension"),
    [("JPEG", "image/jpeg", "jpg"), ("PNG", "image/png", "png"), ("WEBP", "image/webp", "webp")],
)
def test_supported_formats_are_normalized(fmt, media_type, extension):
    prepared = prepare_image(encode(Image.new("RGB", (8, 6), "red"), fmt))
    assert prepared.media_type == media_type
    assert prepared.extension == extension
    assert (prepared.width, prepared.height) == (8, 6)
    assert len(prepared.sha256) == 64


def test_oversized_payload_is_rejected():
    with pytest.raises(ImageValidationError) as error:
        prepare_image(b"\x00" * (MAX_BYTES + 1))
    assert error.value.code == "ASSET_TOO_LARGE"


def test_non_image_payload_is_rejected():
    with pytest.raises(ImageValidationError) as error:
        prepare_image(b"definitely not an image")
    assert error.value.code == "INVALID_IMAGE"


def test_unsupported_format_is_rejected():
    with pytest.raises(ImageValidationError) as error:
        prepare_image(encode(Image.new("RGB", (4, 4), "red"), "GIF"))
    assert error.value.code == "UNSUPPORTED_MEDIA_TYPE"


def test_exif_and_gps_are_stripped():
    source = Image.new("RGB", (8, 8), "blue")
    exif = Image.Exif()
    exif[0x010F] = "SecretCamera"  # Make
    exif[0x0112] = 3  # Orientation
    raw = encode(source, "JPEG", exif=exif.tobytes())
    assert Image.open(BytesIO(raw)).getexif()

    prepared = prepare_image(raw)

    assert not Image.open(BytesIO(prepared.data)).getexif()
