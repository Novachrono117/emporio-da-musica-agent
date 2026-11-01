"""The store policy manual (data/políticas_da_loja.pdf), split into its numbered sections.

pypdf's layout mode keeps each heading at the start of its own line ("3.1 Regras de Parcelamento"), so sections are
found line by line. The repeated page header and the "Página N" footers are dropped, which joins the sections that
cross a page break. See docs/DATA_NOTES.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

from emporio.data.loader import DATA_DIR, DataError

POLICY_PDF = DATA_DIR / "políticas_da_loja.pdf"
PAGE_HEADER = "Empório da Música Manual de Políticas e Procedimentos"
COVER_ID = "0"
_FOOTER = re.compile(r"^Página \d+$")
_HEADING = re.compile(r"^(?:(?P<chapter>\d{1,2})\.|(?P<sub>\d{1,2}\.\d{1,2})) (?P<title>[A-ZÀ-Ú].*)$")


@dataclass(frozen=True)
class PolicySection:
    id: str  # "0" for the cover, "3" for a chapter, "3.1" for a sub-section
    title: str
    text: str

    @property
    def chapter(self) -> str:
        return self.id.split(".")[0]


@dataclass(frozen=True)
class PolicyManual:
    sections: tuple[PolicySection, ...]

    def section(self, section_id: str) -> PolicySection | None:
        return next((s for s in self.sections if s.id == section_id), None)

    def chapter(self, number: str) -> tuple[PolicySection, ...]:
        """A chapter with its sub-sections, in order ("4" gives 4, 4.1, 4.2, ...)."""
        return tuple(s for s in self.sections if s.chapter == number)


def load_policy_manual(path: Path = POLICY_PDF) -> PolicyManual:
    lines = []
    for page in PdfReader(path).pages:
        lines += page.extract_text(extraction_mode="layout").splitlines()
    return PolicyManual(_split_sections(lines))


def _split_sections(lines: list[str]) -> tuple[PolicySection, ...]:
    sections: list[tuple[str, str, list[str]]] = [(COVER_ID, "Capa", [])]
    for raw in lines:
        line = raw.strip()
        if line == PAGE_HEADER or _FOOTER.match(line):
            continue
        # Headings start at column 0; indented lines (numbered steps, table rows) never open a section.
        match = _HEADING.match(raw) if raw == raw.lstrip() else None
        if match and _is_next(sections[-1][0], match["chapter"] or match["sub"]):
            sections.append((match["chapter"] or match["sub"], match["title"].strip(), []))
        else:
            sections[-1][2].append(line)
    if len(sections) == 1:
        raise DataError("no numbered sections found in the policy manual")
    return tuple(PolicySection(id_, title, _clean(body)) for id_, title, body in sections)


def _is_next(previous: str, candidate: str) -> bool:
    """Accept a heading only when it follows the previous one (3 -> 3.1 -> 3.2 -> 4), so stray matches are ignored."""
    chapter, _, sub = previous.partition(".")
    next_chapter = str(int(chapter) + 1)
    next_sub = f"{chapter}.{int(sub or 0) + 1}"
    return candidate in (next_chapter, next_sub)


def _clean(lines: list[str]) -> str:
    out: list[str] = []
    for line in lines:
        line = re.sub(r"^(•|\d+\.)\s+", r"\1 ", line)  # "•    text" -> "• text"
        line = re.sub(r"\s{2,}", " | ", line)  # table columns
        if line or (out and out[-1]):
            out.append(line)
    return "\n".join(out).strip()
