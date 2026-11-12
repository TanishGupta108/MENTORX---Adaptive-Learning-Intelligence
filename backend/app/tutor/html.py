"""Allowlist HTML sanitiser for dataset question text.

Dataset HTML is untrusted input. Nothing is passed through: the markup is parsed and then
REBUILT from an allowlist of tags and attributes, with all text re-escaped. Links, scripts,
event handlers and inline styles can never survive. MathML is kept (browsers render MathML
Core natively); the deprecated <mfenced> is rewritten into <mrow> with brackets so it still
displays.

Images:
- Formula images made by the WIRIS editor carry their formula as MathML (a `data-mathml`
  attribute, or a comment inside an inline SVG). They are replaced by that MathML, so the
  formula becomes real, accessible maths instead of a picture.
- Other images are kept only when their address resolves to an allowlisted host over HTTPS
  (the dataset's own content servers). Whether each address actually loads is checked once
  by scripts/check_images.py; questions with an unverified image are not served.
"""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit, urlunsplit

IMAGE_HOSTS = frozenset(
    {
        "resources.assistments.org",
        "app.assistments.org",
        "cms-k12oer-staging.s3.amazonaws.com",
        "cdn.openupresources.org",
        "access.openupresources.org",
        "cms-assets.illustrativemathematics.org",
    }
)
RELATIVE_IMAGE_BASE = "https://app.assistments.org"
_WIRIS = str.maketrans({"«": "<", "»": ">", "¨": '"', "§": "&", "`": "'"})
_SVG_MATHML = re.compile(r"MathML:\s*(<math.*?</math>)", re.S)


def resolve_image_url(src: str | None) -> str | None:
    """Absolute HTTPS address of a dataset image on an allowlisted host, else None."""
    src = html.unescape((src or "").strip())
    if not src or src.startswith("data:"):
        return None
    if src.startswith("//"):
        src = "https:" + src
    elif src.startswith("/"):
        src = RELATIVE_IMAGE_BASE + src
    u = urlsplit(src)
    if u.scheme not in ("http", "https") or (u.hostname or "") not in IMAGE_HOSTS:
        return None
    return urlunsplit(("https", u.netloc, u.path, u.query, ""))


def wiris_mathml(attrs: dict[str, str | None]) -> str | None:
    """The MathML behind a WIRIS formula image, if this <img> is one."""
    if attrs.get("data-mathml"):
        return (attrs["data-mathml"] or "").translate(_WIRIS)
    src = attrs.get("src") or ""
    if src.startswith("data:image/svg+xml"):
        m = _SVG_MATHML.search(unquote(src))
        if m:
            return m.group(1)  # entities inside are decoded by the parser, not here
    return None


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


def _dimension(v: str | None) -> int | None:
    return int(v) if v and v.isdigit() and 0 < int(v) <= 2000 else None


class _Rebuilder(HTMLParser):
    def __init__(self, image_ok=None) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.stack: list[str] = []
        self.fences: list[tuple[str, str]] = []
        self.image_ok = image_ok  # callable(url) -> bool; None = any allowlisted address

    def _image(self, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): v for k, v in attrs}
        formula = wiris_mathml(a)
        if formula:
            self.out.append(_rebuild(formula))
            return
        url = resolve_image_url(a.get("src"))
        if url is None or (self.image_ok is not None and not self.image_ok(url)):
            return
        dims = "".join(
            f' {k}="{d}"' for k in ("width", "height") if (d := _dimension(a.get(k))) is not None
        )
        self.out.append(
            f'<img src="{html.escape(url, quote=True)}" alt="Diagram for this question" '
            f'loading="lazy" decoding="async" referrerpolicy="no-referrer"{dims}>'
        )

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "img":
            self._image(attrs)
            return
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


def _rebuild(raw: str, image_ok=None) -> str:
    parser = _Rebuilder(image_ok)
    parser.feed(raw)
    parser.close()
    return parser.result()


def sanitize(raw: str, image_ok=None) -> str:
    """Safe HTML for a question body or option. Answer blanks become a visible marker.
    `image_ok(url)` decides which allowlisted images are kept (default: all of them)."""
    raw = BLANK_MARKER.sub("\x00BLANK\x00", raw or "")
    out = _rebuild(raw, image_ok).replace("\x00BLANK\x00", BLANK_HTML)
    out = re.sub(r"(<p>(\s|&nbsp;|\xa0)*</p>\s*)+", "", out)  # empty paragraphs
    return out.strip()


def plain_text(raw: str) -> str:
    """Text only (for search, previews and comparing multiple-choice answers)."""
    text = re.sub(r"<[^>]+>", " ", BLANK_MARKER.sub(" ", raw or ""))
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def count_blanks(raw: str) -> int:
    return len(BLANK_MARKER.findall(raw or ""))


class _ImageScan(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.urls: list[str] = []
        self.unresolvable = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "img":
            return
        a = {k.lower(): v for k, v in attrs}
        if wiris_mathml(a):
            return
        url = resolve_image_url(a.get("src"))
        if url:
            self.urls.append(url)
        else:
            self.unresolvable += 1

    handle_startendtag = handle_starttag


def scan_images(raw: str) -> tuple[list[str], int]:
    """(addresses of real images, number of images that can't be shown at all).
    WIRIS formula images are not counted: they become MathML."""
    p = _ImageScan()
    p.feed(raw or "")
    p.close()
    return p.urls, p.unresolvable


def has_unrenderable(raw: str) -> bool:
    """Layouts no browser renders (long division, stacked arithmetic) or embedded frames."""
    low = (raw or "").lower()
    return any(t in low for t in UNRENDERABLE) or "<iframe" in low


# ---------------------------------------------------------------- readable text for the AI tutor


class _MathText(HTMLParser):
    """Turns sanitised question HTML into plain text an LLM can read: fractions become
    (a)/(b), powers a^(b), roots sqrt(a), blanks ____ and images [diagram]."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, list[str], dict]] = [("root", [], {})]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in ("img", "br"):
            self.stack[-1][1].append(" [diagram] " if tag == "img" else "\n")
            return
        self.stack.append((tag, [], dict(attrs)))

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if not any(t == tag for t, _, _ in self.stack[1:]):
            return
        while len(self.stack) > 1:
            t, parts, attrs = self.stack.pop()
            self.stack[-1][1].append(self._render(t, parts, attrs))
            if t == tag:
                break

    def handle_data(self, data: str) -> None:
        self.stack[-1][1].append(data)

    @staticmethod
    def _render(tag: str, parts: list[str], attrs: dict) -> str:
        kids = [p.strip() for p in parts if p.strip()]
        if tag == "mfrac" and len(kids) == 2:
            return f"({kids[0]})/({kids[1]})"
        if tag == "msup" and len(kids) == 2:
            return f"{kids[0]}^({kids[1]})"
        if tag == "msub" and len(kids) == 2:
            return f"{kids[0]}_{kids[1]}"
        if tag == "msqrt":
            return f"sqrt({''.join(kids)})"
        if tag == "mroot" and len(kids) == 2:
            return f"root{kids[1]}({kids[0]})"
        if tag == "span" and "answer-blank" in (attrs.get("class") or ""):
            return " ____ "
        if tag in ("td", "th"):
            return "".join(parts).strip() + " | "
        if tag in ("p", "div", "li", "tr", "h3", "h4", "table", "ul", "ol"):
            return "".join(parts).strip() + "\n"
        if tag == "math":
            return " " + "".join(kids) + " "
        return "".join(parts)

    def text(self) -> str:
        while len(self.stack) > 1:
            t, parts, attrs = self.stack.pop()
            self.stack[-1][1].append(self._render(t, parts, attrs))
        out = "".join(self.stack[0][1]).replace("\xa0", " ")
        out = re.sub(r"[ \t]+", " ", out)
        return re.sub(r"\n\s*\n+", "\n", out).strip()


def math_text(safe_html: str) -> str:
    p = _MathText()
    p.feed(safe_html or "")
    p.close()
    return p.text()
