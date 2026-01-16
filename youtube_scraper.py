#!/usr/bin/env python3
import argparse
import csv
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


@dataclass
class VideoResult:
    query: str
    url: str
    title: str = ""
    channel: str = ""
    error: str = ""


def read_input_songs(path: Path) -> List[str]:
    songs: List[str] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            song = line.strip()
            if song:
                songs.append(song)
    return songs


def open_youtube(page, timeout_ms: int) -> None:
    page.goto("https://www.youtube.com", wait_until="domcontentloaded", timeout=timeout_ms)
    _handle_consent_popups(page, timeout_ms)


def _handle_consent_popups(page, timeout_ms: int) -> None:
    selectors = [
        "button:has-text('Accept all')",
        "button:has-text('I agree')",
        "button:has-text('Agree')",
        "button:has-text('Aceitar tudo')",
        "button:has-text('Concordo')",
    ]
    for selector in selectors:
        try:
            button = page.locator(selector)
            if button.first.is_visible(timeout=2000):
                button.first.click()
                page.wait_for_timeout(1000)
                break
        except PlaywrightTimeoutError:
            continue
        except Exception:
            continue

    dismiss_selectors = [
        "button:has-text('Not now')",
        "button:has-text('No thanks')",
        "button:has-text('Agora não')",
        "button:has-text('Fechar')",
        "tp-yt-paper-button:has-text('Fechar')",
    ]
    for selector in dismiss_selectors:
        try:
            button = page.locator(selector)
            if button.first.is_visible(timeout=1000):
                button.first.click()
                page.wait_for_timeout(500)
                break
        except PlaywrightTimeoutError:
            continue
        except Exception:
            continue


def search_song(page, query: str, timeout_ms: int) -> None:
    search_box = page.locator("input#search")
    if not search_box.count():
        search_box = page.locator("input[name='search_query']")
    search_box.wait_for(state="visible", timeout=timeout_ms)
    search_box.click()
    page.keyboard.press("Control+A")
    page.keyboard.press("Delete")
    page.keyboard.type(query, delay=20)
    page.keyboard.press("Enter")
    page.wait_for_selector(
        "ytd-video-renderer, ytd-rich-item-renderer",
        timeout=timeout_ms,
    )


def _extract_video_candidates(page) -> Iterable[Tuple[str, str]]:
    candidates = []
    video_renderers = page.locator("ytd-video-renderer, ytd-rich-item-renderer")
    count = video_renderers.count()
    for idx in range(count):
        item = video_renderers.nth(idx)
        if item.locator("ytd-promoted-video-renderer, ytd-ad-slot-renderer").count():
            continue
        link = item.locator("a#video-title")
        href = link.get_attribute("href") if link.count() else None
        if not href:
            continue
        full_url = f"https://www.youtube.com{href}" if href.startswith("/") else href
        candidates.append((full_url, link))
    return candidates


def click_first_valid_video(page, timeout_ms: int) -> Tuple[str, str, str]:
    candidates = _extract_video_candidates(page)
    last_error = "Nenhum resultado de vídeo encontrado."
    for href, link in candidates:
        if "/shorts/" in href:
            last_error = "Apenas Shorts disponíveis nos primeiros resultados."
            continue
        try:
            with page.expect_navigation(wait_until="domcontentloaded", timeout=timeout_ms):
                link.click()
        except PlaywrightTimeoutError:
            link.click()
            page.wait_for_url("**/watch?v=*")
        page.wait_for_selector("ytd-player, video", timeout=timeout_ms)
        current_url = page.url
        if "/shorts/" in current_url:
            page.go_back(wait_until="domcontentloaded")
            page.wait_for_timeout(500)
            continue
        title = page.locator("h1 yt-formatted-string").first.text_content() or ""
        channel = page.locator("ytd-channel-name a").first.text_content() or ""
        return current_url, title.strip(), channel.strip()
    raise RuntimeError(last_error)


def capture_current_url(page) -> str:
    return page.url


def write_output_links(
    path: Path,
    results: List[VideoResult],
    delimiter: str,
    append: bool,
    include_meta: bool,
) -> None:
    mode = "a" if append else "w"
    with path.open(mode, encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter=delimiter)
        for result in results:
            row = [result.query, result.url]
            if include_meta:
                row.extend([result.title, result.channel])
            writer.writerow(row)


def write_errors(path: Path, errors: List[VideoResult]) -> None:
    if not errors:
        return
    with path.open("a", encoding="utf-8") as handle:
        for err in errors:
            timestamp = datetime.now().isoformat(timespec="seconds")
            handle.write(f"{err.query}\t{err.error}\t{timestamp}\n")


def _read_existing_output(path: Path, delimiter: str) -> List[VideoResult]:
    if not path.exists():
        return []
    results: List[VideoResult] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter=delimiter)
        for row in reader:
            if not row:
                continue
            query = row[0]
            url = row[1] if len(row) > 1 else ""
            title = row[2] if len(row) > 2 else ""
            channel = row[3] if len(row) > 3 else ""
            results.append(VideoResult(query=query, url=url, title=title, channel=channel))
    return results


def _write_output_json(path: Path, results: List[VideoResult], append: bool) -> None:
    payload = [result.__dict__ for result in results]
    if append and path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(existing, list):
            payload = existing + payload
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Busca músicas no YouTube e salva links.")
    parser.add_argument("--input", default="musicas.txt", help="Arquivo de entrada com músicas")
    parser.add_argument("--output", default="links.txt", help="Arquivo de saída com links")
    parser.add_argument("--errors", default="erros.txt", help="Arquivo de erros")
    parser.add_argument("--output-json", default="", help="Arquivo JSON opcional de saída")
    parser.add_argument("--limit", type=int, default=0, help="Limite de músicas a processar")
    parser.add_argument("--delay-ms", type=int, default=1200, help="Delay entre buscas")
    parser.add_argument("--timeout", type=int, default=30000, help="Timeout em ms")
    parser.add_argument("--headless", type=str, default="true", help="true/false")
    parser.add_argument("--dedupe", action="store_true", help="Deduplicar buscas")
    parser.add_argument("--resume", action="store_true", help="Continuar processamento")
    parser.add_argument(
        "--delimiter",
        choices=["tab", "comma"],
        default="tab",
        help="Separador do arquivo de saída",
    )
    parser.add_argument(
        "--include-meta",
        action="store_true",
        help="Incluir título e canal do vídeo no output",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    error_path = Path(args.errors)
    json_path = Path(args.output_json) if args.output_json else None
    delimiter = "\t" if args.delimiter == "tab" else ","
    headless = args.headless.lower() == "true"

    songs = read_input_songs(input_path)
    if args.limit > 0:
        songs = songs[: args.limit]

    existing_results: List[VideoResult] = []
    start_index = 0
    if args.resume:
        existing_results = _read_existing_output(output_path, delimiter)
        start_index = len(existing_results)

    cache: Dict[str, VideoResult] = {}
    results: List[VideoResult] = []
    errors: List[VideoResult] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()
        try:
            open_youtube(page, args.timeout)
            for idx, query in enumerate(songs[start_index:], start=start_index + 1):
                total = len(songs)
                if args.dedupe and query in cache:
                    cached = cache[query]
                    results.append(cached)
                    status = cached.url or "SEM URL"
                    print(f"[{idx}/{total}] Buscando: {query} | OK (cache): {status}")
                    continue

                try:
                    search_song(page, query, args.timeout)
                    url, title, channel = click_first_valid_video(page, args.timeout)
                    result = VideoResult(query=query, url=url, title=title, channel=channel)
                    results.append(result)
                    cache[query] = result
                    print(f"[{idx}/{total}] Buscando: {query} | OK: {url}")
                except Exception as exc:
                    error_message = str(exc)
                    result = VideoResult(query=query, url="", error=error_message)
                    results.append(result)
                    cache[query] = result
                    errors.append(result)
                    print(f"[{idx}/{total}] Buscando: {query} | ERRO: {error_message}")
                finally:
                    time.sleep(max(args.delay_ms, 0) / 1000)
        finally:
            context.close()
            browser.close()

    write_output_links(
        output_path,
        results,
        delimiter,
        append=args.resume,
        include_meta=args.include_meta,
    )
    write_errors(error_path, errors)
    if json_path:
        _write_output_json(json_path, results, append=args.resume)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
