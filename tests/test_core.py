import os
import shutil
from pathlib import Path
from pangloss.cli import chunk_text
from pangloss.engine import CacheEngine
from pangloss.audio import pcm_to_wav
import wave
import io

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
    # Create a dummy file
    dummy_file = Path("test_story.txt")
    dummy_file.write_text("Once upon a time...")
    
    options1 = {"target_lang": "German", "source_lang": "English", "level": "B1"}
    options2 = {"target_lang": "German", "source_lang": "English", "level": "B1"}
    options3 = {"target_lang": "Spanish", "source_lang": "English", "level": "B1"}
    
    engine1 = CacheEngine(str(dummy_file), options1)
    engine2 = CacheEngine(str(dummy_file), options2)
    engine3 = CacheEngine(str(dummy_file), options3)
    
    assert engine1.job_id == engine2.job_id
    assert engine1.job_id != engine3.job_id
    
    # Cleanup
    if dummy_file.exists():
        dummy_file.unlink()
    if engine1.cache_root.exists():
        shutil.rmtree(engine1.cache_root)

def test_pcm_to_wav():
    pcm_data = b'\x00\x00' * 100 # 100 samples of silence
    wav_data = pcm_to_wav(pcm_data, sample_rate=24000)
    
    with io.BytesIO(wav_data) as f:
        with wave.open(f, 'rb') as w:
            assert w.getnchannels() == 1
            assert w.getsampwidth() == 2
            assert w.getframerate() == 24000
            assert w.readframes(100) == pcm_data

from unittest.mock import MagicMock, patch
from pangloss.api import GeminiAPI

def test_token_usage_tracking():
    with patch('google.genai.Client') as mock_client:
        api = GeminiAPI(api_key="fake")
        
        assert "gemini-3.7-flash" in api.usage
        assert "gemini-3.1-flash-tts-preview" in api.usage
        assert api.usage["gemini-3.7-flash"]["input_tokens"] == 0
        assert api.usage["gemini-3.7-flash"]["output_tokens"] == 0
        assert api.usage["gemini-3.1-flash-tts-preview"]["input_tokens"] == 0
        assert api.usage["gemini-3.1-flash-tts-preview"]["output_tokens"] == 0
        
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
        
        mock_audio_response = MagicMock()
        mock_audio_response.usage_metadata.prompt_token_count = 80
        mock_audio_response.usage_metadata.candidates_token_count = 500
        mock_part = MagicMock()
        mock_part.inline_data.data = b"audio"
        mock_audio_response.candidates = [MagicMock(content=MagicMock(parts=[mock_part]))]
        api.client.models.generate_content.return_value = mock_audio_response
        
        api.generate_tts({
            "id": 1,
            "turns": [{"speaker": "Narrator", "text": "Dies ist ein Test"}]
        }, [{"name": "Narrator", "voice": "Puck", "voiceProfile": "Clear voice"}])
        
        assert api.usage["gemini-3.1-flash-tts-preview"]["input_tokens"] == 80
        assert api.usage["gemini-3.1-flash-tts-preview"]["output_tokens"] == 500
        
        # Verify print stats doesn't raise exception
        api.print_token_usage_statistics()

if __name__ == "__main__":
    test_chunk_text()
    test_job_id_consistency()
    test_pcm_to_wav()
    test_token_usage_tracking()
    print("All core tests passed!")
