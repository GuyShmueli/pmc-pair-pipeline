#!/usr/bin/env python3

import os
import sys
import json
import time
import argparse
import logging
import tempfile
from concurrent.futures import ProcessPoolExecutor

from PIL import Image
import pytesseract

JSONS_PATH = "<DATA_ROOT>"

OUTPUT_JSON_NAME = "new_imgs_paths_diagrams_4.json"
OUTPUT_RATIO_JSON_NAME = "new_imgs_paths_diagrams_4_by_ratio.json"
OUTPUT_OCR_JSON_NAME = "new_imgs_paths_diagrams_4_by_ocr.json"

THRESHOLD = 250
RATIO_THRESHOLD = 0.5
TEXT_LEN_THRESHOLD = 200

# Cheap-pass settings
RATIO_THUMB = 384  # 256-512 is usually a good range

# OCR settings
# psm 11 = sparse text; drop tessedit_do_invert=0 if some images are light-on-dark
OCR_CONFIG = "--oem 1 --psm 11 -c tessedit_do_invert=0"
OCR_TIMEOUT_SEC = 2.0

MAX_ERROR_LOGS = 20

# Pillow compatibility across versions
RESAMPLE_BOX = getattr(getattr(Image, "Resampling", Image), "BOX")


def setup_logging(log_level="INFO", log_file=None):
    handlers = [logging.StreamHandler(sys.stdout)]

    if log_file:
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        handlers.append(logging.FileHandler(log_file))

    kwargs = {
        "level": getattr(logging, log_level.upper(), logging.INFO),
        "format": "%(asctime)s | %(levelname)s | %(message)s",
        "handlers": handlers,
    }

    try:
        logging.basicConfig(force=True, **kwargs)
    except TypeError:
        logging.basicConfig(**kwargs)

    return logging.getLogger("filter_diagrams")


def usable_cpu_count():
    """
    Prefer the Slurm allocation if present.
    Otherwise fall back to CPU affinity, then process-aware CPU count,
    then system-wide CPU count.
    """
    slurm_cpus = os.environ.get("SLURM_CPUS_PER_TASK")
    if slurm_cpus:
        try:
            n = int(slurm_cpus)
            if n > 0:
                return n
        except ValueError:
            pass

    try:
        return len(os.sched_getaffinity(0))
    except Exception:
        pass

    process_cpu_count = getattr(os, "process_cpu_count", None)
    if callable(process_cpu_count):
        n = process_cpu_count()
        if n:
            return n

    n = os.cpu_count()
    return n if n and n > 0 else 1


def init_worker(tmpdir=None):
    # Best default when outer parallelism handles concurrency.
    os.environ.setdefault("OMP_THREAD_LIMIT", "1")

    if tmpdir:
        os.environ["TMPDIR"] = tmpdir
        tempfile.tempdir = tmpdir


def flatten_alpha_on_white(im):
    """
    Composite RGBA/LA images on white so transparent backgrounds are treated
    like white, not black.
    """
    if "A" not in im.getbands():
        return im

    rgba = im.convert("RGBA")
    bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    out = Image.alpha_composite(bg, rgba)
    return out.convert("RGB")


def white_ratio(path, threshold=THRESHOLD, thumb=RATIO_THUMB):
    """
    Fraction of grayscale pixels >= threshold on a small thumbnail.
    """
    with Image.open(path) as im:
        # JPEG decoder may downscale cheaply during load.
        if im.format == "JPEG":
            im.draft("L", (thumb, thumb))

        im = flatten_alpha_on_white(im)

        try:
            im.thumbnail((thumb, thumb), RESAMPLE_BOX, reducing_gap=2.0)
        except TypeError:
            # Older Pillow may not support reducing_gap here
            im.thumbnail((thumb, thumb), RESAMPLE_BOX)

        gray = im.convert("L")
        hist = gray.histogram()
        white = sum(hist[threshold:])
        total = gray.width * gray.height
        return (white / total) if total else 0.0


def ratio_worker(item):
    idx, path = item
    try:
        ratio = white_ratio(path)
        return idx, path, "ok", ratio, None
    except Exception as e:
        return idx, path, "error", None, str(e)


def ocr_worker(item):
    idx, path = item
    try:
        text = pytesseract.image_to_string(
            path,
            lang="eng",
            config=OCR_CONFIG,
            timeout=OCR_TIMEOUT_SEC,
        )
        return idx, path, "ok", len(text), None
    except RuntimeError as e:
        # pytesseract timeout
        return idx, path, "timeout", None, str(e)
    except Exception as e:
        return idx, path, "error", None, str(e)


def format_seconds(seconds):
    seconds = int(round(max(0.0, seconds)))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m{s:02d}s"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"


def maybe_log_progress(
    logger,
    stage,
    processed,
    total,
    start_time,
    last_log_time,
    log_every,
    log_seconds,
    extra_msg,
):
    now = time.monotonic()

    should_log = (
        processed == total
        or (log_every > 0 and processed % log_every == 0)
        or (log_seconds > 0 and (now - last_log_time) >= log_seconds)
    )

    if not should_log:
        return last_log_time

    elapsed = max(now - start_time, 1e-9)
    rate = processed / elapsed
    remaining = total - processed
    eta = (remaining / rate) if rate > 0 else 0.0
    pct = (100.0 * processed / total) if total else 100.0

    logger.info(
        "[%s] %d/%d (%.1f%%) | %s | rate=%.1f img/s | elapsed=%s | eta=%s",
        stage,
        processed,
        total,
        pct,
        extra_msg,
        rate,
        format_seconds(elapsed),
        format_seconds(eta),
    )
    return now


def log_error_limited(logger, stage, error_count, path, msg, limit=MAX_ERROR_LOGS):
    if error_count <= limit:
        logger.warning("[%s] %s | %s", stage, path, msg)
    elif error_count == limit + 1:
        logger.warning("[%s] further errors suppressed after %d messages", stage, limit)


def run_ratio_stage(
    executor,
    imgs_paths,
    keep_flags,
    ratio_keep_flags,
    logger,
    chunksize,
    log_every,
    log_seconds,
):
    total = len(imgs_paths)
    need_ocr = []
    kept_by_ratio = 0
    ratio_errors = 0

    start = time.monotonic()
    last_log = start

    for processed, result in enumerate(
        executor.map(ratio_worker, enumerate(imgs_paths), chunksize=chunksize),
        start=1,
    ):
        idx, path, status, ratio, err = result

        if status == "ok":
            if ratio > RATIO_THRESHOLD:
                keep_flags[idx] = True
                ratio_keep_flags[idx] = True
                kept_by_ratio += 1
            else:
                need_ocr.append((idx, path))
        else:
            # Fallback: if the cheap pass failed, still try OCR.
            ratio_errors += 1
            need_ocr.append((idx, path))
            log_error_limited(
                logger,
                "ratio",
                ratio_errors,
                path,
                "ratio pass failed; sending to OCR instead: %s" % err,
            )

        last_log = maybe_log_progress(
            logger=logger,
            stage="ratio",
            processed=processed,
            total=total,
            start_time=start,
            last_log_time=last_log,
            log_every=log_every,
            log_seconds=log_seconds,
            extra_msg=(
                f"kept_by_ratio={kept_by_ratio} | "
                f"need_ocr={len(need_ocr)} | "
                f"ratio_errors={ratio_errors}"
            ),
        )

    return need_ocr, {
        "processed": total,
        "kept_by_ratio": kept_by_ratio,
        "ratio_errors": ratio_errors,
    }


def run_ocr_stage(
    executor,
    need_ocr,
    keep_flags,
    ocr_keep_flags,
    logger,
    chunksize,
    log_every,
    log_seconds,
):
    total = len(need_ocr)
    kept_by_ocr = 0
    ocr_timeouts = 0
    ocr_errors = 0

    if total == 0:
        return {
            "processed": 0,
            "kept_by_ocr": 0,
            "ocr_timeouts": 0,
            "ocr_errors": 0,
        }

    start = time.monotonic()
    last_log = start

    for processed, result in enumerate(
        executor.map(ocr_worker, need_ocr, chunksize=chunksize),
        start=1,
    ):
        idx, path, status, text_len, err = result

        if status == "ok":
            if text_len > TEXT_LEN_THRESHOLD:
                keep_flags[idx] = True
                ocr_keep_flags[idx] = True
                kept_by_ocr += 1
        elif status == "timeout":
            ocr_timeouts += 1
            log_error_limited(logger, "ocr-timeout", ocr_timeouts, path, err)
        else:
            ocr_errors += 1
            log_error_limited(logger, "ocr-error", ocr_errors, path, err)

        last_log = maybe_log_progress(
            logger=logger,
            stage="ocr",
            processed=processed,
            total=total,
            start_time=start,
            last_log_time=last_log,
            log_every=log_every,
            log_seconds=log_seconds,
            extra_msg=(
                f"kept_by_ocr={kept_by_ocr} | "
                f"timeouts={ocr_timeouts} | "
                f"errors={ocr_errors}"
            ),
        )

    return {
        "processed": total,
        "kept_by_ocr": kept_by_ocr,
        "ocr_timeouts": ocr_timeouts,
        "ocr_errors": ocr_errors,
    }


def main(
    jsons_path,
    workers=None,
    chunksize=64,
    tmpdir=None,
    output_json=OUTPUT_JSON_NAME,
    output_ratio_json=OUTPUT_RATIO_JSON_NAME,
    output_ocr_json=OUTPUT_OCR_JSON_NAME,
    log_every=5000,
    log_seconds=30.0,
    log_level="INFO",
    log_file=None,
):
    logger = setup_logging(log_level=log_level, log_file=log_file)

    input_json = os.path.join(jsons_path, "new_img_paths.json")
    output_json = os.path.join(jsons_path, output_json)
    output_ratio_json = os.path.join(jsons_path, output_ratio_json)
    output_ocr_json = os.path.join(jsons_path, output_ocr_json)

    with open(input_json, "r", encoding="utf-8") as f:
        imgs_paths = json.load(f)

    total = len(imgs_paths)

    if workers is None:
        workers = usable_cpu_count()
    workers = max(1, min(int(workers), max(1, total)))

    if tmpdir:
        os.makedirs(tmpdir, exist_ok=True)

    logger.info("Loaded %d image paths from %s", total, input_json)
    logger.info(
        "workers=%d | chunksize=%d | tmpdir=%s | ratio_thumb=%d | ocr_timeout=%.2fs",
        workers,
        chunksize,
        tmpdir or "<default>",
        RATIO_THUMB,
        OCR_TIMEOUT_SEC,
    )

    if total == 0:
        empty = []
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(empty, f)
        with open(output_ratio_json, "w", encoding="utf-8") as f:
            json.dump(empty, f)
        with open(output_ocr_json, "w", encoding="utf-8") as f:
            json.dump(empty, f)
        logger.info(
            "No input images. Wrote empty outputs to %s, %s, %s",
            output_json,
            output_ratio_json,
            output_ocr_json,
        )
        return

    keep_flags = [False] * total
    ratio_keep_flags = [False] * total
    ocr_keep_flags = [False] * total

    job_start = time.monotonic()

    with ProcessPoolExecutor(
        max_workers=workers,
        initializer=init_worker,
        initargs=(tmpdir,),
    ) as executor:
        need_ocr, ratio_stats = run_ratio_stage(
            executor=executor,
            imgs_paths=imgs_paths,
            keep_flags=keep_flags,
            ratio_keep_flags=ratio_keep_flags,
            logger=logger,
            chunksize=chunksize,
            log_every=log_every,
            log_seconds=log_seconds,
        )

        logger.info(
            "Ratio stage done | kept_by_ratio=%d | queued_for_ocr=%d | ratio_errors=%d",
            ratio_stats["kept_by_ratio"],
            len(need_ocr),
            ratio_stats["ratio_errors"],
        )

        kept_by_ratio_paths = [path for i, path in enumerate(imgs_paths) if ratio_keep_flags[i]]
        with open(output_ratio_json, "w", encoding="utf-8") as f:
            json.dump(kept_by_ratio_paths, f)

        ocr_stats = run_ocr_stage(
            executor=executor,
            need_ocr=need_ocr,
            keep_flags=keep_flags,
            ocr_keep_flags=ocr_keep_flags,
            logger=logger,
            chunksize=chunksize,
            log_every=log_every,
            log_seconds=log_seconds,
        )

    kept_paths = [path for i, path in enumerate(imgs_paths) if keep_flags[i]]
    kept_by_ocr_paths = [path for i, path in enumerate(imgs_paths) if ocr_keep_flags[i]]

    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(kept_paths, f)


    with open(output_ocr_json, "w", encoding="utf-8") as f:
        json.dump(kept_by_ocr_paths, f)

    elapsed = time.monotonic() - job_start

    logger.info(
        "Done | total=%d | kept=%d | kept_by_ratio=%d | kept_by_ocr=%d | "
        "ocr_candidates=%d | ocr_timeouts=%d | total_errors=%d | elapsed=%s | "
        "all_output=%s | ratio_output=%s | ocr_output=%s",
        total,
        len(kept_paths),
        len(kept_by_ratio_paths),
        len(kept_by_ocr_paths),
        len(need_ocr),
        ocr_stats["ocr_timeouts"],
        ratio_stats["ratio_errors"] + ocr_stats["ocr_errors"],
        format_seconds(elapsed),
        output_json,
        output_ratio_json,
        output_ocr_json,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Filter diagrams using a white-ratio pass and OCR text length."
    )
    parser.add_argument(
        "--jsons_path", "--jsons-path", "-j",
        dest="jsons_path",
        default=JSONS_PATH,
        help="Directory containing new_img_paths.json",
    )
    parser.add_argument(
        "--workers", "-w",
        type=int,
        default=None,
        help="Defaults to SLURM_CPUS_PER_TASK / CPU affinity / process CPU count.",
    )
    parser.add_argument(
        "--chunksize", "-c",
        type=int,
        default=64,
        help="ProcessPoolExecutor.map chunksize",
    )
    parser.add_argument(
        "--tmpdir",
        default=None,
        help="Optional fast local temp directory for worker temp files",
    )
    parser.add_argument(
        "--output-json",
        default=OUTPUT_JSON_NAME,
        help="Output JSON filename for all kept images",
    )
    parser.add_argument(
        "--output-ratio-json",
        default=OUTPUT_RATIO_JSON_NAME,
        help="Output JSON filename for images kept by ratio",
    )
    parser.add_argument(
        "--output-ocr-json",
        default=OUTPUT_OCR_JSON_NAME,
        help="Output JSON filename for images kept by OCR",
    )
    parser.add_argument(
        "--log-every",
        type=int,
        default=5000,
        help="Log every N processed images per stage",
    )
    parser.add_argument(
        "--log-seconds",
        type=float,
        default=30.0,
        help="Also log if at least this many seconds passed since the last log",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    parser.add_argument(
        "--log-file",
        default=None,
        help="Optional extra log file path",
    )

    args = parser.parse_args()

    main(
        jsons_path=args.jsons_path,
        workers=args.workers,
        chunksize=args.chunksize,
        tmpdir=args.tmpdir,
        output_json=args.output_json,
        output_ratio_json=args.output_ratio_json,
        output_ocr_json=args.output_ocr_json,
        log_every=args.log_every,
        log_seconds=args.log_seconds,
        log_level=args.log_level,
        log_file=args.log_file,
    )
