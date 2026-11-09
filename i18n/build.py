#!/usr/bin/env python3
"""Build translated copies of index.html.

index.html (English) is the single source of truth. Each language has one file,
i18n/<code>.json, holding the translated strings plus a few page-level settings.
Running this script writes <code>/index.html for every language file it finds and
refreshes the language links block inside index.html.

Usage:
    python3 i18n/build.py            build everything
    python3 i18n/build.py --check    report stale or missing strings, write nothing
    python3 i18n/build.py --list     print every translatable English string

Safety checks (the build stops if any fail):
    - every link target, tag, number, phone number, email, and web address in a
      translated string must match the English string exactly
    - Arabic-Indic or Persian digits are rejected so phone numbers stay readable
Strings that are missing from a language file stay in English and are reported.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "index.html"
I18N = ROOT / "i18n"

LETTER = re.compile(r"[^\W\d_]")
URLISH = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-]*(?:\.[A-Za-z0-9\-]+)*\.(?:org|gov|edu|net|com|us)(?:/[\w\-./?=&%#]*[\w\-/?=&%#])?")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
FOREIGN_DIGITS = re.compile("[٠-٩۰-۹]")
EN_HERO_LINE = "Automatic translation can contain errors. For an interpreter, call 211 and ask for your language."
# Languages served by the Google widget until a reviewed static page exists for them
# (code, native name, English name)
GT_LANGS = [
    ("ps", "پښتو", "Pashto"),
    ("es", "Español", "Spanish"),
    ("ar", "العربية", "Arabic"),
    ("fr", "Français", "French"),
    ("uk", "Українська", "Ukrainian"),
    ("so", "Soomaali", "Somali"),
    ("ti", "ትግርኛ", "Tigrinya"),
]
EN_NAME = "English"

SKIP_TAGS = {"script", "style", "head", "title"}


def norm(s: str) -> str:
    return " ".join(s.split())


def inner_html(el: Tag) -> str:
    return norm(el.decode_contents())


def is_block(el: Tag) -> bool:
    return any(
        isinstance(c, NavigableString) and not isinstance(c, Comment) and c.strip()
        for c in el.children
    )


def find_blocks(soup):
    """Return [(element, key)] for every translatable block, top-down."""
    out = []

    def walk(parent):
        for child in parent.children:
            if not isinstance(child, Tag) or child.name in SKIP_TAGS:
                continue
            if (child.get("id") == "theme-toggle" or "hero-langs" in (child.get("class") or [])
                    or child.get("data-i18n") == "skip"):
                continue
            if is_block(child):
                text = norm(child.get_text())
                # skip numbers, bare web addresses and all-caps acronyms: nothing to translate
                if (LETTER.search(text) and not URLISH.fullmatch(text)
                        and not re.fullmatch(r"[A-Z0-9 /&]+", text)):
                    out.append((child, inner_html(child)))
            else:
                walk(child)

    walk(soup.body)
    return out


def fingerprint(html: str):
    frag = BeautifulSoup(html, "html.parser")
    text = frag.get_text()
    return {
        "tags": Counter(t.name for t in frag.find_all(True)),
        "hrefs": Counter(t.get("href") for t in frag.find_all("a")),
        "digits": Counter(re.findall(r"\d+", text)),
        "urls": Counter(URLISH.findall(text)),
        "emails": Counter(EMAIL.findall(text)),
    }


def validate(src: str, dst: str):
    problems = []
    a, b = fingerprint(src), fingerprint(dst)
    if a["tags"] != b["tags"]:
        problems.append(f"tags differ: {dict(a['tags'])} vs {dict(b['tags'])}")
    if a["hrefs"] != b["hrefs"]:
        problems.append(f"link targets differ: {dict(a['hrefs'])} vs {dict(b['hrefs'])}")
    if a["digits"] != b["digits"]:
        problems.append(f"numbers differ: {dict(a['digits'])} vs {dict(b['digits'])}")
    if a["urls"] != b["urls"]:
        problems.append(f"web addresses differ: {dict(a['urls'])} vs {dict(b['urls'])}")
    if a["emails"] != b["emails"]:
        problems.append(f"emails differ: {dict(a['emails'])} vs {dict(b['emails'])}")
    if FOREIGN_DIGITS.search(dst):
        problems.append("contains non-Western digits")
    return problems


LTR_RUN = re.compile(r"[A-Za-z0-9(][A-Za-z0-9&'.,:/@+#()\-\u2013|% ]*[A-Za-z0-9)]|[A-Za-z0-9]")


PHONE_RUN = re.compile(r"(?:1-)?(?:\(\d{3}\)|\d{3})[ -]\d{3}-\d{4}|1-800-\d{3}-\d{4}")


def isolate_ltr(soup):
    """In right-to-left pages, wrap every Latin or numeric run in <bdi dir="ltr">.

    Without this the browser reorders addresses and phone numbers inside Arabic-script
    text (for example "(443) 478-8122" can display as "(443) 8122-478").
    """
    for node in list(soup.body.descendants):
        if not isinstance(node, NavigableString) or isinstance(node, Comment):
            continue
        if node.parent.name in ("script", "style") or node.parent.name == "bdi":
            continue
        text = str(node)
        if not LTR_RUN.search(text):
            continue
        pieces, pos = [], 0
        for m in LTR_RUN.finditer(text):
            if m.start() > pos:
                pieces.append(NavigableString(text[pos:m.start()]))
            bdi = soup.new_tag("bdi", dir="ltr")
            bdi.string = m.group(0)
            if PHONE_RUN.fullmatch(m.group(0)):
                bdi["style"] = "white-space:nowrap"  # never split a phone number across lines
            pieces.append(bdi)
            pos = m.end()
        if pos < len(text):
            pieces.append(NavigableString(text[pos:]))
        for piece in pieces:
            node.insert_before(piece)
        node.extract()


def load_lang(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["meta"], data["strings"]


def lang_files():
    return sorted(p for p in I18N.glob("*.json"))


def gt_link(code: str, native: str, rel_prefix: str, in_place: bool) -> str:
    """Link to a language served by the Google widget on the English page.

    href="?lang=xx" works everywhere (shareable, and from translated pages);
    data-gtlang lets the English page switch in place without a reload.
    """
    extra = f' data-gtlang="{code}"' if in_place else ""
    return f'<a href="{rel_prefix}?lang={code}"{extra} lang="{code}" class="notranslate">{native}</a>'


def lang_bar(current: str, langs: dict, rel_prefix: str, sentence: str) -> str:
    """Language links. rel_prefix is '' on the English page and '../' on translated ones."""
    parts = []
    if current == "en":
        parts.append('<a href="./" data-gtlang="en" hreflang="en" lang="en" class="notranslate" aria-current="true">English</a>')
    else:
        parts.append(f'<a href="{rel_prefix or "./"}" hreflang="en" lang="en">{EN_NAME}</a>')
    for code, meta in langs.items():
        if code == current:
            parts.append(f'<span aria-current="true" lang="{meta["lang"]}">{meta["name"]}</span>')
        else:
            href = f"{rel_prefix}{code}/"
            parts.append(f'<a href="{href}" hreflang="{meta["lang"]}" lang="{meta["lang"]}" class="notranslate">{meta["name"]}</a>')
    for code, native, _english in GT_LANGS:
        if code not in langs:
            parts.append(gt_link(code, native, rel_prefix, in_place=(current == "en")))
    links = " &middot; ".join(parts)
    return (f'<p class="hero-langs"><span class="lang-links" translate="no">{links}</span>'
            f'<br>{sentence}</p>')


def lang_grid(langs: dict) -> str:
    """Card grid for the Languages section on the English page."""
    cards = [
        '<li><a class="lang-card" href="./" data-gtlang="en" hreflang="en" lang="en" aria-current="true">'
        '<span class="lang-native">English</span><span class="lang-english">English</span>'
        '<span class="lang-note">Original page</span></a></li>'
    ]
    for code, meta in langs.items():
        cards.append(
            f'<li><a class="lang-card" href="{code}/" hreflang="{meta["lang"]}" lang="{meta["lang"]}">'
            f'<span class="lang-native">{meta["name"]}</span><span class="lang-english">{meta.get("english_name", meta["name"])}</span>'
            f'<span class="lang-note">{meta.get("card_note", "Translated page")}</span></a></li>'
        )
    for code, native, english in GT_LANGS:
        if code in langs:
            continue
        cards.append(
            f'<li><a class="lang-card" href="?lang={code}" data-gtlang="{code}" lang="{code}">'
            f'<span class="lang-native">{native}</span><span class="lang-english">{english}</span>'
            f'<span class="lang-note">Automatic translation</span></a></li>'
        )
    body = "\n          ".join(cards)
    return f'<ul class="lang-grid" translate="no">\n          {body}\n        </ul>'


def alternates(langs: dict, rel_prefix: str) -> str:
    lines = [f'  <link rel="alternate" hreflang="en" href="{rel_prefix or "./"}">']
    for code, meta in langs.items():
        lines.append(f'  <link rel="alternate" hreflang="{meta["lang"]}" href="{rel_prefix}{code}/">')
    return "\n".join(lines)


def patch_markers(text: str, name: str, body: str) -> str:
    pat = re.compile(rf"(<!-- i18n:{name}:start -->).*?(<!-- i18n:{name}:end -->)", re.S)
    if not pat.search(text):
        raise SystemExit(f"index.html is missing the i18n:{name} markers")
    return pat.sub(lambda m: f"{m.group(1)}\n{body}\n    {m.group(2)}", text)


def build(check_only: bool) -> int:
    source_text = SOURCE.read_text(encoding="utf-8")
    src_soup = BeautifulSoup(source_text, "html.parser")
    keys = [k for _, k in find_blocks(src_soup)]
    unique = list(dict.fromkeys(keys))

    langs = {}
    data = {}
    for p in lang_files():
        meta, strings = load_lang(p)
        langs[p.stem] = meta
        data[p.stem] = strings

    failed = False
    reports = {}
    for code, strings in data.items():
        missing = [k for k in unique if k not in strings]
        stale = [k for k in strings if k not in set(unique)]
        bad = []
        for k in unique:
            if k in strings:
                for prob in validate(k, strings[k]):
                    bad.append((k, prob))
        reports[code] = (missing, stale, bad)
        print(f"[{code}] {len(unique) - len(missing)}/{len(unique)} strings translated, "
              f"{len(missing)} missing, {len(stale)} stale, {len(bad)} failed checks")
        for k, prob in bad:
            print(f"    CHECK FAILED: {k[:80]!r}\n        {prob}")
            failed = True
        for k in missing[:15]:
            print(f"    missing: {k[:90]!r}")
        if len(missing) > 15:
            print(f"    ... and {len(missing) - 15} more missing")
        for k in stale[:10]:
            print(f"    stale (English changed or removed): {k[:90]!r}")

    if failed:
        print("\nBuild stopped: fix the failed checks above.")
        return 1
    if check_only:
        return 0

    for code, strings in data.items():
        meta = langs[code]
        soup = BeautifulSoup(source_text, "html.parser")
        for el, key in find_blocks(soup):
            if key in strings:
                frag = BeautifulSoup(strings[key], "html.parser")
                el.clear()
                for n in list(frag.contents):
                    el.append(n.extract())
        html = soup.html
        html["lang"] = meta["lang"]
        html["dir"] = meta["dir"]
        html["data-show-steps"] = meta["show_steps"]
        html["data-hide-steps"] = meta["hide_steps"]
        html["data-dark-label"] = meta["dark_mode"]
        html["data-light-label"] = meta["light_mode"]
        soup.title.string = meta["title"]
        theme = soup.find(id="theme-toggle")
        theme.string = meta["dark_mode"]
        for tag in soup.find_all("link", href="styles.css"):
            tag["href"] = "../styles.css"
        for tag in soup.find_all("script", src="script.js"):
            tag["src"] = "../script.js"
        if meta.get("font_url"):
            soup.head.append(BeautifulSoup(f'<link href="{meta["font_url"]}" rel="stylesheet">', "html.parser"))
        notice = BeautifulSoup(f'<p class="translation-notice" role="note">{meta["notice"]}</p>', "html.parser")
        soup.find("header", class_="site-header").insert_after(notice)
        for el in soup.find_all(attrs={"data-i18n": "skip"}):
            el.decompose()
        for el in soup.find_all(id="google_translate_element"):
            el.decompose()
        for el in soup.find_all("script", src="translate.js"):
            el.decompose()
        hero = soup.find("p", class_="hero-langs")
        hero.replace_with(BeautifulSoup(lang_bar(code, langs, "../", meta["hero_line"]), "html.parser"))
        if meta["dir"] == "rtl":
            isolate_ltr(soup)
        for old in soup.find_all("link", rel="alternate"):
            old.decompose()
        soup.head.append(BeautifulSoup(alternates(langs, "../"), "html.parser"))
        out_dir = ROOT / code
        out_dir.mkdir(exist_ok=True)
        (out_dir / "index.html").write_text(soup.decode(formatter="minimal") + "\n", encoding="utf-8")
        print(f"wrote {code}/index.html")

    patched = patch_markers(source_text, "alternates", alternates(langs, ""))
    patched = patch_markers(patched, "langs", "      " + lang_bar("en", langs, "", EN_HERO_LINE))
    patched = patch_markers(patched, "langgrid", "      " + lang_grid(langs))
    if patched != source_text:
        SOURCE.write_text(patched, encoding="utf-8")
        print("updated language links in index.html")
    return 0


def main():
    if "--list" in sys.argv:
        soup = BeautifulSoup(SOURCE.read_text(encoding="utf-8"), "html.parser")
        keys = list(dict.fromkeys(k for _, k in find_blocks(soup)))
        for i, k in enumerate(keys):
            print(f"{i}\t{k}")
        return 0
    return build("--check" in sys.argv)


if __name__ == "__main__":
    sys.exit(main())
