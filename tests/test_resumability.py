import unittest
from unittest.mock import MagicMock, patch
from pangloss.cli import run_build
import argparse
from pathlib import Path
import json

class TestResumability(unittest.TestCase):
    @patch('pangloss.cli.GeminiAPI')
    @patch('pangloss.cli.CacheEngine')
    @patch('builtins.open', new_callable=unittest.mock.mock_open, read_data="Para 1\n\nPara 2\n\nPara 3")
    def test_run_build_resumes_correctly(self, mock_file, mock_engine_class, mock_api_class):
        # Setup mocks
        mock_engine = mock_engine_class.return_value
        mock_engine.job_id = "test_job"
        
        # Simulate partial metadata (Chunk 1 already processed)
        # "Para 1\n\nPara 2" is indices 0 to 14 (assuming words_per_chunk=4 as in our other test)
        mock_engine.load_metadata.return_value = {
            "title": "Existing Title",
            "characters": [],
            "difficultWords": [],
            "paragraphs": [{"id": 1, "text": "Old stuff"}],
            "processed_chunks": [{"start": 0, "end": 14}]
        }
        mock_engine.list_cached_audio.return_value = [1]
        
        mock_api = mock_api_class.return_value
        mock_api.process_chunk.return_value = {
            "title": "Existing Title",
            "characters": [],
            "difficultWords": [],
            "paragraphs": [{"id": 1, "originalText": "Para 3", "translatedText": "Para 3 DE", "turns": []}]
        }
        mock_api.generate_tts.return_value = b"fake_audio"
        
        # Create args
        args = argparse.Namespace(
            filepath="fake.md",
            target_lang="German",
            source_lang="English",
            level="B1",
            output_dir="./out",
            render_only=None,
            import_characters=None,
            serve=False
        )
        
        # Run build (we need to bypass chunk_text to use predictable indices or just use a small words_per_chunk)
        # In cli.py run_build, it calls chunk_text(text). 
        # With "Para 1\n\nPara 2\n\nPara 3" and default words_per_chunk (2000), it will be 1 chunk.
        # Let's patch chunk_text to return two specific chunks.
        with patch('pangloss.cli.chunk_text') as mock_chunk_text:
            mock_chunk_text.return_value = [
                {"text": "Para 1\n\nPara 2", "start": 0, "end": 14},
                {"text": "Para 3", "start": 16, "end": 22}
            ]
            
            # We need to mock export_results as well to avoid FFmpeg calls
            with patch('pangloss.cli.export_results') as mock_export:
                mock_export.return_value = "fake.html"
                run_build(args)
        
        # VERIFICATION
        
        # 1. API should ONLY be called for the second chunk (start=16)
        # Note: i is index in all_chunks. Loop is: for i, chunk_info in enumerate(all_chunks):
        # It skips if chunk_info["start"] in processed_starts.
        mock_api.process_chunk.assert_called_once()
        args_list = mock_api.process_chunk.call_args_list[0]
        # chunk text passed to API should be "Para 3"
        self.assertEqual(args_list[0][0], "Para 3")
        
        # 2. API should be called for TTS of the new paragraph (id 2)
        # Para 1 was already in cached_audio_ids, so it should be skipped.
        # But wait, run_build re-indexes paragraphs. base_id = max([p["id"] for p in metadata["paragraphs"]] + [0])
        # Metadata had id 1. New para gets id 2.
        mock_api.generate_tts.assert_called_once()
        tts_args = mock_api.generate_tts.call_args[0]
        self.assertEqual(tts_args[0]["id"], 2)

if __name__ == "__main__":
    unittest.main()
