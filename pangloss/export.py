import base64
from concurrent.futures import ThreadPoolExecutor
import json
import os
import string
from pathlib import Path
from .audio import wav_to_mp3_bytes, merge_wavs_to_mp3
from .models import StoryMetadata

def generate_html(metadata: StoryMetadata, audio_chunks: dict, source_lang: str, target_lang: str, level: str, audio_dir: Path | None = None) -> str:
    """Generates a standalone HTML file with embedded audio and metadata using a template file."""
    
    # Encode audio to base64 MP3 data URLs (with optional disk caching & parallel encoding)
    mp3_data_urls = {}

    def _encode_one(item):
        pid, wav_data = item
        try:
            cache_mp3 = (audio_dir / f"{pid}.mp3") if audio_dir is not None else None
            cache_wav = (audio_dir / f"{pid}.wav") if audio_dir is not None else None
            if (
                cache_mp3 is not None
                and cache_mp3.exists()
                and (cache_wav is None or not cache_wav.exists() or cache_mp3.stat().st_mtime >= cache_wav.stat().st_mtime)
            ):
                mp3_bytes = cache_mp3.read_bytes()
            else:
                mp3_bytes = wav_to_mp3_bytes(wav_data)
                if cache_mp3 is not None:
                    try:
                        cache_mp3.write_bytes(mp3_bytes)
                    except OSError:
                        pass
            b64_audio = base64.b64encode(mp3_bytes).decode()
            return pid, f"data:audio/mp3;base64,{b64_audio}"
        except Exception as e:
            print(f"Warning: Failed to encode audio for paragraph {pid}: {e}")
            return pid, ""

    if audio_chunks:
        with ThreadPoolExecutor() as executor:
            for pid, data_url in executor.map(_encode_one, audio_chunks.items()):
                mp3_data_urls[pid] = data_url

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
            "omittedBadge": "Omitted • Copyright Restriction",
            "omittedTitle": "Section omitted from translation due to copyright restrictions",
            "omittedDesc": "This excerpt was flagged under model copyright restrictions and was omitted from translation and audio generation. The original English text is provided below.",
            "originalTextLabel": "Original English Text",
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
            "omittedBadge": "Pominięto • Prawa autorskie",
            "omittedTitle": "Fragment pominięty ze względu na prawa autorskie",
            "omittedDesc": "Ten fragment został objęty ograniczeniami praw autorskich modelu i pominięty w tłumaczeniu oraz audio. Poniżej znajduje się oryginalny tekst.",
            "originalTextLabel": "Oryginalny tekst",
        }
    }
    
    t = ui_translations.get(source_lang, ui_translations["English"])
    
    # SVG constants
    play_svg = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="6 3 22 12 6 21 6 3"/></svg>'
    pause_svg = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>'

    # Load templates
    templates_dir = Path(__file__).parent / "templates"
    with open(templates_dir / "export.css", "r", encoding="utf-8") as f:
        css_str = f.read()
    with open(templates_dir / "export.js", "r", encoding="utf-8") as f:
        js_str = f.read()
    with open(templates_dir / "export.html", "r", encoding="utf-8") as f:
        html_str = f.read()

    # Substitution mapping for HTML
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
    }

    # Render JS placeholders
    js_rendered = (
        js_str.replace("__METADATA_JSON__", json.dumps(metadata))
        .replace("__AUDIO_DATA_JSON__", json.dumps(mp3_data_urls))
        .replace("__PLAY_SVG_JSON__", json.dumps(play_svg))
        .replace("__PAUSE_SVG_JSON__", json.dumps(pause_svg))
        .replace("__CHAPTER_LABEL__", t["chapter"])
        .replace("__FINISHED_LABEL__", t["finished"])
        .replace("__OMITTED_BADGE__", t["omittedBadge"])
        .replace("__OMITTED_TITLE__", t["omittedTitle"])
        .replace("__OMITTED_DESC__", t["omittedDesc"])
        .replace("__ORIGINAL_TEXT_LABEL__", t["originalTextLabel"])
    )

    template = string.Template(html_str)
    rendered_html = template.substitute(subs)
    rendered_html = rendered_html.replace("/* INLINED_CSS */\n", css_str)
    rendered_html = rendered_html.replace("/* INLINED_JS */\n", js_rendered)
    return rendered_html

def find_wav_pauses(frames: bytes, sample_rate: int, start_sec: float, end_sec: float) -> list[tuple[float, float, float]]:
    """Finds acoustic pauses (low-RMS intervals >= 180ms) in 16-bit mono PCM WAV frames within [start_sec, end_sec]."""
    import array
    import math

    if not frames or sample_rate <= 0 or end_sec <= start_sec:
        return []

    win_sec = 0.04
    win_samples = max(1, int(sample_rate * win_sec))
    win_bytes = win_samples * 2
    total_windows = len(frames) // win_bytes
    start_w = max(0, int(start_sec / win_sec))
    end_w = min(total_windows, int(end_sec / win_sec))

    pauses = []
    in_sil = False
    sil_start = 0.0
    for w_idx in range(start_w, end_w):
        chunk = frames[w_idx * win_bytes : (w_idx + 1) * win_bytes]
        samples = array.array("h", chunk)
        rms = math.sqrt(sum(s * s for s in samples) / len(samples)) if samples else 0.0
        t = w_idx * win_sec
        if rms < 120.0:
            if not in_sil:
                in_sil = True
                sil_start = t
        else:
            if in_sil:
                dur = t - sil_start
                if dur >= 0.18:
                    pauses.append((round(sil_start, 3), round(t, 3), round(dur, 3)))
                in_sil = False
    if in_sil:
        t = end_w * win_sec
        dur = t - sil_start
        if dur >= 0.18:
            pauses.append((round(sil_start, 3), round(t, 3), round(dur, 3)))
    return pauses


def spoken_text_weight(text: str, is_last: bool = False) -> float:
    """Computes an estimated spoken duration weight for a sub-paragraph, accounting for punctuation & paragraph pauses."""
    import re

    clean = re.sub(r"<[a-zA-Z\s_\/-]+>", "", text or "")
    clean = re.sub(r"^#+\s*", "", clean.strip())
    clean = clean.replace("**", "").replace("__", "").replace("*", "").replace("_", "")
    char_len = max(1, len(clean))
    sent_pauses = sum(clean.count(ch) for ch in ".!?…") * 6.0
    comma_pauses = sum(clean.count(ch) for ch in ",;:—–") * 3.0
    para_pause = 0.0 if is_last else 14.0
    return float(char_len) + sent_pauses + comma_pauses + para_pause


def split_chunk_across_subparagraphs(
    c: dict, translated_text: str, frames: bytes | None = None, sample_rate: int = 0
) -> list[dict]:
    """Subdivides a chunk that crosses \\n\\n sub-paragraph boundaries and snaps split timestamps to WAV pauses."""
    if not translated_text:
        return [dict(c)]

    c_start = c.get("start_char", 0)
    c_end = c.get("end_char", 0)
    if c_end <= c_start:
        return [dict(c)]

    sub_paras = translated_text.split("\n\n")
    sp_ranges = []
    pos = 0
    for sp in sub_paras:
        sp_start = pos
        sp_end = pos + len(sp)
        sp_ranges.append((sp_start, sp_end))
        pos = sp_end + 2

    overlapping_spans = [
        (max(c_start, sp_start), min(c_end, sp_end))
        for sp_start, sp_end in sp_ranges
        if max(c_start, sp_start) < min(c_end, sp_end)
    ]
    if len(overlapping_spans) <= 1:
        return [dict(c)]

    start_sec = float(c.get("start_sec", 0.0))
    end_sec = float(c.get("end_sec", start_sec))
    total_dur = max(0.05, end_sec - start_sec)

    weights = [
        spoken_text_weight(translated_text[s:e], is_last=(idx == len(overlapping_spans) - 1))
        for idx, (s, e) in enumerate(overlapping_spans)
    ]
    total_w = sum(weights) or 1.0

    raw_pauses = find_wav_pauses(frames, sample_rate, start_sec, end_sec) if frames and sample_rate > 0 else []
    candidate_pauses = [
        p for p in raw_pauses if p[0] > start_sec + 0.35 and p[1] < end_sec - 0.25
    ]
    used_pauses = set()

    result = []
    cur_sec = start_sec
    cum_w = 0.0
    max_search_window = max(2.5, 0.24 * total_dur)

    for idx, (s_char, e_char) in enumerate(overlapping_spans):
        cum_w += weights[idx]
        if idx == len(overlapping_spans) - 1:
            sub_end_sec = round(end_sec, 3)
            next_start_sec = sub_end_sec
        else:
            expected_t = start_sec + (cum_w / total_w) * total_dur
            best_p_idx = None
            best_score = float("inf")
            for p_idx, p in enumerate(candidate_pauses):
                if p_idx in used_pauses:
                    continue
                mid = (p[0] + p[1]) / 2.0
                if mid <= cur_sec + 0.25 or mid >= end_sec - 0.25:
                    continue
                dist = abs(mid - expected_t)
                if dist <= max_search_window:
                    score = dist - 1.2 * min(p[2], 1.2)
                    if score < best_score:
                        best_score = score
                        best_p_idx = p_idx

            if best_p_idx is not None:
                used_pauses.add(best_p_idx)
                p_start, p_end, _ = candidate_pauses[best_p_idx]
                sub_end_sec = round(max(cur_sec + 0.05, p_end - 0.05), 3)
                next_start_sec = round(max(sub_end_sec, p_end - 0.02), 3)
            else:
                sub_end_sec = round(max(cur_sec + 0.05, min(end_sec - 0.05, expected_t)), 3)
                next_start_sec = sub_end_sec

        result.append({
            "chunk_index": 0,
            "start_sec": round(cur_sec, 3),
            "end_sec": sub_end_sec,
            "start_char": s_char,
            "end_char": e_char,
            "speakers": list(c.get("speakers", [])),
        })
        cur_sec = next_start_sec

    return result


def ensure_chunk_metadata(metadata: StoryMetadata, audio_dir: Path):
    """Ensures each paragraph in metadata has chunk timing and character range info."""
    from .api import partition_paragraph_into_subchunks, compute_chunk_ranges
    import io, wave

    for p in metadata.get("paragraphs", []):
        sub_chunks = partition_paragraph_into_subchunks(p.get("turns", []))
        if not sub_chunks:
            p["chunks"] = []
            continue
        translated_text = p.get("translatedText", "")
        chunk_ranges = compute_chunk_ranges(sub_chunks, translated_text)

        wav_path = audio_dir / f"{p['id']}.wav"
        durs = []
        total_wav_dur = 0.0
        frames = b""
        sample_rate = 0
        if wav_path.exists():
            try:
                with open(wav_path, "rb") as f:
                    wav_data = f.read()
                with wave.open(io.BytesIO(wav_data), "rb") as w:
                    frames = w.readframes(w.getnframes())
                    sample_rate = w.getframerate()
                total_wav_dur = (len(frames) / 2) / sample_rate if sample_rate else 0.0
                silence = b"\x00\x00" * int(sample_rate * 0.15)
                parts = frames.split(silence)
                if len(parts) == len(sub_chunks):
                    for part in parts:
                        durs.append(round((len(part) / 2) / sample_rate, 3))
            except Exception:
                durs = []

        existing_chunks = p.get("chunks")
        base_chunks = None
        if (
            existing_chunks
            and len(existing_chunks) == len(sub_chunks)
            and (total_wav_dur <= 0 or abs(existing_chunks[-1].get("end_sec", 0.0) - total_wav_dur) <= 1.5)
        ):
            base_chunks = []
            for idx, c in enumerate(existing_chunks):
                c_copy = dict(c)
                if idx < len(chunk_ranges):
                    c_copy["start_char"], c_copy["end_char"] = chunk_ranges[idx]
                base_chunks.append(c_copy)
        elif (
            existing_chunks
            and len(existing_chunks) > len(sub_chunks)
            and (total_wav_dur <= 0 or abs(existing_chunks[-1].get("end_sec", 0.0) - total_wav_dur) <= 1.5)
            and all(
                len(split_chunk_across_subparagraphs(c, translated_text)) == 1
                for c in existing_chunks
            )
        ):
            for idx, c in enumerate(existing_chunks):
                c["chunk_index"] = idx
            continue

        if base_chunks is None:
            if len(durs) != len(sub_chunks):
                if total_wav_dur > 0:
                    pause_total = 0.150 * max(0, len(sub_chunks) - 1)
                    avail_dur = max(0.1 * len(sub_chunks), total_wav_dur - pause_total)
                    weights = [
                        max(1, (chunk_ranges[idx][1] - chunk_ranges[idx][0]) if idx < len(chunk_ranges) else 1)
                        for idx in range(len(sub_chunks))
                    ]
                    total_weight = sum(weights) or 1
                    durs = [round(avail_dur * (w / total_weight), 3) for w in weights]
                else:
                    durs = [5.0] * len(sub_chunks)

            base_chunks = []
            curr_time = 0.0
            for idx, c in enumerate(sub_chunks):
                spk = list(dict.fromkeys(t["speaker"] for t in c))
                dur = durs[idx]
                start_sec = round(curr_time, 3)
                end_sec = round(curr_time + dur, 3)
                start_char, end_char = chunk_ranges[idx] if idx < len(chunk_ranges) else (0, 0)
                base_chunks.append({
                    "chunk_index": idx,
                    "start_sec": start_sec,
                    "end_sec": end_sec,
                    "start_char": start_char,
                    "end_char": end_char,
                    "speakers": spk
                })
                curr_time = round(end_sec + 0.150, 3)

        subdivided_chunks = []
        for bc in base_chunks:
            for sc in split_chunk_across_subparagraphs(bc, translated_text, frames, sample_rate):
                sc["chunk_index"] = len(subdivided_chunks)
                subdivided_chunks.append(sc)
        p["chunks"] = subdivided_chunks

def export_results(metadata: StoryMetadata, audio_dir: Path, output_dir: str, source_lang: str, target_lang: str, level: str):
    """Orchestrates the export of HTML and MP3 files."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    ensure_chunk_metadata(metadata, audio_dir)

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
    
    html_content = generate_html(metadata, audio_chunks, source_lang, target_lang, level, audio_dir=audio_dir)
    html_output = out_path / f"{title_slug}.html"
    with open(html_output, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    print(f"\nSuccess! Files generated in {output_dir}:")
    print(f" - {html_output.name}")
    print(f" - {mp3_output.name}")
    return str(html_output)
