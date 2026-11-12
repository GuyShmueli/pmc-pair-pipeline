"""Step 4 (filter-images): flag likely diagrams and text-heavy figures.

Procedure (thresholds in the configuration, image_filter):
  1. white-background screen on a 384-px thumbnail: fraction of grey levels >= 250;
     a ratio above 0.5 flags the image,
  2. otherwise OCR (Tesseract, --oem 1 --psm 11 -c tessedit_do_invert=0, 2-second
     timeout); more than 200 recognised characters flags the image.
Images whose OCR times out are kept (not flagged). OCR output depends on the Tesseract
version, its language data and (through the timeout) on machine speed; the Tesseract
version is recorded and every decision is logged in image_filter.jsonl.

Each record carries the id of the screening settings, so changing a threshold re-screens
the images. Images whose OCR failed with an error are flagged ("ocr_error", i.e. not
retained, because they were not screened) and screened again on the next run.
"""

from __future__ import annotations

import os
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from PIL import Image

from .config import log, work_dir
from .io_utils import append_jsonl, iter_jsonl, read_jsonl, sha256_text, stable_json, write_json

RESAMPLE_BOX = getattr(getattr(Image, "Resampling", Image), "BOX")
SCREENING_KEYS = ("white_threshold", "white_ratio_threshold", "thumbnail_size", "ocr_text_length_threshold",
                  "ocr_language", "ocr_config", "ocr_timeout_seconds")


def _limit_ocr_threads():
    os.environ.setdefault("OMP_THREAD_LIMIT", "1")  # parallelism comes from the process pool


def settings_id(settings):
    """Short id of the screening settings (stored with every result)."""
    return sha256_text(stable_json({key: settings[key] for key in SCREENING_KEYS}))[:16]


def tesseract_version(settings):
    """Version of the Tesseract program; stops with a clear message if it is not installed."""
    import pytesseract
    if settings.get("tesseract_cmd"):
        pytesseract.pytesseract.tesseract_cmd = settings["tesseract_cmd"]
    try:
        return str(pytesseract.get_tesseract_version())
    except Exception as error:
        raise SystemExit(f"Tesseract OCR is not available ({type(error).__name__}). Install it "
                         f"(apt install tesseract-ocr / brew install tesseract / conda install -c conda-forge "
                         f"tesseract) or set image_filter.tesseract_cmd to the program's path.")


def white_ratio(path, white_threshold, thumbnail_size):
    """Fraction of greyscale pixels >= white_threshold on a small thumbnail."""
    with Image.open(path) as image:
        if image.format == "JPEG":
            image.draft("L", (thumbnail_size, thumbnail_size))  # fast JPEG downscaling on load
        if "A" in image.getbands():  # transparent background counts as white
            rgba = image.convert("RGBA")
            background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
            image = Image.alpha_composite(background, rgba).convert("RGB")
        image.thumbnail((thumbnail_size, thumbnail_size), RESAMPLE_BOX, reducing_gap=2.0)
        grey = image.convert("L")
        histogram = grey.histogram()
        total = grey.width * grey.height
        return sum(histogram[white_threshold:]) / total if total else 0.0


def screen_image(task):
    image_id, path, settings = task
    result = {"image_id": image_id, "settings_id": settings_id(settings), "white_ratio": None,
              "ocr_characters": None, "ocr_status": "not_run", "flagged": False, "reason": None}
    try:
        result["white_ratio"] = round(white_ratio(path, settings["white_threshold"], settings["thumbnail_size"]), 6)
        if result["white_ratio"] > settings["white_ratio_threshold"]:
            result.update(flagged=True, reason="white_background")
            return result
    except Exception as error:  # unreadable for the cheap screen: still try OCR
        result["white_ratio_error"] = f"{type(error).__name__}: {error}"

    import pytesseract
    if settings.get("tesseract_cmd"):
        pytesseract.pytesseract.tesseract_cmd = settings["tesseract_cmd"]
    try:
        text = pytesseract.image_to_string(str(path), lang=settings["ocr_language"],
                                           config=settings["ocr_config"],
                                           timeout=settings["ocr_timeout_seconds"])
        result["ocr_status"] = "ok"
        result["ocr_characters"] = len(text)
        if len(text) > settings["ocr_text_length_threshold"]:
            result.update(flagged=True, reason="text_heavy")
    except RuntimeError as error:  # pytesseract raises RuntimeError on timeout
        if "timeout" in str(error).lower():
            result["ocr_status"] = "timeout"  # kept: OCR found no text in time
        else:
            result.update(ocr_status="error", ocr_error=str(error), flagged=True, reason="ocr_error")
    except Exception as error:  # not screened, so not retained; the next run tries again
        result.update(ocr_status="error", ocr_error=f"{type(error).__name__}: {error}",
                      flagged=True, reason="ocr_error")
    return result


def filter_images(cfg):
    settings = cfg["image_filter"]
    out_dir = work_dir(cfg, "image_filter")
    results_path = out_dir / "image_filter.jsonl"
    work_root = Path(cfg["paths"]["work_dir"])

    version = tesseract_version(settings)  # stop early if OCR is unavailable
    figures = read_jsonl(work_dir(cfg, "figures") / "figures.jsonl")
    done = {image_id for image_id, r in screening_results(cfg).items() if r["ocr_status"] != "error"}
    tasks = [(f["image_id"], str(work_root / f["image_file"]), settings)
             for f in figures if f["image_id"] not in done]
    log(cfg, f"filter-images: {len(figures)} figures, {len(figures) - len(tasks)} already screened with "
             f"these settings, {len(tasks)} to screen (Tesseract {version})")

    if tasks:
        with ProcessPoolExecutor(max_workers=int(cfg["workers"]), initializer=_limit_ocr_threads) as pool:
            for count, result in enumerate(pool.map(screen_image, tasks, chunksize=16), start=1):
                append_jsonl(result, results_path)  # checkpoint after every image
                if count % 5000 == 0:
                    log(cfg, f"filter-images: {count}/{len(tasks)} screened")

    results = screening_results(cfg)
    current = [results[f["image_id"]] for f in figures if f["image_id"] in results]
    stats = {
        "tesseract_version": version,
        "settings_id": settings_id(settings),
        "figures_screened": len(current),
        "flagged": dict(Counter(r["reason"] for r in current if r["flagged"])),
        "retained": sum(1 for r in current if not r["flagged"]),
        "ocr_status": dict(Counter(r["ocr_status"] for r in current)),
    }
    write_json(stats, out_dir / "stats.json")
    log(cfg, f"filter-images: retained {stats['retained']}, flagged {stats['flagged']}")
    if stats["flagged"].get("ocr_error"):
        log(cfg, f"filter-images: WARNING {stats['flagged']['ocr_error']} images could not be screened and are "
                 f"excluded; run filter-images again to retry them")
    return stats


def screening_results(cfg):
    """{image_id: latest result obtained with the current screening settings}"""
    path = work_dir(cfg, "image_filter") / "image_filter.jsonl"
    current_id = settings_id(cfg["image_filter"])
    results = {}
    if path.exists():
        for record in iter_jsonl(path):
            if record.get("settings_id") == current_id:
                results[record["image_id"]] = record
    return results
