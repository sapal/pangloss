import wave
import io
import subprocess
import os

def pcm_to_wav(pcm_data: bytes, sample_rate: int = 24000) -> bytes:
    """Wraps raw PCM data (Linear16, Mono) into a WAV container."""
    with io.BytesIO() as wav_io:
        with wave.open(wav_io, 'wb') as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm_data)
        return wav_io.getvalue()

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
