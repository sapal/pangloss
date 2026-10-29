import pytest
from pangloss.characters import (
    normalize_title,
    find_matching_character,
    add_alias_to_character,
    canonicalize_chunk_characters,
    apply_character_merges
)
from pangloss.api import GeminiAPI

def test_normalize_title():
    assert normalize_title("Professor McGonagall") == "McGonagall"
    assert normalize_title("Prof. Flitwick") == "Flitwick"
    assert normalize_title("Mr. Potter") == "Potter"
    assert normalize_title("Mrs. Figg") == "Figg"
    assert normalize_title("Dr. Verres") == "Verres"
    assert normalize_title("Harry") == "Harry"

def test_find_matching_character():
    chars = [
        {"name": "Harry James Potter-Evans-Verres", "voice": "Kore", "aliases": []},
        {"name": "Minerva McGonagall", "voice": "Sulafat", "aliases": ["Prof. McGonagall"]},
        {"name": "Fred Weasley", "voice": "Orus", "aliases": []},
        {"name": "George Weasley", "voice": "Orus", "aliases": []},
        {"name": "Narrator", "voice": "Fenrir", "aliases": []},
    ]

    # Exact match
    assert find_matching_character("Harry James Potter-Evans-Verres", chars)["name"] == "Harry James Potter-Evans-Verres"
    # Case-insensitive
    assert find_matching_character("minerva mcgonagall", chars)["name"] == "Minerva McGonagall"
    # Existing alias
    assert find_matching_character("Prof. McGonagall", chars)["name"] == "Minerva McGonagall"
    # Title normalized
    assert find_matching_character("Professor Minerva McGonagall", chars)["name"] == "Minerva McGonagall"
    assert find_matching_character("Professor McGonagall", chars)["name"] == "Minerva McGonagall"
    # Sub-word containment unique match
    assert find_matching_character("Harry Potter", chars)["name"] == "Harry James Potter-Evans-Verres"
    assert find_matching_character("Harry", chars)["name"] == "Harry James Potter-Evans-Verres"
    # Narrator special case
    assert find_matching_character("Erzähler", chars)["name"] == "Narrator"
    assert find_matching_character("narrator", chars)["name"] == "Narrator"
    # Ambiguous sub-word match returns None
    assert find_matching_character("Weasley", chars) is None
    # Unambiguous sub-word match
    assert find_matching_character("Fred", chars)["name"] == "Fred Weasley"

def test_add_alias_to_character():
    char = {"name": "Harry", "aliases": []}
    add_alias_to_character(char, "Harry Potter")
    assert char["aliases"] == ["Harry Potter"]
    # Does not re-add duplicate (case-insensitive)
    add_alias_to_character(char, "harry potter")
    assert char["aliases"] == ["Harry Potter"]
    # Does not add same as canonical name
    add_alias_to_character(char, "Harry")
    assert char["aliases"] == ["Harry Potter"]

def test_canonicalize_chunk_characters():
    existing = [
        {"name": "Harry James Potter-Evans-Verres", "voice": "Kore", "aliases": []},
        {"name": "Narrator", "voice": "Fenrir", "aliases": []}
    ]

    chunk_chars = [
        {"name": "Harry", "voice": "Orus", "voiceProfile": "..."}
    ]
    paragraphs = [
        {
            "id": 1,
            "originalText": "...",
            "translatedText": "...",
            "turns": [
                {"speaker": "Harry", "text": "Hello."},
                {"speaker": "Erzähler", "text": "He said."}
            ]
        }
    ]

    canonicalize_chunk_characters(chunk_chars, paragraphs, existing)

    # Should NOT have added a new character 'Harry' to existing
    assert len(existing) == 2
    assert "Harry" in existing[0]["aliases"]
    assert "Erzähler" in existing[1]["aliases"]
    # Turns should be remapped to canonical names
    assert paragraphs[0]["turns"][0]["speaker"] == "Harry James Potter-Evans-Verres"
    assert paragraphs[0]["turns"][1]["speaker"] == "Narrator"

def test_apply_character_merges():
    meta = {
        "characters": [
            {"name": "Harry James Potter-Evans-Verres", "voice": "Kore", "aliases": []},
            {"name": "Harry Potter", "voice": "Algenib", "aliases": []},
            {"name": "Harry", "voice": "Orus", "aliases": []},
            {"name": "Severus Snape", "voice": "Schedar", "aliases": []}
        ],
        "paragraphs": [
            {
                "id": 1,
                "turns": [
                    {"speaker": "Harry", "text": "Hello"},
                    {"speaker": "Harry Potter", "text": "World"},
                    {"speaker": "Severus Snape", "text": "Silence!"}
                ],
                "chunks": [
                    {"chunk_index": 0, "speakers": ["Harry", "Severus Snape"]}
                ]
            }
        ]
    }

    merges = [
        {
            "canonical": "Harry James Potter-Evans-Verres",
            "aliases": ["Harry", "Harry Potter"]
        }
    ]

    updated = apply_character_merges(meta, merges)

    # Merged characters removed from characters list
    char_names = [c["name"] for c in updated["characters"]]
    assert char_names == ["Harry James Potter-Evans-Verres", "Severus Snape"]
    canonical_h = updated["characters"][0]
    assert set(canonical_h["aliases"]) == {"Harry", "Harry Potter"}

    # Turns remapped
    assert updated["paragraphs"][0]["turns"][0]["speaker"] == "Harry James Potter-Evans-Verres"
    assert updated["paragraphs"][0]["turns"][1]["speaker"] == "Harry James Potter-Evans-Verres"
    assert updated["paragraphs"][0]["turns"][2]["speaker"] == "Severus Snape"

    # Chunk speakers remapped
    assert updated["paragraphs"][0]["chunks"][0]["speakers"] == ["Harry James Potter-Evans-Verres", "Severus Snape"]

def test_generate_tts_alias_support():
    api = GeminiAPI(api_key="mock", dry_run=True)
    chars = [
        {"name": "Harry James Potter-Evans-Verres", "voice": "Kore", "aliases": ["Harry", "Harry Potter"]},
        {"name": "Narrator", "voice": "Fenrir", "aliases": []}
    ]
    p = {
        "id": 1,
        "translatedText": "Hallo Welt.",
        "turns": [{"speaker": "Harry", "text": "Hallo Welt."}]
    }
    # Should resolve "Harry" via alias without raising or falling back to narrator
    res = api.generate_tts(p, chars)
    assert res is not None

def test_find_character_merges_dry_run():
    api = GeminiAPI(api_key="mock", dry_run=True)
    chars = [{"name": "A"}, {"name": "B"}]
    res = api.find_character_merges_with_llm(chars)
    assert res == []
