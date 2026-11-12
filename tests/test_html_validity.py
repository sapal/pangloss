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


def test_original_text_click_and_text_selection_do_not_restart_audio():
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
            paragraphs: [{
                id: 1,
                originalText: 'Original text here.',
                translatedText: 'Übersetzter Text hier.',
                turns: [{speaker: 'Narrator', text: 'Übersetzter Text hier.'}],
                chunks: [{chunk_index: 0, start_sec: 0, end_sec: 5, start_char: 0, end_char: 22, speakers: ['Narrator']}]
            }],
            characters: [],
            difficultWords: []
        }))
        .replace('__AUDIO_DATA_JSON__', JSON.stringify({1: 'data:audio/mp3;base64,AAAA'}))
        .replace('__PLAY_SVG_JSON__', '""')
        .replace('__PAUSE_SVG_JSON__', '""')
        .replace(/__[A-Z][A-Z0-9_]*__/g, '""');

    let selectionText = '';
    const mockEl = (id) => ({
        id, innerHTML: '', textContent: '', innerText: '', style: {}, dataset: {},
        currentTime: 0, src: '',
        play(){}, pause(){},
        classList: { add(){}, remove(){}, toggle(){}, contains(){ return false; } },
        addEventListener(){}, appendChild(){}, querySelectorAll(){ return []; },
        closest(){ return null; }
    });
    const elements = {};
    const getEl = (id) => {
        if (!elements[id]) elements[id] = mockEl(id);
        return elements[id];
    };

    const sandbox = {
        document: {
            getElementById: (id) => getEl(id),
            querySelector: () => null,
            querySelectorAll: () => [],
            addEventListener: () => {},
            documentElement: mockEl('html')
        },
        window: {
            addEventListener: () => {},
            location: { hash: '' },
            matchMedia: () => ({ matches: false }),
            getSelection: () => ({ toString: () => selectionText })
        },
        history: { replaceState(){} },
        IntersectionObserver: function() { return { observe(){} }; },
        console
    };
    vm.createContext(sandbox);
    vm.runInContext(code, sandbox);

    const storyHtml = getEl('story').innerHTML;
    // 1. Start playing paragraph 1 and advance currentTime to 3.2s
    sandbox.playPara(1, true);
    getEl('player').currentTime = 3.2;

    // 2. Simulate selecting text and calling seekToChunk -> must NOT change currentTime!
    selectionText = 'Übersetzter';
    sandbox.seekToChunk({ stopPropagation(){} }, 1, 0);
    const timeAfterSelectedClick = getEl('player').currentTime;

    // 3. Clear selection and call seekToChunk -> MUST seek to 0
    selectionText = '';
    sandbox.seekToChunk({ stopPropagation(){} }, 1, 0);
    const timeAfterNormalSeek = getEl('player').currentTime;

    console.log(JSON.stringify({
        storyHtml,
        timeAfterSelectedClick,
        timeAfterNormalSeek
    }));
    """
    res = subprocess.run(
        ["node", "-e", node_script, str(export_js)],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"Node failed: {res.stderr}"
    data = json.loads(res.stdout.strip())
    # Outer container #trans-1 (which wraps orig-1-0) must NOT have onclick="playPara(1)"
    assert 'id="trans-1" onclick="playPara(1)"' not in data["storyHtml"]
    assert data["timeAfterSelectedClick"] == 3.2
    assert data["timeAfterNormalSeek"] == 0


def test_closing_vocal_tags_and_multichunk_markdown_in_render_trans_row():
    import subprocess
    from pathlib import Path

    export_js = Path(__file__).parent.parent / "pangloss" / "templates" / "export.js"
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
        innerHTML: '', textContent: '', innerText: '', style: {}, dataset: {},
        classList: { add(){}, remove(){}, toggle(){}, contains(){ return false; } },
        addEventListener(){}, appendChild(){}, querySelectorAll(){ return []; },
        closest(){ return null; }
    });
    const sandbox = {
        document: {
            getElementById: () => mockEl(),
            querySelector: () => null,
            querySelectorAll: () => [],
            addEventListener: () => {},
            documentElement: mockEl()
        },
        window: {
            addEventListener: () => {},
            location: { hash: '' },
            matchMedia: () => ({ matches: false })
        },
        history: { replaceState(){} },
        IntersectionObserver: function() { return { observe(){} }; },
        console
    };
    vm.createContext(sandbox);
    vm.runInContext(code, sandbox);

    // 1. Closing vocal tag </whisper> should be stripped
    const pVocal = { id: 1, chunks: [] };
    const outVocal = sandbox.renderTransRow(pVocal, 0, '<whisper>Geheimnis</whisper>', [], 0, 28);

    // 2. Multi-chunk heading and multi-chunk italic emphasis
    const headingText = '## Kapitel 18. Dominanzhierarchien';
    const pHeading = {
        id: 2,
        chunks: [
            { chunk_index: 0, start_sec: 0, end_sec: 1, start_char: 0, end_char: 15, speakers: ['Narrator'] },
            { chunk_index: 1, start_sec: 1, end_sec: 2, start_char: 15, end_char: 34, speakers: ['Narrator'] }
        ]
    };
    const outHeading = sandbox.renderTransRow(pHeading, 0, headingText, [], 0, headingText.length);

    const italicText = '*Erster Teil und zweiter Teil*';
    const pItalic = {
        id: 3,
        chunks: [
            { chunk_index: 0, start_sec: 0, end_sec: 1, start_char: 0, end_char: 13, speakers: ['Narrator'] },
            { chunk_index: 1, start_sec: 1, end_sec: 2, start_char: 13, end_char: 30, speakers: ['Narrator'] }
        ]
    };
    const outItalic = sandbox.renderTransRow(pItalic, 0, italicText, [], 0, italicText.length);

    console.log(JSON.stringify({ outVocal, outHeading, outItalic }));
    """
    res = subprocess.run(
        ["node", "-e", node_script, str(export_js)],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"Node failed: {res.stderr}"
    data = json.loads(res.stdout.strip())
    assert "</whisper>" not in data["outVocal"]
    assert data["outVocal"] == "Geheimnis"
    assert data["outHeading"].startswith("<h2>") and data["outHeading"].endswith("</h2>")
    assert "##" not in data["outHeading"]
    assert "*" not in data["outItalic"]
    assert "<em>Erster Teil " in data["outItalic"]
    assert "<em>und zweiter Teil</em>" in data["outItalic"]


def test_mobile_status_speed_control_and_keyboard_shortcuts():
    import subprocess
    from pathlib import Path

    metadata: StoryMetadata = {
        "title": "Test Story",
        "characters": [{"name": "Narrator", "description": "N", "voice": "Puck", "voiceProfile": "Calm"}],
        "difficultWords": [],
        "paragraphs": [
            {
                "id": 1,
                "originalText": "One.",
                "translatedText": "Eins.",
                "turns": [{"speaker": "Narrator", "text": "Eins."}],
                "chunks": [
                    {"chunk_index": 0, "start_sec": 0.0, "end_sec": 2.0, "start_char": 0, "end_char": 5, "speakers": ["Narrator"]}
                ]
            },
            {
                "id": 2,
                "originalText": "Two.",
                "translatedText": "Zwei.",
                "turns": [{"speaker": "Narrator", "text": "Zwei."}],
                "chunks": [
                    {"chunk_index": 0, "start_sec": 0.0, "end_sec": 2.0, "start_char": 0, "end_char": 5, "speakers": ["Narrator"]}
                ]
            }
        ]
    }
    html_content = generate_html(metadata, {}, "English", "German", "B1")
    assert 'id="speedToggle"' in html_content
    assert 'id="mobileStatus"' in html_content

    export_js = Path(__file__).parent.parent / "pangloss" / "templates" / "export.js"
    node_script = """
    const fs = require('fs');
    const vm = require('vm');
    let code = fs.readFileSync(process.argv[1], 'utf8');
    code = code
        .replace('__METADATA_JSON__', JSON.stringify({
            title: 'T',
            paragraphs: [
                {id: 1, originalText: 'One.', translatedText: 'Eins.', turns: [{speaker: 'Narrator', text: 'Eins.'}], chunks: [{chunk_index: 0, start_sec: 0, end_sec: 2, start_char: 0, end_char: 5, speakers: ['Narrator']}]},
                {id: 2, originalText: 'Two.', translatedText: 'Zwei.', turns: [{speaker: 'Narrator', text: 'Zwei.'}], chunks: [{chunk_index: 0, start_sec: 0, end_sec: 2, start_char: 0, end_char: 5, speakers: ['Narrator']}]}
            ],
            characters: [],
            difficultWords: []
        }))
        .replace('__AUDIO_DATA_JSON__', JSON.stringify({1: 'data:audio/mp3;base64,AAA', 2: 'data:audio/mp3;base64,BBB'}))
        .replace('__PLAY_SVG_JSON__', '"PLAY"')
        .replace('__PAUSE_SVG_JSON__', '"PAUSE"')
        .replace(/__[A-Z][A-Z0-9_]*__/g, '"Paragraph"');

    const docListeners = {};
    const mockEl = (id) => {
        const classes = new Set();
        let _src = '';
        return {
            id, innerHTML: '', textContent: '', innerText: '', style: {}, dataset: {},
            currentTime: 0, playbackRate: 1.0,
            get src() { return _src; },
            set src(v) { _src = v; this.playbackRate = 1.0; }, // HTMLAudioElement resets playbackRate when src changes!
            play(){}, pause(){},
            classList: {
                add(...c){ c.forEach(x => classes.add(x)); },
                remove(...c){ c.forEach(x => classes.delete(x)); },
                toggle(x){ classes.has(x) ? classes.delete(x) : classes.add(x); },
                contains(x){ return classes.has(x); }
            },
            addEventListener(){}, appendChild(){}, querySelectorAll(){ return []; },
            closest(){ return null; }
        };
    };
    const elements = {};
    const getEl = (id) => {
        if (!elements[id]) elements[id] = mockEl(id);
        return elements[id];
    };

    const sandbox = {
        document: {
            getElementById: (id) => getEl(id),
            querySelector: () => null,
            querySelectorAll: () => [],
            addEventListener: (evt, fn) => {
                if (!docListeners[evt]) docListeners[evt] = [];
                docListeners[evt].push(fn);
            },
            documentElement: mockEl('html')
        },
        window: {
            addEventListener: () => {},
            location: { hash: '' },
            matchMedia: () => ({ matches: false })
        },
        history: { replaceState(){} },
        IntersectionObserver: function() { return { observe(){} }; },
        console
    };
    vm.createContext(sandbox);
    vm.runInContext(code, sandbox);

    // 1. Speed toggle cycling & persistence across playPara (which resets player.src)
    getEl('speedToggle').onclick();
    const rateAfterFirstClick = getEl('player').playbackRate;
    const labelAfterFirstClick = getEl('speedToggle').innerText;
    sandbox.playPara(1, true);
    const rateAfterPlayPara = getEl('player').playbackRate;
    const mobileStatusText = getEl('mobileStatus').innerText;

    // 2. Keyboard shortcuts: Space pauses, ArrowRight advances to para 2, Escape closes drawer
    const keydown = (key, code, tagName = 'BODY') => {
        (docListeners['keydown'] || []).forEach(fn => fn({
            key, code, target: { tagName }, preventDefault(){}
        }));
    };
    keydown(' ', 'Space');
    const playingAfterSpace = sandbox.eval ? false : getEl('playToggle').innerHTML === 'PAUSE';
    keydown('ArrowRight', 'ArrowRight');
    const idAfterRight = getEl('mobileStatus').innerText;

    getEl('drawer').classList.add('active');
    keydown('Escape', 'Escape');
    const drawerActiveAfterEsc = getEl('drawer').classList.contains('active');

    console.log(JSON.stringify({
        rateAfterFirstClick,
        labelAfterFirstClick,
        rateAfterPlayPara,
        mobileStatusText,
        playingAfterSpace,
        idAfterRight,
        drawerActiveAfterEsc
    }));
    """
    res = subprocess.run(
        ["node", "-e", node_script, str(export_js)],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"Node failed: {res.stderr}"
    data = json.loads(res.stdout.strip())
    assert data["rateAfterFirstClick"] == 1.25
    assert data["labelAfterFirstClick"] == "1.25x"
    assert data["rateAfterPlayPara"] == 1.25
    assert "1" in data["mobileStatusText"]
    assert data["playingAfterSpace"] is False
    assert "2" in data["idAfterRight"]
    assert data["drawerActiveAfterEsc"] is False


def test_mobile_paragraph_ordering_and_spacing():
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
            paragraphs: [
                {id: 1, originalText: 'English first.\\n\\nEnglish second.', translatedText: 'Deutsch zuerst.\\n\\nDeutsch zweitens.', turns: [{speaker: 'Narrator', text: 'Deutsch zuerst.'}]}
            ],
            characters: [],
            difficultWords: []
        }))
        .replace('__AUDIO_DATA_JSON__', '{}')
        .replace('__PLAY_SVG_JSON__', '""')
        .replace('__PAUSE_SVG_JSON__', '""')
        .replace(/__[A-Z][A-Z0-9_]*__/g, '""');

    const mockEl = (id) => ({
        id, innerHTML: '', textContent: '', innerText: '', style: {}, dataset: {},
        classList: { add(){}, remove(){}, toggle(){}, contains(){ return false; } },
        addEventListener(){}, appendChild(){}, querySelectorAll(){ return []; },
        closest(){ return null; }
    });
    const elements = {};
    const getEl = (id) => {
        if (!elements[id]) elements[id] = mockEl(id);
        return elements[id];
    };

    const sandbox = {
        document: {
            getElementById: (id) => getEl(id),
            querySelector: () => null,
            querySelectorAll: () => [],
            addEventListener: () => {},
            documentElement: mockEl('html')
        },
        window: {
            addEventListener: () => {},
            location: { hash: '' },
            matchMedia: () => ({ matches: false })
        },
        history: { replaceState(){} },
        IntersectionObserver: function() { return { observe(){} }; },
        console
    };
    vm.createContext(sandbox);
    vm.runInContext(code, sandbox);

    console.log(JSON.stringify({ storyHtml: getEl('story').innerHTML }));
    """
    res = subprocess.run(
        ["node", "-e", node_script, str(export_js)],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"Node failed: {res.stderr}"
    story_html = json.loads(res.stdout.strip())["storyHtml"]
    assert "gap-3 md:gap-12 items-start mb-10 last:mb-0" in story_html
    assert "order-2 md:gap-12" not in story_html
    assert "order-2 md:order-1" in story_html
    assert "order-1 md:order-2" in story_html


def test_reading_mode_side_by_side_vs_hold_to_see_original():
    import subprocess
    from pathlib import Path

    metadata: StoryMetadata = {
        "title": "Test Story",
        "characters": [{"name": "Narrator", "description": "N", "voice": "Puck", "voiceProfile": "Calm"}],
        "difficultWords": [],
        "paragraphs": [
            {
                "id": 1,
                "originalText": "Original English sentence.",
                "translatedText": "Übersetzter deutscher Satz.",
                "turns": [{"speaker": "Narrator", "text": "Übersetzter deutscher Satz."}]
            }
        ]
    }
    html_content = generate_html(metadata, {}, "English", "German", "B1")
    assert 'id="readingModeToggle"' in html_content
    assert 'data-reading-mode="hold-original"' in html_content

    export_js = Path(__file__).parent.parent / "pangloss" / "templates" / "export.js"
    node_script = """
    const fs = require('fs');
    const vm = require('vm');
    let code = fs.readFileSync(process.argv[1], 'utf8');
    code = code
        .replace('__METADATA_JSON__', JSON.stringify({
            title: 'T',
            paragraphs: [
                {id: 1, originalText: 'Original.', translatedText: 'Übersetzt.', turns: [{speaker: 'Narrator', text: 'Übersetzt.'}]}
            ],
            characters: [],
            difficultWords: []
        }))
        .replace('__AUDIO_DATA_JSON__', '{}')
        .replace('__PLAY_SVG_JSON__', '""')
        .replace('__PAUSE_SVG_JSON__', '""')
        .replace(/__[A-Z][A-Z0-9_]*__/g, '""');

    function runWithPortrait(isMobilePortrait) {
        const classes = new Set();
        const mockEl = (id) => {
            const elClasses = new Set();
            return {
                id, innerHTML: '', textContent: '', innerText: '', style: {}, dataset: {},
                classList: {
                    add(...c){ c.forEach(x => elClasses.add(x)); },
                    remove(...c){ c.forEach(x => elClasses.delete(x)); },
                    toggle(x){ elClasses.has(x) ? elClasses.delete(x) : elClasses.add(x); },
                    contains(x){ return elClasses.has(x); }
                },
                addEventListener(){}, appendChild(){}, querySelectorAll(){ return []; },
                closest(){ return null; }
            };
        };
        const elements = {};
        const getEl = (id) => {
            if (!elements[id]) elements[id] = mockEl(id);
            return elements[id];
        };
        const docEl = mockEl('html');
        const sandbox = {
            document: {
                getElementById: (id) => getEl(id),
                querySelector: () => null,
                querySelectorAll: () => [],
                addEventListener: () => {},
                documentElement: docEl
            },
            window: {
                addEventListener: () => {},
                location: { hash: '' },
                matchMedia: (q) => ({
                    matches: q.includes('max-width: 767px') && q.includes('orientation: portrait') ? isMobilePortrait : false
                })
            },
            history: { replaceState(){} },
            IntersectionObserver: function() { return { observe(){} }; },
            setTimeout: (fn) => { fn(); return 1; },
            clearTimeout: () => {},
            console
        };
        vm.createContext(sandbox);
        vm.runInContext(code, sandbox);

        const initialMode = docEl.dataset.readingMode;
        getEl('readingModeToggle').onclick();
        const toggledMode = docEl.dataset.readingMode;

        // Test hold-to-see-original press & release
        if (docEl.dataset.readingMode !== 'hold-original') {
            getEl('readingModeToggle').onclick();
        }
        const subpara = mockEl('subpara');
        sandbox.startHoldOriginal(subpara);
        const holdingDuringPress = docEl.classList.contains('holding-original') || subpara.classList.contains('holding-original');
        sandbox.endHoldOriginal();
        const holdingAfterRelease = docEl.classList.contains('holding-original') || subpara.classList.contains('holding-original');

        return { initialMode, toggledMode, holdingDuringPress, holdingAfterRelease };
    }

    console.log(JSON.stringify({
        mobilePortrait: runWithPortrait(true),
        desktop: runWithPortrait(false)
    }));
    """
    res = subprocess.run(
        ["node", "-e", node_script, str(export_js)],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"Node failed: {res.stderr}"
    data = json.loads(res.stdout.strip())
    assert data["mobilePortrait"]["initialMode"] == "hold-original"
    assert data["mobilePortrait"]["toggledMode"] == "side-by-side"
    assert data["desktop"]["initialMode"] == "side-by-side"
    assert data["desktop"]["toggledMode"] == "hold-original"
    assert data["mobilePortrait"]["holdingDuringPress"] is True
    assert data["mobilePortrait"]["holdingAfterRelease"] is False


def test_smart_auto_scroll_detach_and_resume_pill():
    import subprocess
    from pathlib import Path

    metadata: StoryMetadata = {
        "title": "Test Story",
        "characters": [{"name": "Narrator", "description": "N", "voice": "Puck", "voiceProfile": "Calm"}],
        "difficultWords": [],
        "paragraphs": [
            {
                "id": 1,
                "originalText": "One.",
                "translatedText": "Eins.",
                "turns": [{"speaker": "Narrator", "text": "Eins."}],
                "chunks": [
                    {"chunk_index": 0, "start_sec": 0.0, "end_sec": 5.0, "start_char": 0, "end_char": 5, "speakers": ["Narrator"]}
                ]
            }
        ]
    }
    html_content = generate_html(metadata, {}, "English", "German", "B1")
    assert 'id="resumeAutoScrollBtn"' in html_content

    export_js = Path(__file__).parent.parent / "pangloss" / "templates" / "export.js"
    node_script = """
    const fs = require('fs');
    const vm = require('vm');
    let code = fs.readFileSync(process.argv[1], 'utf8');
    code = code
        .replace('__METADATA_JSON__', JSON.stringify({
            title: 'T',
            paragraphs: [
                {id: 1, originalText: 'One.', translatedText: 'Eins.', turns: [{speaker: 'Narrator', text: 'Eins.'}], chunks: [{chunk_index: 0, start_sec: 0, end_sec: 5, start_char: 0, end_char: 5, speakers: ['Narrator']}]}
            ],
            characters: [],
            difficultWords: []
        }))
        .replace('__AUDIO_DATA_JSON__', JSON.stringify({1: 'data:audio/mp3;base64,AAA'}))
        .replace('__PLAY_SVG_JSON__', '"PLAY"')
        .replace('__PAUSE_SVG_JSON__', '"PAUSE"')
        .replace(/__[A-Z][A-Z0-9_]*__/g, '"Resume Auto-Scroll"');

    let scrollCalls = 0;
    const mockEl = (id) => {
        const classes = new Set();
        const listeners = {};
        return {
            id, innerHTML: '', textContent: 'Eins.', innerText: '', style: {}, dataset: {},
            currentTime: 1.0, duration: 5.0, playbackRate: 1.0, src: '',
            clientHeight: 600, scrollTop: 0,
            play(){}, pause(){},
            scrollTo(){ scrollCalls++; },
            getBoundingClientRect(){ return { top: id === 'scrollContainer' ? 0 : 800, height: 40, left: 0, right: 100 }; },
            classList: {
                add(...c){ c.forEach(x => classes.add(x)); },
                remove(...c){ c.forEach(x => classes.delete(x)); },
                toggle(x){ classes.has(x) ? classes.delete(x) : classes.add(x); },
                contains(x){ return classes.has(x); }
            },
            addEventListener(evt, fn){
                if (!listeners[evt]) listeners[evt] = [];
                listeners[evt].push(fn);
            },
            trigger(evt, e = {}){
                (listeners[evt] || []).forEach(fn => fn(e));
            },
            appendChild(){}, querySelectorAll(){ return []; },
            closest(){ return null; }
        };
    };
    const elements = {};
    const getEl = (id) => {
        if (!elements[id]) elements[id] = mockEl(id);
        return elements[id];
    };
    const chunkEl = mockEl('chunk-0');

    const sandbox = {
        document: {
            getElementById: (id) => getEl(id),
            querySelector: () => null,
            querySelectorAll: (sel) => sel.includes('chunk-p1-c0') ? [chunkEl] : [],
            addEventListener: () => {},
            documentElement: mockEl('html')
        },
        window: {
            addEventListener: () => {},
            location: { hash: '' },
            matchMedia: () => ({ matches: false })
        },
        history: { replaceState(){} },
        IntersectionObserver: function() { return { observe(){} }; },
        Date: { now: () => 10000 },
        console
    };
    vm.createContext(sandbox);
    vm.runInContext(code, sandbox);

    sandbox.playPara(1, true);
    scrollCalls = 0;

    // 1. User manually scrolls with wheel while playing -> auto-scroll detaches and pill becomes visible
    getEl('scrollContainer').trigger('wheel', {});
    const pillVisibleAfterWheel = getEl('resumeAutoScrollBtn').classList.contains('visible');

    // 2. Subsequent timeupdate does NOT yank scroll while detached
    getEl('player').trigger('timeupdate', {});
    const scrollCallsWhileDetached = scrollCalls;

    // 3. Clicking resumeAutoScrollBtn hides pill and scrolls back to active chunk
    getEl('resumeAutoScrollBtn').onclick();
    const pillVisibleAfterResume = getEl('resumeAutoScrollBtn').classList.contains('visible');
    const scrollCallsAfterResume = scrollCalls;

    console.log(JSON.stringify({
        pillVisibleAfterWheel,
        scrollCallsWhileDetached,
        pillVisibleAfterResume,
        scrollCallsAfterResume
    }));
    """
    res = subprocess.run(
        ["node", "-e", node_script, str(export_js)],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"Node failed: {res.stderr}"
    data = json.loads(res.stdout.strip())
    assert data["pillVisibleAfterWheel"] is True
    assert data["scrollCallsWhileDetached"] == 0
    assert data["pillVisibleAfterResume"] is False
    assert data["scrollCallsAfterResume"] >= 1


def test_tooltip_viewport_clamping_and_flip():
    import subprocess
    from pathlib import Path

    metadata: StoryMetadata = {
        "title": "Test Story",
        "characters": [{"name": "Narrator", "description": "N", "voice": "Puck", "voiceProfile": "Calm"}],
        "difficultWords": [],
        "paragraphs": [
            {
                "id": 1,
                "originalText": "One.",
                "translatedText": "Eins.",
                "turns": [{"speaker": "Narrator", "text": "Eins."}]
            }
        ]
    }
    html_content = generate_html(metadata, {}, "English", "German", "B1")
    assert "tooltip-below" in html_content
    assert "max-width: calc(100vw - 24px)" in html_content

    export_js = Path(__file__).parent.parent / "pangloss" / "templates" / "export.js"
    node_script = """
    const fs = require('fs');
    const vm = require('vm');
    let code = fs.readFileSync(process.argv[1], 'utf8');
    code = code
        .replace('__METADATA_JSON__', JSON.stringify({
            title: 'T',
            paragraphs: [],
            characters: [],
            difficultWords: []
        }))
        .replace('__AUDIO_DATA_JSON__', '{}')
        .replace('__PLAY_SVG_JSON__', '""')
        .replace('__PAUSE_SVG_JSON__', '""')
        .replace(/__[A-Z][A-Z0-9_]*__/g, '""');

    const mockEl = (id, rectFn) => {
        const classes = new Set();
        return {
            id, innerHTML: '', textContent: '', innerText: '', style: {}, dataset: {},
            getBoundingClientRect: rectFn || (() => ({ left: 100, right: 160, top: 200, bottom: 220, width: 60, height: 20 })),
            classList: {
                add(...c){ c.forEach(x => classes.add(x)); },
                remove(...c){ c.forEach(x => classes.delete(x)); },
                toggle(x){ classes.has(x) ? classes.delete(x) : classes.add(x); },
                contains(x){ return classes.has(x); }
            },
            addEventListener(){}, appendChild(){}, querySelectorAll(){ return []; },
            querySelector(){ return null; }, closest(){ return null; }
        };
    };
    const elements = {};
    const getEl = (id) => {
        if (!elements[id]) elements[id] = mockEl(id);
        return elements[id];
    };

    const sandbox = {
        document: {
            getElementById: (id) => getEl(id),
            querySelector: () => null,
            querySelectorAll: () => [],
            addEventListener: () => {},
            documentElement: mockEl('html')
        },
        window: {
            innerWidth: 360,
            innerHeight: 640,
            addEventListener: () => {},
            location: { hash: '' },
            matchMedia: () => ({ matches: false })
        },
        history: { replaceState(){} },
        IntersectionObserver: function() { return { observe(){} }; },
        console
    };
    vm.createContext(sandbox);
    vm.runInContext(code, sandbox);

    // 1. Word near left edge (x=5..45) and top edge (top=10) -> tooltip clamps right (positive marginLeft) and flips below
    const leftTip = mockEl('tip-left', () => ({ left: -125, right: 175, top: -110, bottom: -10, width: 300, height: 100 }));
    const leftWord = mockEl('word-left', () => ({ left: 5, right: 45, top: 10, bottom: 30, width: 40, height: 20 }));
    leftWord.querySelector = (sel) => sel === '.tooltip' ? leftTip : null;
    sandbox.toggleTooltip({ stopPropagation(){} }, leftWord);

    // 2. Word near right edge (x=320..355) and middle Y (top=300) -> tooltip clamps left (negative marginLeft) and stays above
    const rightTip = mockEl('tip-right', () => ({ left: 187.5, right: 487.5, top: 180, bottom: 280, width: 300, height: 100 }));
    const rightWord = mockEl('word-right', () => ({ left: 320, right: 355, top: 300, bottom: 320, width: 35, height: 20 }));
    rightWord.querySelector = (sel) => sel === '.tooltip' ? rightTip : null;
    sandbox.toggleTooltip({ stopPropagation(){} }, rightWord);

    console.log(JSON.stringify({
        leftMargin: parseFloat(leftTip.style.marginLeft || '0'),
        leftFlippedBelow: leftTip.classList.contains('tooltip-below'),
        rightMargin: parseFloat(rightTip.style.marginLeft || '0'),
        rightFlippedBelow: rightTip.classList.contains('tooltip-below')
    }));
    """
    res = subprocess.run(
        ["node", "-e", node_script, str(export_js)],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"Node failed: {res.stderr}"
    data = json.loads(res.stdout.strip())
    assert data["leftMargin"] > 0
    assert data["leftFlippedBelow"] is True
    assert data["rightMargin"] < 0
    assert data["rightFlippedBelow"] is False


def test_persistent_playback_position_and_progress_bar():
    import subprocess
    from pathlib import Path

    metadata: StoryMetadata = {
        "title": "Teapot Story",
        "characters": [{"name": "Narrator", "description": "N", "voice": "Puck", "voiceProfile": "Calm"}],
        "difficultWords": [],
        "paragraphs": [
            {
                "id": 1,
                "originalText": "One.",
                "translatedText": "Eins.",
                "turns": [{"speaker": "Narrator", "text": "Eins."}],
                "chunks": [{"chunk_index": 0, "start_sec": 0.0, "end_sec": 4.0, "start_char": 0, "end_char": 5, "speakers": ["Narrator"]}]
            },
            {
                "id": 2,
                "originalText": "Two.",
                "translatedText": "Zwei.",
                "turns": [{"speaker": "Narrator", "text": "Zwei."}],
                "chunks": [{"chunk_index": 0, "start_sec": 0.0, "end_sec": 4.0, "start_char": 0, "end_char": 5, "speakers": ["Narrator"]}]
            }
        ]
    }
    html_content = generate_html(metadata, {}, "English", "German", "B1")
    assert 'id="chapterProgressBar"' in html_content

    export_js = Path(__file__).parent.parent / "pangloss" / "templates" / "export.js"
    node_script = """
    const fs = require('fs');
    const vm = require('vm');
    let code = fs.readFileSync(process.argv[1], 'utf8');
    code = code
        .replace('__METADATA_JSON__', JSON.stringify({
            title: 'Teapot Story',
            paragraphs: [
                {id: 1, originalText: 'One.', translatedText: 'Eins.', turns: [{speaker: 'Narrator', text: 'Eins.'}], chunks: [{chunk_index: 0, start_sec: 0, end_sec: 4, start_char: 0, end_char: 5, speakers: ['Narrator']}]},
                {id: 2, originalText: 'Two.', translatedText: 'Zwei.', turns: [{speaker: 'Narrator', text: 'Zwei.'}], chunks: [{chunk_index: 0, start_sec: 0, end_sec: 4, start_char: 0, end_char: 5, speakers: ['Narrator']}]}
            ],
            characters: [],
            difficultWords: []
        }))
        .replace('__AUDIO_DATA_JSON__', JSON.stringify({1: 'data:audio/mp3;base64,AAA', 2: 'data:audio/mp3;base64,BBB'}))
        .replace('__PLAY_SVG_JSON__', '"PLAY"')
        .replace('__PAUSE_SVG_JSON__', '"PAUSE"')
        .replace(/__[A-Z][A-Z0-9_]*__/g, '"Paragraph"');

    const store = {};
    const localStorageMock = {
        getItem: (k) => Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null,
        setItem: (k, v) => { store[k] = String(v); }
    };

    function createSession() {
        const winListeners = {};
        const mockEl = (id) => {
            const classes = new Set();
            const listeners = {};
            return {
                id, innerHTML: '', textContent: '', innerText: '', style: {}, dataset: {},
                currentTime: 0, duration: 4.0, playbackRate: 1.0, src: '',
                clientHeight: 600, scrollTop: 0,
                play(){}, pause(){}, scrollTo(){},
                getBoundingClientRect(){ return { top: 0, height: 40, left: 0, right: 100 }; },
                classList: {
                    add(...c){ c.forEach(x => classes.add(x)); },
                    remove(...c){ c.forEach(x => classes.delete(x)); },
                    toggle(x){ classes.has(x) ? classes.delete(x) : classes.add(x); },
                    contains(x){ return classes.has(x); }
                },
                addEventListener(evt, fn){
                    if (!listeners[evt]) listeners[evt] = [];
                    listeners[evt].push(fn);
                },
                trigger(evt, e = {}){
                    (listeners[evt] || []).forEach(fn => fn(e));
                },
                appendChild(){}, querySelectorAll(){ return []; },
                querySelector(){ return null; }, closest(){ return null; }
            };
        };
        const elements = {};
        const getEl = (id) => {
            if (!elements[id]) elements[id] = mockEl(id);
            return elements[id];
        };
        const sandbox = {
            document: {
                getElementById: (id) => getEl(id),
                querySelector: () => null,
                querySelectorAll: () => [],
                addEventListener: () => {},
                documentElement: mockEl('html')
            },
            window: {
                addEventListener: (evt, fn) => {
                    if (!winListeners[evt]) winListeners[evt] = [];
                    winListeners[evt].push(fn);
                },
                location: { hash: '' },
                matchMedia: () => ({ matches: false }),
                localStorage: localStorageMock
            },
            localStorage: localStorageMock,
            history: { replaceState(){} },
            IntersectionObserver: function() { return { observe(){} }; },
            Date: { now: () => 10000 },
            console
        };
        vm.createContext(sandbox);
        vm.runInContext(code, sandbox);
        (winListeners['load'] || []).forEach(fn => fn());
        return { sandbox, getEl };
    }

    // Session 1: play paragraph 2 at 1.25x speed and time=2.0s -> saves state & updates progress bar
    const s1 = createSession();
    s1.getEl('speedToggle').onclick(); // 1.25x
    s1.sandbox.playPara(2, true);
    s1.getEl('player').currentTime = 2.0;
    s1.getEl('player').trigger('timeupdate', {});
    const progressWidthSession1 = s1.getEl('chapterProgressBar').style.width;

    // Session 2: fresh reload with no URL hash -> restores paragraph 2 and 1.25x speed from localStorage
    const s2 = createSession();
    const restoredStatus = s2.getEl('mobileStatus').innerText;
    const restoredSpeedLabel = s2.getEl('speedToggle').innerText;
    const progressWidthSession2 = s2.getEl('chapterProgressBar').style.width;

    console.log(JSON.stringify({
        progressWidthSession1,
        restoredStatus,
        restoredSpeedLabel,
        progressWidthSession2
    }));
    """
    res = subprocess.run(
        ["node", "-e", node_script, str(export_js)],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"Node failed: {res.stderr}"
    data = json.loads(res.stdout.strip())
    assert data["progressWidthSession1"].endswith("%") and float(data["progressWidthSession1"].rstrip("%")) > 50
    assert "#2/2" in data["restoredStatus"]
    assert data["restoredSpeedLabel"] == "1.25x"
    assert data["progressWidthSession2"].endswith("%") and float(data["progressWidthSession2"].rstrip("%")) >= 50


def test_dark_mode_toggle_and_persistence():
    import subprocess
    from pathlib import Path

    metadata: StoryMetadata = {
        "title": "Test Story",
        "characters": [{"name": "Narrator", "description": "N", "voice": "Puck", "voiceProfile": "Calm"}],
        "difficultWords": [],
        "paragraphs": [
            {
                "id": 1,
                "originalText": "One.",
                "translatedText": "Eins.",
                "turns": [{"speaker": "Narrator", "text": "Eins."}]
            }
        ]
    }
    html_content = generate_html(metadata, {}, "English", "German", "B1")
    assert 'id="themeToggle"' in html_content
    assert 'data-theme="dark"' in html_content

    export_js = Path(__file__).parent.parent / "pangloss" / "templates" / "export.js"
    node_script = """
    const fs = require('fs');
    const vm = require('vm');
    let code = fs.readFileSync(process.argv[1], 'utf8');
    code = code
        .replace('__METADATA_JSON__', JSON.stringify({
            title: 'T',
            paragraphs: [],
            characters: [],
            difficultWords: []
        }))
        .replace('__AUDIO_DATA_JSON__', '{}')
        .replace('__PLAY_SVG_JSON__', '""')
        .replace('__PAUSE_SVG_JSON__', '""')
        .replace(/__[A-Z][A-Z0-9_]*__/g, '""');

    const store = {};
    const localStorageMock = {
        getItem: (k) => Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null,
        setItem: (k, v) => { store[k] = String(v); }
    };

    function createSession() {
        const mockEl = (id) => {
            const classes = new Set();
            return {
                id, innerHTML: '', textContent: '', innerText: '', style: {}, dataset: {},
                classList: {
                    add(...c){ c.forEach(x => classes.add(x)); },
                    remove(...c){ c.forEach(x => classes.delete(x)); },
                    toggle(x){ classes.has(x) ? classes.delete(x) : classes.add(x); },
                    contains(x){ return classes.has(x); }
                },
                addEventListener(){}, appendChild(){}, querySelectorAll(){ return []; },
                querySelector(){ return null; }, closest(){ return null; }
            };
        };
        const elements = {};
        const getEl = (id) => {
            if (!elements[id]) elements[id] = mockEl(id);
            return elements[id];
        };
        const docEl = mockEl('html');
        const sandbox = {
            document: {
                getElementById: (id) => getEl(id),
                querySelector: () => null,
                querySelectorAll: () => [],
                addEventListener: () => {},
                documentElement: docEl
            },
            window: {
                addEventListener: () => {},
                location: { hash: '' },
                matchMedia: () => ({ matches: false }),
                localStorage: localStorageMock
            },
            localStorage: localStorageMock,
            history: { replaceState(){} },
            IntersectionObserver: function() { return { observe(){} }; },
            console
        };
        vm.createContext(sandbox);
        vm.runInContext(code, sandbox);
        return { docEl, getEl };
    }

    const s1 = createSession();
    const initialTheme = s1.docEl.dataset.theme;
    s1.getEl('themeToggle').onclick();
    const toggledTheme = s1.docEl.dataset.theme;

    // Reloading session restores dark theme from localStorage
    const s2 = createSession();
    const restoredTheme = s2.docEl.dataset.theme;

    console.log(JSON.stringify({ initialTheme, toggledTheme, restoredTheme }));
    """
    res = subprocess.run(
        ["node", "-e", node_script, str(export_js)],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"Node failed: {res.stderr}"
    data = json.loads(res.stdout.strip())
    assert data["initialTheme"] == "light"
    assert data["toggledTheme"] == "dark"
    assert data["restoredTheme"] == "dark"


def test_searchable_lexicon_and_jump_to_word():
    import subprocess
    from pathlib import Path

    metadata: StoryMetadata = {
        "title": "Test Story",
        "characters": [{"name": "Narrator", "description": "N", "voice": "Puck", "voiceProfile": "Calm"}],
        "difficultWords": [
            {"word": "die Quanten-Teekanne", "explanation": "Quantum teapot", "anchors": ["Quanten-Teekanne"]},
            {"word": "zögern", "explanation": "to hesitate", "anchors": ["zögerte"]}
        ],
        "paragraphs": [
            {
                "id": 1,
                "originalText": "First.",
                "translatedText": "Die Quanten-Teekanne glänzte.",
                "turns": [{"speaker": "Narrator", "text": "Die Quanten-Teekanne glänzte."}]
            },
            {
                "id": 2,
                "originalText": "Second.",
                "translatedText": "Arthur zögerte kurz.",
                "turns": [{"speaker": "Narrator", "text": "Arthur zögerte kurz."}]
            }
        ]
    }
    html_content = generate_html(metadata, {}, "English", "German", "B1")
    assert 'id="vocabSearch"' in html_content

    export_js = Path(__file__).parent.parent / "pangloss" / "templates" / "export.js"
    node_script = """
    const fs = require('fs');
    const vm = require('vm');
    let code = fs.readFileSync(process.argv[1], 'utf8');
    code = code
        .replace('__METADATA_JSON__', JSON.stringify({
            title: 'T',
            paragraphs: [
                {id: 1, originalText: 'First.', translatedText: 'Die Quanten-Teekanne glänzte.', turns: [{speaker: 'Narrator', text: 'Die Quanten-Teekanne glänzte.'}]},
                {id: 2, originalText: 'Second.', translatedText: 'Arthur zögerte kurz.', turns: [{speaker: 'Narrator', text: 'Arthur zögerte kurz.'}]}
            ],
            characters: [],
            difficultWords: [
                {word: 'die Quanten-Teekanne', explanation: 'Quantum teapot', anchors: ['Quanten-Teekanne']},
                {word: 'zögern', explanation: 'to hesitate', anchors: ['zögerte']}
            ]
        }))
        .replace('__AUDIO_DATA_JSON__', '{}')
        .replace('__PLAY_SVG_JSON__', '""')
        .replace('__PAUSE_SVG_JSON__', '""')
        .replace(/__[A-Z][A-Z0-9_]*__/g, '""');

    let scrollCount = 0;
    const mockEl = (id, text = '') => {
        const classes = new Set();
        const listeners = {};
        return {
            id, innerHTML: '', textContent: text, innerText: text, value: '', style: {}, dataset: {},
            clientHeight: 600, scrollTop: 0,
            scrollTo(){ scrollCount++; },
            getBoundingClientRect(){ return { top: 200, bottom: 220, left: 50, right: 120, width: 70, height: 20 }; },
            classList: {
                add(...c){ c.forEach(x => classes.add(x)); },
                remove(...c){ c.forEach(x => classes.delete(x)); },
                toggle(x){ classes.has(x) ? classes.delete(x) : classes.add(x); },
                contains(x){ return classes.has(x); }
            },
            addEventListener(evt, fn){
                if (!listeners[evt]) listeners[evt] = [];
                listeners[evt].push(fn);
            },
            trigger(evt, e = {}){
                (listeners[evt] || []).forEach(fn => fn(e));
            },
            appendChild(){}, querySelectorAll(){ return []; },
            querySelector(){ return null; },
            closest(sel){ return sel === '[id^="section-"]' ? getEl('section-2') : null; }
        };
    };
    const elements = {};
    const getEl = (id) => {
        if (!elements[id]) elements[id] = mockEl(id);
        return elements[id];
    };
    const wordEl1 = mockEl('w1', 'Quanten-Teekannedie Quanten-Teekanne: Quantum teapot');
    const wordEl2 = mockEl('w2', 'zögertedie zögern: to hesitate');

    const sandbox = {
        document: {
            getElementById: (id) => getEl(id),
            querySelector: () => null,
            querySelectorAll: (sel) => sel.includes('.word') ? [wordEl1, wordEl2] : [],
            addEventListener: () => {},
            documentElement: mockEl('html')
        },
        window: {
            innerWidth: 800,
            innerHeight: 600,
            addEventListener: () => {},
            location: { hash: '' },
            matchMedia: () => ({ matches: false })
        },
        history: { replaceState(){} },
        IntersectionObserver: function() { return { observe(){} }; },
        console
    };
    vm.createContext(sandbox);
    vm.runInContext(code, sandbox);

    const initialVocabHtml = getEl('vocabList').innerHTML;

    // 1. Typing 'hesitate' into #vocabSearch filters #vocabList to only 'zögern'
    const searchInput = getEl('vocabSearch');
    searchInput.value = 'hesitate';
    if (searchInput.oninput) searchInput.oninput({ target: searchInput });
    searchInput.trigger('input', { target: searchInput });
    const filteredVocabHtml = getEl('vocabList').innerHTML;

    // 2. Calling jumpToVocabWord('zögern') closes drawer, scrolls to word, and activates its tooltip
    getEl('drawer').classList.add('active');
    scrollCount = 0;
    sandbox.jumpToVocabWord('zögern');
    const drawerClosedAfterJump = !getEl('drawer').classList.contains('active');
    const word2TooltipActive = wordEl2.classList.contains('active-tooltip');

    console.log(JSON.stringify({
        bothInInitial: initialVocabHtml.includes('Quanten-Teekanne') && initialVocabHtml.includes('zögern'),
        filteredHasZogernOnly: filteredVocabHtml.includes('zögern') && !filteredVocabHtml.includes('Quanten-Teekanne'),
        drawerClosedAfterJump,
        word2TooltipActive,
        scrollCount
    }));
    """
    res = subprocess.run(
        ["node", "-e", node_script, str(export_js)],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"Node failed: {res.stderr}"
    data = json.loads(res.stdout.strip())
    assert data["bothInInitial"] is True
    assert data["filteredHasZogernOnly"] is True
    assert data["drawerClosedAfterJump"] is True
    assert data["word2TooltipActive"] is True
    assert data["scrollCount"] >= 1


def test_dark_mode_contrast_mobile_icon_bar_and_hold_replace_pause():
    import re
    import subprocess
    from pathlib import Path

    metadata: StoryMetadata = {
        "title": "Test Story",
        "characters": [{"name": "Narrator", "description": "N", "voice": "Puck", "voiceProfile": "Calm"}],
        "difficultWords": [],
        "paragraphs": [
            {
                "id": 1,
                "originalText": "First sub.\n\nSecond sub.",
                "translatedText": "Erster Teil.\n\nZweiter Teil.",
                "turns": [{"speaker": "Narrator", "text": "Erster Teil.\n\nZweiter Teil."}]
            }
        ]
    }
    html_content = generate_html(metadata, {}, "English", "German", "B1")

    # 1. Dark mode contrast: play button must override .bg-paper !important and #permanentControls .text-paper must stay light
    assert re.search(r'html\[data-theme="dark"\]\s+#playToggle\s*\{[^}]*background-color:\s*#E8E4D9\s*!important', html_content)
    assert re.search(r'html\[data-theme="dark"\]\s+#permanentControls\s+\.text-paper[^{]*\{[^}]*color:\s*#E8E4D9\s*!important', html_content)
    assert 'fill="black"' not in html_content

    # 2. Mobile portrait bar uses icon-only buttons (.dict-label hidden in mobile portrait)
    portrait_match = re.search(
        r'@media\s*\(max-width:\s*767px\)\s*and\s*\(orientation:\s*portrait\)\s*\{(.*?)\n\s{8}\}',
        html_content,
        re.DOTALL,
    )
    assert portrait_match is not None
    portrait_css = portrait_match.group(1)
    assert re.search(r'\.dict-label\s*\{\s*display:\s*none\s*!important;', portrait_css)

    # 3. Hold-original CSS replaces .trans-col with .orig-col ONLY on the held .subpara-grid
    assert re.search(
        r'html\[data-reading-mode="hold-original"\]\s+\.subpara-grid\.holding-original\s+\.trans-col\s*\{\s*display:\s*none\s*!important;',
        html_content,
    )
    assert 'html[data-reading-mode="hold-original"].holding-original .orig-col' not in html_content

    # 4. Hold-original JS behavior:
    #    - Only tapped sub-paragraph gets .holding-original (not documentElement or other sub-paragraphs)
    #    - If audio was playing, holding pauses audio and lifting finger resumes audio
    #    - If audio was NOT playing, holding and lifting finger does NOT start audio
    export_js = Path(__file__).parent.parent / "pangloss" / "templates" / "export.js"
    node_script = """
    const fs = require('fs');
    const vm = require('vm');
    let code = fs.readFileSync(process.argv[1], 'utf8');
    code = code
        .replace('__METADATA_JSON__', JSON.stringify({
            title: 'T',
            paragraphs: [
                {id: 1, originalText: 'First.\\n\\nSecond.', translatedText: 'Erster.\\n\\nZweiter.', turns: [{speaker: 'Narrator', text: 'Erster.'}]}
            ],
            characters: [],
            difficultWords: []
        }))
        .replace('__AUDIO_DATA_JSON__', JSON.stringify({1: 'data:audio/mp3;base64,AAA'}))
        .replace('__PLAY_SVG_JSON__', '"PLAY"')
        .replace('__PAUSE_SVG_JSON__', '"PAUSE"')
        .replace(/__[A-Z][A-Z0-9_]*__/g, '""');

    let playCalls = 0;
    let pauseCalls = 0;
    const mockEl = (id) => {
        const classes = new Set();
        return {
            id, innerHTML: '', textContent: '', innerText: '', style: {}, dataset: {},
            currentTime: 0, duration: 5, playbackRate: 1, src: '', clientHeight: 600, scrollTop: 0,
            play(){ playCalls++; },
            pause(){ pauseCalls++; },
            scrollTo(){},
            getBoundingClientRect(){ return { top: 0, height: 40, left: 0, right: 100 }; },
            classList: {
                add(...c){ c.forEach(x => classes.add(x)); },
                remove(...c){ c.forEach(x => classes.delete(x)); },
                toggle(x){ classes.has(x) ? classes.delete(x) : classes.add(x); },
                contains(x){ return classes.has(x); }
            },
            addEventListener(){}, appendChild(){}, querySelectorAll(){ return []; },
            querySelector(){ return null; }, closest(){ return null; }
        };
    };
    const elements = {};
    const getEl = (id) => {
        if (!elements[id]) elements[id] = mockEl(id);
        return elements[id];
    };
    const docEl = mockEl('html');
    const subpara1 = mockEl('subpara-1');
    const subpara2 = mockEl('subpara-2');

    const sandbox = {
        document: {
            getElementById: (id) => getEl(id),
            querySelector: () => null,
            querySelectorAll: (sel) => sel === '.holding-original' ? [subpara1, subpara2].filter(el => el.classList.contains('holding-original')) : [],
            addEventListener: () => {},
            documentElement: docEl
        },
        window: {
            addEventListener: () => {},
            location: { hash: '' },
            matchMedia: (q) => ({ matches: q.includes('max-width: 767px') && q.includes('orientation: portrait') })
        },
        history: { replaceState(){} },
        IntersectionObserver: function() { return { observe(){} }; },
        setTimeout: (fn) => { fn(); return 1; },
        clearTimeout: () => {},
        console
    };
    vm.createContext(sandbox);
    vm.runInContext(code, sandbox);

    // Case A: Audio is NOT playing -> hold subpara1 and release -> audio must NOT start
    playCalls = 0;
    pauseCalls = 0;
    sandbox.startHoldOriginal(subpara1);
    const sub1HeldWhenPaused = subpara1.classList.contains('holding-original');
    const sub2HeldWhenPaused = subpara2.classList.contains('holding-original');
    const docHeldWhenPaused = docEl.classList.contains('holding-original');
    sandbox.endHoldOriginal();
    const playCallsWhenNotPlaying = playCalls;
    const pauseCallsWhenNotPlaying = pauseCalls;

    // Case B: Audio IS playing -> hold subpara1 pauses audio -> release resumes audio
    sandbox.playPara(1, true);
    playCalls = 0;
    pauseCalls = 0;
    sandbox.startHoldOriginal(subpara1);
    const pausedDuringHold = pauseCalls === 1 && getEl('playToggle').innerHTML === 'PLAY';
    const sub1HeldWhilePlaying = subpara1.classList.contains('holding-original');
    sandbox.endHoldOriginal();
    const resumedAfterRelease = playCalls === 1 && getEl('playToggle').innerHTML === 'PAUSE';
    const sub1ReleasedAfterHold = !subpara1.classList.contains('holding-original');

    console.log(JSON.stringify({
        sub1HeldWhenPaused,
        sub2HeldWhenPaused,
        docHeldWhenPaused,
        playCallsWhenNotPlaying,
        pauseCallsWhenNotPlaying,
        pausedDuringHold,
        sub1HeldWhilePlaying,
        resumedAfterRelease,
        sub1ReleasedAfterHold
    }));
    """
    res = subprocess.run(
        ["node", "-e", node_script, str(export_js)],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"Node failed: {res.stderr}"
    data = json.loads(res.stdout.strip())
    assert data["sub1HeldWhenPaused"] is True
    assert data["sub2HeldWhenPaused"] is False
    assert data["docHeldWhenPaused"] is False
    assert data["playCallsWhenNotPlaying"] == 0
    assert data["pauseCallsWhenNotPlaying"] == 0
    assert data["pausedDuringHold"] is True
    assert data["sub1HeldWhilePlaying"] is True
    assert data["resumedAfterRelease"] is True
    assert data["sub1ReleasedAfterHold"] is True



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
