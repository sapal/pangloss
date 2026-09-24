import wave
import io
import subprocess
import os

def pcm_to_wav(pcm_data: bytes, sample_rate: int = 24000) -> bytes:
    """Wraps raw PCM data (Linear16, Mono) into a WAV container."""
    if pcm_data.startswith(b"RIFF"):
        return pcm_data
    with io.BytesIO() as wav_io:
        with wave.open(wav_io, 'wb') as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm_data)
        return wav_io.getvalue()

def get_wav_duration_ms(wav_bytes: bytes) -> float:
    """Returns the duration of a WAV byte string in milliseconds."""
    if not wav_bytes.startswith(b"RIFF"):
        return 0.0
    with io.BytesIO(wav_bytes) as bio:
        with wave.open(bio, 'rb') as w:
            frames = w.getnframes()
            rate = w.getframerate()
            return (frames / float(rate)) * 1000.0

def concat_wavs(wav_bytes_list: list[bytes], pause_ms: int = 150, sample_rate: int = 24000) -> bytes:
    """Concatenates multiple WAV (or PCM) byte chunks with an optional pause."""
    if not wav_bytes_list:
        return b""
    if len(wav_bytes_list) == 1:
        return pcm_to_wav(wav_bytes_list[0], sample_rate=sample_rate)
    
    pcm_chunks = []
    for wb in wav_bytes_list:
        if wb.startswith(b"RIFF"):
            with io.BytesIO(wb) as bio:
                with wave.open(bio, 'rb') as w:
                    pcm_chunks.append(w.readframes(w.getnframes()))
        else:
            pcm_chunks.append(wb)
            
    pause_samples = int(sample_rate * (pause_ms / 1000.0))
    pause_bytes = b'\x00\x00' * pause_samples
    combined_pcm = pause_bytes.join(pcm_chunks)
    return pcm_to_wav(combined_pcm, sample_rate=sample_rate)

def merge_wavs_to_mp3(wav_paths: list[str], output_path: str):
    """Merges multiple WAV files into a single MP3 using FFmpeg."""
    list_file = "concat_list.txt"
    with open(list_file, "w") as f:
        for p in wav_paths:
            # Ensure path is absolute and escaped for ffmpeg
            abs_p = os.path.abspath(p).replace("'", "'\\''")
            f.write(f"file '{abs_p}'\n")
    
    try:
        result = subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", 
            "-i", list_file, "-acodec", "libmp3lame", output_path
        ], check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        print(f"FFmpeg merge error: {e.stderr.decode()}")
        raise
    finally:
        if os.path.exists(list_file):
            os.remove(list_file)

def wav_to_mp3_bytes(wav_data: bytes) -> bytes:
    """Encodes a single WAV blob to MP3 bytes using FFmpeg."""
    process = subprocess.Popen(
        ["ffmpeg", "-i", "pipe:0", "-f", "mp3", "pipe:1"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    stdout, stderr = process.communicate(input=wav_data)
    if process.returncode != 0:
        raise Exception(f"FFmpeg error: {stderr.decode()}")
    return stdout
