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
        assert "gemini-3.7-flash" in api.usage
        assert "gemini-3.8-flash-tts" in api.usage
        assert "gemini-3.8-flash-lite-tts" in api.usage
        
        # Test translation tracking
        mock_response = MagicMock()
        mock_response.text = '{"title": "Test Story"}'
        mock_response.usage_metadata.prompt_token_count = 120
        mock_response.usage_metadata.candidates_token_count = 350
        api.client.models.generate_content.return_value = mock_response
        
        api.process_chunk("Chunk content", "German", "B1", "English", True, {
            "title": "", "characters": [], "difficultWords": [], "paragraphs": []
        }, 0, 1)
        assert api.usage["gemini-3.7-flash"]["input_tokens"] == 120
        assert api.usage["gemini-3.7-flash"]["output_tokens"] == 350
        
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
    assert "copyright restrictions" in p["originalText"]

