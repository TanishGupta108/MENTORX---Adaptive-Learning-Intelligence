"""Allowlist HTML sanitiser for dataset question text.

Dataset HTML is untrusted input. Nothing is passed through: the markup is parsed and then
REBUILT from an allowlist of tags and attributes, with all text re-escaped. Links, images,
scripts, event handlers and inline styles can never survive. MathML is kept (browsers render
MathML Core natively); the deprecated <mfenced> is rewritten into <mrow> with brackets so it
still displays.
"""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser

ALLOWED_TAGS = {
    # text and layout
    "p", "br", "span", "div", "strong", "b", "em", "i", "u", "sup", "sub", "ul", "ol", "li",
    "table", "thead", "tbody", "tr", "td", "th", "section", "article", "h3", "h4",
    # MathML Core
    "math", "mi", "mn", "mo", "mtext", "mspace", "ms", "mrow", "mfrac", "msqrt", "mroot",
    "msup", "msub", "msubsup", "mover", "munder", "munderover", "mtable", "mtr", "mtd",
    "mstyle", "mpadded", "mphantom", "semantics", "menclose",
}  # fmt: skip
VOID_TAGS = {"br", "mspace"}
ALLOWED_ATTRS = {
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan", "scope"},
    "math": {"display"},
    "mi": {"mathvariant"},
    "mo": {"stretchy", "fence", "separator"},
    "menclose": {"notation"},
    "mfrac": {"linethickness"},
}
# Elementary long-division / stacked layouts: no browser renders these.
UNRENDERABLE = ("<mlongdiv", "<mstack", "<msgroup", "<msline", "<mscarries")
BLANK_MARKER = re.compile(r"<ast-r\b[^>]*>(\s*</ast-r>)?", re.IGNORECASE)
BLANK_HTML = '<span class="answer-blank" aria-label="answer box">?</span>'


class _Rebuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.stack: list[str] = []
        self.fences: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "mfenced":
            a = dict(attrs)
            open_, close = a.get("open", "("), a.get("close", ")")
            self.fences.append((open_ or "", close or ""))
            self.out.append(f"<mrow><mo>{html.escape(open_ or '')}</mo>")
            self.stack.append("mfenced")
            return
        if tag not in ALLOWED_TAGS:
            return  # drop the tag, keep its text content
        keep = ALLOWED_ATTRS.get(tag, set())
        parts = [
            f'{k}="{html.escape(v or "", quote=True)}"'
            for k, v in attrs
            if k.lower() in keep and v is not None and len(v) < 40
        ]
        self.out.append(f"<{tag}{' ' + ' '.join(parts) if parts else ''}>")
        if tag not in VOID_TAGS:
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        tag = tag.lower()
        if tag in ALLOWED_TAGS and tag not in VOID_TAGS and self.stack and self.stack[-1] == tag:
            self.stack.pop()
            self.out.append(f"</{tag}>")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag not in self.stack:
            return  # stray close tag
        while self.stack:  # close anything left open inside it
            t = self.stack.pop()
            if t == "mfenced":
                _, close = self.fences.pop()
                self.out.append(f"<mo>{html.escape(close)}</mo></mrow>")
            else:
                self.out.append(f"</{t}>")
            if t == tag:
                break

    def handle_data(self, data: str) -> None:
        self.out.append(html.escape(data, quote=False))

    def result(self) -> str:
        while self.stack:
            self.handle_endtag(self.stack[-1])
        return "".join(self.out)


def sanitize(raw: str) -> str:
    """Safe HTML for a question body or option. Answer blanks become a visible marker."""
    raw = BLANK_MARKER.sub("\x00BLANK\x00", raw or "")
    parser = _Rebuilder()
    parser.feed(raw)
    parser.close()
    out = parser.result().replace("\x00BLANK\x00", BLANK_HTML)
    out = re.sub(r"(<p>(\s|&nbsp;|\xa0)*</p>\s*)+", "", out)  # empty paragraphs
    return out.strip()


def plain_text(raw: str) -> str:
    """Text only (for search, previews and comparing multiple-choice answers)."""
    text = re.sub(r"<[^>]+>", " ", BLANK_MARKER.sub(" ", raw or ""))
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def count_blanks(raw: str) -> int:
    return len(BLANK_MARKER.findall(raw or ""))


def has_unrenderable(raw: str) -> bool:
    low = (raw or "").lower()
    return any(t in low for t in UNRENDERABLE) or "<img" in low or "<iframe" in low
