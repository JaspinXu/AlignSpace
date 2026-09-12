import hashlib
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, UnidentifiedImageError

MAX_BYTES = 10 * 1024 * 1024

FORMATS = {
    "JPEG": ("image/jpeg", "jpg"),
    "PNG": ("image/png", "png"),
    "WEBP": ("image/webp", "webp"),
}


class ImageValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class PreparedImage:
    data: bytes
    media_type: str
    extension: str
    sha256: str
    width: int
    height: int


def prepare_image(
    raw: bytes,
    *,
    declared_type: str | None = None,
    filename: str | None = None,
) -> PreparedImage:
    if len(raw) > MAX_BYTES:
        raise ImageValidationError("ASSET_TOO_LARGE", "图片不得超过 10MB。")
    try:
        with Image.open(BytesIO(raw)) as probe:
            probe.verify()
        with Image.open(BytesIO(raw)) as image:
            image.load()
            image_format = image.format or ""
            if image_format not in FORMATS:
                raise ImageValidationError("UNSUPPORTED_MEDIA_TYPE", "仅支持 JPEG、PNG、WebP。")
            media_type, extension = FORMATS[image_format]
            if declared_type not in {None, "", "application/octet-stream", media_type}:
                raise ImageValidationError("UNSUPPORTED_MEDIA_TYPE", "文件类型与图片内容不匹配。")
            if filename:
                suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
                declared_extension = {"jpg": "jpg", "jpeg": "jpg", "png": "png", "webp": "webp"}.get(suffix)
                if suffix and declared_extension is None:
                    raise ImageValidationError("UNSUPPORTED_MEDIA_TYPE", "仅支持 JPEG、PNG、WebP。")
                if declared_extension is not None and declared_extension != extension:
                    raise ImageValidationError("UNSUPPORTED_MEDIA_TYPE", "文件扩展名与图片内容不匹配。")
            width, height = image.size
            buffer = BytesIO()
            # Re-encoding without passing exif= drops EXIF/GPS metadata.
            image.save(buffer, format=image_format)
            cleaned = buffer.getvalue()
    except ImageValidationError:
        raise
    except Image.DecompressionBombError:
        raise ImageValidationError("ASSET_TOO_LARGE", "图片像素尺寸过大。") from None
    except (UnidentifiedImageError, OSError, ValueError):
        raise ImageValidationError("INVALID_IMAGE", "无法识别的图片文件。") from None
    return PreparedImage(
        data=cleaned,
        media_type=media_type,
        extension=extension,
        sha256=hashlib.sha256(cleaned).hexdigest(),
        width=width,
        height=height,
    )
