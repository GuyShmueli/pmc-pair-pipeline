"""Step 2 (download): article XML, metadata and JPEG figure files for the selected cases.

The PMC OA Web Service (oa.fcgi) and the article packages on the PMC FTP site were
retired by NCBI in August 2026. Articles are read one file at a time from the PMC
Cloud Service, which distributes the Open Access collection as individual files (public AWS bucket
`pmc-oa-opendata`, plain HTTPS, no credentials), or from a local folder that mirrors the
bucket layout (for example created with `aws s3 sync --no-sign-request`):

    PMC10009416.1/PMC10009416.1.xml     JATS XML of article version 1
    PMC10009416.1/PMC10009416.1.json    metadata (license_code, is_manuscript, ...)
    PMC10009416.1/NPR2-43-85-g001.jpg   figure and supplementary files

Each article is saved as <work_dir>/articles/PMC<id>/ with article.xml, metadata.json
and the JPEG files. Progress is appended to download_log.jsonl, so an interrupted run
continues where it stopped.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from lxml import etree

from .config import log, work_dir
from .io_utils import append_jsonl, iter_jsonl, read_jsonl, utc_now, write_json

PERMANENT_FAILURES = {"no_version", "not_open_access"}


def is_url(source):
    return str(source).startswith(("http://", "https://"))


def http_get(url, settings, params=None):
    """GET with a few retries; raises FileNotFoundError for HTTP 404."""
    retries = int(settings["retries"])
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(url, params=params, timeout=settings["timeout_seconds"])
            if response.status_code == 404:
                raise FileNotFoundError(url)
            response.raise_for_status()
            return response.content
        except requests.RequestException:
            if attempt == retries:
                raise
            time.sleep(min(30, 2 ** attempt))


def parse_s3_listing(xml_bytes):
    """Read one page of an S3 ListObjectsV2 response."""
    root = etree.fromstring(xml_bytes)

    def texts(xpath):
        return [node.text or "" for node in root.xpath(xpath)]

    prefixes = texts('//*[local-name()="CommonPrefixes"]/*[local-name()="Prefix"]')
    keys = texts('//*[local-name()="Contents"]/*[local-name()="Key"]')
    sizes = [int(s or 0) for s in texts('//*[local-name()="Contents"]/*[local-name()="Size"]')]
    truncated = (texts('//*[local-name()="IsTruncated"]') or ["false"])[0].strip().lower() == "true"
    token = (texts('//*[local-name()="NextContinuationToken"]') or [None])[0]
    return prefixes, dict(zip(keys, sizes)), truncated, token


def s3_list(source, prefix, settings, delimiter=None):
    all_prefixes, all_keys = [], {}
    params = {"list-type": "2", "prefix": prefix}
    if delimiter:
        params["delimiter"] = delimiter
    while True:
        prefixes, keys, truncated, token = parse_s3_listing(http_get(source.rstrip("/") + "/", settings, params))
        all_prefixes.extend(prefixes)
        all_keys.update(keys)
        if not truncated or not token:
            return all_prefixes, all_keys
        params["continuation-token"] = token


def version_number(version):
    return int(version.rsplit(".", 1)[1])


def list_versions(source, pmcid, settings):
    """Article versions such as ["PMC123.1", "PMC123.2"]."""
    if is_url(source):
        prefixes, _ = s3_list(source, f"PMC{pmcid}.", settings, delimiter="/")
        names = [p.rstrip("/") for p in prefixes]
    else:
        names = [p.name for p in Path(source).glob(f"PMC{pmcid}.*") if p.is_dir()]
    pattern = re.compile(rf"^PMC{pmcid}\.\d+$")
    return sorted((n for n in names if pattern.match(n)), key=version_number)


def list_files(source, version, settings):
    """{file name: size in bytes} for one article version."""
    if is_url(source):
        _, keys = s3_list(source, f"{version}/", settings)
        return {key.split("/", 1)[1]: size for key, size in keys.items() if "/" in key}
    folder = Path(source) / version
    return {p.name: p.stat().st_size for p in folder.iterdir() if p.is_file()}


def read_source_file(source, version, name, settings):
    if is_url(source):
        return http_get(f"{source.rstrip('/')}/{version}/{name}", settings)
    return (Path(source) / version / name).read_bytes()


def copy_source_file(source, version, name, destination, settings):
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = destination.with_name(destination.name + ".part")
    if is_url(source):
        tmp_path.write_bytes(read_source_file(source, version, name, settings))
    else:
        if tmp_path.exists():
            tmp_path.unlink()
        try:
            os.link(Path(source) / version / name, tmp_path)  # no extra disk space for local mirrors
        except OSError:
            shutil.copyfile(Path(source) / version / name, tmp_path)
    os.replace(tmp_path, destination)


def choose_version(candidates, settings):
    """Pick one version from [(version, metadata), ...].

    Open Access versions only; published versions are preferred over author manuscripts;
    otherwise the highest version number is used.
    """
    usable = candidates
    if settings["require_open_access"]:
        usable = [(v, m) for v, m in usable if m.get("is_pmc_openaccess") is True]
    if settings["prefer_non_manuscript"]:
        published = [(v, m) for v, m in usable if not m.get("is_manuscript")]
        usable = published or usable
    if not usable:
        return None, None
    return max(usable, key=lambda item: version_number(item[0]))


def download_article(pmcid, source, articles_dir, settings, image_extensions):
    record = {"pmcid": pmcid, "checked_at": utc_now()}
    try:
        versions = list_versions(source, pmcid, settings)
        if not versions:
            return {**record, "status": "no_version"}
        candidates = []
        for version in versions:
            try:
                metadata = json.loads(read_source_file(source, version, f"{version}.json", settings))
            except FileNotFoundError:
                metadata = {}
            candidates.append((version, metadata))
        version, metadata = choose_version(candidates, settings)
        if version is None:
            return {**record, "status": "not_open_access", "versions": versions}

        files = list_files(source, version, settings)
        article_dir = Path(articles_dir) / f"PMC{pmcid}"
        wanted = {f"{version}.xml": "article.xml", f"{version}.json": "metadata.json"}
        for name in files:
            if Path(name).suffix.lower() in image_extensions:
                wanted[name] = name
        for name, local_name in wanted.items():
            if name not in files:
                continue
            destination = article_dir / local_name
            if destination.exists() and destination.stat().st_size == files[name]:
                continue  # already downloaded by an earlier, interrupted run
            copy_source_file(source, version, name, destination, settings)
        if not (article_dir / "article.xml").exists():
            return {**record, "status": "error", "error": "article XML missing", "version": version}
        return {
            **record,
            "status": "ok",
            "version": version,
            "license_code": metadata.get("license_code"),
            "is_manuscript": metadata.get("is_manuscript"),
            "doi": metadata.get("doi"),
            "image_files": sum(1 for name in wanted if Path(name).suffix.lower() in image_extensions),
        }
    except Exception as error:  # keep going; failures are logged and retried on the next run
        return {**record, "status": "error", "error": f"{type(error).__name__}: {error}"}


def latest_download_records(log_path):
    latest = {}
    if Path(log_path).exists():
        for record in iter_jsonl(log_path):
            latest[record["pmcid"]] = record
    return latest


def download_articles(cfg, retry_permanent_failures=False):
    settings = cfg["download"]
    source = cfg["paths"]["pmc_source"]
    image_extensions = {ext.lower() for ext in cfg["figures"]["image_extensions"]}
    articles_dir = work_dir(cfg, "articles")
    log_path = articles_dir / "download_log.jsonl"

    pmcids = sorted({case["pmcid"] for case in read_jsonl(work_dir(cfg, "cases") / "cases.jsonl")}, key=int)
    if settings.get("max_articles"):
        pmcids = pmcids[: int(settings["max_articles"])]

    previous = latest_download_records(log_path)
    pending = []
    for pmcid in pmcids:
        status = previous.get(pmcid, {}).get("status")
        if status == "ok" and (articles_dir / f"PMC{pmcid}" / "article.xml").exists():
            continue
        if status in PERMANENT_FAILURES and not retry_permanent_failures:
            continue
        pending.append(pmcid)
    log(cfg, f"download: {len(pmcids)} articles, {len(pmcids) - len(pending)} already done, "
             f"{len(pending)} to fetch from {source}")

    with ThreadPoolExecutor(max_workers=int(settings["workers"])) as pool:
        futures = [pool.submit(download_article, pmcid, source, articles_dir, settings, image_extensions)
                   for pmcid in pending]
        for done_count, future in enumerate(as_completed(futures), start=1):
            append_jsonl(future.result(), log_path)  # checkpoint after every article
            if done_count % 500 == 0:
                log(cfg, f"download: {done_count}/{len(pending)} articles processed")

    latest = latest_download_records(log_path)
    statuses = Counter(latest[p]["status"] for p in pmcids if p in latest)
    stats = {"articles_requested": len(pmcids), "status_counts": dict(statuses),
             "license_counts": dict(Counter(latest[p].get("license_code") for p in pmcids
                                            if latest.get(p, {}).get("status") == "ok"))}
    write_json(stats, articles_dir / "stats.json")
    log(cfg, f"download: status counts {dict(statuses)}")
    return stats


def downloaded_articles(cfg):
    """{pmcid: download record} for articles whose XML is available."""
    articles_dir = work_dir(cfg, "articles")
    latest = latest_download_records(articles_dir / "download_log.jsonl")
    return {pmcid: rec for pmcid, rec in latest.items()
            if rec["status"] == "ok" and (articles_dir / f"PMC{pmcid}" / "article.xml").exists()}
