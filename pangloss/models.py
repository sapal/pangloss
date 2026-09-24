import re
from typing import TypedDict, List, Optional

class CopyrightRestrictionError(Exception):
    """Raised when the model refuses to process text due to copyright or recitation restrictions."""
    def __init__(self, message: str = "Copyright restriction triggered", raw_text: str = ""):
        super().__init__(message)
        self.raw_text = raw_text

def is_copyright_error_text(text: str) -> bool:
    t = text.lower()
    if "copyright" in t or "recitation" in t:
        return True
    if "cannot translate" in t or "unable to translate" in t:
        return True
    if re.search(r'(cannot|unable to)\s+(provide|offer|generate|produce|give)\s+([^.\n]*?)\s*translation', t):
        return True
    if re.search(r'can\s+(only\s+)?(provide|offer)\s+([^.\n]*?)\s*summary', t):
        return True
    return False

def is_copyright_error(exc: Exception) -> bool:
    if isinstance(exc, CopyrightRestrictionError):
        return True
    raw_text = getattr(exc, "raw_text", "")
    if raw_text and is_copyright_error_text(raw_text):
        return True
    return is_copyright_error_text(str(exc))

class SpeakerTurn(TypedDict):
    speaker: str
    text: str

class ProcessedParagraph(TypedDict, total=False):
    id: int
    originalText: str
    translatedText: str
    turns: List[SpeakerTurn]
    chunks: Optional[List[dict]]
    skip_audio: Optional[bool]
    untranslated: Optional[bool]

class DifficultWord(TypedDict):
    word: str
    explanation: str
    anchors: List[str]

class Character(TypedDict):
    name: str
    description: str
    voice: str
    voiceProfile: str

class ProcessedChunkRange(TypedDict):
    start: int
    end: int

class StoryMetadata(TypedDict):
    title: str
    characters: List[Character]
    difficultWords: List[DifficultWord]
    paragraphs: List[ProcessedParagraph]
    processed_chunks: List[ProcessedChunkRange]
