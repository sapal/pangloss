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

if __name__ == "__main__":
    try:
        test_generated_html_parses()
        print("HTML validity test passed!")
    except AssertionError as e:
        print(f"HTML validity test failed: {e}")
        exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        exit(1)
