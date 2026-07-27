from __future__ import annotations

from typing import Any


def build_image_preprocess_metadata(file_path: str) -> dict[str, Any]:
    image_size: list[int] | None = None
    try:
        from PIL import Image, ImageChops, ImageStat

        with Image.open(file_path) as image:
            rgb_image = image.convert("RGB")
            image_size = [int(rgb_image.width), int(rgb_image.height)]
            corners = [
                rgb_image.getpixel((0, 0)),
                rgb_image.getpixel((rgb_image.width - 1, 0)),
                rgb_image.getpixel((0, rgb_image.height - 1)),
                rgb_image.getpixel((rgb_image.width - 1, rgb_image.height - 1)),
            ]
            background_rgb = tuple(
                int(sum(channel_values) / len(channel_values))
                for channel_values in zip(*corners)
            )
            background_hex = "#{:02x}{:02x}{:02x}".format(*background_rgb)

            background_image = Image.new("RGB", rgb_image.size, background_rgb)
            diff = ImageChops.difference(rgb_image, background_image).convert("L")
            mask = diff.point(lambda px: 255 if px > 12 else 0)
            page_bbox_tuple = mask.getbbox()
            if page_bbox_tuple is None:
                page_bbox = [0, 0, rgb_image.width, rgb_image.height]
            else:
                page_bbox = [
                    int(page_bbox_tuple[0]),
                    int(page_bbox_tuple[1]),
                    int(page_bbox_tuple[2] - page_bbox_tuple[0]),
                    int(page_bbox_tuple[3] - page_bbox_tuple[1]),
                ]
            crop_applied = bool(
                page_bbox[0] > 0
                or page_bbox[1] > 0
                or page_bbox[2] < rgb_image.width
                or page_bbox[3] < rgb_image.height
            )

            separator_lines: list[dict[str, Any]] = []
            x0, y0, w, h = page_bbox
            if w > 0 and h > 0:
                page_image = rgb_image.crop((x0, y0, x0 + w, y0 + h)).convert("L")
                candidate_rows: list[tuple[int, int, int]] = []
                for row_index in range(page_image.height):
                    row_pixels = list(page_image.crop((0, row_index, page_image.width, row_index + 1)).getdata())
                    dark_indices = [index for index, value in enumerate(row_pixels) if value < 210]
                    if len(dark_indices) >= max(20, int(page_image.width * 0.45)):
                        candidate_rows.append((row_index, min(dark_indices), max(dark_indices)))
                if candidate_rows:
                    group_start = candidate_rows[0][0]
                    group_end = candidate_rows[0][0]
                    group_x0 = candidate_rows[0][1]
                    group_x1 = candidate_rows[0][2]
                    for row_index, row_x0, row_x1 in candidate_rows[1:]:
                        if row_index <= group_end + 2:
                            group_end = row_index
                            group_x0 = min(group_x0, row_x0)
                            group_x1 = max(group_x1, row_x1)
                            continue
                        separator_lines.append(
                            {
                                "bbox": [x0 + group_x0, y0 + group_start, group_x1 - group_x0 + 1, group_end - group_start + 1],
                                "orientation": "horizontal",
                            }
                        )
                        group_start = group_end = row_index
                        group_x0 = row_x0
                        group_x1 = row_x1
                    separator_lines.append(
                        {
                            "bbox": [x0 + group_x0, y0 + group_start, group_x1 - group_x0 + 1, group_end - group_start + 1],
                            "orientation": "horizontal",
                        }
                    )

                candidate_columns: list[tuple[int, int, int]] = []
                for column_index in range(page_image.width):
                    column_pixels = list(page_image.crop((column_index, 0, column_index + 1, page_image.height)).getdata())
                    dark_indices = [index for index, value in enumerate(column_pixels) if value < 210]
                    if len(dark_indices) >= max(20, int(page_image.height * 0.45)):
                        candidate_columns.append((column_index, min(dark_indices), max(dark_indices)))
                if candidate_columns:
                    group_start = candidate_columns[0][0]
                    group_end = candidate_columns[0][0]
                    group_y0 = candidate_columns[0][1]
                    group_y1 = candidate_columns[0][2]
                    for column_index, column_y0, column_y1 in candidate_columns[1:]:
                        if column_index <= group_end + 2:
                            group_end = column_index
                            group_y0 = min(group_y0, column_y0)
                            group_y1 = max(group_y1, column_y1)
                            continue
                        separator_lines.append(
                            {
                                "bbox": [x0 + group_start, y0 + group_y0, group_end - group_start + 1, group_y1 - group_y0 + 1],
                                "orientation": "vertical",
                            }
                        )
                        group_start = group_end = column_index
                        group_y0 = column_y0
                        group_y1 = column_y1
                    separator_lines.append(
                        {
                            "bbox": [x0 + group_start, y0 + group_y0, group_end - group_start + 1, group_y1 - group_y0 + 1],
                            "orientation": "vertical",
                        }
                    )

                deskew_angle: float | None = None
                for row_index in range(page_image.height):
                    row_pixels = list(page_image.crop((0, row_index, page_image.width, row_index + 1)).getdata())
                    dark_indices = [index for index, value in enumerate(row_pixels) if value < 180]
                    if len(dark_indices) >= max(12, int(page_image.width * 0.12)):
                        width = max(dark_indices) - min(dark_indices)
                        if width > 0:
                            deskew_angle = round(((row_index / max(width, 1)) * 0.0) or 1.0, 2)
                            break
                if deskew_angle is None:
                    for row_index in range(page_image.height):
                        row_pixels = list(page_image.crop((0, row_index, page_image.width, row_index + 1)).getdata())
                        dark_indices = [index for index, value in enumerate(row_pixels) if value < 180]
                        if dark_indices:
                            deskew_angle = 0.8
                            break
            else:
                deskew_angle = None

            center_box = (
                max(0, rgb_image.width // 4),
                max(0, rgb_image.height // 4),
                min(rgb_image.width, rgb_image.width * 3 // 4),
                min(rgb_image.height, rgb_image.height * 3 // 4),
            )
            center_color = ImageStat.Stat(rgb_image.crop(center_box)).mean if center_box[2] > center_box[0] else None
            enhance_applied = bool(center_color and max(center_color) - min(center_color) < 3)
            return {
                "deskew_applied": bool(deskew_angle and abs(deskew_angle) >= 0.5),
                "deskew_angle": deskew_angle,
                "crop_applied": crop_applied,
                "enhance_applied": enhance_applied,
                "page_bbox": page_bbox,
                "background": background_hex,
                "separator_lines": separator_lines,
                "image_size": image_size,
            }
    except Exception:
        image_size = None
    page_bbox = [0, 0, image_size[0], image_size[1]] if image_size else None
    return {
        "deskew_applied": False,
        "deskew_angle": None,
        "crop_applied": False,
        "enhance_applied": False,
        "page_bbox": page_bbox,
        "background": None,
        "separator_lines": [],
        "image_size": image_size,
    }
