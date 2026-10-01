"""Automatic news fetching from free Indian RSS sources + Google News (Hindi).

- National (राष्ट्रीय): Times of India + The Hindu RSS (two Indian websites).
- Locality feeds (Delhi, Ghaziabad, Noida, Greater Noida, Hapur, Meerut,
  Muzaffarnagar, Lucknow admin transfers): Google News RSS (hl=hi, gl=IN),
  which aggregates Indian publishers in Hindi.

Only items <= MAX_AGE_HOURS old are kept, sorted newest first, capped per feed.
De-duplication by link happens here (within a run) and in server.py (vs DB).
"""
import asyncio
import re
import html
import urllib.parse
from datetime import datetime, timezone, timedelta

import feedparser
import httpx

MAX_AGE_HOURS = 4
UA = "Mozilla/5.0 (compatible; EditorialNewsroomBot/1.0)"
GN = "https://news.google.com/rss/search?q={q}&hl=hi&gl=IN&ceid=IN:hi"


def _gn(query):
    return GN.format(q=urllib.parse.quote(query))


# category is used as the card badge / region filter value
SOURCES = [
    {"category": "राष्ट्रीय", "source": "Times of India", "lang": "en", "cap": 6,
     "url": "https://timesofindia.indiatimes.com/rssfeeds/-2128936835.cms", "gn": False},
    {"category": "राष्ट्रीय", "source": "The Hindu", "lang": "en", "cap": 6,
     "url": "https://www.thehindu.com/news/national/feeder/default.rss", "gn": False},
    {"category": "दिल्ली", "source": "Google News", "lang": "hi", "cap": 10,
     "url": _gn("दिल्ली मुख्य समाचार"), "gn": True},
    {"category": "गाज़ियाबाद", "source": "Google News", "lang": "hi", "cap": 30,
     "url": _gn("गाजियाबाद समाचार"), "gn": True},
    {"category": "नोएडा", "source": "Google News", "lang": "hi", "cap": 8,
     "url": _gn("नोएडा समाचार"), "gn": True},
    {"category": "ग्रेटर नोएडा", "source": "Google News", "lang": "hi", "cap": 8,
     "url": _gn("ग्रेटर नोएडा समाचार"), "gn": True},
    {"category": "हापुड़", "source": "Google News", "lang": "hi", "cap": 6,
     "url": _gn("हापुड़ समाचार"), "gn": True},
    {"category": "मेरठ", "source": "Google News", "lang": "hi", "cap": 8,
     "url": _gn("मेरठ समाचार"), "gn": True},
    {"category": "मुज़फ़्फ़रनगर", "source": "Google News", "lang": "hi", "cap": 10,
     "url": _gn("मुजफ्फरनगर समाचार"), "gn": True},
    {"category": "लखनऊ प्रशासनिक तबादले", "source": "Google News", "lang": "hi", "cap": 10,
     "url": _gn("लखनऊ सरकार प्रशासनिक तबादला विभाग"), "gn": True},
    {"category": "सिनेमा जगत", "source": "Times of India", "lang": "en", "cap": 8,
     "url": "https://timesofindia.indiatimes.com/rssfeeds/1081479906.cms", "gn": False},
    {"category": "सिनेमा जगत", "source": "Google News", "lang": "hi", "cap": 10,
     "url": _gn("बॉलीवुड हिंदी सिनेमा फिल्म समाचार"), "gn": True},
    {"category": "टीवी जगत", "source": "Google News", "lang": "hi", "cap": 10,
     "url": _gn("टीवी सीरियल टेलीविजन मनोरंजन समाचार"), "gn": True},
    {"category": "खेल (क्रिकेट)", "source": "Times of India", "lang": "en", "cap": 8,
     "url": "https://timesofindia.indiatimes.com/rssfeeds/4719148.cms", "gn": False},
    {"category": "खेल (क्रिकेट)", "source": "Google News", "lang": "hi", "cap": 12,
     "url": _gn("क्रिकेट भारतीय टीम अंतरराष्ट्रीय समाचार"), "gn": True},
    {"category": "खेल (अन्य)", "source": "The Hindu", "lang": "en", "cap": 6,
     "url": "https://www.thehindu.com/sport/feeder/default.rss", "gn": False},
    {"category": "खेल (अन्य)", "source": "Google News", "lang": "hi", "cap": 10,
     "url": _gn("हॉकी फुटबॉल कबड्डी बैडमिंटन ओलंपिक भारत खेल समाचार"), "gn": True},
    {"category": "धर्म व आध्यात्म", "source": "Times of India", "lang": "en", "cap": 6, "max_age_hours": 72,
     "url": "https://timesofindia.indiatimes.com/rssfeeds/65857041.cms", "gn": False},
    {"category": "धर्म व आध्यात्म", "source": "Google News", "lang": "hi", "cap": 10, "max_age_hours": 72,
     "url": _gn("भगवान देवी देवता पौराणिक प्रेरक कथा प्रसंग"), "gn": True},
    {"category": "धर्म व आध्यात्म", "source": "Google News", "lang": "hi", "cap": 8, "max_age_hours": 72,
     "url": _gn("रामायण महाभारत व्रत त्योहार पूजा कथा महत्व"), "gn": True},
]


def normalize_title(text):
    if not text:
        return ""
    t = text.lower().strip()
    t = re.sub(r"\s+-\s+[^-]+$", "", t)  # drop " - Publisher" suffix
    t = re.sub(r"[^\w\u0900-\u097f]+", "", t)  # keep latin + devanagari word chars
    return t


def _clean_html(text):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:1500]


def _clean_title(title, src):
    title = html.unescape((title or "").strip())
    if src["gn"] and " - " in title:
        title = title.rsplit(" - ", 1)[0].strip()
    return title


def _publisher(entry, src):
    if src["gn"]:
        s = entry.get("source")
        if s and getattr(s, "get", None):
            return s.get("title") or src["source"]
        return src["source"]
    return src["source"]


def _entry_dt(entry):
    st = entry.get("published_parsed") or entry.get("updated_parsed")
    if not st:
        return None
    try:
        return datetime(*st[:6], tzinfo=timezone.utc)
    except Exception:
        return None


async def _get(client, src):
    try:
        r = await client.get(src["url"], timeout=20.0)
        return src, r.content
    except Exception:
        return src, None


async def collect_candidates():
    async with httpx.AsyncClient(follow_redirects=True, headers={"User-Agent": UA}) as client:
        fetched = await asyncio.gather(*[_get(client, s) for s in SOURCES])

    now = datetime.now(timezone.utc)
    seen_links = set()
    out = []

    for src, content in fetched:
        if not content:
            continue
        max_age = src.get("max_age_hours", MAX_AGE_HOURS)
        parsed = feedparser.parse(content)
        rows = []
        for e in parsed.entries:
            dt = _entry_dt(e)
            if dt is None or (now - dt) > timedelta(hours=max_age):
                continue
            link = (e.get("link") or "").strip()
            if not link or link in seen_links:
                continue
            headline = _clean_title(e.get("title", ""), src)
            if not headline:
                continue
            summary = _clean_html(e.get("summary", "") or e.get("description", ""))
            content_text = summary if len(summary) >= 20 else headline
            rows.append((dt, {
                "headline": headline,
                "content": content_text,
                "category": src["category"],
                "source": _publisher(e, src),
                "source_language": src["lang"],
                "source_url": link,
            }))
        rows.sort(key=lambda x: x[0], reverse=True)
        for _, row in rows[: src["cap"]]:
            if row["source_url"] in seen_links:
                continue
            seen_links.add(row["source_url"])
            out.append(row)

    return out
