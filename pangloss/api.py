import os
import json
import time
import re
from typing import List, Callable, Optional
from google import genai
from google.genai import types
from .models import (
    StoryMetadata, Character, ProcessedParagraph,
    CopyrightRestrictionError, is_copyright_error, is_copyright_error_text
)
from .utils import retry_with_pangloss
from .audio import concat_wavs, get_wav_duration_ms

def to_dict(obj):
    if obj is None:
        return None
    if hasattr(obj, 'to_json_dict'):
        return obj.to_json_dict()
    elif hasattr(obj, 'model_dump'):
        return obj.model_dump(exclude_none=True)
    elif isinstance(obj, (list, tuple)):
        return [to_dict(x) for x in obj]
    elif isinstance(obj, dict):
        return {k: to_dict(v) for k, v in obj.items()}
    return obj

def clean_text_for_tts(text: str) -> str:
    """Cleans Markdown formatting and inserts appropriate audio pauses for TTS."""
    if not text:
        return ""
    # 1. Headings: # Title -> Title. <long pause>, ## Heading -> Heading. <short pause>
    text = re.sub(r'^#\s+(.+)$', r'\1. <long pause>', text, flags=re.MULTILINE)
    text = re.sub(r'^#{2,6}\s+(.+)$', r'\1. <short pause>', text, flags=re.MULTILINE)
    # 2. Horizontal rulers
    text = re.sub(r'^[_\-*]{3,}$', '<long pause>', text, flags=re.MULTILINE)
    # 3. Strip bold/italics markers
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'__(.*?)__', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    text = re.sub(r'_(.*?)_', r'\1', text)
    # 4. Remove stray hashes
    text = re.sub(r'#+\s*', '', text)
    # 5. Normalize whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()
    # 6. Strip isolated leading/trailing quotation marks
    text = re.sub(r'^\s*[„“"\'»«]+|[„“"\'»«]+\s*$', '', text).strip()
    return text

def count_sentences(text: str) -> int:
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    return len([s for s in sentences if any(c.isalnum() for c in s)])

def split_turn_by_sentences(turn: dict, max_sentences: int = 3) -> list[dict]:
    if turn.get("speaker", "").lower() != "narrator":
        return [turn]
    text = turn.get("text", "").strip()
    sentences = re.split(r'(?<=[.!?])\s+', text)
    valid_sentences = [s for s in sentences if s.strip()]
    if len(valid_sentences) <= max_sentences:
        return [turn]
    
    chunks = []
    for i in range(0, len(valid_sentences), max_sentences):
        sub_text = " ".join(valid_sentences[i:i+max_sentences])
        chunks.append({"speaker": turn["speaker"], "text": sub_text})
    return chunks

def partition_paragraph_into_subchunks(turns: list[dict], max_narrator_solo_sentences: int = 3) -> list[list[dict]]:
    # Pre-split any long narrator turns
    expanded_turns = []
    for t in turns:
        expanded_turns.extend(split_turn_by_sentences(t, max_narrator_solo_sentences))
        
    sub_chunks = []
    current_chunk = []
    current_speakers = set()
    solo_narrator_sentences = 0
    
    for t in expanded_turns:
        speaker = t["speaker"]
        s_count = count_sentences(t.get("text", ""))
        
        # If current chunk is strictly solo narrator, check if adding would exceed 3 sentences
        if current_speakers == {"Narrator"} and speaker == "Narrator":
            if solo_narrator_sentences + s_count > max_narrator_solo_sentences:
                sub_chunks.append(current_chunk)
                current_chunk = [t]
                current_speakers = {"Narrator"}
                solo_narrator_sentences = s_count
                continue
                
        new_speakers = current_speakers | {speaker}
        if len(new_speakers) <= 2:
            current_chunk.append(t)
            current_speakers = new_speakers
            if current_speakers == {"Narrator"}:
                solo_narrator_sentences += s_count
            else:
                solo_narrator_sentences = 0
        else:
            if current_chunk:
                sub_chunks.append(current_chunk)
            current_chunk = [t]
            current_speakers = {speaker}
            solo_narrator_sentences = s_count if speaker == "Narrator" else 0
            
    if current_chunk:
        sub_chunks.append(current_chunk)
    return sub_chunks

def clean_turn_text_for_alignment(text: str) -> str:
    """Removes vocal tags like <gasp>, <whisper> for character range alignment."""
    return re.sub(r'<[a-zA-Z\s_/-]+>', '', text)

def is_word_char(c: str) -> bool:
    return c.isalnum()

def snap_to_word_boundary(text: str, idx: int) -> int:
    if idx <= 0 or idx >= len(text):
        return idx
    if not (is_word_char(text[idx - 1]) and is_word_char(text[idx])):
        return idx
    left = idx
    while left > 0 and is_word_char(text[left - 1]):
        left -= 1
    right = idx
    while right < len(text) and is_word_char(text[right]):
        right += 1
    if (idx - left) < (right - idx):
        return left
    else:
        return right

def compute_chunk_ranges(sub_chunks: list[list[dict]], translated_text: str) -> list[tuple[int, int]]:
    """Calculates [start_char, end_char] in translated_text for each subchunk, snapping to paragraph and word breaks."""
    if not sub_chunks:
        return []
    if len(sub_chunks) == 1:
        return [(0, len(translated_text))]

    sub_texts = []
    for c in sub_chunks:
        c_clean = ''.join(clean_turn_text_for_alignment(t.get('text', '')) for t in c)
        sub_texts.append(c_clean)

    boundaries = [0]
    pos = 0

    for i in range(len(sub_chunks) - 1):
        expected_len = len(sub_texts[i])
        expected_pos = pos + expected_len
        next_text = sub_texts[i + 1].strip()

        probe_words = [w for w in re.findall(r'[\w\'-]+|[„“\"\'»«]', next_text) if any(c.isalnum() for c in w)]
        found_idx = -1
        if probe_words:
            sub_probe = ' '.join(probe_words[:2]) if len(probe_words) >= 2 else probe_words[0]
            esc = re.escape(sub_probe)
            pattern = esc.replace(r'\ ', r'\s+')
            window_start = max(0, pos)
            matches = [m.start() for m in re.finditer(pattern, translated_text[window_start:])]
            if matches:
                best = min(matches, key=lambda m: abs((window_start + m) - expected_pos))
                found_idx = window_start + best

        if found_idx != -1:
            boundary = found_idx
        else:
            boundary = snap_to_word_boundary(translated_text, expected_pos)

        # Snap to paragraph break if close to \n\n
        prev_nn = translated_text.rfind('\n\n', max(0, boundary - 20), boundary)
        next_nn = translated_text.find('\n\n', boundary, min(len(translated_text), boundary + 20))
        if prev_nn != -1 and not any(is_word_char(c) for c in translated_text[prev_nn:boundary]):
            boundary = prev_nn + 2
        elif next_nn != -1 and not any(is_word_char(c) for c in translated_text[boundary:next_nn]):
            boundary = next_nn

        # Final guarantee: never cut a word
        boundary = snap_to_word_boundary(translated_text, boundary)
        if boundary <= boundaries[-1]:
            boundary = snap_to_word_boundary(translated_text, boundaries[-1] + 1)
        boundaries.append(boundary)
        pos = boundary

    boundaries.append(len(translated_text))
    return [(boundaries[i], boundaries[i + 1]) for i in range(len(sub_chunks))]

class _MockInlineData:
    def __init__(self, data: bytes):
        self.data = data

class _MockPart:
    def __init__(self, is_audio: bool):
        if is_audio:
            from .audio import pcm_to_wav
            self.inline_data = _MockInlineData(pcm_to_wav(b'\x00\x00' * 2400))
            self.text = ""
        else:
            self.inline_data = None
            self.text = "{}"

class _MockContent:
    def __init__(self, is_audio: bool):
        self.parts = [_MockPart(is_audio)]

class _MockCandidate:
    def __init__(self, is_audio: bool):
        self.content = _MockContent(is_audio)
        self.finish_reason = "STOP"

class _MockResponse:
    def __init__(self, is_audio: bool = False, json_text: str = "{}"):
        self.candidates = [_MockCandidate(is_audio)]
        self.text = json_text
        self.usage_metadata = None

class GeminiAPI:
    def __init__(self, api_key: str, lite: bool = False,
                 dry_run: bool = False, dump_requests: Optional[str] = None):
        self.dry_run = dry_run
        self.dump_requests = dump_requests
        self.request_counter = 0
        if self.dump_requests:
            os.makedirs(self.dump_requests, exist_ok=True)
        self.client = genai.Client(api_key=api_key or "dry_run_key")
        self.tts_model = "gemini-3.8-flash-lite-tts" if lite else "gemini-3.8-flash-tts"
        self.usage = {
            "gemini-3.7-flash": {"input_tokens": 0, "output_tokens": 0},
            "gemini-3.8-flash-tts": {"input_tokens": 0, "output_tokens": 0},
            "gemini-3.8-flash-lite-tts": {"input_tokens": 0, "output_tokens": 0},
        }

    def _dump_request(self, label: str, **kwargs):
        self.request_counter += 1
        payload = {
            "model": kwargs.get("model"),
            "contents": to_dict(kwargs.get("contents")),
            "config": to_dict(kwargs.get("config")),
        }
        if self.dump_requests:
            clean_label = label.replace(" ", "_").replace("/", "_")
            model_name = kwargs.get("model", "model")
            filename = f"{self.request_counter:03d}_{model_name}_{clean_label}.json"
            filepath = os.path.join(self.dump_requests, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
        return payload

    @retry_with_pangloss(max_retries=5, initial_delay=3)
    def _generate_content_with_retry(self, label: str = "request", **kwargs):
        self._dump_request(label, **kwargs)
        if self.dry_run:
            cfg = kwargs.get("config")
            is_audio = False
            if cfg:
                modalities = getattr(cfg, "response_modalities", None) or []
                if "AUDIO" in modalities:
                    is_audio = True
            return _MockResponse(is_audio=is_audio)
        return self.client.models.generate_content(**kwargs)

    @retry_with_pangloss()
    def process_chunk(self, chunk: str, target_lang: str, level: str, source_lang: str, 
                      is_first: bool, full_metadata: StoryMetadata, chunk_index: int, total_chunks: int) -> dict:
        
        context_prompt = ""
        if not is_first or full_metadata["characters"]:
            char_items = []
            for c in full_metadata["characters"]:
                aliases = c.get("aliases") or []
                aliases_str = f" (aliases: {', '.join(aliases)})" if aliases else ""
                char_items.append(f"{c['name']}{aliases_str}")
            char_names = ", ".join(char_items)
            vocab_words = ", ".join([w["word"] for w in full_metadata["difficultWords"]])
            
            # Build known context
            context_items = []
            if full_metadata['title']:
                context_items.append(f"- Title: {full_metadata['title']}")
            if char_names:
                context_items.append(f"- Known Characters: {char_names}")
            if vocab_words:
                context_items.append(f"- Vocabulary already in dictionary: {vocab_words}")
            
            context_prompt = "\nCONTEXT FROM PREVIOUS PARTS:\n" + "\n".join(context_items) + f"""

CRITICAL: 
- Continue the story exactly from where the previous part left off.
- MAINTAIN CONSISTENCY: Use the exact same canonical character names for existing characters.
- DO NOT invent new character names, nicknames, or shortened names for characters that are already in Known Characters (e.g. if 'Harry James Potter-Evans-Verres' is in Known Characters, you MUST use that exact canonical name in dialogue turns, NOT 'Harry' or 'Harry Potter').
- Always use 'Narrator' as the speaker for narration; NEVER translate it to other languages (such as 'Erzähler').
- DO NOT repeat words in the "difficultWords" list that are already present in the context above.
- Identify at least 10 NEW difficult words from this specific chunk.
"""

        prompt = f"""
Translate the following chunk ({chunk_index + 1}/{total_chunks}) of the provided text into {target_lang} at a {level} level for a language learning app.

CRITICAL: DO NOT SUMMARIZE. YOU MUST TRANSLATE THE WHOLE CHUNK. DO NOT OMIT OR SHORTEN ANY PART OF THE ORIGINAL CONTENT.
Every detail, sentence, and dialogue turn from the original must be present in the final translation.
DO NOT provide any text outside of the JSON structure.

{context_prompt}

Tasks for this chunk:
1. Split the translated text into logical "scenes" or segments. 
   Group short adjacent dialogue turns and narration together into a single paragraph entry.
   CRITICAL: You MUST preserve all original paragraph breaks within these segments. 
   Use double newlines (\\n\\n) to separate paragraphs.
   IMPORTANT: The 'originalText' and 'translatedText' within each segment MUST have the exact same number of paragraphs (separated by \\n\\n) so they can be perfectly aligned in the UI.
   The goal is to maintain a high-quality "audiobook" experience while minimizing the number of audio requests.
   Segments should ideally be between 15 and 120 seconds of spoken audio length.
2. Identify every speaking character. You MUST include a "Narrator" character for non-dialogue text. If you encounter NEW characters (including the Narrator if this is the first chunk), provide a short description and voiceProfile.
   - If a character is already listed in Known Characters, do NOT add them to the "characters" list.
   Assign a voice name from this list: 
   - Male/Firm/Deep: 'Puck', 'Charon', 'Kore', 'Fenrir', 'Orus', 'Algenib', 'Rasalgethi', 'Alnilam', 'Iapetus', 'Schedar'
   - Female/Bright/Soft: 'Zephyr', 'Aoede', 'Leda', 'Callirrhoe', 'Autonoe', 'Enceladus', 'Despina', 'Erinome', 'Sulafat', 'Pulcherrima'
3. For each paragraph/segment, provide a list of "turns". A turn is a piece of text spoken by a specific speaker. Narration (even narration between parts of sentence spoken by a character) MUST be assigned to the character "Narrator". If a character has a known canonical name from the context, you MUST use that exact canonical name as the speaker. Concatenating the text of turns MUST give exactly the translated text.
   You may include natural, point-in-time vocal tags in English inside angle brackets within dialogue turns where contextually appropriate, such as <laugh>, <sigh>, <gasp>, <cough>, <throat-clearing>, <whisper>, or <chuckle>.
4. Extract key vocabulary words from the TRANSLATED text ({target_lang}), explaining them in {source_lang}.
   IMPORTANT (Proficiency Level: {level}): 
   - If level is A1 or A2, include even relatively simple/common words in the lexicon. 
   - If the target language is German, all NOUNS in the difficultWords list MUST include their definite article (der, die, das) in the "word" field.
   - For this chunk, you MUST provide at least 10 NEW words not mentioned in the context (for all profficiency levels).
5. Provide an "anchors" array for each difficult word. "Anchor" is a version of the word (e.g. conjugated differently or without the article) which occurs in translated text and should be linked to the explanation.
{f'6. The FIRST LINE of the provided text is the title. Extract it, translate it, and use it as the "title". The title must be the first element in the "turns" of the first paragraph.' if is_first else f'6. Use "{full_metadata["title"]}" as the title.'}

Return exactly this JSON format:
{{
  "title": "string",
  "characters": [
    {{ "name": "string", "description": "string", "voice": "string", "voiceProfile": "string" }}
  ],
  "difficultWords": [
    {{ "word": "string", "explanation": "string", "anchors": ["string"] }}
  ],
  "paragraphs": [
    {{ 
      "id": number, 
      "originalText": "string", 
      "translatedText": "string", 
      "turns": [{{ "speaker": "string", "text": "string" }}] 
    }}
  ]
}}

CHUNK TO PROCESS:
{chunk}
"""
        response = self._generate_content_with_retry(
            label=f"translate_chunk_{chunk_index + 1}",
            model="gemini-3.7-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                automatic_function_calling=dict(disable=True),
            )
        )
        if self.dry_run:
            if full_metadata and full_metadata.get("paragraphs"):
                return full_metadata
            return {
                "title": "Dry Run Title",
                "characters": [{"name": "Narrator", "description": "Narrator", "voice": "Rasalgethi", "voiceProfile": "Male/Firm/Deep"}],
                "difficultWords": [],
                "paragraphs": [{"id": 1, "originalText": chunk, "translatedText": chunk, "turns": [{"speaker": "Narrator", "text": chunk}]}]
            }

        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            self.usage["gemini-3.7-flash"]["input_tokens"] += getattr(response.usage_metadata, 'prompt_token_count', 0)
            self.usage["gemini-3.7-flash"]["output_tokens"] += getattr(response.usage_metadata, 'candidates_token_count', 0)

        raw_text = (response.text or "").strip()
        if not raw_text:
            finish_info = []
            if getattr(response, "candidates", None) and response.candidates:
                cand = response.candidates[0]
                finish_info.append(f"finish_reason={cand.finish_reason}")
                if getattr(cand, "finish_message", None):
                    finish_info.append(f"finish_message={cand.finish_message}")
                if getattr(cand, "safety_ratings", None):
                    blocked = [r for r in cand.safety_ratings if getattr(r, "blocked", False)]
                    if blocked:
                        finish_info.append(f"blocked_safety_ratings={blocked}")
                if "RECITATION" in str(getattr(cand, "finish_reason", "")).upper():
                    raise CopyrightRestrictionError(f"Gemini recitation filter triggered: {cand.finish_reason}", raw_text="")
            detail = f" ({', '.join(finish_info)})" if finish_info else ""
            raise ValueError(f"Gemini returned an empty response{detail}.")

        if raw_text.startswith("```"):
            lines = raw_text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            raw_text = "\n".join(lines).strip()

        try:
            return json.loads(raw_text)
        except json.JSONDecodeError as err:
            if is_copyright_error_text(raw_text):
                raise CopyrightRestrictionError(
                    f"Gemini copyright restriction refusal: {raw_text[:200]}...",
                    raw_text=raw_text
                ) from err
            preview = raw_text[:300] + ("..." if len(raw_text) > 300 else "")
            raise ValueError(
                f"Failed to parse Gemini response as JSON: {err}.\n"
                f"Raw response preview:\n{preview}"
            ) from err

    @retry_with_pangloss()
    def generate_tts(self, paragraph: ProcessedParagraph, characters: List[Character]) -> bytes:
        char_map = {}
        for c in characters:
            char_map[c["name"].lower()] = c
            for a in c.get("aliases", []) or []:
                char_map[a.lower()] = c
        narrator_char = char_map.get("narrator", characters[0] if characters else {"voice": "Rasalgethi", "voiceProfile": "Calm storytelling voice"})

        sub_chunks = partition_paragraph_into_subchunks(paragraph.get("turns", []))
        if not sub_chunks:
            paragraph["chunks"] = []
            return b""

        chunk_ranges = compute_chunk_ranges(sub_chunks, paragraph.get("translatedText", ""))
        chunk_audio_chunks = []
        chunks_info = []
        current_time_sec = 0.0

        for chunk_idx, chunk in enumerate(sub_chunks):
            # Clean each turn's text for TTS and filter empty turns
            prepared_turns = []
            for t in chunk:
                cleaned = clean_text_for_tts(t.get("text", ""))
                if any(c.isalnum() for c in cleaned):
                    prepared_turns.append({"speaker": t["speaker"], "text": cleaned})

            if not prepared_turns:
                continue

            chunk_speakers = list(dict.fromkeys(t["speaker"] for t in prepared_turns))

            if len(chunk_speakers) == 1:
                s = chunk_speakers[0]
                char = char_map.get(s.lower(), narrator_char)
                speech_config = types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=char.get("voice", "Rasalgethi"))
                    )
                )
                parts = [
                    types.Part(
                        text=t["text"],
                        speech_metadata=types.SpeechMetadata(
                            speaker=s,
                            style=char.get("voiceProfile")
                        )
                    )
                    for t in prepared_turns
                ]
                clean_s = s.replace(" ", "_")
                label = f"tts_p{paragraph['id']}_single_{clean_s}" if len(sub_chunks) == 1 else f"tts_p{paragraph['id']}_chunk{chunk_idx:02d}_{clean_s}"
            else:
                speaker_configs = []
                for s in chunk_speakers:
                    char = char_map.get(s.lower(), narrator_char)
                    speaker_configs.append(types.SpeakerVoiceConfig(
                        speaker=s,
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=char.get("voice", "Rasalgethi"))
                        )
                    ))
                speech_config = types.SpeechConfig(
                    multi_speaker_voice_config=types.MultiSpeakerVoiceConfig(
                        speaker_voice_configs=speaker_configs
                    )
                )
                parts = []
                for t in prepared_turns:
                    char = char_map.get(t["speaker"].lower(), narrator_char)
                    parts.append(types.Part(
                        text=t["text"],
                        speech_metadata=types.SpeechMetadata(
                            speaker=t["speaker"],
                            style=char.get("voiceProfile")
                        )
                    ))
                s1 = chunk_speakers[0].replace(" ", "_")
                s2 = chunk_speakers[1].replace(" ", "_")
                label = f"tts_p{paragraph['id']}_dual_{s1}_{s2}" if len(sub_chunks) == 1 else f"tts_p{paragraph['id']}_chunk{chunk_idx:02d}_{s1}_{s2}"

            response = self._generate_content_with_retry(
                label=label,
                model=self.tts_model,
                contents=[types.Content(parts=parts)],
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=speech_config,
                    automatic_function_calling=dict(disable=True),
                )
            )
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                self.usage[self.tts_model]["input_tokens"] += getattr(response.usage_metadata, 'prompt_token_count', 0)
                self.usage[self.tts_model]["output_tokens"] += getattr(response.usage_metadata, 'candidates_token_count', 0)

            candidate = response.candidates[0]
            audio_data = None
            for part in candidate.content.parts:
                if part.inline_data:
                    audio_data = part.inline_data.data
                    break

            if not audio_data:
                raise Exception(f"No audio data returned from Gemini TTS for paragraph {paragraph['id']} chunk {chunk_idx}. Finish reason: {candidate.finish_reason}")

            dur_ms = get_wav_duration_ms(audio_data)
            dur_sec = dur_ms / 1000.0
            start_sec = round(current_time_sec, 3)
            end_sec = round(current_time_sec + dur_sec, 3)
            start_char, end_char = chunk_ranges[chunk_idx] if chunk_idx < len(chunk_ranges) else (0, 0)
            chunks_info.append({
                "chunk_index": chunk_idx,
                "start_sec": start_sec,
                "end_sec": end_sec,
                "start_char": start_char,
                "end_char": end_char,
                "speakers": chunk_speakers,
            })
            current_time_sec = round(end_sec + 0.150, 3)

            chunk_audio_chunks.append(audio_data)

            # Pacing pause to protect against rate limits (skipped in dry_run or on last chunk)
            if not self.dry_run and len(sub_chunks) > 1 and chunk_idx < len(sub_chunks) - 1:
                time.sleep(1.0)

        paragraph["chunks"] = chunks_info
        return concat_wavs(chunk_audio_chunks, pause_ms=150)

    @retry_with_pangloss(max_retries=3, initial_delay=2)
    def find_character_merges_with_llm(self, characters: List[Character]) -> List[dict]:
        """
        Asks the LLM to inspect the full character list and identify characters that represent
        the same person/entity and should be merged.
        """
        if self.dry_run or not characters or len(characters) <= 1:
            return []

        clean_chars = [
            {
                "name": c.get("name"),
                "description": c.get("description", ""),
                "aliases": c.get("aliases", []) or [],
                "voice": c.get("voice", ""),
            }
            for c in characters
        ]

        prompt = f"""
You are an expert literary editor analyzing the cast of characters extracted from an audiobook.
Review the following list of characters, descriptions, and aliases:

{json.dumps(clean_chars, indent=2, ensure_ascii=False)}

Identify any character entries that actually represent the SAME person, entity, or role.
Common examples of duplicates to merge:
- Full formal names vs. shortened names or first names (e.g., 'Harry James Potter-Evans-Verres' and 'Harry' or 'Harry Potter').
- Titles / honorifics (e.g., 'Professor McGonagall' and 'Minerva McGonagall').
- Translated roles (e.g., 'Erzähler' and 'Narrator').
- Minor variations or typos in character names.

Instructions:
1. For each group that should be merged, pick the single best "canonical" name (prefer full/formal name or existing established name).
2. List all other character names from the list that should be merged into that canonical character under "aliases".
3. Do NOT merge distinct characters (e.g., Fred Weasley and George Weasley are different people; Ron Weasley is different).
4. If no characters need to be merged, return an empty array for "merges".

Return strictly JSON format:
{{
  "merges": [
    {{
      "canonical": "Harry James Potter-Evans-Verres",
      "aliases": ["Harry", "Harry Potter"]
    }}
  ]
}}
"""
        try:
            response = self._generate_content_with_retry(
                label="find_character_merges",
                model="gemini-3.7-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema={
                        "type": "OBJECT",
                        "properties": {
                            "merges": {
                                "type": "ARRAY",
                                "items": {
                                    "type": "OBJECT",
                                    "properties": {
                                        "canonical": {"type": "STRING"},
                                        "aliases": {"type": "ARRAY", "items": {"type": "STRING"}}
                                    },
                                    "required": ["canonical", "aliases"]
                                }
                            }
                        },
                        "required": ["merges"]
                    }
                )
            )
            raw_text = response.text or "{}"
            data = json.loads(raw_text)
            return data.get("merges", [])
        except Exception as e:
            print(f"Warning: Failed to obtain or parse character merges from LLM: {e}")
            return []

    def print_token_usage_statistics(self):
        print("\n" + "="*50)
        print("GEMINI API TOKEN USAGE & COST STATISTICS")
        print("="*50)
        
        total_cost = 0.0
        
        PRICING = {
            "gemini-3.7-flash": {
                "input": 1.50 / 1_000_000,
                "output": 9.00 / 1_000_000
            },
            "gemini-3.8-flash-tts": {
                "input": 0.50 / 1_000_000,
                "output": 9.00 / 1_000_000
            },
            "gemini-3.8-flash-lite-tts": {
                "input": 0.50 / 1_000_000,
                "output": 6.00 / 1_000_000
            }
        }
        
        for model, usage in self.usage.items():
            if usage["input_tokens"] > 0 or usage["output_tokens"] > 0:
                in_cost = usage["input_tokens"] * PRICING[model]["input"]
                out_cost = usage["output_tokens"] * PRICING[model]["output"]
                model_total = in_cost + out_cost
                total_cost += model_total
                
                print(f"Model: {model}")
                print(f"  Input Tokens:  {usage['input_tokens']:,} (${in_cost:.6f})")
                print(f"  Output Tokens: {usage['output_tokens']:,} (${out_cost:.6f})")
                print(f"  Total Cost:    ${model_total:.6f}")
                print("-" * 50)
                
        print(f"TOTAL API COST FOR THIS RUN: ${total_cost:.6f}")
        print("="*50 + "\n")
