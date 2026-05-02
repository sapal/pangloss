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

def chunk_text(text: str, words_per_chunk: int = 2000) -> list[str]:
    # Split by paragraph boundaries (double newlines)
    raw_paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []
    current_chunk = []
    current_word_count = 0
    
    for p in raw_paragraphs:
        word_count = len(p.split())
        if current_word_count + word_count > words_per_chunk and current_chunk:
            chunks.append("\n\n".join(current_chunk))
            current_chunk = []
            current_word_count = 0
        current_chunk.append(p)
        current_word_count += word_count
    
    if current_chunk:
        chunks.append("\n\n".join(current_chunk))
    return chunks

def run_build(args):
    # 1. Setup Engine
    engine = CacheEngine(args.filepath, vars(args))
    print(f"Job ID: {engine.job_id}")
    
    metadata = engine.load_metadata()
    
    if not args.render_only:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            print("Error: GEMINI_API_KEY environment variable not set.")
            sys.exit(1)
        api = GeminiAPI(api_key)

        if not metadata:
            print("Processing text and generating metadata...")
            with open(args.filepath, "r", encoding="utf-8") as f:
                text = f.read()
            
            chunks = chunk_text(text)
            full_metadata = {
                "title": "",
                "characters": [],
                "difficultWords": [],
                "paragraphs": []
            }

            # Import characters if requested
            if args.import_characters:
                other_meta = engine.load_other_metadata(args.import_characters)
                if other_meta:
                    print(f"Importing characters from project {args.import_characters}...")
                    full_metadata["characters"] = other_meta.get("characters", [])
                else:
                    print(f"Warning: Could not find project {args.import_characters} to import characters.")
            
            for i, chunk in enumerate(chunks):
                print(f"Processing chunk {i+1}/{len(chunks)}...")
                chunk_data = api.process_chunk(
                    chunk, args.target_lang, args.level, args.source_lang, 
                    i == 0, full_metadata, i, len(chunks)
                )
                
                if i == 0:
                    full_metadata["title"] = chunk_data.get("title", "Untitled")
                
                # Merge characters
                for new_char in chunk_data.get("characters", []):
                    if not any(c["name"].lower() == new_char["name"].lower() for c in full_metadata["characters"]):
                        full_metadata["characters"].append(new_char)
                
                # Merge words
                for new_word in chunk_data.get("difficultWords", []):
                    if not any(w["word"].lower() == new_word["word"].lower() for w in full_metadata["difficultWords"]):
                        full_metadata["difficultWords"].append(new_word)
                
                # Merge paragraphs (re-indexing)
                base_id = max([p["id"] for p in full_metadata["paragraphs"]] + [0])
                for j, p in enumerate(chunk_data.get("paragraphs", [])):
                    p["id"] = base_id + j + 1
                    full_metadata["paragraphs"].append(p)
                
                # Intermediate save
                engine.save_metadata(full_metadata)
            
            metadata = full_metadata

        # 2. Generate Audio Chunks
        print("Generating audio chunks...")
        cached_audio_ids = engine.list_cached_audio()
        
        for p in metadata["paragraphs"]:
            if p["id"] in cached_audio_ids:
                continue
            
            print(f"Generating audio for paragraph {p['id']}...")
            try:
                pcm_data = api.generate_tts(p, metadata["characters"])
                wav_data = pcm_to_wav(pcm_data)
                engine.save_audio_chunk(p["id"], wav_data)
            except Exception as e:
                log_pangloss(f"Failed to generate audio for paragraph {p['id']}: {e}")
                print(f"Warning: Skipping paragraph {p['id']} due to error.")

    else:
        if not metadata:
            print(f"Error: No metadata found for job ID {args.render_only}")
            sys.exit(1)
        print(f"Render-only mode for job {args.render_only}")

    # 3. Export Results
    html_file = export_results(
        metadata, engine.audio_dir, args.output_dir, 
        args.source_lang, args.target_lang, args.level
    )

    # 4. Serve if requested
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
    build_parser.add_argument("--serve", action="store_true", help="Spin up a local server to preview")
    
    args = parser.parse_args()
    
    if args.command == "build":
        run_build(args)

if __name__ == "__main__":
    main()
