from typing import TypedDict, List, Optional

class SpeakerTurn(TypedDict):
    speaker: str
    text: str

class ProcessedParagraph(TypedDict):
    id: int
    originalText: str
    translatedText: str
    turns: List[SpeakerTurn]

class DifficultWord(TypedDict):
    word: str
    explanation: str
    anchors: List[str]

class Character(TypedDict):
    name: str
    description: str
    voice: str
    voiceProfile: str

class StoryMetadata(TypedDict):
    title: str
    characters: List[Character]
    difficultWords: List[DifficultWord]
    paragraphs: List[ProcessedParagraph]
