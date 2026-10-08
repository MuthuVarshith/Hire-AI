"""Section-aware chunking of resumes and job descriptions.

A document is split into sections at recognized headings (a fixed vocabulary per
document type, so names and company lines are never mistaken for headings), and
each section is packed into chunks of whole paragraphs up to a size limit.

Every chunk keeps exact character offsets into the source text:
`source[chunk.start:chunk.end] == chunk.text`. Retrieval answers cite chunks, and
offsets let a citation point at the precise passage of the original resume.
"""
import re
from collections.abc import Callable
from dataclasses import dataclass

# First-pass size limit. all-MiniLM-L6-v2 truncates input at 256 word-piece tokens; 800
# characters of prose is well under that, but dense technical lists are not (800 characters of
# tool names measured 310 tokens). Callers that embed pass `fits` with the model's real token
# count, which guarantees each chunk is embedded whole.
DEFAULT_MAX_CHARS = 800

RESUME_SECTIONS: dict[str, tuple[str, ...]] = {
    "summary": ("summary", "professional summary", "career summary", "profile", "professional profile",
                "objective", "career objective", "about me", "about", "research interests"),
    "experience": ("experience", "work experience", "professional experience", "relevant experience",
                   "employment", "employment history", "work history", "career history",
                   "internship", "internships", "internship experience"),
    "projects": ("projects", "personal projects", "key projects", "selected projects", "academic projects",
                 "side projects", "project experience"),
    "skills": ("skills", "technical skills", "core skills", "key skills", "skills and tools", "technologies",
               "tech stack", "tools", "competencies", "core competencies", "technical proficiencies"),
    "education": ("education", "academic background", "education and training", "academics"),
    "certifications": ("certifications", "certificates", "licenses and certifications", "courses"),
    "other": ("awards", "achievements", "publications", "languages", "interests", "volunteer experience",
              "volunteering", "references", "additional information"),
}

JD_SECTIONS: dict[str, tuple[str, ...]] = {
    "about": ("about us", "about the company", "who we are", "company overview"),
    "summary": ("role summary", "summary", "job summary", "position summary", "overview", "the role",
                "about the role", "role overview"),
    "responsibilities": ("responsibilities", "key responsibilities", "what you'll do", "what you will do",
                         "duties", "your responsibilities"),
    "requirements": ("requirements", "qualifications", "required qualifications", "minimum qualifications",
                     "what we're looking for", "what you'll need", "must have", "must haves"),
    "preferred": ("nice to have", "nice to haves", "preferred qualifications", "preferred", "bonus",
                  "bonus points", "good to have", "plus"),
    "benefits": ("benefits", "benefits and perks", "perks", "what we offer", "compensation"),
}

SECTION_LABELS: dict[str, str] = {
    "header": "Contact", "summary": "Summary", "experience": "Experience", "projects": "Projects",
    "skills": "Skills", "education": "Education", "certifications": "Certifications", "other": "Other",
    "about": "About the company", "responsibilities": "Responsibilities", "requirements": "Requirements",
    "preferred": "Nice to have", "benefits": "Benefits",
}

_DECORATION = re.compile(r"^[\s#=*_\-~>|]+|[\s#=*_\-~|:]+$")
_INLINE = re.compile(r"^(?P<head>[^:\n]{2,40}?)\s*[:–—-]\s+(?P<rest>\S.*)$")
_LINE = re.compile(r"[^\n]*(?:\n|$)")
_SEPARATOR = re.compile(r"^\s*[=\-*_~#]{3,}\s*$")
_PARENTHETICAL = re.compile(r"\s*\([^)]*\)$")


@dataclass(frozen=True)
class Chunk:
    section: str           # canonical section, e.g. "experience"
    index: int             # position of the chunk within the document
    text: str              # exactly source[start:end]
    start: int
    end: int
    heading: str | None    # the heading as written in the document, if any

    @property
    def embedding_text(self) -> str:
        """Text sent to the embedding model; the section label disambiguates short chunks like 'Python, SQL'."""
        return f"{SECTION_LABELS.get(self.section, self.section.title())}: {self.text}"


# Optional check supplied by the embedding side, e.g. "embedding_text is within the model's token limit".
# Chunks that fail it are split further at line, sentence or word boundaries.
Fits = Callable[[Chunk], bool]


def _normalize(heading: str) -> str:
    text = _DECORATION.sub("", heading).replace("&", "and").lower()
    return re.sub(r"\s+", " ", text).strip()


def _lookup(vocabulary: dict[str, tuple[str, ...]]) -> dict[str, str]:
    return {_normalize(alias): section for section, aliases in vocabulary.items() for alias in aliases}


def _classify(heading: str, lookup: dict[str, str]) -> str | None:
    """Section for a candidate heading line, also trying it without a trailing "(...)" qualifier."""
    normalized = _normalize(heading)
    return lookup.get(normalized) or lookup.get(_PARENTHETICAL.sub("", normalized).strip())


def _find_sections(source: str, vocabulary: dict[str, tuple[str, ...]], preamble: str
                   ) -> list[tuple[str, str | None, int, int]]:
    """(section, heading as written, content start, content end) for each section, in order."""
    lookup = _lookup(vocabulary)
    marks: list[tuple[str, str | None, int, int]] = []  # section, heading, heading start, content start
    for match in _LINE.finditer(source):
        line = match.group(0)
        if not line:
            break
        stripped = line.strip()
        if not stripped:
            continue
        line_start = match.start() + (len(line) - len(line.lstrip()))
        section = _classify(stripped, lookup)
        if section:
            marks.append((section, stripped, line_start, match.end()))
            continue
        inline = _INLINE.match(stripped)
        if inline and (section := _classify(inline.group("head"), lookup)):
            content_start = line_start + inline.start("rest")
            marks.append((section, inline.group("head").strip(), line_start, content_start))

    sections: list[tuple[str, str | None, int, int]] = []
    first_heading = marks[0][2] if marks else len(source)
    if first_heading > 0:
        sections.append((preamble, None, 0, first_heading))
    for i, (section, heading, _heading_start, content_start) in enumerate(marks):
        end = marks[i + 1][2] if i + 1 < len(marks) else len(source)
        sections.append((section, heading, content_start, end))
    return sections


def _paragraphs(source: str, start: int, end: int) -> list[tuple[int, int]]:
    """Spans of paragraphs inside [start, end): runs of lines broken by blank or separator lines.

    Separator lines (=====, -----) are layout, not content, so they never end up in a chunk.
    """
    spans: list[tuple[int, int]] = []
    block_start: int | None = None
    block_end = start
    position = start
    for line in source[start:end].splitlines(keepends=True):
        line_start = position
        position += len(line)
        if not line.strip() or _SEPARATOR.match(line):
            if block_start is not None:
                spans.append((block_start, block_end))
                block_start = None
            continue
        if block_start is None:
            block_start = line_start + len(line) - len(line.lstrip())
        block_end = line_start + len(line.rstrip())
    if block_start is not None:
        spans.append((block_start, block_end))
    return spans


def _split_long(source: str, start: int, end: int, max_chars: int) -> list[tuple[int, int]]:
    """Split one oversized paragraph at line, then sentence, then word boundaries."""
    if end - start <= max_chars:
        return [(start, end)]
    pieces: list[tuple[int, int]] = []
    cursor = start
    while end - cursor > max_chars:
        window = source[cursor:cursor + max_chars]
        cut = max(window.rfind("\n"), window.rfind(". "), window.rfind("; "))
        if cut <= 0:
            cut = window.rfind(" ")
        if cut <= 0:
            cut = max_chars - 1  # no boundary at all: hard split
        piece_end = cursor + cut + 1
        piece = source[cursor:piece_end]
        pieces.append((cursor, cursor + len(piece.rstrip())))
        cursor = piece_end
        while cursor < end and source[cursor].isspace():
            cursor += 1
    if cursor < end:
        pieces.append((cursor, end))
    return pieces


def _chunk(source: str, vocabulary: dict[str, tuple[str, ...]], preamble: str, max_chars: int,
           fits: Fits | None) -> list[Chunk]:
    if max_chars < 50:
        raise ValueError("max_chars must be at least 50")
    spans: list[tuple[str, str | None, int, int]] = []
    for section, heading, start, end in _find_sections(source, vocabulary, preamble):
        pieces = [piece for p_start, p_end in _paragraphs(source, start, end)
                  for piece in _split_long(source, p_start, p_end, max_chars)]
        group: list[tuple[int, int]] = []
        for span in pieces + [(-1, -1)]:  # sentinel flushes the last group
            # A chunk is one contiguous slice of the source, so only join paragraphs whose gap is
            # whitespace; a separator line in between would otherwise end up inside the chunk.
            joinable = span[0] >= 0 and bool(group) and not source[group[-1][1]:span[0]].strip()
            if group and (not joinable or span[1] - group[0][0] > max_chars):
                spans.append((section, heading, group[0][0], group[-1][1]))
                group = []
            if span[0] >= 0:
                group.append(span)

    chunks: list[Chunk] = []
    for section, heading, start, end in spans:
        for s_start, s_end in _fit(source, start, end, max_chars, section, heading, fits):
            chunks.append(Chunk(section, len(chunks), source[s_start:s_end], s_start, s_end, heading))
    return chunks


def _fit(source: str, start: int, end: int, max_chars: int, section: str, heading: str | None,
         fits: Fits | None) -> list[tuple[int, int]]:
    """Split a span until every piece passes `fits` (e.g. the embedding model's token limit)."""
    if fits is None or fits(Chunk(section, 0, source[start:end], start, end, heading)):
        return [(start, end)]
    limit = min(max_chars, end - start) // 2
    if limit < 20:
        raise ValueError(f"cannot split text at {start}:{end} small enough to fit")
    return [piece for p_start, p_end in _split_long(source, start, end, limit)
            for piece in _fit(source, p_start, p_end, limit, section, heading, fits)]


def chunk_resume(text: str, max_chars: int = DEFAULT_MAX_CHARS, fits: Fits | None = None) -> list[Chunk]:
    """Chunks of a resume; text before the first heading (name, contact details) is the 'header' section.

    A resume with no recognizable headings yields paragraph chunks in the 'header' section, which
    callers should treat as uncategorized.
    """
    return _chunk(text or "", RESUME_SECTIONS, "header", max_chars, fits)


def chunk_job_description(text: str, max_chars: int = DEFAULT_MAX_CHARS,
                          fits: Fits | None = None) -> list[Chunk]:
    """Chunks of a job description; text before the first heading is the 'summary' section."""
    return _chunk(text or "", JD_SECTIONS, "summary", max_chars, fits)
