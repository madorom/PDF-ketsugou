"""Regression checks for visible PDF geometry and preserved source content.

Run with: python -m unittest discover -s tests -v
Only pypdf and the Python standard library are required.
"""

import io
import math
import unittest

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    DecodedStreamObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    NumberObject,
    RectangleObject,
)

from page_sizes import add_output_page, size_signature


POINTS_PER_MM = 72 / 25.4


def fixture(width=400, height=200, *, crop=None, rotation=0, user_unit=1):
    """Create an actual PDF with a visible border and searchable text."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=width, height=height)
    bounds = crop or (0, 0, width, height)
    page.cropbox = RectangleObject(bounds)
    page[NameObject("/Rotate")] = NumberObject(rotation)
    page[NameObject("/UserUnit")] = FloatObject(user_unit)
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({
            NameObject("/F1"): DictionaryObject({
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }),
        }),
    })
    x0, y0, x1, y1 = bounds
    stream = DecodedStreamObject()
    stream.set_data((
        f"q 0 0 0 RG 0.1 w {x0} {y0} {x1-x0} {y1-y0} re S Q\n"
        f"BT /F1 12 Tf {x0+12} {y0+20} Td (KEEP_TEXT) Tj ET\n"
    ).encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    data = io.BytesIO()
    writer.write(data)
    return PdfReader(io.BytesIO(data.getvalue()))


def snapshot(page):
    return (
        tuple(page.mediabox),
        tuple(page.cropbox),
        page.rotation,
        page.user_unit,
        page.get_contents().get_data(),
    )


def visual_dimensions(page):
    width = float(page.cropbox.width) * float(page.user_unit)
    height = float(page.cropbox.height) * float(page.user_unit)
    return (height, width) if page.rotation % 180 else (width, height)


def multiply(left, right):
    """Compose affine matrices as used by the PDF graphics state."""
    a, b, c, d, e, f = left
    g, h, i, j, k, l = right
    return (
        a*g+c*h, b*g+d*h, a*i+c*j, b*i+d*j,
        a*k+c*l+e, b*k+d*l+f,
    )


def painted_rectangles(page):
    """Inspect painted border coordinates, ignoring clipping-only rectangles."""
    transform = (1, 0, 0, 1, 0, 0)
    stack, path, painted = [], [], []
    for operands, operator in page.get_contents().operations:
        if operator == b"q":
            stack.append(transform)
        elif operator == b"Q":
            transform = stack.pop()
        elif operator == b"cm":
            transform = multiply(transform, tuple(float(x) for x in operands))
        elif operator == b"re":
            x, y, width, height = (float(n) for n in operands)
            a, b, c, d, e, f = transform
            corners = [(a*px+c*py+e, b*px+d*py+f) for px, py in (
                (x, y), (x+width, y), (x+width, y+height), (x, y+height),
            )]
            path.append((min(p[0] for p in corners), min(p[1] for p in corners),
                         max(p[0] for p in corners), max(p[1] for p in corners)))
        elif operator in (b"S", b"s", b"f", b"F", b"f*", b"B", b"B*", b"b", b"b*"):
            painted.extend(path)
            path = []
        elif operator == b"n":
            path = []
    return painted


class PageSizeTests(unittest.TestCase):
    def assert_size_mm(self, page, width, height):
        actual = visual_dimensions(page)
        self.assertAlmostEqual(actual[0] / POINTS_PER_MM, width, places=5)
        self.assertAlmostEqual(actual[1] / POINTS_PER_MM, height, places=5)

    def assert_border_fits_and_is_centered(self, page):
        border, = painted_rectangles(page)
        left, bottom, right, top = map(float, page.cropbox)
        x0, y0, x1, y1 = border
        self.assertGreaterEqual(x0, left - 1e-5)
        self.assertGreaterEqual(y0, bottom - 1e-5)
        self.assertLessEqual(x1, right + 1e-5)
        self.assertLessEqual(y1, top + 1e-5)
        self.assertAlmostEqual(x0-left, right-x1, places=5)
        self.assertAlmostEqual(y0-bottom, top-y1, places=5)
        self.assertTrue(math.isclose(x1-x0, right-left, abs_tol=1e-5)
                        or math.isclose(y1-y0, top-bottom, abs_tol=1e-5))
        return border

    def test_original_keeps_boxes_and_only_adds_requested_rotation(self):
        source = fixture(600, 800, crop=(40, 70, 440, 270), rotation=90,
                         user_unit=2).pages[0]
        before = snapshot(source)
        output = add_output_page(PdfWriter(), source,
                                 {"paper_size": "original", "rotation": 90})
        self.assertEqual(tuple(output.mediabox), before[0])
        self.assertEqual(tuple(output.cropbox), before[1])
        self.assertEqual(output.rotation % 360, 180)
        self.assertEqual(output.user_unit, 2)
        self.assertIn("KEEP_TEXT", output.extract_text())
        self.assertEqual(snapshot(source), before)

    def test_mixed_pages_become_exact_a4_with_automatic_orientation(self):
        writer = PdfWriter()
        for width, height, expected in (
            (300, 600, (210, 297)),
            (900, 600, (297, 210)),
            (400, 400, (210, 297)),
        ):
            with self.subTest(width=width, height=height):
                source = fixture(width, height).pages[0]
                output = add_output_page(writer, source,
                                         {"paper_size": "A4", "paper_orientation": "auto"})
                self.assert_size_mm(output, *expected)
                self.assert_border_fits_and_is_centered(output)
        data = io.BytesIO()
        writer.write(data)
        reopened = PdfReader(io.BytesIO(data.getvalue()))
        self.assertEqual(len(reopened.pages), 3)
        self.assertTrue(all("KEEP_TEXT" in page.extract_text() for page in reopened.pages))

    def test_a3_landscape_and_explicit_custom_dimensions(self):
        source = fixture().pages[0]
        cases = (
            ({"paper_size": "A3", "paper_orientation": "landscape"}, (420, 297)),
            ({"paper_size": "custom", "paper_orientation": "auto",
              "paper_width_mm": 200, "paper_height_mm": 100}, (200, 100)),
        )
        for settings, expected in cases:
            with self.subTest(settings=settings):
                output = add_output_page(PdfWriter(), source, settings)
                self.assert_size_mm(output, *expected)
                self.assert_border_fits_and_is_centered(output)

    def test_fit_preserves_aspect_ratio_with_balanced_margins(self):
        source = fixture(400, 200).pages[0]
        output = add_output_page(PdfWriter(), source,
                                 {"paper_size": "A4", "paper_orientation": "portrait"})
        x0, y0, x1, y1 = self.assert_border_fits_and_is_centered(output)
        self.assertAlmostEqual((x1-x0) / (y1-y0), 2, places=6)
        self.assertGreater(y0, 0)

    def test_rotated_crop_with_nonzero_origin_and_user_unit(self):
        for rotation in (0, 90, 180, 270):
            with self.subTest(rotation=rotation):
                source = fixture(600, 800, crop=(40, 70, 440, 270),
                                 rotation=rotation, user_unit=2).pages[0]
                before = snapshot(source)
                output = add_output_page(PdfWriter(), source,
                                         {"paper_size": "A4", "paper_orientation": "auto"})
                expected = (210, 297) if rotation % 180 else (297, 210)
                self.assert_size_mm(output, *expected)
                self.assert_border_fits_and_is_centered(output)
                self.assertEqual(snapshot(source), before)

    def test_additional_rotation_is_used_before_automatic_orientation(self):
        source = fixture(200, 400, rotation=90).pages[0]
        output = add_output_page(PdfWriter(), source, {
            "paper_size": "A4", "paper_orientation": "auto", "rotation": 90,
        })
        self.assert_size_mm(output, 210, 297)
        self.assert_border_fits_and_is_centered(output)

    def test_resizing_twice_does_not_change_the_source_or_first_output(self):
        source = fixture(400, 200).pages[0]
        before = snapshot(source)
        writer = PdfWriter()
        first = add_output_page(writer, source, {"paper_size": "A4"})
        first_before = snapshot(first)
        add_output_page(writer, source, {"paper_size": "A3", "rotation": 90})
        self.assertEqual(snapshot(source), before)
        self.assertEqual(snapshot(first), first_before)

    def test_custom_sizes_reject_nonfinite_and_out_of_range_values(self):
        source = fixture().pages[0]
        for dimension in (0, -10, 9.9, 2000.1, float("nan"), float("inf")):
            with self.subTest(dimension=dimension):
                with self.assertRaises(ValueError):
                    add_output_page(PdfWriter(), source, {
                        "paper_size": "custom", "paper_width_mm": dimension,
                        "paper_height_mm": 100,
                    })

    def test_signature_changes_when_output_size_settings_change(self):
        cases = (
            ({}, {"paper_size": "A4"}),
            ({"paper_size": "A4"}, {"paper_size": "A3"}),
            ({"paper_size": "A4", "paper_orientation": "portrait"},
             {"paper_size": "A4", "paper_orientation": "landscape"}),
            ({"paper_size": "custom", "paper_width_mm": 200, "paper_height_mm": 100},
             {"paper_size": "custom", "paper_width_mm": 250, "paper_height_mm": 100}),
        )
        for before, after in cases:
            with self.subTest(before=before, after=after):
                self.assertNotEqual(size_signature(before), size_signature(after))


if __name__ == "__main__":
    unittest.main()
