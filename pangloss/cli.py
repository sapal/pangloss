import argparse
import sys
import os
import http.server
import socketserver
from pathlib import Path
from .engine import CacheEngine
from .api import GeminiAPI
from .audio import pcm_to_wav
from .export import export_results
from .utils import log_pangloss

def chunk_text(text: str, words_per_chunk: int = 2000) -> list[dict]:
    # Split by paragraph boundaries (double newlines)
    paragraphs = text.split("\n\n")
    chunks = []
    current_chunk_paragraphs = []
    current_word_count = 0
    current_start_index = 0
    
    char_ptr = 0
    for i, p in enumerate(paragraphs):
        word_count = len(p.split())
        p_len = len(p)
        
        if current_word_count + word_count > words_per_chunk and current_chunk_paragraphs:
            chunk_text_str = "\n\n".join(current_chunk_paragraphs)
            chunks.append({
                "text": chunk_text_str,
                "start": current_start_index,
                "end": char_ptr - 2
            })
            current_chunk_paragraphs = []
            current_word_count = 0
            current_start_index = char_ptr
        
        current_chunk_paragraphs.append(p)
        current_word_count += word_count
        char_ptr += p_len + 2
    
    if current_chunk_paragraphs:
        chunk_text_str = "\n\n".join(current_chunk_paragraphs)
        chunks.append({
            "text": chunk_text_str,
            "start": current_start_index,
            "end": len(text)
        })
    return chunks

def process_chunk_with_fallback(
    api: GeminiAPI,
    text: str,
    target_lang: str,
    level: str,
    source_lang: str,
    is_first: bool,
    metadata: dict,
    chunk_index: int,
    total_chunks: int,
    depth: int = 0
) -> dict:
    from .models import is_copyright_error
    try:
        return api.process_chunk(
            text, target_lang, level, source_lang,
            is_first, metadata, chunk_index, total_chunks
        )
    except Exception as e:
        if not is_copyright_error(e):
            raise e

        paras = [p for p in text.split("\n\n") if p.strip()]
        if len(paras) <= 1:
            log_pangloss("Copyright restriction reoccurred on atomic text fragment. Including untranslated in output without audio.")
            explanatory_message = "[This section was omitted from translation due to copyright restrictions / Dieser Abschnitt wurde aufgrund von Urheberrechtsbeschränkungen nicht übersetzt]"
            return {
                "title": "",
                "characters": [],
                "difficultWords": [],
                "paragraphs": [{
                    "id": 1,
                    "originalText": f"*{explanatory_message}*\n\n{text}",
                    "translatedText": f"*{explanatory_message}*\n\n{text}",
                    "turns": [],
                    "skip_audio": True,
                    "untranslated": True
                }]
            }

        log_pangloss(f"Copyright restriction triggered on chunk ({e}). Slicing text into smaller chunks ({len(paras)} paragraphs)...")
        mid = len(paras) // 2
        slice_1 = "\n\n".join(paras[:mid])
        slice_2 = "\n\n".join(paras[mid:])

        # Process first slice
        res_1 = process_chunk_with_fallback(
            api, slice_1, target_lang, level, source_lang,
            is_first, metadata, chunk_index, total_chunks, depth + 1
        )

        # Merge intermediate title and characters into metadata context for slice 2
        if not metadata.get("title") and res_1.get("title"):
            metadata["title"] = res_1["title"]
        for new_char in res_1.get("characters", []):
            if not any(c["name"].lower() == new_char["name"].lower() for c in metadata.get("characters", [])):
                metadata["characters"].append(new_char)
        for new_word in res_1.get("difficultWords", []):
            if not any(w["word"].lower() == new_word["word"].lower() for w in metadata.get("difficultWords", [])):
                metadata["difficultWords"].append(new_word)

        # Process second slice
        is_first_slice_2 = is_first and not bool(metadata.get("title"))
        res_2 = process_chunk_with_fallback(
            api, slice_2, target_lang, level, source_lang,
            is_first_slice_2, metadata, chunk_index, total_chunks, depth + 1
        )

        combined_paras = res_1.get("paragraphs", []) + res_2.get("paragraphs", [])
        for idx, p in enumerate(combined_paras, 1):
            p["id"] = idx

        return {
            "title": res_1.get("title") or res_2.get("title") or "",
            "characters": res_1.get("characters", []) + [
                c for c in res_2.get("characters", [])
                if not any(x["name"].lower() == c["name"].lower() for x in res_1.get("characters", []))
            ],
            "difficultWords": res_1.get("difficultWords", []) + [
                w for w in res_2.get("difficultWords", [])
                if not any(x["word"].lower() == w["word"].lower() for x in res_1.get("difficultWords", []))
            ],
            "paragraphs": combined_paras
        }

def run_build(args):
    # 1. Setup Engine
    engine = CacheEngine(args.filepath, vars(args))
    print(f"Job ID: {engine.job_id}")
    
    metadata = engine.load_metadata()
    dry_run = getattr(args, "dry_run", False)
    dump_requests = getattr(args, "dump_requests", None)
    lite = getattr(args, "lite", False)
    
    if not args.render_only:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key and not dry_run:
            print("Error: GEMINI_API_KEY environment variable not set.")
            sys.exit(1)
        api = GeminiAPI(api_key or "dry_run_key", lite=lite, dry_run=dry_run, dump_requests=dump_requests)

        with open(args.filepath, "r", encoding="utf-8") as f:
            text = f.read()
        
        all_chunks = chunk_text(text)
        
        if not metadata:
            print("Initializing new project metadata...")
            metadata = {
                "title": "",
                "characters": [],
                "difficultWords": [],
                "paragraphs": [],
                "processed_chunks": []
            }

            # Import characters if requested
            if args.import_characters:
                other_meta = engine.load_other_metadata(args.import_characters)
                if other_meta:
                    print(f"Importing characters from project {args.import_characters}...")
                    metadata["characters"] = other_meta.get("characters", [])
                else:
                    print(f"Warning: Could not find project {args.import_characters} to import characters.")
        
        processed_starts = [c["start"] for c in metadata.get("processed_chunks", [])]
        chunks_to_process = [c for c in all_chunks if c["start"] not in processed_starts]
        
        if chunks_to_process:
            print(f"Processing {len(chunks_to_process)} missing text chunks...")
            
            for i, chunk_info in enumerate(all_chunks):
                if chunk_info["start"] in processed_starts and not dump_requests:
                    print(f"Skipping already processed chunk {i+1}/{len(all_chunks)}...")
                    continue
                
                print(f"Processing chunk {i+1}/{len(all_chunks)}...")
                chunk_data = process_chunk_with_fallback(
                    api, chunk_info["text"], args.target_lang, args.level, args.source_lang, 
                    i == 0 and not metadata["processed_chunks"], metadata, i, len(all_chunks)
                )
                
                if not metadata["title"]:
                    metadata["title"] = chunk_data.get("title", "Untitled")
                
                # Merge characters
                for new_char in chunk_data.get("characters", []):
                    if not any(c["name"].lower() == new_char["name"].lower() for c in metadata["characters"]):
                        metadata["characters"].append(new_char)
                
                # Merge words
                for new_word in chunk_data.get("difficultWords", []):
                    if not any(w["word"].lower() == new_word["word"].lower() for w in metadata["difficultWords"]):
                        metadata["difficultWords"].append(new_word)
                
                # Merge paragraphs (re-indexing)
                base_id = max([p["id"] for p in metadata["paragraphs"]] + [0])
                for j, p in enumerate(chunk_data.get("paragraphs", [])):
                    p["id"] = base_id + j + 1
                    metadata["paragraphs"].append(p)
                
                # Mark as processed
                metadata["processed_chunks"].append({
                    "start": chunk_info["start"],
                    "end": chunk_info["end"]
                })
                
                if not dry_run:
                    engine.save_metadata(metadata)
        else:
            print("All text chunks already processed.")
            if dump_requests:
                for i, chunk_info in enumerate(all_chunks):
                    api.process_chunk(
                        chunk_info["text"], args.target_lang, args.level, args.source_lang, 
                        i == 0, metadata, i, len(all_chunks)
                    )

        # 2. Generate Audio Chunks
        print("Generating audio chunks...")
        cached_audio_ids = engine.list_cached_audio()
        
        total_paras = len(metadata["paragraphs"])
        for idx, p in enumerate(metadata["paragraphs"], 1):
            if p.get("skip_audio"):
                print(f"Skipping audio for paragraph {p['id']} (marked untranslated / skip_audio).")
                continue
            if p["id"] in cached_audio_ids and not dry_run and not dump_requests:
                continue
            
            print(f"Generating audio for paragraph {idx}/{total_paras}...")
            try:
                pcm_data = api.generate_tts(p, metadata["characters"])
                if not dry_run:
                    wav_data = pcm_to_wav(pcm_data)
                    engine.save_audio_chunk(p["id"], wav_data)
            except Exception as e:
                log_pangloss(f"Failed to generate audio for paragraph {p['id']}: {e}")
                print(f"Warning: Skipping paragraph {p['id']} due to error.")

        if not dry_run:
            engine.save_metadata(metadata)

    else:
        if not metadata:
            print(f"Error: No metadata found for job ID {args.render_only}")
            sys.exit(1)
        print(f"Render-only mode for job {args.render_only}")

    # Dry run exit
    if dry_run:
        print("\nDry run completed successfully. No remote API calls made or cache modified.")
        if dump_requests:
            print(f"Requests dumped to: {os.path.abspath(dump_requests)}")
        return

    # 3. Export Results
    html_file = export_results(
        metadata, engine.audio_dir, args.output_dir, 
        args.source_lang, args.target_lang, args.level
    )

    # 4. Print token usage statistics
    if not args.render_only:
        api.print_token_usage_statistics()

    # 5. Serve if requested
    if args.serve:
        serve_output(args.output_dir, html_file)
    
    print(f"\nFinal Job ID: {engine.job_id}")

def serve_output(directory, html_file):
    os.chdir(directory)
    handler = http.server.SimpleHTTPRequestHandler
    port = 8000
    while True:
        try:
            with socketserver.TCPServer(("", port), handler) as httpd:
                print(f"\nServing at http://localhost:{port}/{os.path.basename(html_file)}")
                print("Press Ctrl+C to stop.")
                httpd.serve_forever()
        except OSError:
            port += 1

def main():
    parser = argparse.ArgumentParser(description="Pangloss: Immersive Bilingual Audiobooks")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    build_parser = subparsers.add_parser("build", help="Build an audiobook from a text file")
    build_parser.add_argument("filepath", help="Path to the input text file")
    build_parser.add_argument("--target-lang", default="German", help="Target language (default: German)")
    build_parser.add_argument("--source-lang", default="English", help="Source language (default: English)")
    build_parser.add_argument("--level", default="B1", help="Proficiency level (default: B1)")
    build_parser.add_argument("--output-dir", default="./pangloss_output", help="Output directory (default: ./pangloss_output)")
    build_parser.add_argument("--render-only", help="Skip API calls; force generation from existing cache job ID")
    build_parser.add_argument("--import-characters", help="Import character names and voices from a previous Job ID")
    build_parser.add_argument("--lite", action="store_true", help="Use Gemini 3.8 Flash Lite TTS instead of Gemini 3.8 Flash TTS")
    build_parser.add_argument("--dry-run", action="store_true", help="Perform a dry run without calling remote Gemini API or saving cache")
    build_parser.add_argument("--dump-requests", type=str, default=None, metavar="DIR", help="Directory to dump raw JSON request payloads")
    build_parser.add_argument("--serve", action="store_true", help="Spin up a local server to preview")
    
    args = parser.parse_args()
    
    if args.command == "build":
        run_build(args)

if __name__ == "__main__":
    main()
