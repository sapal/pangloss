import unittest
from unittest.mock import MagicMock, patch
from pangloss.cli import run_build
import argparse
from pathlib import Path
import json

class TestResumability(unittest.TestCase):
    @patch.dict('os.environ', {'GEMINI_API_KEY': 'fake_key'})
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

    @patch.dict('os.environ', {'GEMINI_API_KEY': 'fake_key'})
    @patch('pangloss.cli.GeminiAPI')
    @patch('pangloss.cli.CacheEngine')
    @patch('builtins.open', new_callable=unittest.mock.mock_open, read_data="Para 1")
    def test_resume_runs_unmerged_character_dedup_and_reports_failed_tts(self, mock_file, mock_engine_class, mock_api_class):
        import io
        from contextlib import redirect_stdout

        mock_engine = mock_engine_class.return_value
        mock_engine.job_id = "test_job_2"
        metadata = {
            "title": "Existing Title",
            "characters": [
                {"name": "Harry", "description": "Boy", "voice": "Puck", "voiceProfile": "Young"},
                {"name": "Harry Potter", "description": "Wizard", "voice": "Fenrir", "voiceProfile": "Calm"}
            ],
            "difficultWords": [],
            "paragraphs": [
                {"id": 1, "originalText": "Para 1", "translatedText": "Absatz 1", "turns": [{"speaker": "Harry Potter", "text": "Hallo"}]}
            ],
            "processed_chunks": [{"start": 0, "end": 6}]
            # Note: characters_merged is NOT set!
        }
        mock_engine.load_metadata.return_value = metadata
        mock_engine.list_cached_audio.return_value = []

        mock_api = mock_api_class.return_value
        mock_api.find_character_merges_with_llm.return_value = [
            {"canonical": "Harry", "aliases": ["Harry Potter"]}
        ]
        mock_api.generate_tts.side_effect = RuntimeError("TTS quota exceeded")

        args = argparse.Namespace(
            filepath="fake.md",
            target_lang="German",
            source_lang="English",
            level="B1",
            output_dir="./out",
            render_only=None,
            import_characters=None,
            merge_characters=False,
            serve=False
        )

        buf = io.StringIO()
        with patch('pangloss.cli.chunk_text', return_value=[{"text": "Para 1", "start": 0, "end": 6}]), \
             patch('pangloss.cli.export_results', return_value="fake.html"), \
             redirect_stdout(buf):
            run_build(args)

        output = buf.getvalue()
        mock_api.find_character_merges_with_llm.assert_called_once()
        self.assertTrue(metadata.get("characters_merged"))
        self.assertEqual(len(metadata["characters"]), 1)
        self.assertIn("Failed to generate audio for 1 paragraph(s): [1]", output)

    @patch.dict('os.environ', {'GEMINI_API_KEY': 'fake_key'})
    @patch('pangloss.api.genai.Client')
    @patch('pangloss.cli.CacheEngine')
    @patch('builtins.open', new_callable=unittest.mock.mock_open, read_data="Para 1\n\nPara 2")
    def test_save_and_resume_api_costs_in_metadata(self, mock_file, mock_engine_class, mock_genai_client):
        import io
        from contextlib import redirect_stdout
        from pangloss.api import GeminiAPI

        mock_engine = mock_engine_class.return_value
        mock_engine.job_id = "test_cost_job"

        # Simulate metadata saved from a previous interrupted run where chunk 0 was translated
        # with 100,000 input tokens ($0.15) and 10,000 output tokens ($0.09) -> $0.240000
        saved_metadata = {
            "title": "Existing Title",
            "characters": [
                {"name": "Narrator", "description": "Narrator", "voice": "Rasalgethi", "voiceProfile": "Firm"}
            ],
            "difficultWords": [],
            "paragraphs": [
                {"id": 1, "originalText": "Para 1", "translatedText": "Absatz 1", "turns": [{"speaker": "Narrator", "text": "Absatz 1"}]}
            ],
            "processed_chunks": [{"start": 0, "end": 6}],
            "characters_merged": True,
            "api_usage": {
                "gemini-3.7-flash": {"input_tokens": 100_000, "output_tokens": 10_000, "cost_usd": 0.24},
            },
            "total_cost_usd": 0.24,
        }
        mock_engine.load_metadata.return_value = saved_metadata
        mock_engine.list_cached_audio.return_value = []

        # On resume, only TTS for paragraph 1 runs:
        # 20,000 input tokens ($0.01) + 50,000 output tokens ($0.45) on gemini-3.8-flash-tts -> $0.460000
        def fake_generate_tts(self_api, paragraph, characters):
            self_api.usage["gemini-3.8-flash-tts"]["input_tokens"] += 20_000
            self_api.usage["gemini-3.8-flash-tts"]["output_tokens"] += 50_000
            paragraph["chunks"] = [{
                "chunk_index": 0, "start_sec": 0.0, "end_sec": 1.0,
                "start_char": 0, "end_char": 8, "speakers": ["Narrator"]
            }]
            return b"\x00\x00" * 2400

        args = argparse.Namespace(
            filepath="fake.md",
            target_lang="German",
            source_lang="English",
            level="B1",
            output_dir="./out",
            render_only=None,
            import_characters=None,
            merge_characters=False,
            lite=False,
            dry_run=False,
            dump_requests=None,
            serve=False,
        )

        buf = io.StringIO()
        with patch.object(GeminiAPI, 'generate_tts', autospec=True, side_effect=fake_generate_tts), \
             patch('pangloss.cli.chunk_text', return_value=[{"text": "Para 1", "start": 0, "end": 6}]), \
             patch('pangloss.cli.export_results', return_value="fake.html"), \
             redirect_stdout(buf):
            run_build(args)

        output = buf.getvalue()
        # Session cost is $0.460000, previous cost was $0.240000, total cost so far is $0.700000
        self.assertAlmostEqual(saved_metadata.get("total_cost_usd"), 0.70, places=6)
        self.assertEqual(saved_metadata["api_usage"]["gemini-3.7-flash"]["input_tokens"], 100_000)
        self.assertEqual(saved_metadata["api_usage"]["gemini-3.8-flash-tts"]["output_tokens"], 50_000)
        self.assertIn("$0.460000", output)
        self.assertIn("$0.700000", output)

    @patch.dict('os.environ', {'GEMINI_API_KEY': 'fake_key'})
    @patch('pangloss.api.genai.Client')
    @patch('pangloss.cli.CacheEngine')
    @patch('builtins.open', new_callable=unittest.mock.mock_open, read_data="Para 1")
    def test_save_and_resume_gemini_3_8_flash_costs(self, mock_file, mock_engine_class, mock_genai_client):
        import io
        from contextlib import redirect_stdout
        from pangloss.api import GeminiAPI

        mock_engine = mock_engine_class.return_value
        mock_engine.job_id = "test_3_8_cost_job"

        # Prior session used gemini-3.8-flash:
        # 100,000 input ($0.75/1M = $0.075000) + 10,000 output ($3.75/1M = $0.037500) = $0.112500
        saved_metadata = {
            "title": "Existing Title",
            "characters": [
                {"name": "Narrator", "description": "Narrator", "voice": "Rasalgethi", "voiceProfile": "Firm"}
            ],
            "difficultWords": [],
            "paragraphs": [
                {"id": 1, "originalText": "Para 1", "translatedText": "Absatz 1", "turns": [{"speaker": "Narrator", "text": "Absatz 1"}]}
            ],
            "processed_chunks": [{"start": 0, "end": 6}],
            "characters_merged": True,
            "api_usage": {
                "gemini-3.8-flash": {"input_tokens": 100_000, "output_tokens": 10_000, "cost_usd": 0.1125},
            },
            "total_cost_usd": 0.1125,
        }
        mock_engine.load_metadata.return_value = saved_metadata
        mock_engine.list_cached_audio.return_value = [1]

        # On resume with --merge-characters, LLM merge check runs on gemini-3.8-flash:
        # 40,000 input ($0.030000) + 2,000 output ($0.007500) = $0.037500 -> cumulative $0.150000
        def fake_merge_chars(self_api, chars):
            self_api.usage["gemini-3.8-flash"]["input_tokens"] += 40_000
            self_api.usage["gemini-3.8-flash"]["output_tokens"] += 2_000
            return []

        args = argparse.Namespace(
            filepath="fake.md",
            target_lang="German",
            source_lang="English",
            level="B1",
            output_dir="./out",
            render_only=None,
            import_characters=None,
            merge_characters=True,
            lite=False,
            dry_run=False,
            dump_requests=None,
            serve=False,
        )

        # Ensure len(characters) > 1 so merge pass triggers
        saved_metadata["characters"].append(
            {"name": "Alice", "description": "Alice", "voice": "Zephyr", "voiceProfile": "Bright"}
        )

        buf = io.StringIO()
        with patch.object(GeminiAPI, 'find_character_merges_with_llm', autospec=True, side_effect=fake_merge_chars), \
             patch('pangloss.cli.chunk_text', return_value=[{"text": "Para 1", "start": 0, "end": 6}]), \
             patch('pangloss.cli.export_results', return_value="fake.html"), \
             redirect_stdout(buf):
            run_build(args)

        output = buf.getvalue()
        self.assertEqual(saved_metadata["api_usage"]["gemini-3.8-flash"]["input_tokens"], 140_000)
        self.assertEqual(saved_metadata["api_usage"]["gemini-3.8-flash"]["output_tokens"], 12_000)
        self.assertAlmostEqual(saved_metadata["api_usage"]["gemini-3.8-flash"]["cost_usd"], 0.15, places=6)
        self.assertAlmostEqual(saved_metadata.get("total_cost_usd"), 0.15, places=6)
        self.assertIn("$0.037500", output)
        self.assertIn("$0.150000", output)


if __name__ == "__main__":
    unittest.main()
