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
