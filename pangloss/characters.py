import re
from typing import List, Optional, Union, Dict
from .models import Character, StoryMetadata, ProcessedParagraph

TITLE_PATTERN = re.compile(
    r'^(professor|prof\.|mr\.|mr|mrs\.|mrs|miss|ms\.|ms|herr|frau|doktor|dr\.|dr)\s+',
    re.IGNORECASE
)

NARRATOR_NAMES = {
    "narrator", "erzähler", "erzaehler", "le narrateur", "narrador", "narratore"
}

def normalize_title(name: str) -> str:
    """Strips leading titles / honorifics (e.g., 'Professor McGonagall' -> 'McGonagall')."""
    return TITLE_PATTERN.sub('', name.strip()).strip()

def find_matching_character(name: str, characters: List[Character]) -> Optional[Character]:
    """
    Finds an existing character that matches the given name either by exact name,
    known aliases, title-normalized matching, or unique word-subset containment.
    """
    if not name or not characters:
        return None

    name_clean = name.strip()
    name_lower = name_clean.lower()

    # 1. Narrator special case
    if name_lower in NARRATOR_NAMES:
        for c in characters:
            if c.get("name", "").lower() in NARRATOR_NAMES:
                return c

    # 2. Exact match on name or registered aliases
    for c in characters:
        if c.get("name", "").lower() == name_lower:
            return c
        for a in c.get("aliases", []) or []:
            if a.lower() == name_lower:
                return c

    # 3. Match normalized title (e.g. 'Professor McGonagall' -> 'Minerva McGonagall')
    norm_name = normalize_title(name_clean).lower()
    for c in characters:
        norm_c = normalize_title(c.get("name", "")).lower()
        if norm_c and norm_c == norm_name:
            return c
        for a in c.get("aliases", []) or []:
            norm_a = normalize_title(a).lower()
            if norm_a and norm_a == norm_name:
                return c

    # 4. Word subset containment:
    # e.g., 'Harry' or 'Harry Potter' in 'Harry James Potter-Evans-Verres'
    name_words = set(re.findall(r'\w+', norm_name))
    if not name_words:
        return None

    candidates = []
    for c in characters:
        norm_c = normalize_title(c.get("name", "")).lower()
        c_words = set(re.findall(r'\w+', norm_c))
        if not c_words:
            continue
        # Name words are strict subset of character words, or character words subset of name words
        if name_words.issubset(c_words) or c_words.issubset(name_words):
            candidates.append(c)

    # Only return if uniquely identified (avoids conflating e.g. 'Fred Weasley' and 'George Weasley' on 'Weasley')
    if len(candidates) == 1:
        return candidates[0]

    return None

def add_alias_to_character(char: Character, alias: str):
    """Adds alias to character's alias list if not identical to canonical name or already present."""
    if not alias:
        return
    alias = alias.strip()
    if not alias or alias.lower() == char.get("name", "").lower():
        return
    if "aliases" not in char or char["aliases"] is None:
        char["aliases"] = []
    if not any(a.lower() == alias.lower() for a in char["aliases"]):
        char["aliases"].append(alias)

def canonicalize_chunk_characters(chunk_characters: List[dict],
                                 paragraphs: List[ProcessedParagraph],
                                 all_characters: List[Character]):
    """
    Normalizes newly received chunk characters and paragraph turns against existing characters.
    Modifies chunk_characters, paragraphs, and all_characters in-place.
    """
    # 1. Normalize characters
    for new_char in chunk_characters:
        match = find_matching_character(new_char.get("name", ""), all_characters)
        if match:
            # Register new_char's name and aliases as aliases of the canonical match
            add_alias_to_character(match, new_char.get("name", ""))
            for a in new_char.get("aliases", []) or []:
                add_alias_to_character(match, a)
        else:
            if "aliases" not in new_char or new_char["aliases"] is None:
                new_char["aliases"] = []
            all_characters.append(new_char)

    # 2. Normalize paragraph turn speakers
    for p in paragraphs:
        for t in p.get("turns", []):
            spk = t.get("speaker", "").strip()
            if not spk:
                continue
            match = find_matching_character(spk, all_characters)
            if match:
                add_alias_to_character(match, spk)
                t["speaker"] = match["name"]

def apply_character_merges(metadata: StoryMetadata, merges: List[dict]) -> StoryMetadata:
    """
    Applies explicit merge instructions (e.g. from LLM or manual configuration).
    Each merge item: {"canonical": str, "aliases": [str, ...]}
    Updates metadata['characters'] and remaps turn speakers in metadata['paragraphs'].
    """
    if not merges:
        return metadata

    alias_to_canonical: Dict[str, str] = {}
    characters = metadata.get("characters", [])

    for m in merges:
        canonical_name = m.get("canonical", "").strip()
        aliases = m.get("aliases", [])
        if not canonical_name or not aliases:
            continue

        canonical_char = next((c for c in characters if c.get("name", "").lower() == canonical_name.lower()), None)
        if not canonical_char:
            # Fall back to matching
            canonical_char = find_matching_character(canonical_name, characters)
        if not canonical_char:
            continue

        for alias in aliases:
            alias_clean = alias.strip()
            if not alias_clean or alias_clean.lower() == canonical_char["name"].lower():
                continue
            alias_to_canonical[alias_clean.lower()] = canonical_char["name"]
            add_alias_to_character(canonical_char, alias_clean)

            # Check if there is an existing character with this alias name
            existing_alias_c = next((c for c in characters if c.get("name", "").lower() == alias_clean.lower()), None)
            if existing_alias_c:
                for sub_a in existing_alias_c.get("aliases", []) or []:
                    add_alias_to_character(canonical_char, sub_a)
                    alias_to_canonical[sub_a.lower()] = canonical_char["name"]

    # Filter out merged characters
    metadata["characters"] = [
        c for c in characters
        if c.get("name", "").lower() not in alias_to_canonical
        or c.get("name", "").lower() == alias_to_canonical.get(c.get("name", "").lower(), "").lower()
    ]

    # Remap turn speakers and chunk speakers
    for p in metadata.get("paragraphs", []):
        for t in p.get("turns", []):
            spk = t.get("speaker", "").strip()
            if spk.lower() in alias_to_canonical:
                t["speaker"] = alias_to_canonical[spk.lower()]
        for c in p.get("chunks", []) or []:
            if "speakers" in c:
                c["speakers"] = [
                    alias_to_canonical.get(s.lower(), s) for s in c["speakers"]
                ]

    return metadata
