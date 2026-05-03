import os
import json
from typing import List, Callable, Optional
from google import genai
from google.genai import types
from .models import StoryMetadata, Character, ProcessedParagraph
from .utils import retry_with_pangloss

class GeminiAPI:
    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)

    @retry_with_pangloss()
    def process_chunk(self, chunk: str, target_lang: str, level: str, source_lang: str, 
                      is_first: bool, full_metadata: StoryMetadata, chunk_index: int, total_chunks: int) -> dict:
        
        context_prompt = ""
        if not is_first or full_metadata["characters"]:
            char_names = ", ".join([c["name"] for c in full_metadata["characters"]])
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
- MAINTAIN CONSISTENCY: Use the same character names and descriptions for existing characters.
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
   Assign a voice name from this list: 
   - Male/Firm/Deep: 'Puck', 'Charon', 'Kore', 'Fenrir', 'Orus', 'Algenib', 'Rasalgethi', 'Alnilam', 'Iapetus', 'Schedar'
   - Female/Bright/Soft: 'Zephyr', 'Aoede', 'Leda', 'Callirrhoe', 'Autonoe', 'Enceladus', 'Despina', 'Erinome', 'Sulafat', 'Pulcherrima'
3. For each paragraph/segment, provide a list of "turns". A turn is a piece of text spoken by a specific speaker. Narration MUST be assigned to the character "Narrator".
4. Extract key vocabulary words from the TRANSLATED text ({target_lang}), explaining them in {source_lang}.
   IMPORTANT (Proficiency Level: {level}): 
   - If level is A1 or A2, include even relatively simple/common words in the lexicon. 
   - If the target language is German, all NOUNS in the difficultWords list MUST include their definite article (der, die, das) in the "word" field.
   - For this chunk, you MUST provide at least 10 NEW words not mentioned in the context (for all profficiency levels).
5. Provide an "anchors" array for each difficult word.
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
        response = self.client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            )
        )
        return json.loads(response.text)

    @retry_with_pangloss()
    def generate_tts(self, paragraph: ProcessedParagraph, characters: List[Character]) -> bytes:
        char_profiles = "\n".join([f"- {c['name']}: {c['voiceProfile']} (Voice: {c['voice']})" for c in characters])
        script = "\n".join([f"{t['speaker']}: {t['text']}" for t in paragraph["turns"]])

        prompt = f"""
Perform the following script in audio. 
Use the provided character profiles to guide your vocal performance for each speaker.
It is crucial that you switch voices and tones appropriately between characters.

CHARACTER PROFILES:
{char_profiles}

SCRIPT:
{script}
"""
        speakers = list(set([t["speaker"] for t in paragraph["turns"]]))
        
        # Build speech config
        if len(speakers) == 2:
            speaker_configs = []
            for s in speakers:
                # Find character by name (case-insensitive)
                char = next((c for c in characters if c["name"].lower() == s.lower()), None)
                if not char:
                    # Fallback to Narrator if specific character not found
                    char = next((c for c in characters if c["name"].lower() == "narrator"), characters[0])
                
                speaker_configs.append(types.SpeakerVoiceConfig(
                    speaker=s,
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=char["voice"])
                    )
                ))
            speech_config = types.SpeechConfig(
                multi_speaker_voice_config=types.MultiSpeakerVoiceConfig(
                    speaker_voice_configs=speaker_configs
                )
            )
        else:
            # Fallback for 1 or 3+ speakers
            # Use Narrator if present, otherwise the first available speaker
            primary_speaker = next((s for s in speakers if s.lower() == "narrator"), speakers[0])
            char = next((c for c in characters if c["name"].lower() == primary_speaker.lower()), characters[0])
            speech_config = types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=char["voice"])
                )
            )

        response = self.client.models.generate_content(
            model="gemini-3.1-flash-tts-preview",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=speech_config,
            )
        )
        
        # Extract audio data
        candidate = response.candidates[0]
        for part in candidate.content.parts:
            if part.inline_data:
                return part.inline_data.data
        
        raise Exception(f"No audio data returned from Gemini TTS. Finish reason: {candidate.finish_reason}")
