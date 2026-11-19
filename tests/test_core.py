import os
import shutil
import json
import wave
import io
from pathlib import Path
from unittest.mock import MagicMock, patch

from pangloss.cli import chunk_text
from pangloss.engine import CacheEngine
from pangloss.audio import pcm_to_wav, concat_wavs
from pangloss.api import GeminiAPI, clean_text_for_tts, partition_paragraph_into_subchunks

def test_chunk_text():
    text = "Para 1\n\nPara 2\n\nPara 3"
    chunks = chunk_text(text, words_per_chunk=4)
    assert len(chunks) == 2
    assert chunks[0]["text"] == "Para 1\n\nPara 2"
    assert chunks[0]["start"] == 0
    assert chunks[0]["end"] == 14
    assert chunks[1]["text"] == "Para 3"
    assert chunks[1]["start"] == 16
    assert chunks[1]["end"] == 22

def test_job_id_consistency():
    dummy_file = Path("test_story.txt")
    dummy_file.write_text("Once upon a time...")
    
    options1 = {"target_lang": "German", "source_lang": "English", "level": "B1"}
    options2 = {"target_lang": "German", "source_lang": "English", "level": "B1", "lite": True}
    options3 = {"target_lang": "Spanish", "source_lang": "English", "level": "B1"}
    
    engine1 = CacheEngine(str(dummy_file), options1)
    engine2 = CacheEngine(str(dummy_file), options2)
    engine3 = CacheEngine(str(dummy_file), options3)
    
    assert engine1.job_id == engine2.job_id
    assert engine1.job_id != engine3.job_id
    assert "audio_chunks_lite" in str(engine2.audio_dir)
    
    # Cleanup
    if dummy_file.exists():
        dummy_file.unlink()
    if engine1.cache_root.exists():
        shutil.rmtree(engine1.cache_root)

def test_pcm_to_wav():
    pcm_data = b'\x00\x00' * 100
    wav_data = pcm_to_wav(pcm_data, sample_rate=24000)
    
    with io.BytesIO(wav_data) as f:
        with wave.open(f, 'rb') as w:
            assert w.getnchannels() == 1
            assert w.getsampwidth() == 2
            assert w.getframerate() == 24000
            assert w.readframes(100) == pcm_data
            
    # Verify that existing WAV is not double-wrapped
    assert pcm_to_wav(wav_data) == wav_data

def test_clean_text_for_tts():
    raw = "# Die Quanten-Teekanne\n\nArthur sah etwas **Unmögliches**.\n\n## Die Entdeckung\n\n„Gib mir den Zucker!«"
    cleaned = clean_text_for_tts(raw)
    assert "#" not in cleaned
    assert "**" not in cleaned
    assert "<long pause>" in cleaned
    assert "<short pause>" in cleaned
    assert "Unmögliches" in cleaned
    assert "Gib mir den Zucker!" in cleaned

def test_partition_narrator_splitting():
    # Test solo narrator block of 8 sentences gets split into chunks of max 3 sentences
    turns = [{"speaker": "Narrator", "text": f"Satz {i}."} for i in range(1, 9)]
    chunks = partition_paragraph_into_subchunks(turns, max_narrator_solo_sentences=3)
    assert len(chunks) == 3
    assert len(chunks[0]) == 3
    assert len(chunks[1]) == 3
    assert len(chunks[2]) == 2

def test_token_usage_and_tts_generation():
    with patch('google.genai.Client'):
        api = GeminiAPI(api_key="fake")
        assert api.text_model == "gemini-3.8-flash"
        assert "gemini-3.8-flash" in api.usage
        assert "gemini-3.8-flash-tts" in api.usage
        assert "gemini-3.8-flash-lite-tts" in api.usage
        
        # Test translation tracking (including thinking tokens billed as output tokens)
        mock_response = MagicMock()
        mock_response.text = '{"title": "Test Story"}'
        mock_response.usage_metadata.prompt_token_count = 120
        mock_response.usage_metadata.candidates_token_count = 350
        mock_response.usage_metadata.thoughts_token_count = 50
        api.client.models.generate_content.return_value = mock_response
        
        api.process_chunk("Chunk content", "German", "B1", "English", True, {
            "title": "", "characters": [], "difficultWords": [], "paragraphs": []
        }, 0, 1)
        assert api.client.models.generate_content.call_args.kwargs["model"] == "gemini-3.8-flash"
        assert api.usage["gemini-3.8-flash"]["input_tokens"] == 120
        assert api.usage["gemini-3.8-flash"]["output_tokens"] == 400
        expected_cost = 120 * (0.75 / 1_000_000) + 400 * (3.75 / 1_000_000)
        assert abs(api.get_session_cost() - expected_cost) < 1e-12

        # Test find_character_merges_with_llm uses gemini-3.8-flash and records tokens
        mock_merge_response = MagicMock()
        mock_merge_response.text = '{"merges": []}'
        mock_merge_response.usage_metadata.prompt_token_count = 20
        mock_merge_response.usage_metadata.candidates_token_count = 10
        mock_merge_response.usage_metadata.thoughts_token_count = 5
        api.client.models.generate_content.return_value = mock_merge_response
        merges = api.find_character_merges_with_llm([{"name": "A"}, {"name": "B"}])
        assert merges == []
        assert api.client.models.generate_content.call_args.kwargs["model"] == "gemini-3.8-flash"
        assert api.usage["gemini-3.8-flash"]["input_tokens"] == 140
        assert api.usage["gemini-3.8-flash"]["output_tokens"] == 415
        
        # Test 3.8 Flash Lite TTS
        sample_wav = pcm_to_wav(b'\x01\x00' * 50, sample_rate=24000)
        mock_audio_response = MagicMock()
        mock_audio_response.usage_metadata.prompt_token_count = 80
        mock_audio_response.usage_metadata.candidates_token_count = 500
        mock_part = MagicMock()
        mock_part.inline_data.data = sample_wav
        mock_audio_response.candidates = [MagicMock(content=MagicMock(parts=[mock_part]))]
        
        api_lite = GeminiAPI(api_key="fake", lite=True)
        api_lite.client.models.generate_content.return_value = mock_audio_response
        res = api_lite.generate_tts({
            "id": 1,
            "turns": [{"speaker": "Narrator", "text": "Dies ist ein Test"}]
        }, [{"name": "Narrator", "voice": "Rasalgethi", "voiceProfile": "Clear voice"}])
        assert res.startswith(b"RIFF")
        assert api_lite.usage["gemini-3.8-flash-lite-tts"]["input_tokens"] == 80
        assert api_lite.usage["gemini-3.8-flash-lite-tts"]["output_tokens"] == 500

def test_dry_run_and_dump_requests(tmp_path):
    dump_dir = str(tmp_path / "dumped")
    api = GeminiAPI(api_key="fake", lite=True, dry_run=True, dump_requests=dump_dir)
    
    audio_data = api.generate_tts({
        "id": 1,
        "turns": [
            {"speaker": "Narrator", "text": "# Once upon a time."},
            {"speaker": "Arthur", "text": "Is that a teapot?"}
        ]
    }, [
        {"name": "Narrator", "voice": "Kore", "voiceProfile": "Calm"},
        {"name": "Arthur", "voice": "Puck", "voiceProfile": "Anxious"}
    ])
    assert audio_data.startswith(b"RIFF")
    
    chunk_res = api.process_chunk("Test chunk", "German", "B1", "English", True, {
        "title": "Story", "characters": [], "difficultWords": [], "paragraphs": []
    }, 0, 1)
    assert chunk_res is not None
    
    dumped_files = list((tmp_path / "dumped").glob("*.json"))
    assert len(dumped_files) == 2

    translate_dump = next(f for f in dumped_files if "translate" in f.name)
    with open(translate_dump, "r") as f:
        translate_data = json.load(f)
        assert translate_data["model"] == "gemini-3.8-flash"

    tts_dump = next(f for f in dumped_files if "tts" in f.name)
    with open(tts_dump, "r") as f:
        data = json.load(f)
        assert data["model"] == "gemini-3.8-flash-lite-tts"
        # Verify markdown heading was converted to pause and not raw '#'
        parts = data["contents"][0]["parts"]
        assert not any("#" in p["text"] for p in parts)

def test_import_characters():
    engine = CacheEngine("tests/sample.md", {})
    other = engine.load_other_metadata("7f0c79bb3cd6")
    assert other is not None
    assert len(other["characters"]) == 3
    assert other["characters"][0]["name"] == "Narrator"

def test_chunk_timings_and_ranges():
    from pangloss.api import GeminiAPI, compute_chunk_ranges, partition_paragraph_into_subchunks
    api = GeminiAPI(api_key="fake", lite=True, dry_run=True)
    
    p = {
        "id": 1,
        "originalText": "Hello world. How are you?\n\nFine.",
        "translatedText": "Hallo Welt. Wie geht es dir?\n\nGut.",
        "turns": [
            {"speaker": "Narrator", "text": "Hallo Welt. "},
            {"speaker": "Arthur", "text": "Wie geht es dir?\n\n"},
            {"speaker": "Elara", "text": "Gut."}
        ]
    }
    chars = [
        {"name": "Narrator", "voice": "Rasalgethi", "voiceProfile": "Calm"},
        {"name": "Arthur", "voice": "Alnilam", "voiceProfile": "Deep"},
        {"name": "Elara", "voice": "Aoede", "voiceProfile": "Soft"}
    ]
    audio_data = api.generate_tts(p, chars)
    assert audio_data.startswith(b"RIFF")
    assert "chunks" in p
    assert len(p["chunks"]) >= 1
    
    for c in p["chunks"]:
        assert "chunk_index" in c
        assert "start_sec" in c
        assert "end_sec" in c
        assert "start_char" in c
        assert "end_char" in c
        assert "speakers" in c
        assert c["end_sec"] >= c["start_sec"]
        assert c["end_char"] >= c["start_char"]

def test_ensure_chunk_metadata_from_wav(tmp_path):
    from pangloss.export import ensure_chunk_metadata
    from pangloss.audio import concat_wavs, pcm_to_wav
    
    # Create two chunks separated by 150ms silence
    c1 = pcm_to_wav(b'\x01\x00' * 2400) # 0.1s
    c2 = pcm_to_wav(b'\x02\x00' * 4800) # 0.2s
    combined = concat_wavs([c1, c2], pause_ms=150)
    
    wav_path = tmp_path / "1.wav"
    with open(wav_path, "wb") as f:
        f.write(combined)
        
    meta = {
        "title": "Story",
        "characters": [],
        "difficultWords": [],
        "paragraphs": [
            {
                "id": 1,
                "translatedText": "Part one. Part two. Part three.",
                "turns": [
                    {"speaker": "Arthur", "text": "Part one. "},
                    {"speaker": "Colin", "text": "Part two. "},
                    {"speaker": "Inspector Barnes", "text": "Part three."}
                ]
            }
        ]
    }
    
    ensure_chunk_metadata(meta, tmp_path)
    p = meta["paragraphs"][0]
    assert "chunks" in p
    assert len(p["chunks"]) == 2
    assert p["chunks"][0]["start_sec"] == 0.0
    assert "Arthur" in p["chunks"][0]["speakers"]
    assert "Inspector Barnes" in p["chunks"][1]["speakers"]


def test_compute_chunk_ranges_no_word_breaks():
    from pangloss.api import compute_chunk_ranges, snap_to_word_boundary

    text = "„Professor McGonagall hat es mir nicht erzählt“, sagte Harrys Stimme."
    # Turn has vocal tag <whisper>...</whisper> that is not in translated_text
    sub_chunks = [
        [{"speaker": "Minerva", "text": "<whisper>„Es tut mir leid, Albus“</whisper>"}],
        [{"speaker": "Harry", "text": "„Professor McGonagall hat es mir nicht erzählt“, sagte Harrys Stimme."}]
    ]
    ranges = compute_chunk_ranges(sub_chunks, text)
    assert len(ranges) == 2
    # Boundary between chunk 0 and 1 must NOT be in the middle of McGonagall
    boundary = ranges[0][1]
    assert not (text[boundary - 1].isalnum() and text[boundary].isalnum())
    assert ranges[1][0] == boundary


def test_copyright_error_detection():
    from pangloss.models import is_copyright_error, CopyrightRestrictionError

    assert is_copyright_error(CopyrightRestrictionError("recitation"))
    assert is_copyright_error(Exception("Recitation check failed"))
    assert is_copyright_error(ValueError("Contains copyrighted material"))
    assert is_copyright_error(ValueError("I cannot provide a full line-by-line translation of this text, but I can provide a general summary"))
    assert is_copyright_error(ValueError("I cannot provide a verbatim translation of this text. However, I can offer a general summary"))
    assert is_copyright_error(ValueError("I cannot provide a full translation of this excerpt, but I can offer a brief, general summary"))
    assert not is_copyright_error(ValueError("JSON decode error: Expecting value"))
    assert not is_copyright_error(RuntimeError("API quota exceeded"))



def test_retry_with_pangloss_no_retry_on_copyright():
    from pangloss.utils import retry_with_pangloss
    from pangloss.models import CopyrightRestrictionError

    calls = 0

    @retry_with_pangloss(max_retries=3, initial_delay=0.01)
    def fail_with_copyright():
        nonlocal calls
        calls += 1
        raise CopyrightRestrictionError("Copyright refused")

    try:
        fail_with_copyright()
    except CopyrightRestrictionError:
        pass

    assert calls == 1  # Should not retry!


def test_process_chunk_with_fallback():
    from pangloss.cli import process_chunk_with_fallback
    from pangloss.models import CopyrightRestrictionError

    api = MagicMock()

    # Case 1: Non-copyright error is re-raised directly
    api.process_chunk.side_effect = ValueError("Some other API error")
    try:
        process_chunk_with_fallback(api, "Para 1\n\nPara 2", "German", "B1", "English", True, {
            "title": "", "characters": [], "difficultWords": [], "paragraphs": []
        }, 0, 1)
        assert False, "Should have re-raised ValueError"
    except ValueError as e:
        assert "Some other API error" in str(e)

    # Case 2: Slicing on copyright error, slice 1 succeeds, slice 2 succeeds
    text = "Paragraph 1\n\nParagraph 2"
    def mock_process_chunk(chunk, target_lang, level, source_lang, is_first, metadata, chunk_index, total_chunks):
        if chunk == text:
            raise CopyrightRestrictionError("Recitation blocked")
        return {
            "title": "Title" if is_first else "",
            "characters": [{"name": f"Char_{chunk[:5]}"}],
            "difficultWords": [{"word": f"Word_{chunk[:5]}"}],
            "paragraphs": [{"id": 1, "originalText": chunk, "translatedText": f"TR_{chunk}", "turns": [{"speaker": "Narrator", "text": chunk}]}]
        }

    api.process_chunk.side_effect = mock_process_chunk
    res = process_chunk_with_fallback(api, text, "German", "B1", "English", True, {
        "title": "", "characters": [], "difficultWords": [], "paragraphs": []
    }, 0, 1)

    assert res["title"] == "Title"
    assert len(res["paragraphs"]) == 2
    assert res["paragraphs"][0]["id"] == 1
    assert res["paragraphs"][1]["id"] == 2
    assert res["paragraphs"][0]["originalText"] == "Paragraph 1"
    assert res["paragraphs"][1]["originalText"] == "Paragraph 2"

    # Case 3: Copyright error reoccurs on atomic paragraph -> fallback untranslated
    def mock_process_chunk_always_fails(chunk, *args, **kwargs):
        raise CopyrightRestrictionError("Recitation blocked")

    api.process_chunk.side_effect = mock_process_chunk_always_fails
    res_fallback = process_chunk_with_fallback(api, "Atomic copyright paragraph", "German", "B1", "English", False, {
        "title": "Existing", "characters": [], "difficultWords": [], "paragraphs": []
    }, 0, 1)

    assert len(res_fallback["paragraphs"]) == 1
    p = res_fallback["paragraphs"][0]
    assert p["skip_audio"] is True
    assert p["untranslated"] is True
    assert p["turns"] == []
    assert "Atomic copyright paragraph" in p["originalText"]


def test_merge_wavs_tempfile_and_mp3_chunk_caching(tmp_path):
    from pangloss.audio import merge_wavs_to_mp3, pcm_to_wav
    from pangloss.export import export_results

    wav1 = tmp_path / "1.wav"
    wav1.write_bytes(pcm_to_wav(b"\x00\x00" * 2400))

    # 1. Verify merge_wavs_to_mp3 uses a tempfile instead of "concat_list.txt" in cwd
    recorded_args = []
    def fake_run(cmd, **kwargs):
        recorded_args.append(cmd)
        # Ensure concat_list.txt was NOT created in current working directory
        assert not Path("concat_list.txt").exists()
        Path(cmd[-1]).write_bytes(b"FAKE_MP3")
        return MagicMock(returncode=0)

    with patch("pangloss.audio.subprocess.run", side_effect=fake_run):
        out_mp3 = tmp_path / "out.mp3"
        merge_wavs_to_mp3([str(wav1)], str(out_mp3))
        assert len(recorded_args) == 1
        concat_idx = recorded_args[0].index("-i") + 1
        concat_file_arg = recorded_args[0][concat_idx]
        assert concat_file_arg != "concat_list.txt"
        assert not Path(concat_file_arg).exists()  # cleaned up in finally

    # 2. Verify export_results caches .mp3 chunks in audio_dir and reuses them on subsequent calls
    meta = {
        "title": "Cache Test",
        "characters": [{"name": "Narrator", "description": "N", "voice": "Puck", "voiceProfile": "Calm"}],
        "difficultWords": [],
        "paragraphs": [
            {"id": 1, "originalText": "Hello.", "translatedText": "Hallo.", "turns": [{"speaker": "Narrator", "text": "Hallo."}]}
        ],
    }
    encode_calls = 0
    def fake_wav_to_mp3(data):
        nonlocal encode_calls
        encode_calls += 1
        return b"ENCODED_MP3_BYTES"

    with patch("pangloss.export.merge_wavs_to_mp3"), patch("pangloss.export.wav_to_mp3_bytes", side_effect=fake_wav_to_mp3):
        export_results(meta, tmp_path, str(tmp_path / "out"), "English", "German", "B1")
        assert encode_calls == 1
        assert (tmp_path / "1.mp3").exists()

        # Second export should reuse cached 1.mp3 without calling wav_to_mp3_bytes again
        export_results(meta, tmp_path, str(tmp_path / "out"), "English", "German", "B1")
        assert encode_calls == 1


def test_partition_narrator_case_and_alias_insensitive():
    # 1. Multiple solo turns with lowercase "narrator"
    turns_lower = [{"speaker": "narrator", "text": f"Sentence {i}."} for i in range(1, 10)]
    chunks_lower = partition_paragraph_into_subchunks(turns_lower, max_narrator_solo_sentences=3)
    assert len(chunks_lower) == 3
    assert all(len(c) == 3 for c in chunks_lower)

    # 2. Single 9-sentence turn with "Erzähler"
    long_erzaehler = [{"speaker": "Erzähler", "text": " ".join(f"Satz {i}." for i in range(1, 10))}]
    chunks_de = partition_paragraph_into_subchunks(long_erzaehler, max_narrator_solo_sentences=3)
    assert len(chunks_de) == 3
    assert all(len(c) == 1 for c in chunks_de)


def test_chunk_highlight_sync_and_proportional_wav_durations(tmp_path):
    from pangloss.api import compute_chunk_ranges
    from pangloss.export import ensure_chunk_metadata
    from pangloss.audio import pcm_to_wav

    # 1. Punctuation between probe words ("„Es, tut mir leid“") must match first occurrence,
    # not jump to a later sentence ("„Es tut mir leid, dass...“") in the next sub-paragraph!
    translated_text = (
        "Vor ihr stand ein Kind.\n\n"
        "„Es, tut mir leid“, flüsterte er mit brüchiger Stimme. „Es tut mir leid, dass ich Sie enttäuscht habe.“"
    )
    sub_chunks = [
        [{"speaker": "Narrator", "text": "Vor ihr stand ein Kind.\n\n"}],
        [{"speaker": "Harry", "text": "<whisper>„Es, tut mir leid“,</whisper> flüsterte er mit brüchiger Stimme. „Es tut mir leid, dass ich Sie enttäuscht habe.“"}],
    ]
    ranges = compute_chunk_ranges(sub_chunks, translated_text)
    assert ranges[0] == (0, 25)
    assert translated_text[ranges[1][0]:].startswith("„Es, tut mir leid“")

    # 2. When a WAV file has 1 continuous stream (or != len(sub_chunks) silence parts) of 60s
    # and saved p["chunks"] had only 1 chunk (or None), ensure_chunk_metadata must distribute
    # the 60s proportionally across all sub_chunks instead of using 5.0s fallback or leaving stale 1-chunk list.
    wav_60s = pcm_to_wav(b"\x01\x00" * (24000 * 60), sample_rate=24000)
    (tmp_path / "1.wav").write_bytes(wav_60s)

    meta = {
        "title": "Sync Test",
        "characters": [],
        "difficultWords": [],
        "paragraphs": [
            {
                "id": 1,
                "originalText": "Part 1.\n\nPart 2.",
                "translatedText": "Erster Teil ist zwanzig.\n\nZweiter Teil ist genauso.",
                "turns": [
                    {"speaker": "Arthur", "text": "Erster Teil ist zwanzig.\n\n"},
                    {"speaker": "Elara", "text": "Part 1b."},
                    {"speaker": "Inspector Barnes", "text": "Zweiter Teil ist genauso."},
                ],
                # Stale 1-chunk metadata from before sub-chunking changed
                "chunks": [
                    {"chunk_index": 0, "start_sec": 0.0, "end_sec": 60.0, "start_char": 0, "end_char": 51, "speakers": ["Arthur"]}
                ],
            }
        ],
    }
    ensure_chunk_metadata(meta, tmp_path)
    chunks = meta["paragraphs"][0]["chunks"]
    assert len(chunks) == 2
    assert chunks[0]["end_sec"] > 15.0  # Not 5.0s fallback!
    assert abs(chunks[-1]["end_sec"] - 60.0) < 1.0

    # 3. When a single chunk spans across multiple sub-paragraphs (.chunk-p1-c0 in both row 0 and row 1),
    # highlightActiveChunk should highlight only the sub-paragraph currently being spoken at player.currentTime,
    # not highlight the next sub-paragraph prematurely!
    import subprocess
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
                originalText: 'First subpara.\\n\\nSecond subpara.',
                translatedText: 'Erster Absatz ist lang.\\n\\nZweiter Absatz folgt.',
                turns: [{speaker: 'Narrator', text: 'Erster Absatz ist lang.\\n\\nZweiter Absatz folgt.'}],
                chunks: [{chunk_index: 0, start_sec: 0, end_sec: 10, start_char: 0, end_char: 46, speakers: ['Narrator']}]
            }],
            characters: [],
            difficultWords: []
        }))
        .replace('__AUDIO_DATA_JSON__', JSON.stringify({1: 'data:audio/mp3;base64,AAA'}))
        .replace('__PLAY_SVG_JSON__', '""')
        .replace('__PAUSE_SVG_JSON__', '""')
        .replace(/__[A-Z][A-Z0-9_]*__/g, '""');

    const makeSpan = (text) => {
        const cls = new Set(['chunk-target', 'chunk-p1-c0']);
        return {
            textContent: text,
            classList: {
                add(c){ cls.add(c); },
                remove(c){ cls.delete(c); },
                contains(c){ return cls.has(c); }
            },
            getBoundingClientRect: () => ({ top: 0, height: 20 })
        };
    };
    const span0 = makeSpan('Erster Absatz ist lang.');
    const span1 = makeSpan('Zweiter Absatz folgt.');

    const mockEl = (id) => ({
        id, innerHTML: '', textContent: '', innerText: '', style: {}, dataset: {},
        currentTime: 0, playbackRate: 1.0, clientHeight: 500, scrollTop: 0,
        play(){}, pause(){}, scrollTo(){},
        getBoundingClientRect: () => ({ top: 0, height: 500 }),
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
            querySelectorAll: (sel) => {
                if (sel === '.chunk-p1-c0' || sel === '.active-chunk') return [span0, span1];
                return [];
            },
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

    sandbox.playPara(1, true);
    getEl('player').currentTime = 1.0; // 10% into 10s chunk -> still in span0!
    sandbox.highlightActiveChunk(0);
    const earlySpan0 = span0.classList.contains('active-chunk');
    const earlySpan1 = span1.classList.contains('active-chunk');

    getEl('player').currentTime = 8.0; // 80% into 10s chunk -> now in span1!
    sandbox.highlightActiveChunk(0);
    const lateSpan0 = span0.classList.contains('active-chunk');
    const lateSpan1 = span1.classList.contains('active-chunk');

    console.log(JSON.stringify({ earlySpan0, earlySpan1, lateSpan0, lateSpan1 }));
    """
    res = subprocess.run(["node", "-e", node_script, str(export_js)], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    js_data = json.loads(res.stdout.strip())
    assert js_data["earlySpan0"] is True
    assert js_data["earlySpan1"] is False, "Second sub-paragraph must NOT be highlighted while first sub-paragraph is playing!"
    assert js_data["lateSpan0"] is False
    assert js_data["lateSpan1"] is True


def test_paragraph_1_highlight_not_ahead_of_audio_with_tooltips_and_subparagraphs():
    """
    Verify that on Paragraph 1 of Die Quanten-Teekanne:
    1) Hidden .tooltip dictionary explanations inside .chunk-target spans do NOT inflate
       sub-paragraph length weights in getActiveSubTargetForChunk (causing early highlight jumps).
    2) ensure_chunk_metadata subdivides chunks that span multiple sub-paragraphs (\n\n) and snaps
       split timestamps to actual acoustic pauses in the WAV file so each sub-paragraph has
       accurate start_sec / end_sec.
    """
    import copy
    import subprocess
    from pangloss.export import ensure_chunk_metadata

    meta_path = Path(__file__).parent / ".pangloss" / "1144ef38aae2" / "metadata.json"
    audio_dir = Path(__file__).parent / ".pangloss" / "1144ef38aae2" / "audio_chunks_lite"
    assert meta_path.exists()

    with open(meta_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    # 1) Test JS getActiveSubTargetForChunk with tooltips inside later sub-paragraphs (unsplit Chunk 0 case)
    export_js = Path(__file__).parent.parent / "pangloss" / "templates" / "export.js"
    node_script = r"""
    const fs = require('fs');
    const vm = require('vm');
    let code = fs.readFileSync(process.argv[1], 'utf8');
    const meta = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));

    code = code
        .replace('__METADATA_JSON__', JSON.stringify(meta))
        .replace('__AUDIO_DATA_JSON__', JSON.stringify({1: "data:audio/mp3;base64,AAAA"}))
        .replace('__PLAY_SVG_JSON__', JSON.stringify('<svg>play</svg>'))
        .replace('__PAUSE_SVG_JSON__', JSON.stringify('<svg>pause</svg>'));

    let renderedStoryHtml = '';
    const makeClassList = (initial = []) => {
        const set = new Set(initial);
        return {
            add: (...cls) => cls.forEach(c => set.add(c)),
            remove: (...cls) => cls.forEach(c => set.delete(c)),
            toggle: (c) => set.has(c) ? set.delete(c) : set.add(c),
            contains: (c) => set.has(c)
        };
    };

    const mockEl = (id) => ({
        id, innerHTML: '', innerText: '', textContent: '', style: {}, dataset: {},
        currentTime: 0, duration: 29.71, playbackRate: 1,
        play(){}, pause(){}, scrollTo(){},
        getBoundingClientRect: () => ({ top: 0, height: 500 }),
        classList: makeClassList(),
        addEventListener(){}, appendChild(){}, querySelectorAll(){ return []; },
        closest(){ return null; }
    });
    const elements = {};
    const getEl = (id) => {
        if (!elements[id]) elements[id] = mockEl(id);
        return elements[id];
    };

    let chunkSpans = [];
    const sandbox = {
        document: {
            getElementById: (id) => getEl(id),
            querySelector: () => null,
            querySelectorAll: (sel) => {
                if (sel === '.chunk-p1-c0' || sel === '.active-chunk') return chunkSpans;
                return [];
            },
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

    // Parse rendered chunk-p1-c0 spans from story HTML, simulating browser textContent (which includes .tooltip text!)
    const storyHtml = getEl('story').innerHTML;
    const spanRegex = /<span class="chunk-target chunk-p1-c0"([^>]*)>([\s\S]*?)<\/span>(?=<\/h|<\/div|<span class="chunk-target)/g;
    let m;
    while ((m = spanRegex.exec(storyHtml)) !== null) {
        const attrs = m[1];
        const inner = m[2];
        const textWithTooltips = inner.replace(/<[^>]+>/g, '');
        const spokenLenMatch = attrs.match(/data-spoken-len="([^"]+)"/);
        const dataset = {};
        if (spokenLenMatch) dataset.spokenLen = spokenLenMatch[1];
        chunkSpans.push({
            innerHTML: inner,
            textContent: textWithTooltips,
            dataset,
            classList: makeClassList(['chunk-target', 'chunk-p1-c0']),
            getBoundingClientRect: () => ({ top: 100, height: 30 })
        });
    }

    sandbox.playPara(1, true);
    // At t = 7.5s, the narrator is speaking Row 1 ("Es war ein kalter Morgen in London...").
    // Row 2 ("## Die Entdeckung") does not start until 12.3s!
    getEl('player').currentTime = 7.5;
    sandbox.highlightActiveChunk(0);
    const activeIdxAt7_5 = chunkSpans.findIndex(s => s.classList.contains('active-chunk'));
    console.log(JSON.stringify({ spanCount: chunkSpans.length, activeIdxAt7_5 }));
    """
    res = subprocess.run(["node", "-e", node_script, str(export_js), str(meta_path)], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    js_out = json.loads(res.stdout.strip())
    assert js_out["spanCount"] >= 5
    assert js_out["activeIdxAt7_5"] == 1, (
        f"At t=7.5s in Paragraph 1, Row 1 ('Es war ein kalter Morgen...') should be highlighted, "
        f"got row {js_out['activeIdxAt7_5']} (hidden tooltip text inflated later rows!)"
    )

    # 2) Test ensure_chunk_metadata subdivides Paragraph 1 across \n\n and snaps to WAV acoustic pauses
    meta_copy = copy.deepcopy(metadata)
    ensure_chunk_metadata(meta_copy, audio_dir)
    p1_chunks = meta_copy["paragraphs"][0]["chunks"]
    assert len(p1_chunks) == 6, f"Expected 6 sub-paragraph chunks in Paragraph 1, got {len(p1_chunks)}"
    # Check acoustic alignment against 1.wav:
    # Chunk 0: "# Die Quanten-Teekanne" (~0.0s - ~3.0s)
    assert 2.0 <= p1_chunks[0]["end_sec"] <= 3.3
    # Chunk 1: "Es war ein kalter Morgen..." (~3.0s - ~12.3s)
    assert 2.0 <= p1_chunks[1]["start_sec"] <= 3.3
    assert 11.3 <= p1_chunks[1]["end_sec"] <= 12.5
    # Chunk 2: "## Die Entdeckung" (~12.3s - ~14.1s)
    assert 12.0 <= p1_chunks[2]["start_sec"] <= 12.6
    assert 13.1 <= p1_chunks[2]["end_sec"] <= 14.3
    # Chunk 3: "„Gibst du mir bitte den Zucker?“..." (~14.1s - ~20.8s)
    assert 13.8 <= p1_chunks[3]["start_sec"] <= 14.4
    assert 19.8 <= p1_chunks[3]["end_sec"] <= 21.0






