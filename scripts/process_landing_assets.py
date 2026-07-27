from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = PROJECT_ROOT / "jimeng"
OUTPUT_DIR = PROJECT_ROOT / "frontend" / "public" / "landing"


@dataclass(frozen=True)
class AssetSpec:
    token: str
    output_name: str
    size: tuple[int, int]
    crop: str


ASSETS = [
    AssetSpec("AI个人知识库核心", "hero-core.jpg", (1024, 1024), "square"),
    AssetSpec("网页文章", "source-web.jpg", (512, 512), "square"),
    AssetSpec("视频内容", "source-video.jpg", (512, 512), "square"),
    AssetSpec("本地文件", "source-file.jpg", (512, 512), "square"),
    AssetSpec("AI对话", "source-chat.jpg", (512, 512), "square"),
    AssetSpec("书籍阅读", "source-book.jpg", (512, 512), "square"),
    AssetSpec("录音灵感", "source-audio.jpg", (512, 512), "square"),
    AssetSpec("蓝紫渐变光晕", "hero-glow.jpg", (1600, 900), "wide"),
]


def find_source(token: str) -> Path:
    matches = sorted(path for path in SOURCE_DIR.glob("*.png") if token in path.name)
    if not matches:
        raise FileNotFoundError(f"No source image matched token: {token}")
    return matches[0]


def crop_without_watermark(image: Image.Image, crop: str) -> Image.Image:
    width, height = image.size

    # Jimeng watermark is in the upper-left corner. Start the working crop far
    # enough from the left edge while preserving the centered generated object.
    safe_left = int(width * 0.14)
    safe_top = 0
    safe_right = width
    safe_bottom = height

    if crop == "square":
        safe_width = safe_right - safe_left
        side = min(safe_width, safe_bottom - safe_top)
        left = safe_left + (safe_width - side) // 2
        top = safe_top + (safe_bottom - safe_top - side) // 2
        return image.crop((left, top, left + side, top + side))

    if crop == "wide":
        target_ratio = 16 / 9
        safe_width = safe_right - safe_left
        safe_height = safe_bottom - safe_top
        current_ratio = safe_width / safe_height
        if current_ratio > target_ratio:
            new_width = int(safe_height * target_ratio)
            left = safe_left + (safe_width - new_width) // 2
            return image.crop((left, safe_top, left + new_width, safe_bottom))
        new_height = int(safe_width / target_ratio)
        top = safe_top + (safe_height - new_height) // 2
        return image.crop((safe_left, top, safe_right, top + new_height))

    raise ValueError(f"Unsupported crop mode: {crop}")


def is_edge_background(red: int, green: int, blue: int) -> bool:
    min_channel = min(red, green, blue)
    max_channel = max(red, green, blue)
    saturation = max_channel - min_channel
    return min_channel >= 218 and saturation <= 42


def get_foreground_bounds(image: Image.Image) -> tuple[int, int, int, int] | None:
    rgb = image.convert("RGB")
    pixels = rgb.load()
    width, height = rgb.size
    visited = bytearray(width * height)
    queue: deque[tuple[int, int]] = deque()

    def add_if_background(x: int, y: int) -> None:
        index = y * width + x
        if visited[index]:
            return
        red, green, blue = pixels[x, y]
        if not is_edge_background(red, green, blue):
            return
        visited[index] = 1
        queue.append((x, y))

    for x in range(width):
        add_if_background(x, 0)
        add_if_background(x, height - 1)
    for y in range(height):
        add_if_background(0, y)
        add_if_background(width - 1, y)

    while queue:
        x, y = queue.popleft()
        for next_x, next_y in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= next_x < width and 0 <= next_y < height:
                add_if_background(next_x, next_y)

    left, top, right, bottom = width, height, 0, 0
    for y in range(height):
        for x in range(width):
            if visited[y * width + x]:
                continue
            left = min(left, x)
            top = min(top, y)
            right = max(right, x + 1)
            bottom = max(bottom, y + 1)

    if left >= right or top >= bottom:
        return None
    return left, top, right, bottom


def clear_corner_watermarks(image: Image.Image) -> Image.Image:
    rgb = image.convert("RGB")
    pixels = rgb.load()
    width, height = rgb.size

    regions = [
        (0, 0, int(width * 0.24), int(height * 0.16)),
        (0, int(height * 0.62), int(width * 0.24), height),
        (int(width * 0.76), int(height * 0.68), width, height),
    ]

    for left, top, right, bottom in regions:
        for y in range(top, bottom):
            for x in range(left, right):
                pixels[x, y] = (255, 255, 255)

    return rgb


def crop_to_foreground(image: Image.Image, padding_ratio: float = 0.12) -> Image.Image:
    rgb = image.convert("RGB")
    bounds = get_foreground_bounds(rgb)
    if not bounds:
        return rgb

    width, height = rgb.size
    left, top, right, bottom = bounds
    padding = int(max(right - left, bottom - top) * padding_ratio)
    left = max(0, left - padding)
    top = max(0, top - padding)
    right = min(width, right + padding)
    bottom = min(height, bottom + padding)
    return rgb.crop((left, top, right, bottom))


def fit_to_canvas(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    target_width, target_height = size
    fitted = image.convert("RGB")
    fitted.thumbnail((target_width, target_height), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", size, (255, 255, 255))
    left = (target_width - fitted.width) // 2
    top = (target_height - fitted.height) // 2
    canvas.paste(fitted, (left, top))
    return canvas


def process_asset(spec: AssetSpec) -> None:
    source = find_source(spec.token)
    with Image.open(source) as image:
        cropped = crop_without_watermark(image.convert("RGB"), spec.crop)
        working = cropped.resize(spec.size, Image.Resampling.LANCZOS)
        cleaned = clear_corner_watermarks(working)
        bounded = crop_to_foreground(cleaned)
        output = fit_to_canvas(bounded, spec.size)
        output_path = OUTPUT_DIR / spec.output_name
        output.save(output_path, format="JPEG", quality=94, optimize=True, progressive=True)
        print(f"{source.name} -> {output_path.relative_to(PROJECT_ROOT)}")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for spec in ASSETS:
        process_asset(spec)


if __name__ == "__main__":
    main()
