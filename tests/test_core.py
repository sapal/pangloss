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
    assert chunks[0] == "Para 1\n\nPara 2"
    assert chunks[1] == "Para 3"

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

if __name__ == "__main__":
    test_chunk_text()
    test_job_id_consistency()
    test_pcm_to_wav()
    print("All core tests passed!")
