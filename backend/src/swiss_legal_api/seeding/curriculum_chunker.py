"""Doctrinal-PDF chunker for the curriculum collection.

Split into two cleanly separable pieces so tests don't need a real PDF:

  * ``extract_pdf_pages(path)`` — pypdf wrapper that returns one string per
    page. Pure I/O; mock it (or skip its tests) when you don't have a PDF.
  * ``chunk_pages(...)`` — deterministic, sentence-aware splitter that
    consumes the page strings and returns ``CurriculumChunk`` records.
    Stable ``chunk_index`` per page so re-runs upsert in place.

The split matters: every change reviewer who touches the chunking heuristic
should be able to write a regression test against a literal Python list of
page strings instead of having to forge a PDF byte-stream.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# Conservative defaults for `intfloat/multilingual-e5-small`: ~512-token
# context window. We aim ~400 words ≈ 500 tokens with a ~60-word overlap so
# a sentence that lands on a chunk boundary still has surrounding context
# in at least one of the two chunks it straddles.
DEFAULT_MAX_WORDS = 400
DEFAULT_OVERLAP_WORDS = 60


@dataclass(frozen=True)
class CurriculumChunk:
    """One indexed chunk of a doctrinal source.

    Identity tuple is ``(source_doc, page, chunk_index)``; everything else
    is payload that travels with the vector. Both ``chapter`` and
    ``section`` are optional doctrinal locators — contributors who
    maintain page→chapter / page→section sidecars populate them. The
    ``section`` is the finer-grained unit (e.g. "§ 12 — Error of fact"
    inside a chapter on errors); when absent the UI falls back to chapter,
    and finally to "page N".
    """

    source_doc: str
    page: int
    chunk_index: int
    text: str
    language: str = "en"
    chapter: str | None = None
    section: str | None = None
    topic_tags: tuple[str, ...] = field(default_factory=tuple)


def extract_pdf_pages(path: Path) -> list[str]:
    """Return one extracted-text string per page of ``path``.

    Imports pypdf lazily because the chunker module is imported on every
    backend startup (config-time chain) and pulling pypdf into that path
    would slow down cold starts. Tests that exercise the splitter only
    never trigger this import.
    """
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages: list[str] = []
    for p in reader.pages:
        try:
            text = p.extract_text() or ""
        except Exception:
            # pypdf raises on malformed content streams; treat the page as
            # empty rather than aborting the whole ingest of a 200-page PDF
            # because of one corrupted page.
            text = ""
        pages.append(text)
    return pages


# Sentence boundary heuristic: split on ., !, ? followed by whitespace +
# capital letter / digit / EOL. Deliberately conservative so abbreviations
# like "Art." or "lit. a" don't trigger false splits. The downstream chunk
# packer always preserves whole sentences, so a missed split just produces
# a slightly longer chunk, not a corrupted citation.
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÄÖÜ0-9])")
_PARAGRAPH_RE = re.compile(r"\n{2,}")
_WHITESPACE_RE = re.compile(r"\s+")


def _split_into_sentences(text: str) -> list[str]:
    """Yield sentence-ish fragments preserving order. Empty fragments are
    skipped. Whitespace inside a sentence is collapsed to single spaces so
    PDF extraction artefacts (random newlines mid-sentence) don't bloat
    the embedding text or confuse the verifier prompt."""
    parts: list[str] = []
    for paragraph in _PARAGRAPH_RE.split(text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        for sentence in _SENTENCE_RE.split(paragraph):
            collapsed = _WHITESPACE_RE.sub(" ", sentence).strip()
            if collapsed:
                parts.append(collapsed)
    return parts


def _word_count(s: str) -> int:
    return len(s.split())


def chunk_pages(
    source_doc: str,
    pages: list[str],
    *,
    language: str = "en",
    topic_tags: tuple[str, ...] = (),
    chapter_index: dict[int, str] | None = None,
    section_index: dict[int, str] | None = None,
    max_words: int = DEFAULT_MAX_WORDS,
    overlap_words: int = DEFAULT_OVERLAP_WORDS,
) -> list[CurriculumChunk]:
    """Split a list of page-strings into deterministic curriculum chunks.

    Determinism contract: same inputs → byte-identical chunks (same text,
    same chunk_index sequence) every time. This is what the UUID5 stable
    ID in the seeder relies on for idempotent upserts.

    Algorithm: per page, split on sentence boundaries, then greedily pack
    sentences into chunks of up to ``max_words``. When a chunk would exceed
    ``max_words``, flush it and start the next chunk with the trailing
    ``overlap_words``-worth of sentences so cross-boundary context is
    preserved. ``chunk_index`` resets per page so a single page's chunks are
    a contiguous 0..N range.
    """
    if max_words <= 0:
        raise ValueError("max_words must be positive")
    if overlap_words < 0 or overlap_words >= max_words:
        raise ValueError("overlap_words must be in [0, max_words)")

    chunks: list[CurriculumChunk] = []
    chapter_index = chapter_index or {}
    section_index = section_index or {}

    for page_offset, raw_page in enumerate(pages):
        # 1-indexed page number — matches what users see in a PDF reader.
        page_number = page_offset + 1
        sentences = _split_into_sentences(raw_page)
        if not sentences:
            continue

        chapter = chapter_index.get(page_number)
        section = section_index.get(page_number)
        page_state = _PageChunkState(
            source_doc=source_doc,
            page_number=page_number,
            language=language,
            chapter=chapter,
            section=section,
            topic_tags=tuple(topic_tags),
            overlap_words=overlap_words,
            sink=chunks,
        )

        for sentence in sentences:
            sw = _word_count(sentence)
            # If a single sentence is bigger than the chunk window, emit it
            # as its own chunk (truncating would lose meaning) and reset.
            if sw >= max_words:
                page_state.flush()
                page_state.emit_singleton(sentence)
                continue
            if page_state.buffer_word_count + sw > max_words:
                page_state.flush()
            page_state.append(sentence, sw)

        # Flush whatever is left after the page; the next page starts with
        # a fresh state object so a previous page's tail can't leak into
        # the next page (page boundaries are meaningful for citations).
        page_state.flush()

    return chunks


@dataclass
class _PageChunkState:
    """Mutable per-page state for the chunk packer.

    Lifted out of ``chunk_pages`` so the inner emit loop is a method on a
    proper object instead of a closure that captures loop variables. The
    closure form tripped ruff B023 (loop-variable capture) and made the
    flush-vs-emit-singleton paths harder to follow."""

    source_doc: str
    page_number: int
    language: str
    chapter: str | None
    section: str | None
    topic_tags: tuple[str, ...]
    overlap_words: int
    sink: list[CurriculumChunk]
    chunk_index: int = 0
    buffer: list[str] = field(default_factory=list)
    buffer_word_count: int = 0

    def _make(self, text: str) -> CurriculumChunk:
        return CurriculumChunk(
            source_doc=self.source_doc,
            page=self.page_number,
            chunk_index=self.chunk_index,
            text=text,
            language=self.language,
            chapter=self.chapter,
            section=self.section,
            topic_tags=self.topic_tags,
        )

    def append(self, sentence: str, words: int) -> None:
        self.buffer.append(sentence)
        self.buffer_word_count += words

    def emit_singleton(self, sentence: str) -> None:
        """Flush a single oversized sentence as its own chunk and reset."""
        self.sink.append(self._make(sentence))
        self.chunk_index += 1
        self.buffer = []
        self.buffer_word_count = 0

    def flush(self) -> None:
        if not self.buffer:
            return
        text = " ".join(self.buffer).strip()
        if text:
            self.sink.append(self._make(text))
            self.chunk_index += 1
        # Compute the overlap suffix from the just-flushed buffer so the
        # next chunk picks up where this one ended (in whole-sentence
        # units, never mid-sentence).
        suffix: list[str] = []
        suffix_words = 0
        for s in reversed(self.buffer):
            w = _word_count(s)
            if suffix_words + w > self.overlap_words and suffix:
                break
            suffix.append(s)
            suffix_words += w
        self.buffer = list(reversed(suffix))
        self.buffer_word_count = suffix_words
