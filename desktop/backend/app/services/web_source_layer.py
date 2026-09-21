from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.models.summary_input import MetaContext, PageContext, SummaryInput


class WebSourceLayer:
    _NOISE_SELECTORS = [
        "script",
        "style",
        "noscript",
        "nav",
        "header",
        "footer",
        "aside",
        '[class*="ad"]',
        '[id*="ad"]',
        '[class*="advert"]',
        '[id*="advert"]',
        '[class*="promo"]',
        '[id*="promo"]',
        '[class*="recommend"]',
        '[id*="recommend"]',
        '[class*="related"]',
        '[id*="related"]',
    ]
    _LONG_LINK_TEXT_LIMIT = 80
    _LONG_LINK_NOISE_LIMIT = 120

    def from_html(self, input_id: str, url: str, html: str, user_options: dict) -> SummaryInput:
        page_context = self.extract_page_context(url, html)
        return SummaryInput(
            input_id=input_id,
            input_type="web_link",
            source_url=url,
            platform=None,
            title=page_context.title,
            user_goal=user_options.get("extras"),
            user_options=user_options,
            page_context=page_context,
            transcript_context=None,
            vision_context=None,
            social_context=None,
            meta_context=MetaContext(
                resource_type="web_link",
                platform=None,
                raw={
                    "supported_media_count": len(page_context.detected_media),
                    "link_count": len(page_context.links),
                    "heading_count": len(page_context.headings),
                },
            ),
        )

    def extract_page_context(self, url: str, html: str) -> PageContext:
        soup = BeautifulSoup(html or "", "html.parser")
        title = self._extract_title(soup)
        links = self._extract_links(soup, url)
        detected_media = self._extract_supported_media(soup, url)
        main_text = self._extract_main_text(soup)
        key_points = self._extract_key_points(soup)

        return PageContext(
            title=title,
            description=self._extract_description(soup),
            url=url,
            site_name=None,
            page_type="web_page",
            topic=title,
            headings=self._extract_headings(soup),
            main_text_summary=main_text,
            key_points=key_points,
            links=links,
            detected_media=detected_media,
            confidence=0.82 if title or links else 0.5,
        )

    def _extract_title(self, soup: BeautifulSoup) -> str:
        candidates = [
            self._meta_content(soup, "property", "og:title"),
            soup.title.get_text(" ", strip=True) if soup.title else None,
            self._first_text(soup, "h1"),
        ]
        return next((value for value in candidates if value), "")

    def _extract_description(self, soup: BeautifulSoup) -> Optional[str]:
        return self._meta_content(soup, "name", "description") or self._meta_content(
            soup, "property", "og:description"
        )

    def _extract_headings(self, soup: BeautifulSoup) -> list[dict]:
        headings = []
        for node in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
            text = node.get_text(" ", strip=True)
            if text:
                headings.append({"level": int(node.name[1]), "text": text})
        return headings

    def _extract_links(self, soup: BeautifulSoup, base_url: str) -> list[dict]:
        links = []
        seen = set()
        for node in soup.find_all("a"):
            href = node.get("href")
            if not href:
                continue
            absolute_url = urljoin(base_url, href)
            if absolute_url in seen:
                continue
            seen.add(absolute_url)
            links.append({"text": self._link_text(node), "url": absolute_url})
        return links

    def _extract_supported_media(self, soup: BeautifulSoup, base_url: str) -> list[dict]:
        media = []
        seen = set()
        for node in soup.find_all(["a", "iframe", "video", "source"]):
            raw_url = node.get("href") or node.get("src")
            if not raw_url:
                continue
            media_url = urljoin(base_url, raw_url)
            platform = self._detect_supported_platform(media_url)
            if not platform or media_url in seen:
                continue
            seen.add(media_url)
            media.append({"type": "video", "url": media_url, "platform": platform})
        return media

    def _extract_main_text(self, soup: BeautifulSoup) -> str:
        self._remove_noise(soup)
        candidate = self._main_content_node(soup)
        paragraphs = self._extract_content_lines(candidate, include_headings=False)

        if not paragraphs and candidate:
            text = candidate.get_text("\n", strip=True)
            paragraphs = [line.strip() for line in text.splitlines() if line.strip()]

        return "\n".join(paragraphs[:80])

    def _extract_key_points(self, soup: BeautifulSoup) -> list[str]:
        candidate = self._main_content_node(soup)
        return self._extract_content_lines(candidate, include_headings=True)[:20]

    def _remove_noise(self, soup: BeautifulSoup) -> None:
        for selector in self._NOISE_SELECTORS:
            for node in soup.select(selector):
                node.decompose()

    def _main_content_node(self, soup: BeautifulSoup):
        candidates = soup.find_all("article")
        if candidates:
            return max(candidates, key=lambda node: len(node.get_text(" ", strip=True)))
        return soup.find("main") or soup.body or soup

    def _extract_content_lines(self, node, include_headings: bool) -> list[str]:
        if not node:
            return []

        tags = ["p", "li"]
        if include_headings:
            tags = ["h1", "h2", "h3", "p", "li"]

        lines = []
        seen = set()
        for child in node.find_all(tags):
            if child.find_parent(["p", "li", "h1", "h2", "h3"]) is not None:
                continue
            if self._is_long_link_only_block(child):
                continue
            text = child.get_text(" ", strip=True)
            if text and text not in seen:
                seen.add(text)
                lines.append(text)
        return lines

    def _is_long_link_only_block(self, node) -> bool:
        links = node.find_all("a")
        if len(links) != 1:
            return False
        link_text = links[0].get_text(" ", strip=True)
        node_text = node.get_text(" ", strip=True)
        return bool(link_text and link_text == node_text and len(link_text) > self._LONG_LINK_NOISE_LIMIT)

    def _link_text(self, node) -> str:
        text = node.get_text(" ", strip=True)
        if len(text) <= self._LONG_LINK_TEXT_LIMIT:
            return text
        return f"{text[: self._LONG_LINK_TEXT_LIMIT]}..."

    def _detect_supported_platform(self, url: str) -> Optional[str]:
        lowered = url.lower()
        if "bilibili.com/video/" in lowered or "b23.tv" in lowered:
            return "bilibili"
        if (
            "youtube.com/watch" in lowered
            or "youtube.com/embed/" in lowered
            or "youtu.be/" in lowered
        ):
            return "youtube"
        if "douyin.com" in lowered:
            return "douyin"
        if "kuaishou.com" in lowered:
            return "kuaishou"
        return None

    def _meta_content(self, soup: BeautifulSoup, attr: str, value: str) -> Optional[str]:
        node = soup.find("meta", attrs={attr: value})
        if not node:
            return None
        content = node.get("content")
        return content.strip() if content else None

    def _first_text(self, soup: BeautifulSoup, selector: str) -> Optional[str]:
        node = soup.select_one(selector)
        return node.get_text(" ", strip=True) if node else None
