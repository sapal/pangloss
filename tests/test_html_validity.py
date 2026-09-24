import json
from html.parser import HTMLParser
from pangloss.export import generate_html
from pangloss.models import StoryMetadata

class SimpleHTMLValidator(HTMLParser):
    def __init__(self):
        super().__init__()
        self.errors = []

    def handle_error(self, message):
        self.errors.append(message)

def test_generated_html_parses():
    # Mock metadata
    metadata: StoryMetadata = {
        "title": "Test Story",
        "characters": [
            {"name": "Narrator", "description": "The storyteller", "voice": "Puck", "voiceProfile": "Clear and neutral"}
        ],
        "difficultWords": [
            {"word": "test", "explanation": "a trial or experiment", "anchors": ["test"]}
        ],
        "paragraphs": [
            {
                "id": 1,
                "originalText": "This is a test.",
                "translatedText": "Dies ist ein Test.",
                "turns": [{"speaker": "Narrator", "text": "Dies ist ein Test."}]
            }
        ]
    }
    
    audio_chunks = {1: b"fake_wav_data"}
    
    # Generate HTML
    html_content = generate_html(metadata, audio_chunks, "English", "German", "B1")
    
    # Validate HTML
    parser = SimpleHTMLValidator()
    try:
        parser.feed(html_content)
        assert len(parser.errors) == 0, f"HTML Parser found errors: {parser.errors}"
    except Exception as e:
        assert False, f"HTML Parsing failed with exception: {e}"

def test_inlined_fonts():
    metadata: StoryMetadata = {
        "title": "Test Story",
        "characters": [
            {"name": "Narrator", "description": "The storyteller", "voice": "Puck", "voiceProfile": "Clear and neutral"}
        ],
        "difficultWords": [
            {"word": "test", "explanation": "a trial or experiment", "anchors": ["test"]}
        ],
        "paragraphs": [
            {
                "id": 1,
                "originalText": "This is a test.",
                "translatedText": "Dies ist ein Test.",
                "turns": [{"speaker": "Narrator", "text": "Dies ist ein Test."}]
            }
        ]
    }
    audio_chunks = {1: b"fake_wav_data"}
    html_content = generate_html(metadata, audio_chunks, "English", "German", "B1")

    assert "fonts.googleapis.com" not in html_content, "Generated HTML contains Google Fonts link"
    assert "data:font/woff2;base64," in html_content, "Generated HTML missing inlined WOFF2 font data URL"

def test_inlined_tailwind():
    metadata: StoryMetadata = {
        "title": "Test Story",
        "characters": [
            {"name": "Narrator", "description": "The storyteller", "voice": "Puck", "voiceProfile": "Clear and neutral"}
        ],
        "difficultWords": [
            {"word": "test", "explanation": "a trial or experiment", "anchors": ["test"]}
        ],
        "paragraphs": [
            {
                "id": 1,
                "originalText": "This is a test.",
                "translatedText": "Dies ist ein Test.",
                "turns": [{"speaker": "Narrator", "text": "Dies ist ein Test."}]
            }
        ]
    }
    audio_chunks = {1: b"fake_wav_data"}
    html_content = generate_html(metadata, audio_chunks, "English", "German", "B1")

    assert "cdn.tailwindcss.com" not in html_content, "Generated HTML contains tailwind CDN script tag"

def test_chunk_navigation_controls_and_styles():
    metadata: StoryMetadata = {
        "title": "Test Story",
        "characters": [
            {"name": "Narrator", "description": "The storyteller", "voice": "Puck", "voiceProfile": "Clear and neutral"}
        ],
        "difficultWords": [
            {"word": "test", "explanation": "a trial or experiment", "anchors": ["test"]}
        ],
        "paragraphs": [
            {
                "id": 1,
                "originalText": "This is a test.",
                "translatedText": "Dies ist ein Test.",
                "turns": [{"speaker": "Narrator", "text": "Dies ist ein Test."}],
                "chunks": [
                    {
                        "chunk_index": 0,
                        "start_sec": 0.0,
                        "end_sec": 5.0,
                        "start_char": 0,
                        "end_char": 18,
                        "speakers": ["Narrator"]
                    }
                ]
            }
        ]
    }
    audio_chunks = {1: b"fake_wav_data"}
    html_content = generate_html(metadata, audio_chunks, "English", "German", "B1")

    assert 'id="prevChunkBtn"' in html_content
    assert 'id="nextChunkBtn"' in html_content
    assert '.chunk-target' in html_content
    assert '.chunk-target.active-chunk' in html_content
    assert 'seekToChunk' in html_content
    assert 'scrollToActiveChunk' in html_content
    assert 'prevChunk' in html_content
    assert 'nextChunk' in html_content

def test_no_nested_tooltips_with_multiple_anchors():
    metadata: StoryMetadata = {
        "title": "Test Story",
        "characters": [
            {"name": "Narrator", "description": "The storyteller", "voice": "Puck", "voiceProfile": "Clear and neutral"}
        ],
        "difficultWords": [
            {"word": "schweben", "explanation": "to hover", "anchors": ["schwebt", "schweben"]},
            {"word": "das Gefäß", "explanation": "vessel", "anchors": ["Keramikgefäß", "Gefäß"]},
            {"word": "das Wunder", "explanation": "wonder", "anchors": ["Wunder"]}
        ],
        "paragraphs": [
            {
                "id": 1,
                "originalText": "Test",
                "translatedText": "Sie schwebt über dem Keramikgefäß. Es ist ein Wunder.",
                "turns": [{"speaker": "Narrator", "text": "Test"}]
            }
        ]
    }
    audio_chunks = {1: b"fake_wav_data"}
    html_content = generate_html(metadata, audio_chunks, "English", "German", "B1")

    # Verify export.js applyWords contains placeholder-based protection
    assert "tagPlaceholders" in html_content
    assert "wordPlaceholders" in html_content
    assert "\\uE000WORD_" in html_content
    assert "\\uE000TAG_" in html_content


def test_untranslated_paragraph_html():
    metadata: StoryMetadata = {
        "title": "Test Story",
        "characters": [
            {"name": "Narrator", "description": "The storyteller", "voice": "Puck", "voiceProfile": "Clear and neutral"}
        ],
        "difficultWords": [],
        "paragraphs": [
            {
                "id": 1,
                "originalText": "*[This section was omitted]*\n\nCopyrighted quote",
                "translatedText": "*[This section was omitted]*\n\nCopyrighted quote",
                "turns": [],
                "skip_audio": True,
                "untranslated": True
            }
        ]
    }
    audio_chunks = {}
    html_content = generate_html(metadata, audio_chunks, "English", "German", "B1")
    parser = SimpleHTMLValidator()
    parser.feed(html_content)
    assert len(parser.errors) == 0
    assert "Untranslated" in html_content


if __name__ == "__main__":
    try:
        test_generated_html_parses()
        test_inlined_fonts()
        test_inlined_tailwind()
        test_chunk_navigation_controls_and_styles()
        test_no_nested_tooltips_with_multiple_anchors()
        print("HTML validity test passed!")
    except AssertionError as e:
        print(f"HTML validity test failed: {e}")
        exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        exit(1)
