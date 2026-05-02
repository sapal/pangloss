import hashlib
import json
import os
from pathlib import Path
from typing import Optional, List

class CacheEngine:
    def __init__(self, input_file: str, options: dict):
        self.input_file = Path(input_file)
        self.job_id = options.get("render_only") or self._generate_job_id(input_file, options)
        self.cache_root = self.input_file.parent / ".pangloss"
        self.cache_dir = self.cache_root / self.job_id
        self.audio_dir = self.cache_dir / "audio_chunks"
        
        if not options.get("render_only"):
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self.audio_dir.mkdir(parents=True, exist_ok=True)

    def _generate_job_id(self, input_file: str, options: dict) -> str:
        # We only hash the relevant options for the job ID
        relevant_options = {
            "target_lang": options.get("target_lang"),
            "source_lang": options.get("source_lang"),
            "level": options.get("level"),
        }
        
        try:
            with open(input_file, "rb") as f:
                file_content = f.read()
        except FileNotFoundError:
            # If render-only and file is missing, we might have issues, 
            # but usually build mode requires the file.
            file_content = b""
            
        file_hash = hashlib.sha256(file_content).hexdigest()
        options_str = json.dumps(relevant_options, sort_keys=True)
        combined = f"{file_hash}_{options_str}".encode()
        return hashlib.sha256(combined).hexdigest()[:12]

    def save_metadata(self, metadata: dict):
        with open(self.cache_dir / "metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)

    def load_metadata(self) -> Optional[dict]:
        path = self.cache_dir / "metadata.json"
        if path.exists():
            with open(path, "r") as f:
                return json.load(f)
        return None

    def save_audio_chunk(self, paragraph_id: int, wav_data: bytes):
        with open(self.audio_dir / f"{paragraph_id}.wav", "wb") as f:
            f.write(wav_data)

    def get_audio_chunk_path(self, paragraph_id: int) -> Optional[Path]:
        path = self.audio_dir / f"{paragraph_id}.wav"
        return path if path.exists() else None

    def list_cached_audio(self) -> List[int]:
        ids = []
        if not self.audio_dir.exists():
            return []
        for f in self.audio_dir.glob("*.wav"):
            try:
                ids.append(int(f.stem))
            except ValueError:
                continue
        return sorted(ids)
    
    def get_all_audio_paths(self, paragraph_ids: List[int]) -> List[str]:
        paths = []
        for pid in paragraph_ids:
            path = self.get_audio_chunk_path(pid)
            if path:
                paths.append(str(path))
        return paths
