import base64
import json
import os
import string
from pathlib import Path
from .audio import wav_to_mp3_bytes, merge_wavs_to_mp3
from .models import StoryMetadata

def generate_html(metadata: StoryMetadata, audio_chunks: dict, source_lang: str, target_lang: str, level: str) -> str:
    """Generates a standalone HTML file with embedded audio and metadata using a template file."""
    
    # Encode audio to base64 MP3 data URLs
    mp3_data_urls = {}
    for pid, wav_data in audio_chunks.items():
        try:
            mp3_bytes = wav_to_mp3_bytes(wav_data)
            b64_audio = base64.b64encode(mp3_bytes).decode()
            mp3_data_urls[pid] = f"data:audio/mp3;base64,{b64_audio}"
        except Exception as e:
            print(f"Warning: Failed to encode audio for paragraph {pid}: {e}")
            mp3_data_urls[pid] = ""

    # UI Translations
    ui_translations = {
        "English": {
            "targetLang": "Target Language",
            "sourceLang": "Your Native Language",
            "proficiency": "Proficiency Level",
            "lexicon": "Lexicon.",
            "vocabulary": "Key Vocabulary",
            "cast": "Cast & Voice",
            "voice": "Voice",
            "back": "Back",
            "next": "Next",
            "dictionary": "Dictionary",
            "statusLabel": "Status",
            "chapter": "Paragraph",
            "finished": "Finished",
            "statusReady": "Ready!",
        },
        "Polish": {
            "targetLang": "Język Docelowy",
            "sourceLang": "Twój Język Ojczysty",
            "proficiency": "Poziom Zaawansowania",
            "lexicon": "Leksykon.",
            "vocabulary": "Kluczowe Słownictwo",
            "cast": "Obsada i Głos",
            "voice": "Głos",
            "back": "Wstecz",
            "next": "Dalej",
            "dictionary": "Słownik",
            "statusLabel": "Status",
            "chapter": "Akapit",
            "finished": "Zakończono",
            "statusReady": "Gotowe!",
        }
    }
    
    t = ui_translations.get(source_lang, ui_translations["English"])
    
    # SVG constants
    play_svg = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="black" stroke="black" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="6 3 22 12 6 21 6 3"/></svg>'
    pause_svg = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="black" stroke="black" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>'

    # Load template
    template_path = Path(__file__).parent / "templates" / "export.html"
    with open(template_path, "r", encoding="utf-8") as f:
        template_str = f.read()
    
    # Substitution mapping
    subs = {
        "source_lang_code": "pl" if source_lang == "Polish" else "en",
        "title": metadata["title"],
        "dictionary_label": t["dictionary"],
        "lexicon_label": t["lexicon"],
        "vocabulary_label": t["vocabulary"],
        "cast_label": t["cast"],
        "target_lang": target_lang,
        "level": level,
        "status_label": t["statusLabel"],
        "status_ready_label": t["statusReady"],
        "play_svg": play_svg,
        "back_label": t["back"],
        "next_label": t["next"],
        "metadata_json": json.dumps(metadata),
        "audio_data_json": json.dumps(mp3_data_urls),
        "play_svg_json": json.dumps(play_svg),
        "pause_svg_json": json.dumps(pause_svg),
        "chapter_label": t["chapter"],
        "finished_label": t["finished"],
    }
    
    template = string.Template(template_str)
    return template.substitute(subs)

def export_results(metadata: StoryMetadata, audio_dir: Path, output_dir: str, source_lang: str, target_lang: str, level: str):
    """Orchestrates the export of HTML and MP3 files."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    
    title_slug = metadata['title'].lower().replace(" ", "-").replace("/", "-").replace(":", "-")
    
    # 1. Generate MP3
    print(f"Merging audio chunks into {title_slug}.mp3...")
    paragraph_ids = sorted([p['id'] for p in metadata['paragraphs']])
    wav_paths = [str(audio_dir / f"{pid}.wav") for pid in paragraph_ids if (audio_dir / f"{pid}.wav").exists()]
    
    mp3_output = out_path / f"{title_slug}.mp3"
    merge_wavs_to_mp3(wav_paths, str(mp3_output))
    
    # 2. Generate HTML
    print(f"Generating standalone HTML {title_slug}.html...")
    audio_chunks = {}
    for pid in paragraph_ids:
        wav_path = audio_dir / f"{pid}.wav"
        if wav_path.exists():
            with open(wav_path, "rb") as f:
                audio_chunks[pid] = f.read()
    
    html_content = generate_html(metadata, audio_chunks, source_lang, target_lang, level)
    html_output = out_path / f"{title_slug}.html"
    with open(html_output, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    print(f"\nSuccess! Files generated in {output_dir}:")
    print(f" - {html_output.name}")
    print(f" - {mp3_output.name}")
    return str(html_output)
