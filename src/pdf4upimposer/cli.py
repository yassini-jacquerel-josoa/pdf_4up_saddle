from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Sequence

import fitz  # PyMuPDF

MM_TO_PT = 72.0 / 25.4
A4_PORTRAIT = (210 * MM_TO_PT, 297 * MM_TO_PT)


def mm_to_pt(value: float) -> float:
    return value * MM_TO_PT


def pt_to_mm(value: float) -> float:
    return value / MM_TO_PT


def rect_size_mm(rect: fitz.Rect) -> tuple[float, float]:
    return pt_to_mm(rect.width), pt_to_mm(rect.height)


def parse_size_mm(text: str) -> tuple[float, float]:
    normalized = text.lower().replace(" ", "").replace("mm", "").replace("cm", "")
    if "x" not in normalized:
        raise argparse.ArgumentTypeError("Use the format WIDTHxHEIGHT, for example 125x85")
    left, right = normalized.split("x", 1)
    try:
        return float(left), float(right)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Width and height must be numbers, for example 125x85") from exc


def is_valid_rect(rect: fitz.Rect) -> bool:
    return rect is not None and rect.width > 0.1 and rect.height > 0.1


def nearly_same_rect(a: fitz.Rect, b: fitz.Rect, tolerance: float = 0.75) -> bool:
    return (
        abs(a.x0 - b.x0) <= tolerance
        and abs(a.y0 - b.y0) <= tolerance
        and abs(a.x1 - b.x1) <= tolerance
        and abs(a.y1 - b.y1) <= tolerance
    )


def center_rect(container: fitz.Rect, width: float, height: float) -> fitz.Rect:
    x0 = container.x0 + (container.width - width) / 2
    y0 = container.y0 + (container.height - height) / 2
    return fitz.Rect(x0, y0, x0 + width, y0 + height)


def safe_intersect(a: fitz.Rect, b: fitz.Rect) -> fitz.Rect:
    r = fitz.Rect(max(a.x0, b.x0), max(a.y0, b.y0), min(a.x1, b.x1), min(a.y1, b.y1))
    if r.width <= 0 or r.height <= 0:
        return fitz.Rect(a)
    return r


@dataclass(frozen=True)
class PageBoxes:
    media: fitz.Rect
    crop: fitz.Rect
    trim: fitz.Rect
    bleed: fitz.Rect
    trim_source: str
    bleed_source: str


@dataclass(frozen=True)
class Placement:
    source_index: Optional[int]
    page_number: Optional[int]
    target_trim: fitz.Rect
    position_in_spread: str  # left or right


def get_pdf_box(page: fitz.Page, name: str, fallback: fitz.Rect) -> fitz.Rect:
    try:
        value = getattr(page, name)
    except Exception:
        return fitz.Rect(fallback)
    if callable(value):
        try:
            value = value()
        except Exception:
            return fitz.Rect(fallback)
    try:
        rect = fitz.Rect(value)
    except Exception:
        return fitz.Rect(fallback)
    if not is_valid_rect(rect):
        return fitz.Rect(fallback)
    return rect


def read_page_boxes(page: fitz.Page, trim_size_mm: Optional[tuple[float, float]]) -> PageBoxes:
    media = get_pdf_box(page, "mediabox", fitz.Rect(0, 0, page.rect.width, page.rect.height))
    crop = get_pdf_box(page, "cropbox", media)
    trim = get_pdf_box(page, "trimbox", crop)
    bleed = get_pdf_box(page, "bleedbox", crop)

    if trim_size_mm:
        trim_w_pt = mm_to_pt(trim_size_mm[0])
        trim_h_pt = mm_to_pt(trim_size_mm[1])
        trim = center_rect(media, trim_w_pt, trim_h_pt)
        trim_source = "manual centered in MediaBox"
    elif is_valid_rect(trim) and not nearly_same_rect(trim, media):
        trim_source = "PDF TrimBox"
    elif is_valid_rect(crop) and not nearly_same_rect(crop, media):
        trim = crop
        trim_source = "PDF CropBox"
    else:
        trim = media
        trim_source = "PDF MediaBox"

    if is_valid_rect(bleed) and not nearly_same_rect(bleed, trim) and bleed.contains(trim):
        bleed_source = "PDF BleedBox"
    else:
        bleed = trim
        bleed_source = "same as TrimBox"

    return PageBoxes(media=media, crop=crop, trim=trim, bleed=bleed, trim_source=trim_source, bleed_source=bleed_source)


def requested_bleeds_pt(args: argparse.Namespace, position_in_spread: str) -> tuple[float, float, float, float]:
    outer = mm_to_pt(args.bleed_mm)
    spine = mm_to_pt(args.spine_bleed_mm)
    top = mm_to_pt(args.bleed_mm)
    bottom = mm_to_pt(args.bleed_mm)
    if position_in_spread == "left":
        return outer, top, spine, bottom
    return spine, top, outer, bottom


def source_clip_from_trim(
    boxes: PageBoxes,
    args: argparse.Namespace,
    position_in_spread: str,
) -> fitz.Rect:
    left, top, right, bottom = requested_bleeds_pt(args, position_in_spread)
    requested = fitz.Rect(
        boxes.trim.x0 - left,
        boxes.trim.y0 - top,
        boxes.trim.x1 + right,
        boxes.trim.y1 + bottom,
    )
    if args.clip_to_bleed_box and boxes.bleed_source == "PDF BleedBox":
        requested = safe_intersect(requested, boxes.bleed)
    return safe_intersect(requested, boxes.media)


def target_rect_from_clip(
    source_clip: fitz.Rect,
    source_trim: fitz.Rect,
    target_trim: fitz.Rect,
    scale: float,
) -> fitz.Rect:
    left = (source_trim.x0 - source_clip.x0) * scale
    top = (source_trim.y0 - source_clip.y0) * scale
    right = (source_clip.x1 - source_trim.x1) * scale
    bottom = (source_clip.y1 - source_trim.y1) * scale
    return fitz.Rect(
        target_trim.x0 - left,
        target_trim.y0 - top,
        target_trim.x1 + right,
        target_trim.y1 + bottom,
    )


def draw_crop_corner(
    page: fitz.Page,
    rect: fitz.Rect,
    corner: str,
    length: float,
    offset: float,
    width: float,
) -> None:
    x0, y0, x1, y1 = rect.x0, rect.y0, rect.x1, rect.y1
    color = (0, 0, 0)
    if corner == "tl":
        page.draw_line((x0 - offset - length, y0), (x0 - offset, y0), color=color, width=width)
        page.draw_line((x0, y0 - offset - length), (x0, y0 - offset), color=color, width=width)
    elif corner == "tr":
        page.draw_line((x1 + offset, y0), (x1 + offset + length, y0), color=color, width=width)
        page.draw_line((x1, y0 - offset - length), (x1, y0 - offset), color=color, width=width)
    elif corner == "bl":
        page.draw_line((x0 - offset - length, y1), (x0 - offset, y1), color=color, width=width)
        page.draw_line((x0, y1 + offset), (x0, y1 + offset + length), color=color, width=width)
    elif corner == "br":
        page.draw_line((x1 + offset, y1), (x1 + offset + length, y1), color=color, width=width)
        page.draw_line((x1, y1 + offset), (x1, y1 + offset + length), color=color, width=width)


def draw_marks_for_page(page: fitz.Page, rect: fitz.Rect, args: argparse.Namespace, position_in_spread: str) -> None:
    length = mm_to_pt(args.mark_length_mm)
    offset = mm_to_pt(args.mark_offset_mm)
    width = args.mark_width_pt
    if args.marks_style == "full":
        corners = ("tl", "tr", "bl", "br")
    elif position_in_spread == "left":
        corners = ("tl", "bl")
    else:
        corners = ("tr", "br")
    for corner in corners:
        draw_crop_corner(page, rect, corner, length, offset, width)


def draw_fold_marks(page: fitz.Page, left_trim: fitz.Rect, right_trim: fitz.Rect, args: argparse.Namespace) -> None:
    if not args.fold_marks:
        return
    color = (0, 0, 0)
    width = args.mark_width_pt
    offset = mm_to_pt(args.mark_offset_mm)
    length = mm_to_pt(args.mark_length_mm)
    x = (left_trim.x1 + right_trim.x0) / 2
    y0 = min(left_trim.y0, right_trim.y0)
    y1 = max(left_trim.y1, right_trim.y1)
    page.draw_line((x, y0 - offset - length), (x, y0 - offset), color=color, width=width)
    page.draw_line((x, y1 + offset), (x, y1 + offset + length), color=color, width=width)


def draw_debug_rect(page: fitz.Page, rect: fitz.Rect, color: tuple[float, float, float], width: float = 0.4) -> None:
    page.draw_rect(rect, color=color, width=width)


def page_number_to_index(page_number: int, original_page_count: int) -> Optional[int]:
    if 1 <= page_number <= original_page_count:
        return page_number - 1
    return None


def booklet_strips(original_page_count: int, padded_count: int) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    strips = []
    for i in range(padded_count // 4):
        outside = (padded_count - 2 * i, 1 + 2 * i)
        inside = (2 + 2 * i, padded_count - 1 - 2 * i)
        strips.append((outside, inside))
    return strips


def build_row_trim_rects(sheet_rect: fitz.Rect, trim_w: float, trim_h: float, args: argparse.Namespace) -> list[tuple[fitz.Rect, fitz.Rect]]:
    spine_gap = mm_to_pt(args.spine_gap_mm)
    row_gap = mm_to_pt(args.row_gap_mm)
    spread_w = 2 * trim_w + spine_gap
    total_h = 2 * trim_h + row_gap
    if spread_w > sheet_rect.width or total_h > sheet_rect.height:
        raise ValueError(
            "The trim layout does not fit the sheet. Try A4 landscape, smaller trim size, or smaller gaps."
        )
    x0 = sheet_rect.x0 + (sheet_rect.width - spread_w) / 2
    y0 = sheet_rect.y0 + (sheet_rect.height - total_h) / 2
    rows = []
    for row in range(2):
        top = y0 + row * (trim_h + row_gap)
        left = fitz.Rect(x0, top, x0 + trim_w, top + trim_h)
        right = fitz.Rect(x0 + trim_w + spine_gap, top, x0 + 2 * trim_w + spine_gap, top + trim_h)
        rows.append((left, right))
    return rows


def add_blank_box(page: fitz.Page, rect: fitz.Rect, args: argparse.Namespace) -> None:
    if args.debug_boxes:
        page.draw_rect(rect, color=(0.7, 0.7, 0.7), width=0.5)
        page.insert_textbox(rect, "BLANK", fontsize=10, color=(0.45, 0.45, 0.45), align=fitz.TEXT_ALIGN_CENTER)


def place_source_page(
    out_page: fitz.Page,
    src: fitz.Document,
    placement: Placement,
    args: argparse.Namespace,
    scale: float,
) -> None:
    if placement.source_index is None:
        add_blank_box(out_page, placement.target_trim, args)
        return
    source_page = src[placement.source_index]
    boxes = read_page_boxes(source_page, args.trim_size_mm)
    clip = source_clip_from_trim(boxes, args, placement.position_in_spread)
    target = target_rect_from_clip(clip, boxes.trim, placement.target_trim, scale)
    out_page.show_pdf_page(target, src, placement.source_index, clip=clip, keep_proportion=False)

    if args.debug_boxes:
        draw_debug_rect(out_page, target, (1, 0, 0), 0.4)
        draw_debug_rect(out_page, placement.target_trim, (0, 0, 1), 0.5)

    if args.labels and placement.page_number is not None:
        label = f"p.{placement.page_number}"
        label_rect = fitz.Rect(placement.target_trim.x0 + 3, placement.target_trim.y0 + 3, placement.target_trim.x0 + 70, placement.target_trim.y0 + 18)
        out_page.draw_rect(label_rect, fill=(1, 1, 1), color=(0, 0, 0), width=0.2)
        out_page.insert_textbox(label_rect, label, fontsize=8, color=(0, 0, 0), align=fitz.TEXT_ALIGN_LEFT)


def impose(args: argparse.Namespace) -> int:
    input_path = Path(args.input_pdf)
    output_path = Path(args.output_pdf)
    if not input_path.exists():
        raise FileNotFoundError(input_path)

    src = fitz.open(input_path)
    original_page_count = src.page_count
    if original_page_count == 0:
        raise ValueError("Input PDF has no pages")

    first_boxes = read_page_boxes(src[0], args.trim_size_mm)
    trim_w = first_boxes.trim.width
    trim_h = first_boxes.trim.height

    if args.sheet_orientation == "portrait":
        sheet_w, sheet_h = A4_PORTRAIT
    else:
        sheet_h, sheet_w = A4_PORTRAIT
    sheet_rect = fitz.Rect(0, 0, sheet_w, sheet_h)

    padded_count = int(math.ceil(original_page_count / args.pad_multiple) * args.pad_multiple)
    if padded_count % 4 != 0:
        padded_count = int(math.ceil(padded_count / 4) * 4)
    strips = booklet_strips(original_page_count, padded_count)
    row_rects = build_row_trim_rects(sheet_rect, trim_w, trim_h, args)

    out = fitz.open()
    total_output_sheets = math.ceil(len(strips) / 2)

    for sheet_no in range(total_output_sheets):
        strip_a = strips[sheet_no * 2]
        strip_b = strips[sheet_no * 2 + 1] if sheet_no * 2 + 1 < len(strips) else None
        if strip_b is None and args.fill_sheet_mode == "repeat-copy":
            strip_b = strip_a
        sheet_strips = [strip_a, strip_b]

        for side_name, pair_index in (("front", 0), ("back", 1)):
            out_page = out.new_page(width=sheet_w, height=sheet_h)
            for row_idx, strip in enumerate(sheet_strips):
                left_trim, right_trim = row_rects[row_idx]
                if strip is None:
                    add_blank_box(out_page, left_trim, args)
                    add_blank_box(out_page, right_trim, args)
                    continue
                left_page_num, right_page_num = strip[pair_index]
                placements = [
                    Placement(page_number_to_index(left_page_num, original_page_count), left_page_num, left_trim, "left"),
                    Placement(page_number_to_index(right_page_num, original_page_count), right_page_num, right_trim, "right"),
                ]
                for placement in placements:
                    place_source_page(out_page, src, placement, args, scale=1.0)
                    if args.crop_marks:
                        draw_marks_for_page(out_page, placement.target_trim, args, placement.position_in_spread)
                draw_fold_marks(out_page, left_trim, right_trim, args)

            if side_name == "back" and args.rotate_back:
                out_page.set_rotation(180)

    out.save(output_path, deflate=True, garbage=4)
    out.close()
    src.close()

    print(f"OK: wrote {output_path}")
    print(f"Input pages: {original_page_count}")
    print(f"Padded pages: {padded_count}")
    print(f"Output PDF pages: {total_output_sheets * 2} ({total_output_sheets} A4 sheet(s), front/back)")
    return 0


def format_rect_mm(rect: fitz.Rect) -> str:
    return (
        f"x0={pt_to_mm(rect.x0):.2f} y0={pt_to_mm(rect.y0):.2f} "
        f"w={pt_to_mm(rect.width):.2f} h={pt_to_mm(rect.height):.2f}"
    )


def inspect_pdf(args: argparse.Namespace) -> int:
    src = fitz.open(args.input_pdf)
    print(f"File: {args.input_pdf}")
    print(f"Pages: {src.page_count}")
    max_pages = min(args.pages, src.page_count)
    for i in range(max_pages):
        page = src[i]
        boxes = read_page_boxes(page, args.trim_size_mm)
        print(f"\nPage {i + 1}")
        print(f"  MediaBox: {format_rect_mm(boxes.media)}")
        print(f"  CropBox : {format_rect_mm(boxes.crop)}")
        print(f"  TrimBox : {format_rect_mm(boxes.trim)}  [{boxes.trim_source}]")
        print(f"  BleedBox: {format_rect_mm(boxes.bleed)}  [{boxes.bleed_source}]")
        left_bleed = max(0, boxes.trim.x0 - boxes.bleed.x0)
        top_bleed = max(0, boxes.trim.y0 - boxes.bleed.y0)
        right_bleed = max(0, boxes.bleed.x1 - boxes.trim.x1)
        bottom_bleed = max(0, boxes.bleed.y1 - boxes.trim.y1)
        print(
            "  Detected bleed mm: "
            f"left={pt_to_mm(left_bleed):.2f}, top={pt_to_mm(top_bleed):.2f}, "
            f"right={pt_to_mm(right_bleed):.2f}, bottom={pt_to_mm(bottom_bleed):.2f}"
        )
    src.close()
    return 0


def add_common_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--trim-size-mm", type=parse_size_mm, default=None, help="Finished page size, for example 125x85. If omitted, the script tries PDF TrimBox/CropBox/MediaBox.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pdf4up-saddle", description="4-up A4 saddle-stitch imposition for small PDF magazines.")
    sub = parser.add_subparsers(dest="command", required=True)

    inspect_parser = sub.add_parser("inspect", help="Inspect page boxes and detected bleed.")
    inspect_parser.add_argument("input_pdf")
    inspect_parser.add_argument("--pages", type=int, default=2, help="Number of pages to inspect.")
    add_common_options(inspect_parser)
    inspect_parser.set_defaults(func=inspect_pdf)

    impose_parser = sub.add_parser("impose", help="Create an A4 imposed PDF.")
    impose_parser.add_argument("input_pdf")
    impose_parser.add_argument("output_pdf")
    add_common_options(impose_parser)
    impose_parser.add_argument("--sheet-orientation", choices=["landscape", "portrait"], default="landscape")
    impose_parser.add_argument("--bleed-mm", type=float, default=3.0, help="Requested bleed on cut edges, in mm. The PDF must contain artwork outside the trim for real bleed.")
    impose_parser.add_argument("--spine-bleed-mm", type=float, default=0.0, help="Bleed at the fold/spine edge, usually 0 for saddle-stitch.")
    impose_parser.add_argument("--clip-to-bleed-box", action="store_true", default=False, help="Never use content outside the source PDF BleedBox when it exists.")
    impose_parser.add_argument("--row-gap-mm", type=float, default=8.0, help="Gap between the two booklet rows on the A4 sheet.")
    impose_parser.add_argument("--spine-gap-mm", type=float, default=0.0, help="Gap between the left and right page at the fold.")
    impose_parser.add_argument("--pad-multiple", type=int, default=4, help="Pad page count to this multiple. Use 4 for normal saddle-stitch. Use 8 only if you deliberately want every A4 sheet filled by a single copy.")
    impose_parser.add_argument("--fill-sheet-mode", choices=["blank", "repeat-copy"], default="blank", help="When the final A4 has only one booklet strip, leave the second strip blank or repeat the same strip as a second copy. Useful for 4-page test/booklets.")
    impose_parser.add_argument("--crop-marks", action=argparse.BooleanOptionalAction, default=True)
    impose_parser.add_argument("--marks-style", choices=["minimal", "full"], default="minimal", help="minimal marks only outer cut edges; full marks every page corner.")
    impose_parser.add_argument("--fold-marks", action=argparse.BooleanOptionalAction, default=True)
    impose_parser.add_argument("--mark-length-mm", type=float, default=5.0)
    impose_parser.add_argument("--mark-offset-mm", type=float, default=2.0)
    impose_parser.add_argument("--mark-width-pt", type=float, default=0.35)
    impose_parser.add_argument("--labels", action="store_true", help="Print source page numbers on the imposed PDF for test output.")
    impose_parser.add_argument("--debug-boxes", action="store_true", help="Draw blue trim boxes and red placed bleed boxes.")
    impose_parser.add_argument("--rotate-back", action="store_true", help="Rotate every back page 180 degrees if your duplex test is upside down.")
    impose_parser.set_defaults(func=impose)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
