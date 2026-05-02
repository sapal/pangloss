import base64
import json
import os
from pathlib import Path
from .audio import wav_to_mp3_bytes, merge_wavs_to_mp3
from .models import StoryMetadata

def generate_html(metadata: StoryMetadata, audio_chunks: dict, source_lang: str, target_lang: str, level: str) -> str:
    """Generates a standalone HTML file with embedded audio and metadata."""
    
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

    # UI Translations (ported from React)
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
            "paraOriginal": "Original Source",
            "paraLearning": "Learning View",
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
            "paraOriginal": "Źródło Oryginalne",
            "paraLearning": "Widok Nauki",
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

    html_template = f"""<!DOCTYPE html>
<html lang="{ 'pl' if source_lang == 'Polish' else 'en' }">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{metadata['title']} | Pangloss</title>
    <link href="https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,400;0,700;1,400;1,700&display=swap" rel="stylesheet">
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        :root {{
            --paper: #F9F7F2;
            --ink: #1A1A1A;
            --accent: #5A5A40;
            --muted: #8C8A81;
            --highlight: rgba(90, 90, 64, 0.1);
        }}
        body {{ background-color: var(--paper); color: var(--ink); font-family: 'Lora', Georgia, serif; -webkit-font-smoothing: antialiased; }}
        .font-sans {{ font-family: 'Helvetica Neue', Arial, sans-serif; }}
        .text-accent {{ color: var(--accent); }}
        .text-muted {{ color: var(--muted); }}
        .bg-paper {{ background-color: var(--paper); }}
        .bg-ink {{ background-color: var(--ink); }}
        .text-paper {{ color: var(--paper); }}
        .bg-highlight {{ background-color: var(--highlight); }}
        .selection\:bg-highlight *::selection {{ background-color: var(--highlight); }}
        .border-accent {{ border-color: var(--accent); }}
        .ring-accent\/20 {{ --tw-ring-color: rgba(90, 90, 64, 0.2); }}
        
        .drawer {{ transform: translateX(100%); transition: transform 0.4s cubic-bezier(0.16, 1, 0.3, 1); }}
        .drawer.active {{ transform: translateX(0); }}
        .word {{ position: relative; border-bottom: 2px solid #5A5A40; cursor: help; display: inline; text-underline-offset: 4px; }}
        .word:hover .tooltip {{ display: block; }}
        .tooltip {{ display: none; position: absolute; bottom: 100%; left: 50%; transform: translate(-50%, -20px); background: #1A1A1A; color: #F9F7F2; padding: 25px; width: 300px; z-index: 1000; font-size: 0.9rem; font-family: sans-serif; border-radius: 0; box-shadow: 0 15px 45px rgba(0,0,0,0.6); line-height: 1.5; font-style: normal; }}
        .text-content {{ white-space: pre-wrap; }}
    </style>
</head>
<body class="bg-paper text-ink font-serif selection:bg-highlight min-h-screen">
    <button class="fixed top-10 right-10 border-none bg-transparent font-sans text-[11px] font-bold uppercase tracking-[2px] color-muted cursor-pointer z-50 flex items-center gap-2 hover:text-ink transition-colors" id="drawerToggle">
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1-2.5-2.5Z"/><path d="M8 7h8"/><path d="M8 11h8"/><path d="M8 15h5"/></svg>
        {t['dictionary']}
    </button>

    <div class="fixed inset-0 bg-black/20 backdrop-blur-sm z-[1999] opacity-0 pointer-events-none transition-opacity duration-300" id="overlay"></div>
    <div class="drawer fixed right-0 top-0 h-full w-full max-w-[450px] bg-[#F4F1EA] z-[2000] p-[60px_40px] border-l border-ink/10 overflow-y-auto shadow-[-20px_0_60px_rgba(0,0,0,0.2)]" id="drawer">
        <div class="flex justify-between items-start mb-16">
            <h2 class="text-[44px] italic font-bold font-serif">{t['lexicon']}</h2>
            <button id="closeDrawer" class="bg-none border-none cursor-pointer opacity-50 p-2 hover:bg-ink/5 rounded-full transition-colors">
                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
            </button>
        </div>

        <div class="mb-16 space-y-8">
            <h4 class="text-[10px] uppercase font-bold tracking-[3px] text-muted border-b border-ink/10 pb-2">{t['vocabulary']}</h4>
            <div id="vocabList" class="space-y-6"></div>
        </div>

        <div class="space-y-8">
            <h4 class="text-[10px] uppercase font-bold tracking-[3px] text-muted border-b border-ink/10 pb-2">{t['cast']}</h4>
            <div id="castList" class="space-y-8"></div>
        </div>
    </div>

    <div class="max-w-[1400px] mx-auto p-[60px_40px_180px]">
        <header class="border-b-2 border-ink/5 pb-[30px] mb-[60px]">
            <h1 class="text-[3.5rem] m-0 italic font-[900] tracking-[-2px] leading-tight mb-4">{metadata['title']}</h1>
            <p class="font-sans text-[10px] uppercase tracking-[3px] font-extrabold opacity-60 mt-2 text-accent">Pangloss • Immersive Audiobooks • {target_lang} {level}</p>
        </header>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-12 border-b border-ink/5 mb-12 pb-6">
            <header class="space-y-1">
                <span class="text-[10px] uppercase tracking-[2px] font-bold text-muted">{t['paraOriginal']}</span>
                <h3 class="text-[1.8rem] italic m-0 font-bold font-serif">{t['paraOriginal']}</h3>
            </header>
            <header class="space-y-1 hidden md:block">
                <span class="text-[10px] uppercase tracking-[2px] font-bold text-muted">{t['paraLearning']} • {target_lang} {level}</span>
                <h3 class="text-[1.8rem] italic m-0 font-bold font-serif">{t['paraLearning']}</h3>
            </header>
        </div>

        <div id="story" class="space-y-8"></div>
    </div>

    <div class="fixed bottom-[50px] left-1/2 -translate-x-1/2 bg-ink text-paper p-[25px_50px] flex items-center justify-center shadow-[0_40px_80px_rgba(0,0,0,0.5)] z-[100] w-[600px] max-w-[90vw]">
        <div class="flex-1 flex items-center">
            <div class="flex flex-col">
                <span class="text-[8px] uppercase tracking-[3px] opacity-50 font-sans font-bold">{t['statusLabel']}</span>
                <span id="status" class="text-[11px] font-bold uppercase tracking-[2.5px] font-sans border-l-2 border-accent pl-[15px] mt-[6px] min-w-[140px] text-paper">{t['statusReady']}</span>
            </div>
        </div>
        <div class="flex-none flex justify-center mx-10">
            <button class="bg-paper text-ink w-[60px] h-[60px] rounded-full border-none font-bold cursor-pointer flex items-center justify-center transition-transform hover:scale-110" id="playToggle">{play_svg}</button>
        </div>
        <div class="flex-1 flex items-center justify-end">
            <div class="flex items-center gap-[30px]">
                <button class="bg-none border-none text-muted cursor-pointer font-sans text-[11px] font-bold uppercase tracking-[2px] transition-colors hover:text-paper" id="prevBtn" disabled>{t['back']}</button>
                <div class="w-px h-5 bg-white/10"></div>
                <button class="bg-none border-none text-muted cursor-pointer font-sans text-[11px] font-bold uppercase tracking-[2px] transition-colors hover:text-paper" id="nextBtn">{t['next']}</button>
            </div>
        </div>
    </div>

    <audio id="player"></audio>

    <script>
        const metadata = {json.dumps(metadata)};
        const audioData = {json.dumps(mp3_data_urls)};
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

        const PLAY_SVG = {json.dumps(play_svg)};
        const PAUSE_SVG = {json.dumps(pause_svg)};

        function render() {{
            storyEl.innerHTML = metadata.paragraphs.map(p => {{
                const speakersList = Array.from(new Set(p.turns.map(t => t.speaker)));
                const speakers = speakersList.length > 0 ? speakersList.join(' • ') : 'Narrator';
                
                const origParas = p.originalText.split('\\n\\n');
                const transParas = p.translatedText.split('\\n\\n');
                const maxParas = Math.max(origParas.length, transParas.length);

                const sortedWords = [...metadata.difficultWords].sort((a,b) => b.word.length - a.word.length);

                const alignedContent = Array.from({{ length: maxParas }}).map((_, i) => {{
                    let transPara = transParas[i] || "";
                    sortedWords.forEach(dw => {{
                        const anchors = dw.anchors || [dw.word];
                        anchors.forEach(anchor => {{
                            const escaped = anchor.replace(/[.*+?^${{}}()|[\\]\\\\]/g, '\\\\$&');
                            const regex = new RegExp("\\\\b" + escaped + "\\\\b", 'gi');
                            transPara = transPara.replace(regex, `<span class="word">$&<div class="tooltip"><strong>${{dw.word}}</strong>: ${{dw.explanation}}</div></span>`);
                        }});
                    }});

                    return `
                        <div class="grid grid-cols-1 md:grid-cols-2 gap-12 items-start mb-8 last:mb-0">
                            <div id="orig-${{p.id}}-${{i}}" class="text-xl leading-relaxed font-serif opacity-70 transition-all duration-300">${{origParas[i] || ""}}</div>
                            <div id="trans-${{p.id}}-${{i}}" class="text-2xl leading-relaxed font-serif transition-all duration-300">${{transPara}}</div>
                        </div>
                    `;
                }}).join('');

                return `
                    <div class="group/row border-b border-ink/5 pt-12 pb-12 transition-all first:pt-0" id="section-${{p.id}}">
                        <div class="flex items-center gap-4 mb-8">
                            <span class="text-[10px] uppercase tracking-[2px] font-bold text-muted border-b border-accent/30 pb-1">${{speakers}}</span>
                            <button onclick="playPara(${{p.id}})" class="w-8 h-8 rounded-full bg-accent/10 flex items-center justify-center hover:bg-accent hover:text-paper transition-all">
                                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
                            </button>
                        </div>
                        <div id="trans-${{p.id}}" onclick="playPara(${{p.id}})" class="cursor-pointer">
                            ${{alignedContent}}
                        </div>
                    </div>
                `;
            }}).join('');

            document.getElementById('vocabList').innerHTML = metadata.difficultWords.map(dw => `
                <div class="group border-b border-ink/5 pb-6 last:border-0 hover:translate-x-1 transition-transform">
                    <p class="text-2xl font-serif font-bold mb-2">${{dw.word}}</p>
                    <p class="text-sm text-ink/70 font-serif italic leading-relaxed">${{dw.explanation}}</p>
                </div>
            `).join('');

            document.getElementById('castList').innerHTML = metadata.characters.map(char => `
                <div class="flex gap-6">
                    <div class="w-12 h-12 bg-paper border border-ink/10 rounded-full flex items-center justify-center flex-shrink-0 shadow-sm">
                        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#5A5A40" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 5L6 9H2v6h4l5 4V5z"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>
                    </div>
                    <div>
                        <p class="text-xl font-serif font-bold mb-1">${{char.name}}</p>
                        <p class="text-xs text-ink/60 font-serif italic leading-relaxed mb-3">${{char.description}}</p>
                        <div class="flex flex-wrap gap-2">
                            <span class="text-[9px] uppercase tracking-[2px] font-bold px-3 py-1 bg-accent text-paper rounded-full">Voice • ${{char.voice}}</span>
                            <span class="text-[9px] uppercase tracking-[1px] font-bold px-3 py-1 bg-ink/5 text-ink/70 rounded-full italic hover:bg-ink/10 transition-colors cursor-default">${{char.voiceProfile}}</span>
                        </div>
                    </div>
                </div>
            `).join('');
        }}

        drawerToggle.onclick = () => {{
            drawer.classList.add('active');
            overlay.classList.add('opacity-100', 'pointer-events-auto');
        }};

        closeDrawer.onclick = overlay.onclick = () => {{
            drawer.classList.remove('active');
            overlay.classList.remove('opacity-100', 'pointer-events-auto');
        }};

        function playPara(id, restart = true) {{
            if (restart || player.src !== audioData[id]) {{
                player.src = audioData[id];
            }}
            currentId = id;
            player.play();
            isPlaying = true;
            updateUI();
        }}

        function updateUI() {{
            document.querySelectorAll('[id^="section-"]').forEach(el => {{
                el.classList.remove('bg-accent/5', 'ring-1', 'ring-accent/10', 'shadow-sm', 'p-8', '-mx-8', 'rounded-2xl');
            }});
            document.querySelectorAll('[id^="orig-"]').forEach(el => el.classList.add('opacity-40'));

            if (currentId !== null) {{
                const section = document.getElementById('section-' + currentId);
                if (section) {{
                    section.classList.add('bg-accent/5', 'ring-1', 'ring-accent/10', 'shadow-sm', 'p-8', '-mx-8', 'rounded-2xl');
                    section.querySelectorAll('[id^="orig-"]').forEach(el => el.classList.remove('opacity-40'));
                    section.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                }}
                statusEl.innerText = `{t['chapter']} ` + currentId;
            }}
            playBtn.innerHTML = isPlaying ? PAUSE_SVG : PLAY_SVG;
            
            const index = metadata.paragraphs.findIndex(p => p.id === currentId);
            prevBtn.disabled = index <= 0;
            nextBtn.disabled = index >= metadata.paragraphs.length - 1 && index !== -1;
        }}

        playBtn.onclick = () => {{
            if (isPlaying) {{
                player.pause();
                isPlaying = false;
            }} else {{
                if (currentId !== null && player.src === audioData[currentId]) {{
                    player.play();
                    isPlaying = true;
                }} else {{
                    const nextId = currentId !== null ? currentId : metadata.paragraphs[0].id;
                    playPara(nextId);
                }}
            }}
            updateUI();
        }};

        prevBtn.onclick = () => {{
            const index = metadata.paragraphs.findIndex(p => p.id === currentId);
            if (index > 0) playPara(metadata.paragraphs[index - 1].id);
        }};

        nextBtn.onclick = () => {{
            const index = metadata.paragraphs.findIndex(p => p.id === currentId);
            if (index < metadata.paragraphs.length - 1) playPara(metadata.paragraphs[index + 1].id);
        }};

        player.onended = () => {{
            const index = metadata.paragraphs.findIndex(p => p.id === currentId);
            if (index < metadata.paragraphs.length - 1) {{
                playPara(metadata.paragraphs[index + 1].id);
            }} else {{
                isPlaying = false;
                currentId = null;
                updateUI();
                statusEl.innerText = '{t['finished']}';
            }}
        }};

        window.addEventListener('load', () => {{
          render();
          updateUI();
        }});
        // Initial render for immediate visibility
        render();
    </script>
</body>
</html>"""
    return html_template

def export_results(metadata: StoryMetadata, audio_dir: Path, output_dir: str, source_lang: str, target_lang: str, level: str):
    """Orchestrates the export of HTML and MP3 files."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    
    title_slug = metadata['title'].lower().replace(" ", "-").replace("/", "-")
    
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
