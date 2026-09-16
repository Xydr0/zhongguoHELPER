"""Chargement en memoire (une seule fois) des fichiers generes par data/prepare_data.py.
Partage entre plusieurs cogs (dictionary, quiz, ...).
"""
import json
import random
import re
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

IDS_OPERATORS = set("⿰⿱⿲⿳⿴⿵⿶⿷⿸⿹⿺⿻")

POS_LABELS = {
    "n": "nom",
    "v": "verbe",
    "vn": "verbe/nom",
    "adj": "adjectif",
    "adv": "adverbe",
    "prep": "préposition",
    "conj": "conjonction",
    "part": "particule",
    "pron": "pronom",
    "num": "numéral",
    "m": "spécificatif (mesure)",
    "t": "temps",
    "b": "attribut non-prédicatif",
    "c": "conjonction",
    "int": "interjection",
    "on": "onomatopée",
}


def pos_label(tag: str) -> str:
    return POS_LABELS.get(tag, tag)


@lru_cache(maxsize=1)
def get_dictionary() -> dict:
    with open(DATA_DIR / "dictionary.json", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def get_vocab_hsk() -> dict:
    with open(DATA_DIR / "vocab_hsk.json", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def get_radicals() -> dict:
    with open(DATA_DIR / "radicals.json", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def get_sentences() -> dict:
    with open(DATA_DIR / "sentences.json", encoding="utf-8") as f:
        return json.load(f)


def sentences_for_level(level: int) -> list:
    return get_sentences().get(str(level), [])


def vocab_for_level(level: int) -> list:
    return get_vocab_hsk().get(str(level), [])


def all_vocab() -> list:
    combined = []
    for words in get_vocab_hsk().values():
        combined.extend(words)
    return combined


def best_translation(entry: dict, max_items: int = 3) -> tuple[list[str], bool]:
    """Retourne (liste de traductions, is_french). Prefere le francais, sinon anglais."""
    if entry.get("fr"):
        return entry["fr"][:max_items], True
    if entry.get("en"):
        return entry["en"][:max_items], False
    return [], True


def extract_components(decomposition: str | None) -> list[str]:
    if not decomposition:
        return []
    return [c for c in decomposition if c not in IDS_OPERATORS and c != "？"]


def word_of_the_day(date_str: str, level: int | None = None) -> dict:
    """Mot deterministe pour une date donnee (meme mot pour tout le monde, change chaque jour)."""
    pool = vocab_for_level(level) if level else all_vocab()
    seed = f"{date_str}:{level or 'all'}"
    rng = random.Random(seed)
    return rng.choice(pool)
