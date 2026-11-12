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
    assert "Omitted • Copyright Restriction" in html_content


def test_unicode_word_boundaries_and_tooltip_escaping():
    import subprocess
    from pathlib import Path

    export_js = Path(__file__).parent.parent / "pangloss" / "templates" / "export.js"
    js_content = export_js.read_text(encoding="utf-8")

    # Extract escapeHtml (if present) and applyWords from export.js or evaluate inside a mocked context
    node_script = """
    const fs = require('fs');
    const vm = require('vm');
    let code = fs.readFileSync(process.argv[1], 'utf8');
    code = code
        .replace('__METADATA_JSON__', JSON.stringify({title: 'T', paragraphs: [], characters: [], difficultWords: []}))
        .replace('__AUDIO_DATA_JSON__', '{}')
        .replace('__PLAY_SVG_JSON__', '""')
        .replace('__PAUSE_SVG_JSON__', '""')
        .replace(/__[A-Z][A-Z0-9_]*__/g, '""');

    const mockEl = () => ({
        innerHTML: '', textContent: '', style: {}, dataset: {},
        classList: { add(){}, remove(){}, toggle(){}, contains(){ return false; } },
        addEventListener(){}, appendChild(){}, querySelectorAll(){ return []; },
        closest(){ return null; }
    });
    const sandbox = {
        document: {
            getElementById: () => mockEl(),
            querySelectorAll: () => [],
            addEventListener: () => {},
            documentElement: mockEl()
        },
        window: {
            addEventListener: () => {},
            location: { hash: '' },
            matchMedia: () => ({ matches: false })
        },
        IntersectionObserver: function() { return { observe(){} }; },
        console
    };
    vm.createContext(sandbox);
    vm.runInContext(code, sandbox);

    const words = [
        { word: 'über', explanation: 'above <script>alert(1)</script> & "more"', anchors: ['über'] },
        { word: 'das Gefäß', explanation: 'vessel', anchors: ['Gefäß'] },
        { word: 'der Ärger', explanation: 'trouble', anchors: ['Ärger'] },
        { word: 'der Plan', explanation: 'plan', anchors: ['Plan'] }
    ];
    const input = 'Er sprach über das Gefäß, Ärger und seine Pläne.';
    const out = sandbox.applyWords(input, words);
    console.log(JSON.stringify({ out }));
    """
    res = subprocess.run(
        ["node", "-e", node_script, str(export_js)],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"Node failed: {res.stderr}"
    out = json.loads(res.stdout.strip())["out"]
    # Words starting/ending with umlauts/eszett must be matched and wrapped
    assert '<span class="word" onclick="toggleTooltip(event, this)">über<div' in out
    assert '<span class="word" onclick="toggleTooltip(event, this)">Gefäß<div' in out
    assert '<span class="word" onclick="toggleTooltip(event, this)">Ärger<div' in out
    # "Plan" must NOT match inside "Pläne" because 'ä' is a Unicode word character!
    assert "Pläne." in out
    assert ">Plan<" not in out
    # Tooltip explanation must have HTML escaped
    assert "<script>" not in out
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in out


def test_single_initial_render_and_intersection_observer_config():
    import subprocess
    from pathlib import Path

    export_js = Path(__file__).parent.parent / "pangloss" / "templates" / "export.js"
    node_script = """
    const fs = require('fs');
    const vm = require('vm');
    let code = fs.readFileSync(process.argv[1], 'utf8');
    code = code
        .replace('__METADATA_JSON__', JSON.stringify({
            title: 'T',
            paragraphs: [{id: 1, originalText: 'Hi', translatedText: 'Hallo', turns: [{speaker: 'Narrator', text: 'Hallo'}]}],
            characters: [],
            difficultWords: []
        }))
        .replace('__AUDIO_DATA_JSON__', '{}')
        .replace('__PLAY_SVG_JSON__', '""')
        .replace('__PAUSE_SVG_JSON__', '""')
        .replace(/__[A-Z][A-Z0-9_]*__/g, '""');

    let storySetCount = 0;
    let observerOpts = null;
    let observeCallCount = 0;
    const loadListeners = [];

    const mockEl = (id) => {
        let _html = '';
        return {
            id,
            get innerHTML() { return _html; },
            set innerHTML(v) {
                if (id === 'story') storySetCount++;
                _html = v;
            },
            textContent: '', innerText: '', style: {}, dataset: {},
            classList: { add(){}, remove(){}, toggle(){}, contains(){ return false; } },
            addEventListener(){}, appendChild(){}, querySelectorAll(){ return []; },
            closest(){ return null; }
        };
    };
    const elements = {};
    const getEl = (id) => {
        if (!elements[id]) elements[id] = mockEl(id);
        return elements[id];
    };
    const sectionEl = mockEl('section-1');

    const sandbox = {
        document: {
            getElementById: (id) => getEl(id),
            querySelector: () => null,
            querySelectorAll: (sel) => sel === '[id^="section-"]' ? [sectionEl] : [],
            addEventListener: () => {},
            documentElement: mockEl('html')
        },
        window: {
            addEventListener: (evt, fn) => { if (evt === 'load') loadListeners.push(fn); },
            location: { hash: '' },
            matchMedia: () => ({ matches: false })
        },
        history: { replaceState(){} },
        IntersectionObserver: function(cb, opts) {
            observerOpts = opts;
            return { observe() { observeCallCount++; } };
        },
        console
    };
    vm.createContext(sandbox);
    vm.runInContext(code, sandbox);
    loadListeners.forEach(fn => fn());

    console.log(JSON.stringify({
        storySetCount,
        observeCallCount,
        hasScrollContainerRoot: observerOpts && observerOpts.root === getEl('scrollContainer'),
        threshold: observerOpts ? observerOpts.threshold : null,
        rootMargin: observerOpts ? observerOpts.rootMargin : null
    }));
    """
    res = subprocess.run(
        ["node", "-e", node_script, str(export_js)],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"Node failed: {res.stderr}"
    data = json.loads(res.stdout.strip())
    assert data["storySetCount"] == 1, f"Expected storyEl.innerHTML to be set once on startup, got {data['storySetCount']}"
    assert data["observeCallCount"] == 1, f"Expected section-1 to be observed once, got {data['observeCallCount']}"
    assert data["hasScrollContainerRoot"] is True
    assert data["threshold"] == 0
    assert data["rootMargin"] == "-40% 0px -40% 0px"




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
