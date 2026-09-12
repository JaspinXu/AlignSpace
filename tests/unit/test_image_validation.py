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


def test_decompression_bomb_is_rejected(monkeypatch):
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 4)
    with pytest.raises(ImageValidationError) as error:
        prepare_image(encode(Image.new("RGB", (8, 8), "red"), "PNG"))
    assert error.value.code == "ASSET_TOO_LARGE"


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


def test_declared_media_type_must_match_image_bytes():
    with pytest.raises(ImageValidationError) as error:
        prepare_image(
            encode(Image.new("RGB", (4, 4), "red"), "PNG"),
            declared_type="text/plain",
        )
    assert error.value.code == "UNSUPPORTED_MEDIA_TYPE"


def test_filename_extension_must_match_image_bytes():
    with pytest.raises(ImageValidationError) as error:
        prepare_image(
            encode(Image.new("RGB", (4, 4), "red"), "PNG"),
            filename="photo.jpg",
        )
    assert error.value.code == "UNSUPPORTED_MEDIA_TYPE"


@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "WEBP"])
def test_exif_and_gps_are_stripped(fmt):
    source = Image.new("RGB", (8, 8), "blue")
    exif = Image.Exif()
    exif[0x010F] = "SecretCamera"  # Make
    exif[0x0112] = 3  # Orientation
    exif[0x8825] = {1: "N", 2: (1, 2, 3)}  # GPS latitude
    raw = encode(source, fmt, exif=exif.tobytes())
    assert Image.open(BytesIO(raw)).getexif()

    prepared = prepare_image(raw)

    assert not Image.open(BytesIO(prepared.data)).getexif()


@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "WEBP"])
def test_orientation_is_applied_before_metadata_removal(fmt):
    exif = Image.Exif()
    exif[0x0112] = 6
    prepared = prepare_image(encode(Image.new("RGB", (8, 6), "red"), fmt, exif=exif))
    assert (prepared.width, prepared.height) == (6, 8)


def test_palette_transparency_survives_normalization():
    source = Image.new("P", (4, 4))
    prepared = prepare_image(encode(source, "PNG", transparency=0))
    assert Image.open(BytesIO(prepared.data)).convert("RGBA").getpixel((0, 0))[3] == 0
