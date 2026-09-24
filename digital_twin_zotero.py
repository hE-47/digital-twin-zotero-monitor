#!/usr/bin/env python3
"""Find high-relevance digital-twin papers and save them to Zotero.

Uses only Python's standard library, OpenAlex's public API for discovery, and
Zotero Web API v3 for library writes. The Zotero API key is read only from the
ZOTERO_API_KEY environment variable.
"""

from __future__ import annotations

import argparse
import datetime as dt
import difflib
import html
import json
import logging
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
STATE_PATH = ROOT / "state.json"
LOG_DIR = ROOT / "logs"
OPENALEX = "https://api.openalex.org"
ZOTERO = "https://api.zotero.org"
CROSSREF = "https://api.crossref.org"

SEARCH_QUERY = '"digital twin" OR "digital twins"'

MODEL_UPDATE_TERMS = {
    "model updating": 4,
    "model update": 4,
    "online updating": 3,
    "online update": 3,
    "model calibration": 3,
    "parameter identification": 3,
    "system identification": 3,
    "data assimilation": 3,
    "state estimation": 2,
    "kalman filter": 2,
    "bayesian update": 2,
    "adaptive model": 2,
    "model synchronization": 2,
}

REAL_TIME_TERMS = {
    "real-time": 4,
    "real time": 4,
    "realtime": 4,
    "online algorithm": 3,
    "online learning": 3,
    "incremental learning": 3,
    "edge computing": 3,
    "low latency": 3,
    "latency": 2,
    "streaming": 2,
    "adaptive control": 2,
    "embedded system": 2,
}

ALGORITHM_TERMS = {
    "algorithm": 2,
    "optimization": 2,
    "machine learning": 2,
    "deep learning": 2,
    "neural network": 2,
    "physics-informed": 2,
    "pinn": 2,
    "surrogate model": 2,
    "reduced-order model": 2,
    "reduced order model": 2,
    "co-simulation": 1,
    "observer": 1,
    "data fusion": 1,
    "sensor fusion": 1,
    "fault diagnosis": 1,
    "predictive maintenance": 1,
}


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    temp.replace(path)


def setup_logging(verbose: bool) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"run-{dt.date.today().isoformat()}.log"
    handlers: list[logging.Handler] = [logging.FileHandler(log_file, encoding="utf-8")]
    if verbose:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
    )


def request_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    method: str = "GET",
    payload: Any | None = None,
    retries: int = 3,
) -> Any:
    request_headers = {
        "User-Agent": "digital-twin-zotero/2.0",
        "Accept": "application/json",
    }
    request_headers.update(headers or {})
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
            with urllib.request.urlopen(request, timeout=45) as response:
                body = response.read()
                return json.loads(body.decode("utf-8")) if body else None
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if exc.code == 429 or 500 <= exc.code < 600:
                if attempt + 1 < retries:
                    time.sleep(2 ** attempt)
                    continue
            raise RuntimeError(f"HTTP {exc.code} for {url}: {body[:500]}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt + 1 < retries:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"Network error for {url}: {exc}") from exc
    raise RuntimeError(f"Request failed: {url}")


def months_ago(day: dt.date, count: int) -> dt.date:
    year = day.year
    month = day.month - count
    while month <= 0:
        year -= 1
        month += 12
    month_lengths = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                     31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return dt.date(year, month, min(day.day, month_lengths[month - 1]))


def decode_abstract(index: dict[str, list[int]] | None) -> str:
    if not index:
        return ""
    positions: list[tuple[int, str]] = []
    for word, indexes in index.items():
        positions.extend((position, word) for position in indexes)
    positions.sort()
    return " ".join(word for _, word in positions)


def clean_markup(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def work_date(work: dict[str, Any]) -> str:
    return work.get("publication_date") or ""


def normalized_doi(work: dict[str, Any]) -> str:
    doi = (work.get("doi") or "").strip().lower()
    return doi.removeprefix("https://doi.org/").removeprefix("http://doi.org/")


def normalized_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean_markup(value).lower()).strip()


def crossref_verify(work: dict[str, Any]) -> bool:
    doi = normalized_doi(work)
    if not doi:
        logging.warning("Skipping candidate without DOI: %s", work.get("title"))
        return False
    url = f"{CROSSREF}/works/{urllib.parse.quote(doi, safe='')}"
    try:
        response = request_json(url)
        message = response.get("message") or {}
        crossref_title = ((message.get("title") or [""])[0]).strip()
        expected_title = work.get("display_name") or work.get("title") or ""
        similarity = difflib.SequenceMatcher(
            None,
            normalized_title(expected_title),
            normalized_title(crossref_title),
        ).ratio()
        if similarity < 0.80:
            logging.warning(
                "Skipping DOI/title mismatch: %s (similarity %.2f)",
                doi,
                similarity,
            )
            return False
        return True
    except Exception as exc:
        logging.warning("Skipping candidate because DOI verification failed for %s: %s", doi, exc)
        return False


def work_key(work: dict[str, Any]) -> str:
    return normalized_doi(work) or (work.get("id") or "").lower()


def score_work(work: dict[str, Any], journal: dict[str, Any]) -> tuple[int, list[str], str, list[str]]:
    title = clean_markup(work.get("title") or "")
    abstract = decode_abstract(work.get("abstract_inverted_index"))
    text = f"{title} {abstract}".lower()
    title_lower = title.lower()
    digital_twin_in_title = "digital twin" in title_lower or "digital twins" in title_lower
    if "digital twin" not in text and "digital twins" not in text:
        return 0, [], abstract, []
    if title_lower.startswith(("guest editorial", "editorial")):
        return 0, [], abstract, []

    score = 7
    reasons: list[str] = ["题名或摘要明确出现数字孪生（+7）"]
    directions: list[str] = []

    for label, tag, terms, cap in (
        ("模型更新算法", "模型更新算法", MODEL_UPDATE_TERMS, 8),
        ("实时化算法", "实时化算法", REAL_TIME_TERMS, 8),
        ("通用算法方法", "算法方法", ALGORITHM_TERMS, 6),
    ):
        hits = [term for term in terms if term in text]
        if not hits:
            continue
        group_score = min(cap, sum(terms[term] for term in hits))
        score += group_score
        directions.append(tag)
        reasons.append(f"命中{label}（+{group_score}）：" + "、".join(hits[:4]))

    if digital_twin_in_title:
        score += 5
        reasons.append("题名直接包含数字孪生（+5）")
    if abstract:
        score += 1
        reasons.append("有摘要可供相关性判断（+1）")
    if work.get("type") == "review":
        score += 2
        reasons.append("综述论文（+2）")

    cited = int(work.get("cited_by_count") or 0)
    citation_score = min(3, cited // 10)
    score += citation_score
    if citation_score:
        reasons.append(f"OpenAlex 引用量加分（+{citation_score}）")
    reasons.append(f"来源期刊：{journal['short_name']}")
    return score, reasons, abstract, directions


def openalex_search(config: dict[str, Any], start: dt.date, end: dt.date) -> list[dict[str, Any]]:
    candidates: dict[str, dict[str, Any]] = {}
    mailto = (config.get("openalex_mailto") or "").strip()
    openalex_key = os.environ.get("OPENALEX_API_KEY", "").strip()
    headers = {"Authorization": f"Bearer {openalex_key}"} if openalex_key else {}
    if not openalex_key:
        logging.warning("OPENALEX_API_KEY is missing; anonymous/demo quota may be insufficient")
    for journal in config["journals"]:
        filters = (
            f"from_publication_date:{start.isoformat()},"
            f"to_publication_date:{end.isoformat()},"
            f"primary_location.source.issn:{'|'.join(journal['issns'])}"
        )
        params = {
            "filter": filters,
            "search": SEARCH_QUERY,
            "per_page": "100",
            "select": (
                "id,doi,title,display_name,publication_date,authorships,"
                "primary_location,best_oa_location,abstract_inverted_index,"
                "biblio,type,cited_by_count"
            ),
        }
        if mailto:
            params["mailto"] = mailto
        url = f"{OPENALEX}/works?{urllib.parse.urlencode(params)}"
        response = request_json(url, headers=headers)
        for work in response.get("results", []):
            score, reasons, abstract, directions = score_work(work, journal)
            if score < int(config["minimum_score"]):
                continue
            work["_score"] = score
            work["_reasons"] = reasons
            work["_abstract"] = abstract
            work["_directions"] = directions
            work["_journal"] = journal
            key = work_key(work)
            previous = candidates.get(key)
            if key and (previous is None or score > previous["_score"]):
                candidates[key] = work
        time.sleep(0.12)
    return sorted(
        candidates.values(),
        key=lambda work: (work["_score"], work_date(work), int(work.get("cited_by_count") or 0)),
        reverse=True,
    )


def zotero_headers(api_key: str) -> dict[str, str]:
    return {"Zotero-API-Key": api_key, "Zotero-API-Version": "3"}


def zotero_user_id(api_key: str) -> int:
    data = request_json(f"{ZOTERO}/keys/current", headers=zotero_headers(api_key))
    user_id = data.get("userID")
    if not user_id:
        raise RuntimeError("Zotero API key is valid but has no personal-library userID")
    if not data.get("access", {}).get("user", {}).get("write"):
        raise RuntimeError("Zotero API key does not have write access to the personal library")
    return int(user_id)


def zotero_get_all(url: str, api_key: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    start = 0
    while True:
        separator = "&" if "?" in url else "?"
        page = request_json(
            f"{url}{separator}limit=100&start={start}",
            headers=zotero_headers(api_key),
        )
        output.extend(page)
        if len(page) < 100:
            return output
        start += len(page)


def create_zotero_object(url: str, api_key: str, obj: dict[str, Any]) -> dict[str, Any]:
    response = request_json(url, headers=zotero_headers(api_key), method="POST", payload=[obj])
    successful = response.get("successful") or response.get("success") or {}
    created = successful.get("0")
    if isinstance(created, str):
        return {"key": created}
    if isinstance(created, dict):
        return created.get("data") or created
    failed = response.get("failed") or {}
    raise RuntimeError(f"Zotero rejected object: {failed or response}")


def ensure_collection(
    user_id: int,
    api_key: str,
    name: str,
    parent_key: str | bool,
) -> str:
    url = f"{ZOTERO}/users/{user_id}/collections"
    collections = zotero_get_all(url, api_key)
    for collection in collections:
        data = collection.get("data", collection)
        if data.get("name") == name and data.get("parentCollection", False) == parent_key:
            return data["key"]
    created = create_zotero_object(
        url,
        api_key,
        {"name": name, "parentCollection": parent_key},
    )
    return created["key"]


def zotero_existing_dois(user_id: int, api_key: str) -> set[str]:
    items = zotero_get_all(
        f"{ZOTERO}/users/{user_id}/items/top?itemType=journalArticle&format=json",
        api_key,
    )
    return {
        (item.get("data", item).get("DOI") or "").strip().lower()
        for item in items
        if item.get("data", item).get("DOI")
    }


def creators_from_work(work: dict[str, Any]) -> list[dict[str, str]]:
    creators = []
    for authorship in work.get("authorships") or []:
        name = ((authorship.get("author") or {}).get("display_name") or "").strip()
        if not name:
            continue
        parts = name.rsplit(" ", 1)
        if len(parts) == 2:
            creators.append({"creatorType": "author", "firstName": parts[0], "lastName": parts[1]})
        else:
            creators.append({"creatorType": "author", "name": name})
    return creators


def oa_pdf_url(work: dict[str, Any]) -> str:
    locations = [work.get("best_oa_location"), work.get("primary_location")]
    for location in locations:
        if location and location.get("pdf_url"):
            return location["pdf_url"]
    return ""


def zotero_item(work: dict[str, Any], collection_key: str) -> dict[str, Any]:
    journal = work["_journal"]
    biblio = work.get("biblio") or {}
    primary = work.get("primary_location") or {}
    source = primary.get("source") or {}
    doi = normalized_doi(work)
    landing_url = work.get("doi") or primary.get("landing_page_url") or work.get("id") or ""
    tags = [
        {"tag": "数字孪生"},
        {"tag": "来源:每日自动检索"},
        {"tag": f"期刊:{journal['short_name']}"},
    ]
    tags.extend({"tag": f"方向:{direction}"} for direction in work.get("_directions") or [])
    return {
        "itemType": "journalArticle",
        "title": clean_markup(work.get("display_name") or work.get("title") or ""),
        "creators": creators_from_work(work),
        "abstractNote": clean_markup(work.get("_abstract") or ""),
        "publicationTitle": source.get("display_name") or journal["name"],
        "volume": str(biblio.get("volume") or ""),
        "issue": str(biblio.get("issue") or ""),
        "pages": str(biblio.get("first_page") or ""),
        "date": work_date(work),
        "DOI": doi,
        "ISSN": ", ".join(source.get("issn") or journal["issns"]),
        "url": landing_url,
        "libraryCatalog": "OpenAlex / publisher metadata",
        "extra": f"OpenAlex: {work.get('id', '')}\n规则相关性评分: {work['_score']}",
        "tags": tags,
        "collections": [collection_key],
    }


def add_note_and_oa_link(user_id: int, api_key: str, parent_key: str, work: dict[str, Any]) -> None:
    url = f"{ZOTERO}/users/{user_id}/items"
    reason = "；".join(work.get("_reasons") or [])
    note = (
        "<p><strong>自动筛选说明</strong></p>"
        f"<p>{html.escape(reason)}。自动相关性优先级评分（规则计算）：{work['_score']}。</p>"
        "<p>该分数由固定规则计算，不是 GPT 的主观估计，也不代表论文质量；仅用于安排阅读优先级。请以出版商页面和论文全文为准。</p>"
    )
    create_zotero_object(url, api_key, {"itemType": "note", "parentItem": parent_key, "note": note})
    pdf_url = oa_pdf_url(work)
    if pdf_url:
        create_zotero_object(
            url,
            api_key,
            {
                "itemType": "attachment",
                "parentItem": parent_key,
                "linkMode": "linked_url",
                "title": "开放获取 PDF",
                "url": pdf_url,
                "contentType": "application/pdf",
                "tags": [{"tag": "开放获取"}],
            },
        )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Search and rank without writing Zotero")
    parser.add_argument("--initial", action="store_true", help="Force initial eight-month lookback")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    setup_logging(args.verbose or args.dry_run)

    config = load_json(CONFIG_PATH, None)
    if not config:
        raise RuntimeError(f"Missing configuration: {CONFIG_PATH}")
    state = load_json(STATE_PATH, {"initialized": False, "imported": []})
    today = dt.date.today()
    initial = args.initial or not state.get("initialized")
    if initial:
        start = months_ago(today, int(config["initial_lookback_months"]))
        limit = int(config["initial_limit"])
    else:
        if "daily_lookback_months" in config:
            start = months_ago(today, int(config["daily_lookback_months"]))
        else:
            start = today - dt.timedelta(days=int(config.get("daily_lookback_days", 7)))
        limit = int(config["daily_limit"])

    logging.info("Searching %s to %s; initial=%s", start, today, initial)
    candidates = openalex_search(config, start, today)
    locally_seen = set(state.get("imported") or [])
    candidates = [work for work in candidates if work_key(work) not in locally_seen]

    api_key = os.environ.get("ZOTERO_API_KEY", "").strip()
    if not args.dry_run and not api_key:
        raise RuntimeError("ZOTERO_API_KEY is not available. Run setup.ps1 first.")

    existing_dois: set[str] = set()
    user_id = 0
    if not args.dry_run:
        user_id = zotero_user_id(api_key)
        existing_dois = zotero_existing_dois(user_id, api_key)
        candidates = [work for work in candidates if not normalized_doi(work) or normalized_doi(work) not in existing_dois]

    selected: list[dict[str, Any]] = []
    for work in candidates:
        if crossref_verify(work):
            selected.append(work)
        if len(selected) >= limit:
            break
    if args.dry_run:
        print(json.dumps([
            {
                "score": work["_score"],
                "date": work_date(work),
                "journal": work["_journal"]["short_name"],
                "title": work.get("display_name") or work.get("title"),
                "doi": normalized_doi(work),
                "reasons": work["_reasons"],
            }
            for work in selected
        ], ensure_ascii=False, indent=2))
        return 0

    parent_key = ensure_collection(user_id, api_key, config["parent_collection"], False)
    child_key = ensure_collection(user_id, api_key, today.isoformat(), parent_key)
    if not selected:
        logging.info("No unread high-relevance papers found; created/confirmed today's Zotero collection")
        state["initialized"] = True
        state["last_run"] = dt.datetime.now().astimezone().isoformat()
        save_json_atomic(STATE_PATH, state)
        return 0

    item_url = f"{ZOTERO}/users/{user_id}/items"
    imported = list(state.get("imported") or [])
    failures = 0
    for work in selected:
        try:
            created = create_zotero_object(item_url, api_key, zotero_item(work, child_key))
            add_note_and_oa_link(user_id, api_key, created["key"], work)
            imported.append(work_key(work))
            logging.info("Imported [%s] %s", work["_journal"]["short_name"], work.get("title"))
        except Exception:
            failures += 1
            logging.exception("Failed to import %s", work.get("title"))

    state["initialized"] = True
    state["last_run"] = dt.datetime.now().astimezone().isoformat()
    state["imported"] = list(dict.fromkeys(imported))[-5000:]
    save_json_atomic(STATE_PATH, state)
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        logging.exception("Fatal error")
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
