"""Page-size settings shared by PDF export and its previews.

PDF content is transformed directly; it is never rasterized for export.
"""

from copy import copy
from math import isfinite

from pypdf import Transformation
from pypdf.errors import PdfReadError
from pypdf.generic import NameObject, RectangleObject


POINTS_PER_MM = 72 / 25.4
PAPER_SIZES_MM = {
    "A4": (210, 297),
    "A3": (297, 420),
    "A5": (148, 210),
    "B4": (257, 364),  # JIS, as used in Japan.
    "B5": (182, 257),
}


def _dimension(value):
    try:
        value = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("用紙の幅・高さは10〜2000 mmで指定してください。") from exc
    if not isfinite(value) or not 10 <= value <= 2000:
        raise ValueError("用紙の幅・高さは10〜2000 mmで指定してください。")
    return value


def size_signature(settings):
    """Return only effective settings, suitable for preview/result cache keys."""
    paper_size = settings.get("paper_size", "original")
    if paper_size == "original":
        return ("original",)
    if paper_size == "custom":
        return (
            "custom",
            _dimension(settings.get("paper_width_mm", 210)),
            _dimension(settings.get("paper_height_mm", 297)),
        )
    if paper_size not in PAPER_SIZES_MM:
        raise ValueError("用紙サイズを選び直してください。")
    orientation = settings.get("paper_orientation", "auto")
    if orientation not in ("auto", "portrait", "landscape"):
        raise ValueError("用紙の向きを選び直してください。")
    return (paper_size, orientation)


def source_size_metadata(source_page):
    """Read the original visible size in mm, including its stored rotation.

    Reading rectangle properties can populate defaults in a page dictionary,
    so even these read-only measurements must operate on a shallow copy.
    """
    try:
        source = copy(source_page)
        media, crop = source.mediabox, source.cropbox
        coordinates = [float(value) for value in (*media, *crop)]
        unit, rotation = float(source.user_unit), float(source.rotation)
        if (len(coordinates) != 8
                or not all(isfinite(v) for v in (*coordinates, unit, rotation))
                or unit <= 0 or rotation % 90):
            raise ValueError("Invalid page geometry")
        left, bottom = max(coordinates[0], coordinates[4]), max(coordinates[1], coordinates[5])
        right, top = min(coordinates[2], coordinates[6]), min(coordinates[3], coordinates[7])
        width, height = (right - left) * unit / POINTS_PER_MM, (top - bottom) * unit / POINTS_PER_MM
        if not all(isfinite(v) and v > 0 for v in (width, height)):
            raise ValueError("Invalid visible page size")
        if rotation % 180:
            width, height = height, width
        return {"source_width_mm": width, "source_height_mm": height}
    except (TypeError, ValueError, KeyError, IndexError, AttributeError, OverflowError, PdfReadError) as exc:
        raise ValueError("元のPDFのページサイズを読み取れませんでした。") from exc


def _source_dimensions(settings, rotated=False):
    try:
        width = float(settings["source_width_mm"])
        height = float(settings["source_height_mm"])
        if not all(isfinite(v) and v > 0 for v in (width, height)):
            return None
        if rotated:
            rotation = settings.get("rotation", 0)
            if not isinstance(rotation, int) or rotation % 90:
                return None
            if rotation % 180:
                width, height = height, width
        return width, height
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def _paper_name(name):
    return name + ("（JIS）" if name.startswith("B") else "")


def _describe_dimensions(width, height, detailed=False):
    # One decimal is useful for actual PDF measurements without displaying
    # floating-point noise or hiding a nonstandard size behind a paper label.
    dimension_text = f"{width:.1f}".removesuffix(".0") + " × " + f"{height:.1f}".removesuffix(".0") + " mm"
    short_side, long_side = sorted((width, height))
    for name, (paper_width, paper_height) in PAPER_SIZES_MM.items():
        if abs(short_side - paper_width) <= 1 and abs(long_side - paper_height) <= 1:
            label = f"{_paper_name(name)}・{'横' if width > height else '縦'}"
            return f"{label}（{dimension_text}）" if detailed else label
    return dimension_text


def describe_source_size(settings, detailed=False):
    """Describe the uploaded page, before any rotation made in the app."""
    dimensions = _source_dimensions(settings)
    if dimensions is None:
        return "サイズ不明"
    return _describe_dimensions(*dimensions, detailed=detailed)


def describe_size(settings):
    signature = size_signature(settings)
    if signature[0] == "original":
        dimensions = _source_dimensions(settings, rotated=True)
        if dimensions is not None:
            return _describe_dimensions(*dimensions) + "（元）"
        return "元のサイズ"
    if signature[0] == "custom":
        return f"{signature[1]:g} × {signature[2]:g} mm"
    name = _paper_name(signature[0])
    orientation = {"auto": "元の向き", "portrait": "縦", "landscape": "横"}
    direction = orientation[signature[1]]
    if signature[1] == "auto":
        dimensions = _source_dimensions(settings, rotated=True)
        if dimensions is not None:
            direction = "横" if dimensions[0] > dimensions[1] else "縦"
    return f"{name}・{direction}"


def add_output_page(writer, source_page, settings):
    """Append one independently sized page without modifying the source PDF.

    The visible CropBox is fitted to the destination, with any existing and
    user-requested clockwise rotations applied first. A fixed-size destination
    uses normal PDF points, including when the input has a non-default UserUnit.
    ``custom`` always respects the explicit width and height.
    """
    signature = size_signature(settings)
    rotation = settings.get("rotation", 0)
    if not isinstance(rotation, int) or rotation % 90:
        raise ValueError("ページの回転は90度単位で指定してください。")
    if signature[0] == "original":
        added = writer.add_page(source_page)
        if rotation % 360:
            added.rotate(rotation % 360)
        return added

    # Rectangle properties may add an inherited default to the page dictionary.
    # Work on a shallow copy so even those lookups leave the source untouched.
    source = copy(source_page)
    media, crop = source.mediabox, source.cropbox
    left = max(float(media.left), float(crop.left))
    bottom = max(float(media.bottom), float(crop.bottom))
    right = min(float(media.right), float(crop.right))
    top = min(float(media.top), float(crop.top))
    unit = float(source.user_unit)
    if (not all(isfinite(v) for v in (left, bottom, right, top, unit))
            or right <= left or top <= bottom or unit <= 0):
        raise ValueError("元のPDFのページサイズを読み取れませんでした。")
    source.cropbox = RectangleObject((left, bottom, right, top))

    # The viewer rotates the page clockwise; PDF content coordinates need the
    # opposite sign. Computing all corners also covers non-zero box origins.
    total_rotation = (source.rotation + rotation) % 360
    if total_rotation % 90:
        raise ValueError("元のPDFのページ回転を読み取れませんでした。")
    transform = Transformation().translate(-left, -bottom).rotate(-total_rotation)
    corners = [transform.apply_on(point) for point in (
        (left, bottom), (left, top), (right, bottom), (right, top)
    )]
    min_x, min_y = min(p[0] for p in corners), min(p[1] for p in corners)
    width = max(p[0] for p in corners) - min_x
    height = max(p[1] for p in corners) - min_y

    if signature[0] == "custom":
        width_mm, height_mm = signature[1:]
    else:
        width_mm, height_mm = PAPER_SIZES_MM[signature[0]]
        landscape = (signature[1] == "landscape"
                     or (signature[1] == "auto" and width > height))
        if landscape:
            width_mm, height_mm = height_mm, width_mm
    target_width, target_height = width_mm * POINTS_PER_MM, height_mm * POINTS_PER_MM

    # Normalize input user-space units and scale with one common factor.
    scale = min(target_width / (width * unit), target_height / (height * unit)) * unit
    offset_x = (target_width - width * scale) / 2
    offset_y = (target_height - height * scale) / 2
    transform = (transform.translate(-min_x, -min_y).scale(scale)
                 .translate(offset_x, offset_y))

    added = writer.add_blank_page(width=target_width, height=target_height)
    if source.pdf is not None:
        writer.pdf_header = max(writer.pdf_header, source.pdf.pdf_header)
    # A page-level transparency group still applies when the whole visible
    # page is placed onto the new sheet.
    if "/Group" in source:
        added[NameObject("/Group")] = source["/Group"].clone(writer)
    # pypdf clips to the source CropBox before transforming it, and carries
    # across resources, searchable text and annotation rectangles/appearances.
    added.merge_transformed_page(source, transform, expand=False)
    return added
