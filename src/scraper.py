"""Naver Finance research report scraper.

Scrapes PDF links from https://finance.naver.com/research/company_list.naver
and downloads new PDFs to data/uploads/.
"""

import sys
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://finance.naver.com/research/company_list.naver"
UPLOAD_DIR = Path("data/uploads")
DOWNLOAD_DELAY = 0.5   # seconds between PDF downloads
PAGE_DELAY = 1.0       # seconds between page requests
DEFAULT_MAX_PAGES = 5

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://finance.naver.com/research/",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
}


def _fetch_page(page: int) -> BeautifulSoup:
    resp = requests.get(BASE_URL, params={"page": page}, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = "euc-kr"
    return BeautifulSoup(resp.text, "html.parser")


def _extract_pdf_urls(soup: BeautifulSoup) -> list:
    """Return all PDF links found in the research report table."""
    urls = []
    for a in soup.select("table.type_1 a[href]"):
        href = a["href"]
        if href.lower().endswith(".pdf"):
            # Resolve relative URLs just in case
            full = urljoin("https://ssl.pstatic.net", href) if href.startswith("/") else href
            urls.append(full)
    return urls


def _download(url: str, dest_dir: Path) -> Optional[str]:
    """Download a PDF; return filename on success, None if already exists."""
    filename = url.split("/")[-1].split("?")[0]
    dest = dest_dir / filename
    if dest.exists():
        return None

    resp = requests.get(url, headers=HEADERS, timeout=60, stream=True)
    resp.raise_for_status()

    with open(dest, "wb") as fh:
        for chunk in resp.iter_content(chunk_size=8192):
            fh.write(chunk)
    return filename


def scrape(max_pages: int = DEFAULT_MAX_PAGES) -> int:
    """Scrape up to *max_pages* pages and return the number of new PDFs downloaded."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    total_new = 0

    for page in range(1, max_pages + 1):
        print(f"[page {page}/{max_pages}] fetching ...", flush=True)
        try:
            soup = _fetch_page(page)
        except requests.RequestException as exc:
            print(f"  ERROR fetching page {page}: {exc}", file=sys.stderr)
            break

        urls = _extract_pdf_urls(soup)
        if not urls:
            print(f"  No PDF links found on page {page} — stopping.")
            break

        new_on_page = 0
        for url in urls:
            try:
                name = _download(url, UPLOAD_DIR)
            except requests.RequestException as exc:
                print(f"  ERROR downloading {url}: {exc}", file=sys.stderr)
                continue

            if name:
                print(f"  + {name}")
                total_new += 1
                new_on_page += 1
            else:
                print(f"  = {url.split('/')[-1]} (exists)")

            time.sleep(DOWNLOAD_DELAY)

        # All PDFs on this page already exist → we've caught up
        if new_on_page == 0:
            print("  All PDFs on this page already downloaded — stopping early.")
            break

        if page < max_pages:
            time.sleep(PAGE_DELAY)

    print(f"\nDone. {total_new} new PDF(s) downloaded to {UPLOAD_DIR}/")
    return total_new


if __name__ == "__main__":
    pages = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_MAX_PAGES
    scrape(max_pages=pages)
