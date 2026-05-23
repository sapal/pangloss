# Pangloss

Pangloss is a command-line interface (CLI) tool that transforms text files into immersive, bilingual audiobooks and self-contained HTML study aids. It uses the Google Generative AI SDK to chunk text, translate it, extract vocabulary, assign character voices, and generate multi-speaker TTS audio.

Built with a philosophy of "optimism through caching," Pangloss ensures that expensive API operations are saved and resumable, living up to its namesake's belief that we live in "the best of all possible worlds."

## Features

- **Aggressive Caching:** Interrupted jobs can be resumed without losing data or incurring duplicate API costs.
- **Multi-Speaker TTS:** High-quality audio with distinct voices for different characters and narrators.
- **Bilingual HTML:** Interactive study aids with synced audio, vocabulary tooltips, and parallel text.
- **MP3 Export:** A single, merged audiobook file for offline listening.
- **Minimal Dependencies:** Built primarily with Python's standard library and the `google-genai` SDK.

## Prerequisites

- **Python 3.10+**
- **FFmpeg:** Required for audio merging and MP3 encoding.
  - *Linux:* `sudo apt install ffmpeg`
  - *macOS:* `brew install ffmpeg`
- **Gemini API Key:** Obtain one from [Google AI Studio](https://aistudio.google.com/).

## Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/your-username/pangloss.git
   cd pangloss
   ```

2. **Install dependencies:**
   ```bash
   pip install google-genai
   ```

## Usage

### Basic Build
Generate an audiobook from a text file:
```bash
export GEMINI_API_KEY="your_api_key"
python3 pangloss.py build story.txt --target-lang German --level B1
```

### Options
- `--target-lang`: The language you want to learn (e.g., "Spanish", "French").
- `--source-lang`: Your native language (default: "English").
- `--level`: Proficiency level (e.g., "A1", "B2").
- `--output-dir`: Path to save results (default: `./pangloss_output`).
- `--render-only <job_id>`: Skip API calls and regenerate output from an existing cache.
- `--serve`: Spin up a local server to preview the generated HTML immediately.

### Example with Server
```bash
python3 pangloss.py build my_story.txt --target-lang "French" --serve
```

## How It Works

1. **Hashing:** The input file and configuration are hashed to create a unique Job ID.
2. **Caching:** All metadata and audio segments are saved in `.pangloss/<job_id>/`.
3. **Resumability:** If you stop the process (Ctrl+C), simply run the same command again to resume exactly where you left off.
4. **Export:** Once all segments are generated, Pangloss merges the audio and injects everything into a standalone HTML template.

## Testing

Ensure your python path includes the current folder:
```bash
export PYTHONPATH=$PYTHONPATH:.
```

Run the core unit tests (including API token tracking validation):
```bash
python3 tests/test_core.py
```

Run the HTML validity tests to verify the generated template:
```bash
python3 tests/test_html_validity.py
```

Run the resumability and caching tests (requires setting a dummy API key):
```bash
GEMINI_API_KEY="dummy" python3 tests/test_resumability.py
```

---
*"Private misfortunes make the general good. All is for the best in the best of all possible worlds."*
