# **TASK OVERVIEW**

You are an expert Python developer. Your task is to build pangloss, a command-line interface (CLI) tool that transforms text files into immersive, bilingual audiobooks and self-contained HTML study aids.

pangloss is a Python port of a React web application called "Linguist AI". It uses the Google Generative AI SDK (google-genai) to chunk text, translate it, extract vocabulary, assign character voices, and generate multi-speaker TTS audio.

The defining feature of pangloss is its **aggressive file-system caching**, allowing long, expensive API operations to be paused, interrupted, and resumed without losing data or incurring duplicate API costs. Keep third-party dependencies to an absolute minimum (ideally just google-genai).

# **1\. ARCHITECTURE & SPECIFICATION**

## **1.1 CLI Interface & Commands**

The CLI should be built using Python's built-in argparse module. For progress indication, you may simply write to sys.stdout.

**Command Signature:** python pangloss.py build \<filepath\> \[options\]

**Options:**

* \--target-lang \<language\> (e.g., "German", "Spanish")  
* \--source-lang \<language\> (e.g., "English")  
* \--level \<level\> (e.g., "A1", "B2")  
* \--output-dir \<path\> (default: ./pangloss\_output)  
* \--render-only \<job\_id\> (Skips all API calls; forces generation of HTML and MP3 from an existing cache)  
* \--serve (Automatically spins up a local HTTP server to preview the generated HTML)

## **1.2 The Caching Engine (.pangloss/)**

Instead of browser storage, pangloss will use a hidden .pangloss/ directory adjacent to the input file (managed via Python's pathlib or os modules) to manage state. When python pangloss.py build story.txt is run, the engine must:

1. Hash story.txt and the CLI arguments (using hashlib) to create a unique job ID.  
2. Create .pangloss/\<job\_id\>/.  
3. Save the LLM generated metadata to .pangloss/\<job\_id\>/metadata.json.  
4. Save each of the processed original text chunks to .pangloss/\<job\_id\>/text\_chunks.json (append chunks as they are processed).  
5. Save the raw PCM or WAV audio chunks returned by Gemini TTS as .pangloss/\<job\_id\>/audio\_chunks/\<paragraph\_id\>.wav.  
6. **Resumability:** If the command is killed (Ctrl+C) and restarted, it must read metadata.json and skip LLM generation if it exists. It must then check the audio\_chunks/ directory and ONLY call the Gemini TTS API for paragraph IDs that are missing from the disk.

## **1.3 Audio Handling (PCM to WAV)**

The Gemini TTS API returns raw PCM data (Linear16, 24kHz, Mono). You must use Python's built-in wave module or struct to wrap the raw PCM bytes into a valid WAV file before saving it to disk, ensuring it's playable.

## **1.4 Exports (HTML and MP3)**

Once all audio chunks are cached on disk:

1. **HTML Export:** Generate a single, standalone HTML file. Read all cached .wav files from disk, encode them to MP3, encode them to base64 data:audio/mp3;base64,... (using the base64 module), and inject them directly into the provided HTML template. Serialize the metadata.json cleanly and inject it into the \<script\> tag.  
2. **MP3 Export:** Merge all the raw PCM/WAV chunks in sequential order. To minimize Python dependencies, you should use Python's built-in subprocess module to call the system's ffmpeg executable directly to concatenate the WAV files and encode them into a single .mp3 file.

## **1.5 The "Pangloss" Personality (Easter Eggs)**

Dr. Pangloss famously believed we live in "the best of all possible worlds" and that every disaster happens for a reason.

* When an API call fails and the app executes an exponential backoff retry (using a custom retry decorator or loop), log a warning with a Pangloss quote, e.g., \[Warning: API Rate Limit Hit\] "Private misfortunes make the general good. Retrying in 4s..."  
* If an audio chunk fails to encode but the app recovers, log: "Warning ignored. All is for the best in the best of all possible worlds."

## **1.6 Testing & Offline Iteration**

The application architecture must support rapid, offline iteration and robust testing:

* **Offline Iteration Mode (\--render-only \<job\_id\>):** To allow developers to tweak the HTML template, CSS, or MP3 encoding logic without making expensive Gemini API requests, implement a render-only flag. When provided, the app MUST bypass all network/GenAI calls, read the raw data exclusively from .pangloss/\<job\_id\>/, and generate the final output files.  
* **Manual UI Testing (\--serve):** Browsers sometimes block script execution in large local files. Providing the \--serve flag should execute python \-m http.server (or similar) in the output directory and print the localhost link to quickly verify the interactive HTML output.  
* **Unit Testing (pytest):** The codebase must be highly modular and fully testable using pytest. Core logic—such as text chunking algorithms, WAV header binary construction, payload formatting, and cache-path resolution—must be pure functions that do not require network access. Network layers (like the Gemini SDK) must be dependency-injected or easily mockable to allow the test suite to run in a CI/CD environment without real API keys.

# **2\. SPECIFIC AI PROMPTS TO PORT**

You must port the exact prompts used in the original app. Use the google-genai Python SDK.

**Model for Text/Metadata:** gemini-3-flash-preview (or latest available) **Model for TTS:** gemini-3.1-flash-tts-preview

### **Text Processing Prompt Template:**

Translate the following chunk (${chunkIndex}/${totalChunks}) of the provided text into ${targetLanguage} at a ${level} level for a language learning app.

CRITICAL: DO NOT SUMMARIZE. YOU MUST TRANSLATE THE WHOLE CHUNK. DO NOT OMIT OR SHORTEN ANY PART OF THE ORIGINAL CONTENT.  
Every detail, sentence, and dialogue turn from the original must be present in the final translation.  
DO NOT provide any text outside of the JSON structure.

${contextPrompt}

Tasks for this chunk:  
1\. Split the translated text into logical "scenes" or segments. Group short adjacent dialogue turns and narration together into a single paragraph entry. You MUST preserve all original paragraph breaks. Use double newlines (\\n\\n) to separate paragraphs. The 'originalText' and 'translatedText' MUST have the exact same number of paragraphs.  
2\. Identify every speaking character. If you encounter NEW characters, provide a short description and voiceProfile. Assign a voice name from this list: Male: 'Puck', 'Charon', 'Fenrir'. Female / children: 'Zephyr', 'Kore', 'Sulafat', 'Erinome'.  
3\. For each paragraph/segment, provide a list of "turns". A turn is a piece of text spoken by a specific speaker. Narration counts as "Narrator".  
4\. Extract key vocabulary words from the TRANSLATED text (${targetLanguage}), explaining them in ${sourceLanguage}. Provide an "anchors" array for each.

Return exactly this JSON format:  
{  
  "title": "string",  
  "characters": \[{ "name": "string", "description": "string", "voice": "string", "voiceProfile": "string" }\],  
  "difficultWords": \[{ "word": "string", "explanation": "string", "anchors": \["string"\] }\],  
  "paragraphs": \[{ "id": number, "originalText": "string", "translatedText": "string", "turns": \[{ "speaker": "string", "text": "string" }\] }\]  
}

CHUNK TO PROCESS:  
${chunkText}

### **Context Injection Logic (For chunks \> 1):**

CONTEXT FROM PREVIOUS PARTS:  
\- Title: ${fullMetadata.title}  
\- Known Characters: ${fullMetadata.characters.map(c \=\> c.name).join(', ')}  
\- Vocabulary already in dictionary: ${fullMetadata.difficultWords.map(w \=\> w.word).join(', ')}

CRITICAL:   
\- Continue the story exactly from where the previous part left off.  
\- MAINTAIN CONSISTENCY: Use the same character names and descriptions.  
\- DO NOT repeat words in the "difficultWords" list that are already present.  
\- Identify at least 10 NEW difficult words from this specific chunk.

### **TTS Generation Prompt Template:**

Perform the following script in audio.   
Use the provided character profiles to guide your vocal performance for each speaker.  
It is crucial that you switch voices and tones appropriately between characters.

CHARACTER PROFILES:  
${characterProfilesString}

SCRIPT:  
${scriptString}

*Note: The Gemini 3.1 TTS model currently expects speech\_config.multi\_speaker\_voice\_config for exactly 2 speakers. For 1 or 3+ speakers, fall back to a standard speech\_config.voice\_config using the narrator or primary speaker's voice.*

# **3\. REFERENCE SOURCE CODE**

Below is the original React/TypeScript source code. Use this to understand the metadata JSON schemas (which you should port to Python TypedDict or Pydantic models if you choose), the chunking logic (\~2000 words), and the exact HTML/CSS template string that must be generated for the final output.

Translate the browser APIs (localStorage, Blob, URL.createObjectURL) into their Python equivalents (json.dump, built-in wave or file I/O, direct base64 injection).

import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { BookOpen, Upload, Play, Pause, ChevronRight, Settings, Languages, Volume2, Info, X, BookMarked, Loader2, Download, Check, AlertCircle, RotateCw } from 'lucide-react';
import { createMp3Encoder } from 'wasm-media-encoders';
import { processStory, generateParagraphTTS, type StoryMetadata, type ProcessedParagraph } from './lib/gemini';

const uiTranslations: Record<string, any> = {
  English: {
    targetLang: "Target Language",
    sourceLang: "Your Native Language",
    proficiency: "Proficiency Level",
    inputText: "Input Text",
    placeholder: "Paste or type your story here...",
    process: "Process Story",
    statusReady: "Ready!",
    statusAnalyzing: "Analyzing and translating text...",
    statusAudio: "Generating audio for each paragraph...",
    statusWav: "Encoding MP3 file...",
    lexicon: "Lexicon.",
    vocabulary: "Key Vocabulary",
    cast: "Cast & Voice",
    voice: "Voice",
    back: "Back",
    next: "Next",
    export: "Export HTML",
    exportAudio: "Export MP3",
    dictionary: "Dictionary",
    setupTitle: "What would you like to read today?",
    setupDesc: "Upload an article, story, or message. We'll translate it, identify voices, and create a living audiobook for your learning journey.",
    paraOriginal: "Original Source",
    paraLearning: "Learning View",
    statusLabel: "Status",
    chapter: "Paragraph",
    finished: "Finished",
    progress: "Progress",
    est: "Est.",
    left: "left",
    levels: ["A1 - Beginner", "A2 - Elementary", "B1 - Intermediate", "B2 - Upper Intermediate", "C1 - Advanced"],
    languages: ["German", "French", "Spanish", "Italian", "Polish", "Japanese", "English"]
  },
  Polish: {
    targetLang: "Język Docelowy",
    sourceLang: "Twój Język Ojczysty",
    proficiency: "Poziom Zaawansowania",
    inputText: "Tekst wejściowy",
    placeholder: "Wklej lub wpisz swoją historię tutaj...",
    process: "Przetwórz Historię",
    statusReady: "Gotowe!",
    statusAnalyzing: "Analizowanie i tłumaczenie tekstu...",
    statusAudio: "Generowanie dźwięku dla każdego akapitu...",
    statusWav: "Kodowanie pliku MP3...",
    lexicon: "Leksykon.",
    vocabulary: "Kluczowe Słownictwo",
    cast: "Obsada i Głos",
    voice: "Głos",
    back: "Wstecz",
    next: "Dalej",
    export: "Eksportuj HTML",
    exportAudio: "Eksportuj MP3",
    dictionary: "Słownik",
    setupTitle: "Co chciałbyś dzisiaj przeczytać?",
    setupDesc: "Wgraj artykuł, historię lub wiadomość. Przetłumaczymy ją, zidentyfikujemy głosy i stworzymy interaktywny audiobook dla Twojej nauki.",
    paraOriginal: "Źródło Oryginalne",
    paraLearning: "Widok Nauki",
    statusLabel: "Status",
    chapter: "Akapit",
    finished: "Zakończono",
    progress: "Postęp",
    est: "Szac.",
    left: "pozostało",
    levels: ["A1 - Początkujący", "A2 - Podstawowy", "B1 - Średniozaawansowany", "B2 - Średniozaawansowany wyższy", "C1 - Zaawansowany"],
    languages: ["Niemiecki", "Francuski", "Hiszpański", "Włoski", "Polski", "Japoński", "Angielski"]
  }
};

const getPcmFromBlobUrl = async (blobUrl: string) => {
  try {
    const response = await fetch(blobUrl);
    const buffer = await response.arrayBuffer();
    // WAV header is 44 bytes
    return new Uint8Array(buffer).slice(44);
  } catch (e) {
    console.error("[getPcmFromBlobUrl] Failed:", e);
    throw e;
  }
};

const wavHeader = (pcmLength: number, sampleRate: number) => {
  const header = new ArrayBuffer(44);
  const view = new DataView(header);
  view.setUint32(0, 0x52494646, false);
  view.setUint32(4, 36 + pcmLength, true);
  view.setUint32(8, 0x57415645, false);
  view.setUint32(12, 0x666d7420, false);
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  view.setUint32(36, 0x64617461, false);
  view.setUint32(40, pcmLength, true);

  return header;
};

const base64ToBlobUrl = (base64: string) => {
  const binary = atob(base64);
  const pcmData = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) pcmData[i] = binary.charCodeAt(i);
  
  const header = wavHeader(pcmData.length, 24000);
  const blob = new Blob([header, pcmData], { type: 'audio/wav' });
  return URL.createObjectURL(blob);
};

export default function App() {
  const [text, setText] = useState('');
  const [language, setLanguage] = useState('German');
  const [sourceLanguage, setSourceLanguage] = useState('English');
  const [level, setLevel] = useState('B1');
  const [isLoading, setIsLoading] = useState(false);
  const [status, setStatus] = useState('');
  const [progress, setProgress] = useState(0);
  const [timeEstimate, setTimeEstimate] = useState<string | null>(null);
  const [metadata, setMetadata] = useState<StoryMetadata | null>(null);
  const [activeParagraphId, setActiveParagraphId] = useState<number | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [audioUrls, setAudioUrls] = useState<Record<number, string>>({});
  const audioUrlsRef = useRef<Record<number, string>>({});
  
  // Cleanup object URLs on unmount
  useEffect(() => {
    return () => {
      Object.values(audioUrlsRef.current).forEach((url: string | null) => {
        if (url && url.startsWith('blob:')) URL.revokeObjectURL(url);
      });
    };
  }, []);

  // Sync ref with state
  useEffect(() => {
    audioUrlsRef.current = audioUrls;
  }, [audioUrls]);

  const [paragraphErrors, setParagraphErrors] = useState<Record<number, string>>({});
  const [showDictionary, setShowDictionary] = useState(false);
  
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const t = uiTranslations[sourceLanguage] || uiTranslations.English;

  // Persistence: Load from localStorage on mount
  useEffect(() => {
    const savedText = localStorage.getItem('linguist_text');
    const savedLang = localStorage.getItem('linguist_language');
    const savedSourceLang = localStorage.getItem('linguist_sourceLanguage');
    const savedLevel = localStorage.getItem('linguist_level');
    const savedMetadata = localStorage.getItem('linguist_metadata');

    if (savedText) setText(savedText);
    if (savedLang) setLanguage(savedLang);
    if (savedSourceLang) setSourceLanguage(savedSourceLang);
    if (savedLevel) setLevel(savedLevel);
    
    if (savedMetadata) {
      try {
        const parsedMetadata: StoryMetadata = JSON.parse(savedMetadata);
        setMetadata(parsedMetadata);
        
        // Load audio from storage if available
        console.log("[Persistence] Metadata loaded, checking for saved audio...");
        const initialAudioUrls: Record<number, string> = {};
        parsedMetadata.paragraphs.forEach(p => {
          const savedBase64 = localStorage.getItem(`linguist_audio_${p.id}`);
          if (savedBase64) {
            console.log(`[Persistence] Found saved audio for para ${p.id}`);
            initialAudioUrls[p.id] = base64ToBlobUrl(savedBase64);
          }
        });
        setAudioUrls(initialAudioUrls);
      } catch (e) {
        console.error("Failed to parse saved metadata", e);
      }
    }
  }, []);

  // Persistence: Save to localStorage on changes
  useEffect(() => {
    if (text) {
      localStorage.setItem('linguist_text', text);
    } else {
      localStorage.removeItem('linguist_text');
    }
    
    localStorage.setItem('linguist_language', language);
    localStorage.setItem('linguist_sourceLanguage', sourceLanguage);
    localStorage.setItem('linguist_level', level);
    
    if (metadata) {
      localStorage.setItem('linguist_metadata', JSON.stringify(metadata));
    } else {
      localStorage.removeItem('linguist_metadata');
    }
  }, [text, language, sourceLanguage, level, metadata]);

  useEffect(() => {
    if (activeParagraphId && isPlaying) {
      const element = document.getElementById(`section-${activeParagraphId}`);
      if (element) {
        element.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }
  }, [activeParagraphId, isPlaying]);

  const processingIdRef = useRef(0);

  const handleReset = () => {
    console.log("[handleReset] Triggered");
    // Invalidate any ongoing background processing
    processingIdRef.current++;

    // Manual cleanup of blob URLs
    Object.values(audioUrls).forEach((url: string) => {
      if (url && url.startsWith('blob:')) URL.revokeObjectURL(url);
    });
    
    // Only proceed if there is something to discard
    const hasActiveContent = !!metadata || isLoading || text.trim().length > 0;
    console.log("[handleReset] hasActiveContent:", hasActiveContent);
    if (!hasActiveContent) return;

    // We remove the confirm to ensure immediate response to user clicks
    setMetadata(null);
    setAudioUrls({});
    setParagraphErrors({});
    setIsPlaying(false);
    setActiveParagraphId(null);
    setIsLoading(false);
    setStatus(t.statusReady);
    setProgress(0);
    setTimeEstimate(null);
    setText(''); // Return to totally empty setup
    
    // Explicitly clear persistent storage
    localStorage.removeItem('linguist_metadata');
    localStorage.removeItem('linguist_text');
    
    // Clear all audio segments from storage
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key?.startsWith('linguist_audio_')) {
        localStorage.removeItem(key);
        i--; // Adjust index after removal
      }
    }
    
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.src = '';
    }
  };

  const handleProcess = async () => {
    console.log("[handleProcess] Started", { language, level, sourceLanguage, textLength: text.length });
    if (!text.trim()) return;
    
    const opId = ++processingIdRef.current;
    console.log("[handleProcess] opId:", opId);
    
    setIsLoading(true);
    setStatus(t.statusAnalyzing);
    setProgress(0);
    setTimeEstimate(null);
    setParagraphErrors({});
    
    // Revoke and clear old audio
    Object.values(audioUrls).forEach((url: string) => {
      if (url && url.startsWith('blob:')) URL.revokeObjectURL(url);
    });
    setAudioUrls({});

    // Clear old audio from storage
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key?.startsWith('linguist_audio_')) {
        localStorage.removeItem(key);
        i--;
      }
    }

    setMetadata(null);

    try {
      const data = await processStory(text, language, level, sourceLanguage, 
        (p) => {
          if (processingIdRef.current !== opId) return;
          setProgress(p * 0.3); // First 30% for analysis/translation
        },
        (partial) => {
          if (processingIdRef.current !== opId) return;
          setMetadata(partial);
        }
      );
      
      if (processingIdRef.current !== opId) {
        return;
      }
      
      setMetadata(data);
      setStatus(t.statusAudio);
      
      const total = data.paragraphs.length;
      const startTime = Date.now();
      
      // Sequential processing
      for (const [index, p] of data.paragraphs.entries()) {
        if (processingIdRef.current !== opId) {
          return;
        }

        const audioProgress = Math.round(((index + 1) / total) * 70);
        setProgress(30 + audioProgress); // Next 70% for audio
        
        // Estimate remaining time
        if (index > 0) {
          const elapsed = Date.now() - startTime;
          const avgPerPara = elapsed / index;
          const remaining = (total - index) * avgPerPara;
          const remainingSecs = Math.ceil(remaining / 1000);
          const mins = Math.floor(remainingSecs / 60);
          const secs = remainingSecs % 60;
          setTimeEstimate(`${mins > 0 ? `${mins}m ` : ''}${secs}s`);
        }

        setStatus(`${t.statusAudio} (${index + 1}/${data.paragraphs.length})`);
        
        try {
          console.log(`[handleProcess] Generating TTS for paragraph ${p.id}...`);
          const base64 = await generateParagraphTTS(p, data.characters);
          if (processingIdRef.current !== opId) {
            console.log(`[handleProcess] Process ${opId} cancelled during TTS for ${p.id}`);
            return;
          }
          
          console.log(`[handleProcess] TTS generated for ${p.id}, length: ${base64.length}`);
          
          // Save to localStorage
          try {
            localStorage.setItem(`linguist_audio_${p.id}`, base64);
          } catch (e) {
            console.warn(`[handleProcess] Failed to save para ${p.id} to storage (likely quota)`, e);
          }

          const blobUrl = base64ToBlobUrl(base64);
          setAudioUrls(prev => {
            // Revoke old URL if it exists
            if (prev[p.id]?.startsWith('blob:')) URL.revokeObjectURL(prev[p.id]);
            return { ...prev, [p.id]: blobUrl };
          });
        } catch (err: any) {
          console.error(`Error generating audio for paragraph ${p.id}:`, err);
          if (processingIdRef.current === opId) {
            setParagraphErrors(prev => ({ ...prev, [p.id]: err.message || "Failed to generate audio" }));
          }
        }
      }
      
      if (processingIdRef.current === opId) {
        setStatus(t.statusReady);
        setIsLoading(false);
        setProgress(0);
        setTimeEstimate(null);
      }
    } catch (error: any) {
      if (processingIdRef.current !== opId) {
        return;
      }
      console.error(error);
      const errorMessage = error.message || 'Error occurred. Please try again.';
      setStatus(`Error: ${errorMessage}`);
      setIsLoading(false);
      setProgress(0);
      setTimeEstimate(null);
    }
  };

  const retryParagraph = async (pId: number) => {
    if (!metadata) return;
    const p = metadata.paragraphs.find(para => para.id === pId);
    if (!p) return;

    setParagraphErrors(prev => {
      const { [pId]: _, ...rest } = prev;
      return rest;
    });

    try {
      const base64 = await generateParagraphTTS(p, metadata.characters);
      // Save to localStorage
      try {
        localStorage.setItem(`linguist_audio_${pId}`, base64);
      } catch (e) {
        console.warn(`[retryParagraph] Failed to save para ${pId} to storage`, e);
      }
      const blobUrl = base64ToBlobUrl(base64);
      setAudioUrls(prev => {
        if (prev[pId]?.startsWith('blob:')) URL.revokeObjectURL(prev[pId]);
        return { ...prev, [pId]: blobUrl };
      });
    } catch (err: any) {
      console.error(`Retry error for paragraph ${pId}:`, err);
      setParagraphErrors(prev => ({ ...prev, [pId]: err.message || "Failed to generate audio" }));
    }
  };

  const encodePcmToMp3 = async (pcmChunks: Uint8Array[]) => {
    console.log(`[encodePcmToMp3] Encoding ${pcmChunks.length} chunks`);
    try {
      const encoder = await createMp3Encoder();
      console.log("[encodePcmToMp3] Encoder created");
      encoder.configure({
        sampleRate: 24000,
        channels: 1,
        vbrQuality: 5,
      });

      const mp3Chunks: Uint8Array[] = [];
      for (const [idx, chunk] of pcmChunks.entries()) {
        console.log(`[encodePcmToMp3] Processing chunk ${idx + 1}/${pcmChunks.length}, size: ${chunk.length}`);
        const int16 = new Int16Array(chunk.buffer, chunk.byteOffset, chunk.byteLength / 2);
        const float32 = new Float32Array(int16.length);
        for (let i = 0; i < int16.length; i++) {
          float32[i] = int16[i] / 32768;
        }
        
        const mp3Data = encoder.encode([float32]);
        if (mp3Data.length > 0) mp3Chunks.push(new Uint8Array(mp3Data));
      }

      console.log("[encodePcmToMp3] Finalizing encoder");
      const finalMp3Data = encoder.finalize();
      if (finalMp3Data.length > 0) mp3Chunks.push(new Uint8Array(finalMp3Data));

      const totalLength = mp3Chunks.reduce((acc, chunk) => acc + chunk.length, 0);
      const result = new Uint8Array(totalLength);
      let offset = 0;
      for (const chunk of mp3Chunks) {
        result.set(chunk, offset);
        offset += chunk.length;
      }
      console.log(`[encodePcmToMp3] Success, total MP3 size: ${result.length}`);
      return result;
    } catch (err) {
      console.error("[encodePcmToMp3] Error:", err);
      throw err;
    }
  };

  const playParagraph = (id: number, restart = true) => {
    console.log(`[playParagraph] id: ${id}, restart: ${restart}`);
    if (!audioUrls[id]) {
      console.warn(`[playParagraph] No audio URL for id: ${id}`);
      return;
    }
    if (!audioRef.current) {
      console.error("[playParagraph] audioRef.current is null");
      return;
    }
    
    try {
      // Only restart if explicitly asked OR if it's a different audio source
      if (restart || audioRef.current.src !== audioUrls[id]) {
        console.log(`[playParagraph] Setting src for id: ${id}`);
        audioRef.current.src = audioUrls[id];
      }
      
      console.log(`[playParagraph] Calling play() for id: ${id}`);
      const playPromise = audioRef.current.play();
      if (playPromise !== undefined) {
        playPromise.catch(err => {
          console.error("[playParagraph] play() failed:", err);
          setIsPlaying(false);
        });
      }
      setActiveParagraphId(id);
      setIsPlaying(true);
    } catch (e) {
      console.error("[playParagraph] Exception:", e);
    }
  };

  const togglePlay = () => {
    console.log("[togglePlay] Triggered, isPlaying:", isPlaying);
    if (!metadata) {
      console.warn("[togglePlay] No metadata");
      return;
    }
    if (isPlaying) {
      console.log("[togglePlay] Pausing...");
      audioRef.current?.pause();
      setIsPlaying(false);
    } else {
      console.log("[togglePlay] Playing...");
      // Resume current paragraph if it's already loaded
      if (activeParagraphId && audioRef.current && audioRef.current.src === audioUrls[activeParagraphId]) {
        console.log(`[togglePlay] Resuming paragraph ${activeParagraphId}`);
        audioRef.current.play().catch(err => console.error("[togglePlay] resume failed:", err));
        setIsPlaying(true);
      } else {
        const nextId = activeParagraphId || metadata.paragraphs[0].id;
        console.log(`[togglePlay] Starting from paragraph ${nextId}`);
        playParagraph(nextId);
      }
    }
  };

  const handleAudioEnded = () => {
    console.log("[handleAudioEnded] activeParagraphId:", activeParagraphId);
    if (!metadata) return;
    const currentIndex = metadata.paragraphs.findIndex(p => p.id === activeParagraphId);
    
    // Find the next paragraph that HAS audio
    let nextIndex = currentIndex + 1;
    while (nextIndex < metadata.paragraphs.length) {
      const nextPara = metadata.paragraphs[nextIndex];
      if (audioUrls[nextPara.id]) {
        console.log(`[handleAudioEnded] Transitioning to next paragraph: ${nextPara.id}`);
        playParagraph(nextPara.id);
        return;
      }
      nextIndex++;
    }
    
    console.log("[handleAudioEnded] End of story reached.");
    setIsPlaying(false);
    setActiveParagraphId(null);
  };

  const exportToAudio = async () => {
    console.log("[exportToAudio] Started");
    if (!metadata) {
      console.warn("[exportToAudio] No metadata");
      return;
    }
    setStatus(t.statusWav);
    setIsLoading(true);
    setProgress(0);
    try {
      const pcmChunks: Uint8Array[] = [];
      
      console.log(`[exportToAudio] Gathering audio for ${metadata.paragraphs.length} paragraphs...`);
      for (const [idx, p] of metadata.paragraphs.entries()) {
        setProgress((idx / metadata.paragraphs.length) * 50); 
        let currentUrl = audioUrls[p.id];
        let pcmBytes: Uint8Array;
        
        if (currentUrl) {
          pcmBytes = await getPcmFromBlobUrl(currentUrl);
        } else {
          console.log(`[exportToAudio] Paragraph ${p.id} missing audio, generating...`);
          const base64 = await generateParagraphTTS(p, metadata.characters);
          
          // Save to localStorage
          try {
            localStorage.setItem(`linguist_audio_${p.id}`, base64);
          } catch (e) {
            console.warn(`[exportToAudio] Failed to save para ${p.id} to storage`, e);
          }

          const newUrl = base64ToBlobUrl(base64);
          setAudioUrls(prev => ({ ...prev, [p.id]: newUrl }));
          pcmBytes = await getPcmFromBlobUrl(newUrl);
        }
        pcmChunks.push(pcmBytes);
      }
      
      console.log("[exportToAudio] Encoding to MP3...");
      setProgress(60);
      const response = await encodePcmToMp3(pcmChunks);
      console.log(`[exportToAudio] MP3 encoded, size: ${response.length}`);
      setProgress(100);
      const blob = new Blob([response], { type: 'audio/mp3' });
      const url = URL.createObjectURL(blob);
      
      const link = document.createElement('a');
      link.style.display = 'none';
      document.body.appendChild(link);
      link.href = url;
      link.download = `${metadata.title.toLowerCase().replace(/[^a-z0-9]/g, '-')}-${Date.now()}.mp3`;
      link.click();
      
      setTimeout(() => {
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
      }, 100);
      
      setStatus(t.statusReady);
    } catch (err) {
      console.error("[exportToAudio] Error:", err);
      setStatus("Failed to export audio.");
    } finally {
      setIsLoading(false);
      setProgress(0);
    }
  };

  const exportToHtml = async () => {
    console.log("[exportToHtml] Started");
    if (!metadata) {
      console.warn("[exportToHtml] No metadata");
      return;
    }
    setStatus(t.statusAudio);
    setIsLoading(true);
    setProgress(0);
    
    try {
      const mp3DataUrls: Record<number, string> = {};
      
      console.log(`[exportToHtml] Gathering and encoding ${metadata.paragraphs.length} paragraphs...`);
      for (const [idx, p] of metadata.paragraphs.entries()) {
        setProgress((idx / metadata.paragraphs.length) * 100);
        let currentUrl = audioUrls[p.id];
        let pcmBytes: Uint8Array;
        
        if (currentUrl) {
          pcmBytes = await getPcmFromBlobUrl(currentUrl);
        } else {
          console.log(`[exportToHtml] Paragraph ${p.id} missing audio, generating...`);
          const base64 = await generateParagraphTTS(p, metadata.characters);
          
          // Save to localStorage
          try {
            localStorage.setItem(`linguist_audio_${p.id}`, base64);
          } catch (e) {
            console.warn(`[exportToHtml] Failed to save para ${p.id} to storage`, e);
          }

          const newUrl = base64ToBlobUrl(base64);
          setAudioUrls(prev => ({ ...prev, [p.id]: newUrl }));
          pcmBytes = await getPcmFromBlobUrl(newUrl);
        }

        const int16 = new Int16Array(pcmBytes.buffer, pcmBytes.byteOffset, pcmBytes.byteLength / 2);
        const float32 = new Float32Array(int16.length);
        for (let i = 0; i < int16.length; i++) float32[i] = int16[i] / 32768;

        const encoder = await createMp3Encoder();
        encoder.configure({ sampleRate: 24000, channels: 1, vbrQuality: 5 });
        const mp3Body = new Uint8Array(encoder.encode([float32]));
        const mp3Tail = new Uint8Array(encoder.finalize());
        
        const segmentMp3 = new Uint8Array(mp3Body.length + mp3Tail.length);
        segmentMp3.set(mp3Body, 0);
        segmentMp3.set(mp3Tail, mp3Body.length);
        
        // Efficient way to convert Uint8Array to base64
        let binary = '';
        for (let i = 0; i < segmentMp3.length; i++) binary += String.fromCharCode(segmentMp3[i]);
        const mp3Base64 = btoa(binary);
        mp3DataUrls[p.id] = `data:audio/mp3;base64,${mp3Base64}`;
      }

      console.log("[exportToHtml] Generating HTML content...");
      const playSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="black" stroke="black" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="6 3 22 12 6 21 6 3"/></svg>`;
      const pauseSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="black" stroke="black" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>`;

      const htmlContent = `<!DOCTYPE html>
<html lang="${sourceLanguage === 'Polish' ? 'pl' : 'en'}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>${metadata.title} | Linguist</title>
    <link href="https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,400;0,700;1,400;1,700&display=swap" rel="stylesheet">
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        :root {
            --paper: #F9F7F2;
            --ink: #1A1A1A;
            --accent: #5A5A40;
            --muted: #8C8A81;
            --highlight: rgba(90, 90, 64, 0.1);
        }
        body { background-color: var(--paper); color: var(--ink); font-family: 'Lora', Georgia, serif; -webkit-font-smoothing: antialiased; }
        .font-sans { font-family: 'Helvetica Neue', Arial, sans-serif; }
        .text-accent { color: var(--accent); }
        .text-muted { color: var(--muted); }
        .bg-paper { background-color: var(--paper); }
        .bg-ink { background-color: var(--ink); }
        .text-paper { color: var(--paper); }
        .bg-highlight { background-color: var(--highlight); }
        .selection\:bg-highlight *::selection { background-color: var(--highlight); }
        .border-accent { border-color: var(--accent); }
        .ring-accent\/20 { --tw-ring-color: rgba(90, 90, 64, 0.2); }
        
        .drawer { transform: translateX(100%); transition: transform 0.4s cubic-bezier(0.16, 1, 0.3, 1); }
        .drawer.active { transform: translateX(0); }
        .word { position: relative; border-bottom: 2px solid #5A5A40; cursor: help; display: inline; text-underline-offset: 4px; }
        .word:hover .tooltip { display: block; }
        .tooltip { display: none; position: absolute; bottom: 100%; left: 50%; transform: translate(-50%, -20px); background: #1A1A1A; color: #F9F7F2; padding: 25px; width: 300px; z-index: 1000; font-size: 0.9rem; font-family: sans-serif; border-radius: 0; box-shadow: 0 15px 45px rgba(0,0,0,0.6); line-height: 1.5; font-style: normal; }
        .text-content { white-space: pre-wrap; }
    </style>
</head>
<body class="bg-paper text-ink font-serif selection:bg-highlight min-h-screen">
    <button class="fixed top-10 right-10 border-none bg-transparent font-sans text-[11px] font-bold uppercase tracking-[2px] color-muted cursor-pointer z-50 flex items-center gap-2 hover:text-ink transition-colors" id="drawerToggle">
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1-2.5-2.5Z"/><path d="M8 7h8"/><path d="M8 11h8"/><path d="M8 15h5"/></svg>
        ${t.dictionary}
    </button>

    <div class="fixed inset-0 bg-black/20 backdrop-blur-sm z-[1999] opacity-0 pointer-events-none transition-opacity duration-300" id="overlay"></div>
    <div class="drawer fixed right-0 top-0 h-full w-full max-w-[450px] bg-[#F4F1EA] z-[2000] p-[60px_40px] border-l border-ink/10 overflow-y-auto shadow-[-20px_0_60px_rgba(0,0,0,0.2)]" id="drawer">
        <div class="flex justify-between items-start mb-16">
            <h2 class="text-[44px] italic font-bold font-serif">${t.lexicon}</h2>
            <button id="closeDrawer" class="bg-none border-none cursor-pointer opacity-50 p-2 hover:bg-ink/5 rounded-full transition-colors">
                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
            </button>
        </div>

        <div class="mb-16 space-y-8">
            <h4 class="text-[10px] uppercase font-bold tracking-[3px] text-muted border-b border-ink/10 pb-2">${t.vocabulary}</h4>
            <div id="vocabList" class="space-y-6"></div>
        </div>

        <div class="space-y-8">
            <h4 class="text-[10px] uppercase font-bold tracking-[3px] text-muted border-b border-ink/10 pb-2">${t.cast}</h4>
            <div id="castList" class="space-y-8"></div>
        </div>
    </div>

    <div class="max-w-[1400px] mx-auto p-[60px_40px_180px]">
        <header class="border-b-2 border-ink/5 pb-[30px] mb-[60px]">
            <h1 class="text-[3.5rem] m-0 italic font-[900] tracking-[-2px] leading-tight mb-4">${metadata.title}</h1>
            <p class="font-sans text-[10px] uppercase tracking-[3px] font-extrabold opacity-60 mt-2 text-accent">Linguist • Immersive Audiobooks • ${language} ${level}</p>
        </header>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-12 border-b border-ink/5 mb-12 pb-6">
            <header class="space-y-1">
                <span class="text-[10px] uppercase tracking-[2px] font-bold text-muted">${t.paraOriginal}</span>
                <h3 class="text-[1.8rem] italic m-0 font-bold font-serif">${t.paraOriginal}</h3>
            </header>
            <header class="space-y-1 hidden md:block">
                <span class="text-[10px] uppercase tracking-[2px] font-bold text-muted">${t.paraLearning} • ${language} ${level}</span>
                <h3 class="text-[1.8rem] italic m-0 font-bold font-serif">${t.paraLearning}</h3>
            </header>
        </div>

        <div id="story" class="space-y-8"></div>
    </div>

    <div class="fixed bottom-[50px] left-1/2 -translate-x-1/2 bg-ink text-paper p-[25px_50px] flex items-center justify-center shadow-[0_40px_80px_rgba(0,0,0,0.5)] z-[100] w-[600px] max-w-[90vw]">
        <div class="flex-1 flex items-center">
            <div class="flex flex-col">
                <span class="text-[8px] uppercase tracking-[3px] opacity-50 font-sans font-bold">${t.statusLabel}</span>
                <span id="status" class="text-[11px] font-bold uppercase tracking-[2.5px] font-sans border-l-2 border-accent pl-[15px] mt-[6px] min-w-[140px] text-paper">${t.statusReady}</span>
            </div>
        </div>
        <div class="flex-none flex justify-center mx-10">
            <button class="bg-paper text-ink w-[60px] h-[60px] rounded-full border-none font-bold cursor-pointer flex items-center justify-center transition-transform hover:scale-110" id="playToggle">${playSvg}</button>
        </div>
        <div class="flex-1 flex items-center justify-end">
            <div class="flex items-center gap-[30px]">
                <button class="bg-none border-none text-muted cursor-pointer font-sans text-[11px] font-bold uppercase tracking-[2px] transition-colors hover:text-paper" id="prevBtn" disabled>${t.back}</button>
                <div class="w-px h-5 bg-white/10"></div>
                <button class="bg-none border-none text-muted cursor-pointer font-sans text-[11px] font-bold uppercase tracking-[2px] transition-colors hover:text-paper" id="nextBtn">${t.next}</button>
            </div>
        </div>
    </div>

    <audio id="player"></audio>

    <script>
        const metadata = ${JSON.stringify(metadata)};
        const audioData = ${JSON.stringify(mp3DataUrls)};
        const storyEl = document.getElementById('story');
        const playBtn = document.getElementById('playToggle');
        const statusEl = document.getElementById('status');
        const player = document.getElementById('player');
        const prevBtn = document.getElementById('prevBtn');
        const nextBtn = document.getElementById('nextBtn');
        const drawer = document.getElementById('drawer');
        const overlay = document.getElementById('overlay');
        const drawerToggle = document.getElementById('drawerToggle');
        const closeDrawer = document.getElementById('closeDrawer');
        
        let currentId = null;
        let isPlaying = false;

        const PLAY_SVG = ${JSON.stringify(playSvg)};
        const PAUSE_SVG = ${JSON.stringify(pauseSvg)};

        function render() {
            storyEl.innerHTML = metadata.paragraphs.map(p => {
                const speakersList = Array.from(new Set(p.turns.map(t => t.speaker)));
                const speakers = speakersList.length > 0 ? speakersList.join(' • ') : 'Narrator';
                
                const origParas = p.originalText.split('\\n\\n');
                const transParas = p.translatedText.split('\\n\\n');
                const maxParas = Math.max(origParas.length, transParas.length);

                const sortedWords = [...metadata.difficultWords].sort((a,b) => b.word.length - a.word.length);

                const alignedContent = Array.from({ length: maxParas }).map((_, i) => {
                    let transPara = transParas[i] || "";
                    sortedWords.forEach(dw => {
                        const anchors = dw.anchors || [dw.word];
                        anchors.forEach(anchor => {
                            const escaped = anchor.replace(/[.*+?^$\{}(\)|[\]\\]/g, '\\\\$&');
                            const regex = new RegExp(\`(\\\\b)\${escaped}(\\\\b)\`, 'gi');
                            transPara = transPara.replace(regex, \`$1<span class="word">\${anchor}<div class="tooltip"><strong>\${dw.word}</strong>: \${dw.explanation}</div></span>$2\`);
                        });
                    });

                    return \`
                        <div class="grid grid-cols-1 md:grid-cols-2 gap-12 items-start mb-8 last:mb-0">
                            <div id="orig-\${p.id}-\${i}" class="text-xl leading-relaxed font-serif opacity-70 transition-all duration-300">\${origParas[i] || ""}</div>
                            <div id="trans-\${p.id}-\${i}" class="text-2xl leading-relaxed font-serif transition-all duration-300">\${transPara}</div>
                        </div>
                    \`;
                }).join('');

                return \`
                    <div class="group/row border-b border-ink/5 pt-12 pb-12 transition-all first:pt-0" id="section-\${p.id}">
                        <div class="flex items-center gap-4 mb-8">
                            <span class="text-[10px] uppercase tracking-[2px] font-bold text-muted border-b border-accent/30 pb-1">\${speakers}</span>
                            <button onclick="playPara(\${p.id})" class="w-8 h-8 rounded-full bg-accent/10 flex items-center justify-center hover:bg-accent hover:text-paper transition-all">
                                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
                            </button>
                        </div>
                        <div id="trans-\${p.id}" onclick="playPara(\${p.id})" class="cursor-pointer">
                            \${alignedContent}
                        </div>
                    </div>
                \`;
            }).join('');

            document.getElementById('vocabList').innerHTML = metadata.difficultWords.map(dw => \`
                <div class="group border-b border-ink/5 pb-6 last:border-0 hover:translate-x-1 transition-transform">
                    <p class="text-2xl font-serif font-bold mb-2">\${dw.word}</p>
                    <p class="text-sm text-ink/70 font-serif italic leading-relaxed">\${dw.explanation}</p>
                </div>
            \`).join('');

            document.getElementById('castList').innerHTML = metadata.characters.map(char => \`
                <div class="flex gap-6">
                    <div class="w-12 h-12 bg-paper border border-ink/10 rounded-full flex items-center justify-center flex-shrink-0 shadow-sm">
                        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#5A5A40" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 5L6 9H2v6h4l5 4V5z"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>
                    </div>
                    <div>
                        <p class="text-xl font-serif font-bold mb-1">\${char.name}</p>
                        <p class="text-xs text-ink/60 font-serif italic leading-relaxed mb-3">\${char.description}</p>
                        <div class="flex flex-wrap gap-2">
                            <span class="text-[9px] uppercase tracking-[2px] font-bold px-3 py-1 bg-accent text-paper rounded-full">Voice • \${char.voice}</span>
                            <span class="text-[9px] uppercase tracking-[1px] font-bold px-3 py-1 bg-ink/5 text-ink/70 rounded-full italic hover:bg-ink/10 transition-colors cursor-default">\${char.voiceProfile}</span>
                        </div>
                    </div>
                </div>
            \`).join('');
        }

        drawerToggle.onclick = () => {
            drawer.classList.add('active');
            overlay.classList.add('opacity-100', 'pointer-events-auto');
        };

        closeDrawer.onclick = overlay.onclick = () => {
            drawer.classList.remove('active');
            overlay.classList.remove('opacity-100', 'pointer-events-auto');
        };

        function playPara(id, restart = true) {
            if (restart || player.src !== audioData[id]) {
                player.src = audioData[id];
            }
            currentId = id;
            player.play();
            isPlaying = true;
            updateUI();
        }

        function updateUI() {
            document.querySelectorAll('[id^="section-"]').forEach(el => {
                el.classList.remove('bg-accent/5', 'ring-1', 'ring-accent/10', 'shadow-sm', 'p-8', '-mx-8', 'rounded-2xl');
            });
            document.querySelectorAll('[id^="orig-"]').forEach(el => el.classList.add('opacity-40'));

            if (currentId !== null) {
                const section = document.getElementById('section-' + currentId);
                if (section) {
                    section.classList.add('bg-accent/5', 'ring-1', 'ring-accent/10', 'shadow-sm', 'p-8', '-mx-8', 'rounded-2xl');
                    section.querySelectorAll('[id^="orig-"]').forEach(el => el.classList.remove('opacity-40'));
                    section.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }
                statusEl.innerText = \`${t.chapter} \` + currentId;
            }
            playBtn.innerHTML = isPlaying ? PAUSE_SVG : PLAY_SVG;
            
            const index = metadata.paragraphs.findIndex(p => p.id === currentId);
            prevBtn.disabled = index <= 0;
            nextBtn.disabled = index >= metadata.paragraphs.length - 1 && index !== -1;
        }

        playBtn.onclick = () => {
            if (isPlaying) {
                player.pause();
                isPlaying = false;
            } else {
                if (currentId !== null && player.src === audioData[currentId]) {
                    player.play();
                    isPlaying = true;
                } else {
                    const nextId = currentId !== null ? currentId : metadata.paragraphs[0].id;
                    playPara(nextId);
                }
            }
            updateUI();
        };

        prevBtn.onclick = () => {
            const index = metadata.paragraphs.findIndex(p => p.id === currentId);
            if (index > 0) playPara(metadata.paragraphs[index - 1].id);
        };

        nextBtn.onclick = () => {
            const index = metadata.paragraphs.findIndex(p => p.id === currentId);
            if (index < metadata.paragraphs.length - 1) playPara(metadata.paragraphs[index + 1].id);
        };

        player.onended = () => {
            const index = metadata.paragraphs.findIndex(p => p.id === currentId);
            if (index < metadata.paragraphs.length - 1) {
                playPara(metadata.paragraphs[index + 1].id);
            } else {
                isPlaying = false;
                currentId = null;
                updateUI();
                statusEl.innerText = '${t.finished}';
            }
        };

        window.addEventListener('load', () => {
          render();
          updateUI();
        });
        // Initial render for immediate visibility
        render();
    </script>
</body>
</html>`;

    setProgress(100);
    const blob = new Blob([htmlContent], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${metadata.title.toLowerCase().replace(/[^a-z0-9]/g, '-')}-${new Date().getTime()}.html`;
    a.click();
    URL.revokeObjectURL(url);
    console.log("[exportToHtml] Success");
    
    setStatus(t.statusReady);
  } catch (err) {
    console.error("[exportToHtml] Error:", err);
    setStatus("Failed to export HTML.");
  } finally {
    setIsLoading(false);
    setProgress(0);
  }
};

  return (
    <div className="min-h-screen bg-paper text-ink font-serif selection:bg-highlight">
      {/* Header */}
      <header className="fixed top-0 w-full z-50 bg-paper/80 backdrop-blur-md border-b border-ink/5 px-8 h-24 flex justify-between items-center transition-all duration-500">
        <div 
          className="flex items-center gap-4 cursor-pointer group" 
          onClick={() => (metadata || isLoading || text.trim()) && handleReset()}
        >
          <div className="w-14 h-14 bg-ink text-paper flex items-center justify-center rounded-full shadow-2xl shadow-ink/30 group-hover:scale-105 transition-transform duration-500">
            <BookOpen className="w-7 h-7" />
          </div>
          <div className="flex flex-col">
            <h1 className="text-4xl font-serif font-black italic tracking-tighter leading-[0.8] text-ink">Linguist.</h1>
            <span className="text-[10px] uppercase tracking-[4px] font-bold text-accent opacity-60 mt-1">Immersive Learning</span>
          </div>
        </div>
        
        {/* Universal Activity / Progress Bar */}
        <div className="flex-1 max-w-2xl mx-16">
          <AnimatePresence>
            {isLoading && (
              <motion.div 
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 5 }}
                className="w-full space-y-3"
              >
                <div className="flex justify-between items-end">
                  <div className="flex flex-col">
                    <span className="text-[9px] uppercase tracking-[3px] font-bold text-muted mb-1">{t.statusLabel}</span>
                    <span className="text-[11px] font-bold uppercase tracking-[2px] text-ink flex items-center gap-3">
                      <Loader2 className="w-3 h-3 animate-spin text-accent" />
                      {status}
                    </span>
                  </div>
                  <div className="flex items-center gap-6 text-[10px] uppercase tracking-[2px] font-bold text-muted">
                    {timeEstimate && (
                      <span className="flex items-center gap-2 bg-ink/5 px-3 py-1 rounded-full">
                        <RotateCw className="w-2 h-2 animate-spin-slow" />
                        {t.est} {timeEstimate}
                      </span>
                    )}
                    <span className="w-12 text-right text-accent font-black">{Math.round(progress)}%</span>
                  </div>
                </div>
                <div className="w-full h-1.5 bg-ink/5 rounded-full overflow-hidden p-[2px]">
                  <motion.div 
                    className="h-full bg-accent rounded-full shadow-[0_0_10px_rgba(90,90,64,0.3)]"
                    initial={{ width: 0 }}
                    animate={{ width: `${progress}%` }}
                    transition={{ type: "spring", bounce: 0, duration: 0.8 }}
                  />
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        <div className="flex items-center gap-8">
          {(metadata || isLoading) && (
            <div className="flex items-center gap-8 font-sans text-[11px] uppercase tracking-[2px] font-bold">
              {metadata && !isLoading && (
                <div className="flex items-center gap-6 border-r border-ink/10 pr-8 mr-2">
                  <button 
                    onClick={exportToAudio}
                    className="flex items-center gap-2 hover:text-accent transition-colors group"
                    title="Save as single MP3 file"
                  >
                    <Download className="w-4 h-4 group-hover:-translate-y-1 transition-transform" />
                    <span>{t.exportAudio}</span>
                  </button>
                  <button 
                    onClick={exportToHtml}
                    className="flex items-center gap-2 hover:text-accent transition-colors group"
                    title="Save as self-contained HTML"
                  >
                    <BookMarked className="w-4 h-4 group-hover:rotate-12 transition-transform" />
                    <span>{t.export}</span>
                  </button>
                </div>
              )}

              {metadata && (
                <button 
                  onClick={() => setShowDictionary(!showDictionary)}
                  className="flex items-center gap-2 hover:text-accent transition-colors"
                >
                  <Languages className="w-4 h-4" />
                  <span>{t.dictionary}</span>
                </button>
              )}
              
              <button 
                onClick={handleReset}
                className="p-3 hover:bg-ink/5 rounded-full transition-colors group"
                title={isLoading ? "Cancel Processing" : "Return to setup"}
              >
                <X className={`w-6 h-6 ${isLoading ? 'text-accent animate-pulse' : ''}`} />
              </button>
            </div>
          )}
        </div>
      </header>

      <main className="pt-24 pb-32 px-6 max-w-6xl mx-auto">
        <AnimatePresence mode="wait">
          {!metadata ? (
            <motion.div 
              key="setup"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              className="max-w-4xl mx-auto space-y-8"
            >
              <div className="text-center space-y-4">
                <h2 className="text-6xl font-serif font-normal leading-tight italic">{t.setupTitle}</h2>
                <p className="text-muted max-w-lg mx-auto font-serif">
                  {t.setupDesc}
                </p>
              </div>

              <div className="bg-white rounded-none p-10 shadow-xl border border-ink/5 space-y-8">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  {/* Native Language */}
                  <div className="space-y-2">
                    <label className="text-[10px] uppercase tracking-[2px] font-bold font-sans text-muted px-1">{t.sourceLang}</label>
                    <div className="relative">
                      <Info className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 opacity-40" />
                      <select 
                        value={sourceLanguage}
                        onChange={(e) => setSourceLanguage(e.target.value)}
                        className="w-full pl-10 pr-4 py-4 border-b border-ink/20 appearance-none bg-paper focus:outline-none focus:border-accent transition-all font-sans text-sm font-bold tracking-wide"
                      >
                        <option value="English">English</option>
                        <option value="Polish">Polski</option>
                      </select>
                    </div>
                  </div>

                  {/* Target Language */}
                  <div className="space-y-2">
                    <label className="text-[10px] uppercase tracking-[2px] font-bold font-sans text-muted px-1">{t.targetLang}</label>
                    <div className="relative">
                      <Languages className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 opacity-40" />
                      <select 
                        value={language}
                        onChange={(e) => setLanguage(e.target.value)}
                        className="w-full pl-10 pr-4 py-4 border-b border-ink/20 appearance-none bg-paper focus:outline-none focus:border-accent transition-all font-sans text-sm font-bold tracking-wide"
                      >
                        {t.languages.map((lang: string, i: number) => (
                          <option key={lang} value={uiTranslations.English.languages[i]}>{lang}</option>
                        ))}
                      </select>
                    </div>
                  </div>

                  {/* Proficiency Level */}
                  <div className="space-y-2">
                    <label className="text-[10px] uppercase tracking-[2px] font-bold font-sans text-muted px-1">{t.proficiency}</label>
                    <div className="relative">
                      <Settings className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 opacity-40" />
                      <select 
                        value={level}
                        onChange={(e) => setLevel(e.target.value)}
                        className="w-full pl-10 pr-4 py-4 border-b border-ink/20 appearance-none bg-paper focus:outline-none focus:border-accent transition-all font-sans text-sm font-bold tracking-wide"
                      >
                        {t.levels.map((lvl: string, i: number) => (
                          <option key={lvl} value={uiTranslations.English.levels[i].split(' - ')[0]}>{lvl}</option>
                        ))}
                      </select>
                    </div>
                  </div>
                </div>

                <div className="space-y-2">
                  <label className="text-[10px] uppercase tracking-[2px] font-bold font-sans text-muted px-1">{t.inputText}</label>
                  <textarea 
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                    placeholder={t.placeholder}
                    className="w-full min-h-[250px] p-6 border border-ink/10 bg-paper focus:outline-none focus:border-accent transition-all resize-none font-serif text-lg leading-relaxed"
                  />
                </div>

                <div className="space-y-4">
                  <button 
                    onClick={handleProcess}
                    disabled={isLoading || !text.trim()}
                    className="group w-full bg-ink text-paper py-5 font-sans font-bold uppercase tracking-[3px] flex items-center justify-center gap-4 hover:bg-accent transition-all disabled:opacity-50"
                  >
                    {isLoading ? (
                      <div className="flex items-center gap-4">
                        <Loader2 className="w-5 h-5 animate-spin" />
                        <span>{status}</span>
                      </div>
                    ) : (
                      <>
                        <Upload className="w-5 h-5 group-hover:scale-110 transition-transform" />
                        <span>{t.process}</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            </motion.div>
          ) : (
            <motion.div 
              key="reader"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="space-y-0"
            >
              {/* Reader Header */}
              <div className="mb-20 border-b border-ink/10 pb-16">
                <div className="mb-16">
                  <h2 className="text-6xl md:text-8xl font-serif font-black italic tracking-tighter leading-[0.85] text-ink mb-8">
                    {metadata.title}
                  </h2>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-16 mb-8">
                  <header className="space-y-2">
                    <span className="text-[10px] uppercase tracking-[3px] font-bold text-muted opacity-60">{t.paraOriginal}</span>
                    <h3 className="text-4xl font-serif font-bold italic tracking-tight">{t.paraOriginal}</h3>
                  </header>
                  <header className="space-y-2 hidden md:block">
                    <span className="text-[10px] uppercase tracking-[3px] font-bold text-muted opacity-60">{t.paraLearning} • {language} {level}</span>
                    <h3 className="text-4xl font-serif font-bold italic tracking-tight">{t.paraLearning}</h3>
                  </header>
                </div>
              </div>

              {/* Paragraph Rows */}
              <div className="space-y-16">
                {metadata.paragraphs.map(p => {
                  const origParas = p.originalText.split('\n\n');
                  const transParas = p.translatedText.split('\n\n');
                  const maxParas = Math.max(origParas.length, transParas.length);
                  
                  const isFailed = !!paragraphErrors[p.id];
                  
                  return (
                    <div 
                      key={p.id} 
                      id={`section-${p.id}`}
                      className={`group/row transition-all duration-500 rounded-lg relative ${activeParagraphId === p.id ? 'bg-accent/5 ring-1 ring-accent/10 p-8 shadow-sm' : 'p-0'} ${isFailed ? 'border border-red-100 bg-red-50/30' : ''}`}
                    >
                      {isFailed && (
                        <div className="absolute -top-3 right-4 bg-red-500 text-white text-[9px] font-bold px-2 py-1 rounded shadow-sm z-10 flex items-center gap-1">
                          <AlertCircle className="w-2 h-2" />
                          <span>Generation Failed</span>
                        </div>
                      )}
                      
                      <div className="flex items-center gap-4 mb-8">
                        <span className="text-[10px] uppercase tracking-[2px] font-bold text-muted border-b border-accent/30 pb-1">
                          {Array.from(new Set(p.turns.map(t => t.speaker))).join(' • ')}
                        </span>
                        
                        <div className="flex items-center gap-2">
                          {audioUrls[p.id] ? (
                            <button 
                              onClick={() => playParagraph(p.id)}
                              className={`w-8 h-8 rounded-full flex items-center justify-center transition-all ${
                                activeParagraphId === p.id && isPlaying 
                                  ? 'bg-accent text-paper' 
                                  : 'bg-accent/10 text-accent hover:bg-accent hover:text-paper'
                              }`}
                            >
                              {activeParagraphId === p.id && isPlaying ? <Pause className="w-4 h-4 fill-current" /> : <Play className="w-4 h-4 fill-current" />}
                            </button>
                          ) : isFailed ? (
                            <button 
                              onClick={() => retryParagraph(p.id)}
                              className="w-8 h-8 rounded-full bg-red-100 text-red-600 flex items-center justify-center hover:bg-red-500 hover:text-white transition-all shadow-sm"
                              title="Retry generation"
                            >
                              <RotateCw className="w-4 h-4" />
                            </button>
                          ) : isLoading ? (
                            <div className="w-8 h-8 flex items-center justify-center">
                              <div className="w-4 h-4 border-2 border-accent border-t-transparent rounded-full animate-spin" />
                            </div>
                          ) : null}
                          
                          {audioUrls[p.id] && activeParagraphId === p.id && isPlaying && (
                            <motion.div 
                              animate={{ opacity: [0.4, 1, 0.4] }} 
                              transition={{ repeat: Infinity, duration: 1 }}
                            >
                              <Volume2 className="w-3 h-3 text-accent" />
                            </motion.div>
                          )}
                        </div>
                      </div>

                      <div className="space-y-12">
                        {Array.from({ length: maxParas }).map((_, i) => (
                          <div key={i} className="grid grid-cols-1 md:grid-cols-2 gap-12 items-start">
                            {/* Left: Original */}
                            <div className={`transition-all duration-300 ${activeParagraphId === p.id ? 'opacity-70' : 'opacity-30'} ${isFailed ? 'opacity-40' : ''}`}>
                              <div className="text-xl leading-relaxed font-serif">{origParas[i] || ""}</div>
                            </div>

                            {/* Right: Translated */}
                            <div 
                              onClick={() => audioUrls[p.id] && playParagraph(p.id)}
                              className={`group transition-all duration-300 ${activeParagraphId === p.id ? 'opacity-100' : 'opacity-40 hover:opacity-100'} ${audioUrls[p.id] ? 'cursor-pointer' : 'cursor-default'} ${isFailed ? 'opacity-40' : ''}`}
                            >
                              <div className="text-2xl leading-relaxed font-serif">
                                {(() => {
                                  const dwList = [...metadata.difficultWords].sort((a,b) => b.word.length - a.word.length);
                                  const paraText = transParas[i] || "";
                                  let parts: any[] = [paraText];
                                  
                                  dwList.forEach(dw => {
                                    const anchors = dw.anchors || [dw.word];
                                    anchors.forEach(anchor => {
                                      const newParts: any[] = [];
                                      parts.forEach((part, idx) => {
                                        if (typeof part !== 'string') {
                                          newParts.push(part);
                                          return;
                                        }
                                        
                                        const escaped = anchor.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                                        const regex = new RegExp(`(\\b${escaped}\\b)`, 'gi');
                                        const subParts = part.split(regex);
                                        
                                        subParts.forEach((sub, j) => {
                                          if (sub.toLowerCase() === anchor.toLowerCase()) {
                                            newParts.push(
                                              <span key={`${dw.word}-${idx}-${j}`} className="relative group/word inline">
                                                <span className="underline decoration-accent underline-offset-4 decoration-2 cursor-help">
                                                  {sub}
                                                </span>
                                                <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-3 hidden group-hover/word:block w-56 p-4 bg-ink text-paper text-sm font-sans rounded-none shadow-2xl z-20 text-left">
                                                  <div className="font-bold border-b border-paper/20 pb-2 mb-2 uppercase tracking-widest text-[10px] whitespace-normal">{dw.word}</div>
                                                  <div className="opacity-80 italic font-serif leading-relaxed whitespace-normal text-xs">{dw.explanation}</div>
                                                </div>
                                              </span>
                                            );
                                          } else if (sub) {
                                            newParts.push(sub);
                                          }
                                        });
                                      });
                                      parts = newParts;
                                    });
                                  });
                                  return parts;
                                })()}
                              </div>
                              {isFailed && i === 0 && (
                                <p className="mt-4 text-xs font-sans text-red-500 italic border-t border-red-100 pt-2">
                                  {paragraphErrors[p.id]}
                                </p>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </main>

      {/* Dictionary Drawer */}
      <AnimatePresence>
        {showDictionary && metadata && (
          <>
            <motion.div 
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setShowDictionary(false)}
              className="fixed inset-0 bg-black/20 backdrop-blur-sm z-50"
            />
            <motion.div 
              initial={{ x: '100%' }}
              animate={{ x: 0 }}
              exit={{ x: '100%' }}
              transition={{ type: 'spring', damping: 30, stiffness: 200 }}
              className="fixed right-0 top-0 h-full w-full max-w-md bg-[#F4F1EA] shadow-2xl z-[60] p-10 overflow-y-auto border-l border-ink/10"
            >
              <div className="flex justify-between items-center mb-16">
                <h2 className="text-4xl font-serif font-bold italic">{t.lexicon}</h2>
                <button onClick={() => setShowDictionary(false)} className="p-2 hover:bg-ink/5 rounded-full transition-colors">
                  <X className="w-6 h-6" />
                </button>
              </div>

              <div className="space-y-16">
                <section className="space-y-8">
                  <h4 className="text-[10px] uppercase tracking-[3px] font-bold text-muted border-b border-muted/20 pb-2">{t.vocabulary}</h4>
                  <div className="grid gap-6">
                    {metadata.difficultWords.map((dw, i) => (
                      <div key={i} className="group border-b border-ink/5 pb-6 last:border-0">
                        <p className="text-2xl font-serif font-bold mb-2 group-hover:translate-x-1 transition-transform">{dw.word}</p>
                        <p className="text-sm text-ink/70 font-serif italic leading-relaxed">{dw.explanation}</p>
                      </div>
                    ))}
                  </div>
                </section>

                <section className="space-y-8">
                  <h4 className="text-[10px] uppercase tracking-[3px] font-bold text-muted border-b border-muted/20 pb-2">{t.cast}</h4>
                  <div className="grid gap-8">
                    {metadata.characters.map((char, i) => (
                      <div key={i} className="flex gap-6">
                        <div className="w-12 h-12 bg-paper border border-ink/10 rounded-full flex items-center justify-center flex-shrink-0 shadow-sm">
                          <Volume2 className="w-5 h-5 text-accent" />
                        </div>
                        <div>
                          <p className="text-xl font-serif font-bold mb-1">{char.name}</p>
                          <p className="text-xs text-ink/60 font-serif italic leading-relaxed mb-3">{char.description}</p>
                          <div className="flex flex-wrap gap-2">
                            <span className="text-[9px] uppercase tracking-[2px] font-bold px-3 py-1 bg-accent/10 text-accent rounded-full border border-accent/20">{t.voice} • {char.voice}</span>
                            <span className="text-[9px] uppercase tracking-[2px] font-bold px-3 py-1 bg-ink/5 text-muted rounded-full italic">{char.voiceProfile}</span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>

      {/* Floating Audio Controls */}
      {metadata && (
        <div className="fixed bottom-10 left-1/2 -translate-x-1/2 z-40">
          <motion.div 
            initial={{ y: 100 }}
            animate={{ y: 0 }}
            className="bg-ink text-paper px-10 py-5 rounded-none shadow-[0_20px_60px_-15px_rgba(0,0,0,0.3)] flex items-center justify-center gap-10 border border-white/5 min-w-[500px]"
          >
            <div className="flex-1 flex flex-col">
              <span className="text-[9px] uppercase tracking-[2px] font-bold text-muted mb-1">{t.statusLabel}</span>
              <span className="text-xs font-sans font-bold uppercase tracking-wider truncate w-40 border-l-2 border-accent pl-4">
                {activeParagraphId ? `${t.chapter} ${activeParagraphId}` : t.statusReady}
              </span>
            </div>

            <div className="flex-shrink-0 flex items-center gap-6">
              <button 
                onClick={togglePlay}
                className="w-14 h-14 bg-paper text-ink rounded-full flex items-center justify-center hover:bg-accent hover:text-paper transition-all shadow-xl"
              >
                {isPlaying ? <Pause className="w-6 h-6 fill-current" /> : <Play className="w-6 h-6 fill-current ml-1" />}
              </button>
            </div>

            <div className="flex-1 flex items-center gap-6 font-sans text-[11px] uppercase tracking-[2px] font-bold text-muted justify-end">
              <button 
                onClick={() => {
                   const currentIndex = metadata.paragraphs.findIndex(p => p.id === activeParagraphId);
                   if (currentIndex > 0) playParagraph(metadata.paragraphs[currentIndex - 1].id);
                }}
                className="hover:text-paper transition-colors disabled:opacity-30"
                disabled={!activeParagraphId || metadata.paragraphs.findIndex(p => p.id === activeParagraphId) === 0}
              >
                {t.back}
              </button>
              <div className="w-[1px] h-6 bg-white/10" />
              <button 
                onClick={() => {
                  const currentIndex = metadata.paragraphs.findIndex(p => p.id === activeParagraphId);
                  if (currentIndex < metadata.paragraphs.length - 1) playParagraph(metadata.paragraphs[currentIndex + 1].id);
                }}
                className="hover:text-paper transition-colors disabled:opacity-30"
                disabled={!activeParagraphId || metadata.paragraphs.findIndex(p => p.id === activeParagraphId) === metadata.paragraphs.length - 1}
              >
                {t.next}
              </button>
            </div>
          </motion.div>
        </div>
      )}

      {/* Hidden Audio */}
      <audio 
        ref={audioRef} 
        onEnded={handleAudioEnded}
        onPause={() => setIsPlaying(false)}
        onPlay={() => setIsPlaying(true)}
        onError={(e) => console.error("[audio] Error event:", e)}
      />
    </div>
  );
}
import { GoogleGenAI, Type, Modality } from "@google/genai";

const ai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY || "" });

export interface SpeakerTurn {
  speaker: string;
  text: string;
}

export interface ProcessedParagraph {
  id: number;
  originalText: string;
  translatedText: string;
  turns: SpeakerTurn[];
}

export interface DifficultWord {
  word: string;
  explanation: string;
  translation?: string;
  anchors?: string[]; // Array of strings (exact matches in text) that should trigger this word's tooltip
}

export interface StoryMetadata {
  title: string;
  characters: { name: string; description: string; voice: string; voiceProfile: string }[];
  difficultWords: DifficultWord[];
  paragraphs: ProcessedParagraph[];
}

async function withRetry<T>(fn: () => Promise<T>, maxRetries = 3, delay = 2000): Promise<T> {
  let lastError: any;
  for (let i = 0; i < maxRetries; i++) {
    try {
      return await fn();
    } catch (err) {
      lastError = err;
      console.warn(`Attempt ${i + 1} failed. Retrying in ${delay}ms...`, err);
      if (i < maxRetries - 1) {
        await new Promise(resolve => setTimeout(resolve, delay));
        delay *= 2; // Exponential backoff
      }
    }
  }
  throw lastError;
}

export async function processStory(
  text: string,
  targetLanguage: string,
  level: string,
  sourceLanguage: string,
  onProgress?: (progress: number) => void,
  onChunk?: (metadata: StoryMetadata) => void
): Promise<StoryMetadata> {
  // 1. Chunk the text into ~2000 word segments, split by paragraph boundaries
  const wordsPerChunk = 2000;
  const rawParagraphs = text.split(/\n\s*\n/);
  const chunks: string[] = [];
  let currentChunk: string[] = [];
  let currentWordCount = 0;

  for (const p of rawParagraphs) {
    const wordCount = p.split(/\s+/).length;
    if (currentWordCount + wordCount > wordsPerChunk && currentChunk.length > 0) {
      chunks.push(currentChunk.join('\n\n'));
      currentChunk = [];
      currentWordCount = 0;
    }
    currentChunk.push(p);
    currentWordCount += wordCount;
  }
  if (currentChunk.length > 0) {
    chunks.push(currentChunk.join('\n\n'));
  }

  let fullMetadata: StoryMetadata = {
    title: "",
    characters: [],
    difficultWords: [],
    paragraphs: []
  };

  for (let i = 0; i < chunks.length; i++) {
    const chunk = chunks[i];
    const isFirst = i === 0;

    const contextPrompt = !isFirst ? `
      CONTEXT FROM PREVIOUS PARTS:
      - Title: ${fullMetadata.title}
      - Known Characters: ${fullMetadata.characters.map(c => c.name).join(', ')}
      - Vocabulary already in dictionary: ${fullMetadata.difficultWords.map(w => w.word).join(', ')}
      
      CRITICAL: 
      - Continue the story exactly from where the previous part left off.
      - MAINTAIN CONSISTENCY: Use the same character names and descriptions for existing characters.
      - DO NOT repeat words in the "difficultWords" list that are already present in the context above.
      - Identify at least 10 NEW difficult words from this specific chunk.
    ` : "";

    const prompt = `
      Translate the following chunk (${i + 1}/${chunks.length}) of the provided text into ${targetLanguage} at a ${level} level for a language learning app.
      
      CRITICAL: DO NOT SUMMARIZE. YOU MUST TRANSLATE THE WHOLE CHUNK. DO NOT OMIT OR SHORTEN ANY PART OF THE ORIGINAL CONTENT.
      Every detail, sentence, and dialogue turn from the original must be present in the final translation.
      DO NOT provide any text outside of the JSON structure.

      ${contextPrompt}

      Tasks for this chunk:
      1. Split the translated text into logical "scenes" or segments. 
         Group short adjacent dialogue turns and narration together into a single paragraph entry.
         CRITICAL: You MUST preserve all original paragraph breaks within these segments. 
         Use double newlines (\\n\\n) to separate paragraphs.
         IMPORTANT: The 'originalText' and 'translatedText' within each segment MUST have the exact same number of paragraphs (separated by \\n\\n) so they can be perfectly aligned in the UI.
         The goal is to maintain a high-quality "audiobook" experience while minimizing the number of audio requests.
         Segments should ideally be between 15 and 120 seconds of spoken audio length.
      2. Identify every speaking character. If you encounter NEW characters, provide a short description and voiceProfile.
         Assign a voice name from this list: Male: 'Puck', 'Charon', 'Fenrir'. Female / children: 'Zephyr', 'Kore', 'Sulafat', 'Erinome'.
      3. For each paragraph/segment, provide a list of "turns". A turn is a piece of text spoken by a specific speaker. Narration counts as "Narrator".
      4. Extract key vocabulary words from the TRANSLATED text (${targetLanguage}), explaining them in ${sourceLanguage}.
         IMPORTANT (Proficiency Level: ${level}): 
         - If level is A1 or A2, include even relatively simple/common words in the lexicon. 
         - If the target language is German, all NOUNS in the difficultWords list MUST include their definite article (der, die, das) in the "word" field.
         - For this chunk, you MUST provide at least 10 NEW words not mentioned in the context (for all profficiency levels).
      5. Provide an "anchors" array for each difficult word.
      ${isFirst ? `6. The FIRST LINE of the provided text is the title. Extract it, translate it, and use it as the "title". The title must be the first element in the "turns" of the first paragraph.` : `6. Use "${fullMetadata.title}" as the title.`}

      Return exactly this JSON format:
      {
        "title": "string",
        "characters": [
          { "name": "string", "description": "string", "voice": "string", "voiceProfile": "string" }
        ],
        "difficultWords": [
          { "word": "string", "explanation": "string", "anchors": ["string"] }
        ],
        "paragraphs": [
          { 
            "id": number, 
            "originalText": "string", 
            "translatedText": "string", 
            "turns": [{ "speaker": "string", "text": "string" }] 
          }
        ]
      }

      CHUNK TO PROCESS:
      ${chunk}
    `;

    const chunkMetadata: StoryMetadata = await withRetry(async () => {
      const response = await ai.models.generateContent({
        model: "gemini-3-flash-preview",
        contents: [{ parts: [{ text: prompt }] }],
        config: {
          responseMimeType: "application/json",
          maxOutputTokens: 65536,
          responseSchema: {
            type: Type.OBJECT,
            properties: {
              title: { type: Type.STRING },
              characters: {
                type: Type.ARRAY,
                items: {
                  type: Type.OBJECT,
                  properties: {
                    name: { type: Type.STRING },
                    description: { type: Type.STRING },
                    voice: { type: Type.STRING },
                    voiceProfile: { type: Type.STRING },
                  },
                  required: ["name", "description", "voice", "voiceProfile"],
                },
              },
              difficultWords: {
                type: Type.ARRAY,
                items: {
                  type: Type.OBJECT,
                  properties: {
                    word: { type: Type.STRING },
                    explanation: { type: Type.STRING },
                    anchors: { type: Type.ARRAY, items: { type: Type.STRING } },
                  },
                  required: ["word", "explanation", "anchors"],
                },
              },
              paragraphs: {
                type: Type.ARRAY,
                items: {
                  type: Type.OBJECT,
                  properties: {
                    id: { type: Type.INTEGER },
                    originalText: { type: Type.STRING },
                    translatedText: { type: Type.STRING },
                    turns: {
                      type: Type.ARRAY,
                      items: {
                        type: Type.OBJECT,
                        properties: {
                          speaker: { type: Type.STRING },
                          text: { type: Type.STRING },
                        },
                        required: ["speaker", "text"],
                      }
                    }
                  },
                  required: ["id", "originalText", "translatedText", "turns"],
                },
              },
            },
            required: ["title", "characters", "difficultWords", "paragraphs"],
          },
        },
      });

      if (!response.text) {
        throw new Error(`Failed to process chunk ${i + 1}/${chunks.length}`);
      }

      return JSON.parse(response.text);
    });

    if (isFirst) {
      fullMetadata.title = chunkMetadata.title;
    }

    // Merge characters (avoiding duplicates)
    chunkMetadata.characters.forEach(newChar => {
      const existing = fullMetadata.characters.find(c => c.name.toLowerCase() === newChar.name.toLowerCase());
      if (!existing) {
        fullMetadata.characters.push(newChar);
      }
    });

    // Merge words (avoiding duplicates)
    chunkMetadata.difficultWords.forEach(newWord => {
      const existing = fullMetadata.difficultWords.find(w => w.word.toLowerCase() === newWord.word.toLowerCase());
      if (!existing) {
        fullMetadata.difficultWords.push(newWord);
      }
    });

    // Merge paragraphs (re-indexing IDs)
    const baseId = fullMetadata.paragraphs.length > 0 
      ? Math.max(...fullMetadata.paragraphs.map(p => p.id)) + 1 
      : 1;
    
    chunkMetadata.paragraphs.forEach((p, idx) => {
      fullMetadata.paragraphs.push({
        ...p,
        id: baseId + idx
      });
    });

    if (onProgress) {
      onProgress(Math.round(((i + 1) / chunks.length) * 100));
    }
    
    if (onChunk) {
      onChunk({...fullMetadata});
    }
  }

  return fullMetadata;
}

export async function generateParagraphTTS(
  paragraph: ProcessedParagraph,
  characters: StoryMetadata["characters"]
): Promise<string> {
  console.log(`[gemini] generateParagraphTTS for para ${paragraph.id}`);
  return await withRetry(async () => {
    // Construct a multi-speaker script for the TTS model
    const characterProfiles = characters.map(c => `- ${c.name}: ${c.voiceProfile} (Voice: ${c.voice})`).join('\n');
    const script = paragraph.turns.map(t => `${t.speaker}: ${t.text}`).join('\n');

    console.log(`[gemini] TTS script length: ${script.length} chars`);
    const prompt = `
      Perform the following script in audio. 
      Use the provided character profiles to guide your vocal performance for each speaker.
      It is crucial that you switch voices and tones appropriately between characters.

      CHARACTER PROFILES:
      ${characterProfiles}

      SCRIPT:
      ${script}
    `;

    // Build speaker voice configurations for the multi-speaker feature
    const paragraphSpeakers = new Set(paragraph.turns.map(t => t.speaker));
    const speakerVoiceConfigs = Array.from(paragraphSpeakers).map(speakerName => {
      const char = characters.find(c => c.name === speakerName) || 
                   characters.find(c => c.name.toLowerCase() === 'narrator') || 
                   characters[0];
      return {
        speaker: speakerName,
        voiceConfig: {
          prebuiltVoiceConfig: { voiceName: char.voice as any },
        },
      };
    });

    const speechConfig: any = {};
    
    // The Gemini 3.1 TTS model currently requires exactly 2 voices for multi-speaker config
    if (paragraphSpeakers.size === 2) {
      speechConfig.multiSpeakerVoiceConfig = {
        speakerVoiceConfigs: speakerVoiceConfigs,
      };
    } else {
      // Fallback to standard voiceConfig for 1 or 3+ speakers
      // Use the narrator or the first speaker as the base voice
      const primarySpeaker = characters.find(c => c.name.toLowerCase() === 'narrator')?.name || paragraph.turns[0].speaker;
      const char = characters.find(c => c.name === primarySpeaker) || characters[0];
      speechConfig.voiceConfig = {
        prebuiltVoiceConfig: { voiceName: char.voice as any },
      };
    }

    console.log(`[gemini] Calling generateContent (TTS) for para ${paragraph.id}...`);
    const response = await ai.models.generateContent({
      model: "gemini-3.1-flash-tts-preview",
      contents: [{ parts: [{ text: prompt }] }],
      config: {
        responseModalities: [Modality.AUDIO],
        speechConfig: speechConfig,
      },
    });

    const candidate = response.candidates?.[0];
    const base64Audio = candidate?.content?.parts?.[0]?.inlineData?.data;

    if (!base64Audio) {
      console.error(`[gemini] TTS failed for para ${paragraph.id}`, response);
      const finishReason = candidate?.finishReason || "UNKNOWN";
      const statusText = (candidate as any)?.status?.message || "No audio data returned";
      throw new Error(`TTS generation failed for segment ${paragraph.id}. Reason: ${finishReason}. Details: ${statusText}`);
    }
    
    return base64Audio;
  });
}
