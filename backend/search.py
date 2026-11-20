"""Project Golu: Real-Time Internet Search Module.
Provides live web search capabilities via DuckDuckGo and Wikipedia APIs
to answer real-time questions, current facts, and queries beyond local memory.
Zero-Cloud LLM integration: search snippets are summarized locally by qwen2.5:1.5b.
100% Graceful Fallback: Never crashes or hangs if offline or in Airplane Mode.
"""

import re
import time
import json
import logging
import urllib.request
import urllib.parse
from html.parser import HTMLParser
from typing import List, Dict, Any, Optional

from backend.llm_engine import llm_engine

logger = logging.getLogger("golu.search")

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


class DDGHtmlParser(HTMLParser):
    """Lightweight zero-dependency HTML parser for DuckDuckGo HTML Lite results."""

    def __init__(self):
        super().__init__()
        self.results: List[Dict[str, str]] = []
        self._current_result: Dict[str, str] = {}
        self._in_title = False
        self._in_snippet = False
        self._text_buffer = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        class_name = attrs_dict.get("class", "")

        if tag == "a" and "result__url" in class_name:
            self._current_result["url"] = attrs_dict.get("href", "")

        if tag == "a" and "result__snippet" in class_name:
            self._in_snippet = True
            self._text_buffer = []
        elif tag == "td" and "result-snippet" in class_name:
            self._in_snippet = True
            self._text_buffer = []
        elif tag == "a" and "result__a" in class_name:
            self._in_title = True
            self._text_buffer = []
            if "href" in attrs_dict and "url" not in self._current_result:
                self._current_result["url"] = attrs_dict["href"]

    def handle_endtag(self, tag):
        if self._in_title and tag == "a":
            self._in_title = False
            self._current_result["title"] = "".join(self._text_buffer).strip()
            self._text_buffer = []

        if self._in_snippet and tag in ("a", "td"):
            self._in_snippet = False
            self._current_result["snippet"] = "".join(self._text_buffer).strip()
            self._text_buffer = []
            if self._current_result.get("title") or self._current_result.get("snippet"):
                self.results.append(self._current_result)
                self._current_result = {}

    def handle_data(self, data):
        if self._in_title or self._in_snippet:
            self._text_buffer.append(data)


class InternetSearchEngine:
    """Robust zero-dependency search engine for Project Golu."""

    def __init__(self, timeout: float = 3.5):
        self.timeout = timeout

    def search_duckduckgo_api(self, query: str) -> List[Dict[str, str]]:
        """Queries DuckDuckGo Instant Answer API."""
        results = []
        try:
            params = urllib.parse.urlencode({"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"})
            url = f"https://api.duckduckgo.com/?{params}"
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))

                # Check Abstract
                if data.get("AbstractText"):
                    results.append({
                        "title": data.get("Heading", query),
                        "snippet": data["AbstractText"],
                        "url": data.get("AbstractURL", "")
                    })

                # Check RelatedTopics
                for topic in data.get("RelatedTopics", [])[:3]:
                    if isinstance(topic, dict) and topic.get("Text"):
                        results.append({
                            "title": topic.get("Text", "")[:60],
                            "snippet": topic.get("Text", ""),
                            "url": topic.get("FirstURL", "")
                        })
        except Exception as e:
            logger.debug("DDG API search failed or offline: %s", e)

        return results

    def search_wikipedia(self, query: str) -> List[Dict[str, str]]:
        """Queries Wikipedia Search API for factual definitions."""
        results = []
        try:
            params = urllib.parse.urlencode({
                "action": "query",
                "list": "search",
                "srsearch": query,
                "utf8": "",
                "format": "json"
            })
            url = f"https://en.wikipedia.org/w/api.php?{params}"
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
                search_hits = data.get("query", {}).get("search", [])
                for hit in search_hits[:3]:
                    title = hit.get("title", "")
                    raw_snippet = hit.get("snippet", "")
                    # Strip HTML tags like <span class="searchmatch">
                    clean_snippet = re.sub(r"<[^>]+>", "", raw_snippet)
                    page_url = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"
                    results.append({
                        "title": title,
                        "snippet": clean_snippet,
                        "url": page_url
                    })
        except Exception as e:
            logger.debug("Wikipedia search failed or offline: %s", e)

        return results

    def search_duckduckgo_html(self, query: str) -> List[Dict[str, str]]:
        """Queries DuckDuckGo HTML search for general web results."""
        results = []
        try:
            url = "https://html.duckduckgo.com/html/"
            data = urllib.parse.urlencode({"q": query}).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                html_content = response.read().decode("utf-8", errors="ignore")
                parser = DDGHtmlParser()
                parser.feed(html_content)
                results = parser.results[:4]
        except Exception as e:
            logger.debug("DDG HTML search failed or offline: %s", e)

        return results

    def search(self, query: str, max_results: int = 4) -> List[Dict[str, str]]:
        """Executes multi-source search with priority: DDG API -> Wikipedia -> DDG HTML."""
        combined: List[Dict[str, str]] = []
        t0 = time.perf_counter()

        # Try DDG Instant Answer API first
        api_results = self.search_duckduckgo_api(query)
        combined.extend(api_results)

        # If not enough, try Wikipedia
        if len(combined) < 2:
            wiki_results = self.search_wikipedia(query)
            combined.extend(wiki_results)

        # If still empty, try DDG HTML
        if not combined:
            html_results = self.search_duckduckgo_html(query)
            combined.extend(html_results)

        elapsed = time.perf_counter() - t0
        logger.info("Web search for '%s' returned %d results in %.2fs", query, len(combined), elapsed)
        return combined[:max_results]

    def answer_query_with_web(self, query: str) -> Dict[str, Any]:
        """Searches the internet and synthesizes a concise, grounded answer using local LLM."""
        t0 = time.perf_counter()
        results = self.search(query, max_results=4)

        if not results:
            # Fallback to local LLM knowledge
            prompt = (
                f"You are Golu, a smart AI assistant. Answer the user's question directly, accurately, "
                f"and concisely in 2-3 sentences in natural Hinglish or English:\n\nQuestion: {query}"
            )
            answer = llm_engine.generate(
                prompt=prompt,
                system_prompt="You are Golu, a helpful local AI assistant. Answer concisely and accurately.",
                max_tokens=150
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return {
                "query": query,
                "answer": answer.strip(),
                "source": "local_llm",
                "results_count": 0,
                "sources": [],
                "latency_ms": round(elapsed_ms, 2)
            }

        # Build context from web snippets
        snippets = []
        for r in results:
            snippets.append(f"• [{r.get('title', 'Web Result')}]: {r.get('snippet', '')} (URL: {r.get('url', '')})")
        context_block = "\n".join(snippets)

        prompt = (
            f"You are Golu, a smart AI assistant. Given the following live internet search results, "
            f"answer the user's question directly, accurately, and concisely in 2-3 sentences in natural Hinglish or English:\n\n"
            f"Question: {query}\n\n"
            f"Live Search Results:\n{context_block}\n\n"
            f"Concise Answer:"
        )

        answer = llm_engine.generate(
            prompt=prompt,
            system_prompt="You are Golu. Provide direct, factual, grounded answers using the provided search results.",
            max_tokens=150
        )

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return {
            "query": query,
            "answer": answer.strip(),
            "source": "internet_search",
            "results_count": len(results),
            "sources": [r.get("url", "") for r in results if r.get("url")],
            "latency_ms": round(elapsed_ms, 2)
        }


# Global search engine instance
web_search_engine = InternetSearchEngine()
