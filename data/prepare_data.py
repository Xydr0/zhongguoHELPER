"""
Script de préparation des données (à exécuter une seule fois, ou après mise à jour des sources brutes).

Lit les fichiers dans data/raw/ et génère dans data/ :
  - dictionary.json : dictionnaire fusionné CFDICT (français, prioritaire) + CC-CEDICT (anglais, repli)
  - vocab_hsk.json  : vocabulaire HSK 1-6, avec traduction résolue via dictionary.json
  - radicals.json   : décomposition des caractères en radicaux (makemeahanzi)

Usage:
    python prepare_data.py
"""
import json
import re
from pathlib import Path

RAW = Path(__file__).parent / "raw"
OUT = Path(__file__).parent

CEDICT_LINE = re.compile(r"^(\S+) (\S+) \[([^\]]*)\] /(.*)/$")


def parse_cedict_style(path: str) -> dict:
    """Parse un fichier au format CEDICT (traditionnel simplifié [pinyin] /def1/def2/.../).

    Retourne un dict {simplifie: {"traditional": str, "pinyin": str, "definitions": [str, ...]}}
    Ne garde que la première entrée rencontrée par mot simplifié (les fichiers CEDICT
    listent les homographes/variantes de prononciation comme des lignes séparées).
    """
    result = {}
    with open(RAW / path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = CEDICT_LINE.match(line)
            if not m:
                continue
            traditional, simplified, pinyin, defs_raw = m.groups()
            defs = [d.strip() for d in defs_raw.split("/") if d.strip()]
            if not defs:
                continue
            if simplified not in result:
                result[simplified] = {
                    "traditional": traditional,
                    "pinyin": pinyin,
                    "definitions": defs,
                }
    return result


def build_dictionary():
    print("Parsing CC-CEDICT (anglais)...")
    cedict = parse_cedict_style("cedict.txt")
    print(f"  {len(cedict)} mots simplifies uniques")

    print("Parsing CFDICT (francais)...")
    cfdict = parse_cedict_style("cfdict.u8")
    print(f"  {len(cfdict)} mots simplifies uniques")

    merged = {}
    all_keys = set(cedict) | set(cfdict)
    for key in all_keys:
        fr_entry = cfdict.get(key)
        en_entry = cedict.get(key)
        base = fr_entry or en_entry
        entry = {
            "traditional": base["traditional"],
            "pinyin": base["pinyin"],
        }
        if fr_entry:
            entry["fr"] = fr_entry["definitions"]
        if en_entry:
            entry["en"] = en_entry["definitions"]
        merged[key] = entry

    with open(OUT / "dictionary.json", "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, separators=(",", ":"))
    print(f"-> dictionary.json ecrit ({len(merged)} entrees, {(OUT / 'dictionary.json').stat().st_size // 1024} Ko)")
    return merged


def build_vocab_hsk(dictionary: dict):
    print("Construction du vocabulaire HSK 1-6...")
    levels = {}
    for level in range(1, 7):
        with open(RAW / f"hsk_old_exclusive_{level}.json", encoding="utf-8") as f:
            raw_words = json.load(f)

        words = []
        for w in raw_words:
            simplified = w["simplified"]
            form = w["forms"][0] if w.get("forms") else {}
            pinyin = form.get("transcriptions", {}).get("pinyin", "")
            en_meanings = form.get("meanings", [])

            dict_entry = dictionary.get(simplified)
            fr = dict_entry["fr"] if dict_entry and "fr" in dict_entry else None
            en = dict_entry["en"] if dict_entry and "en" in dict_entry else (en_meanings or None)

            words.append({
                "simplified": simplified,
                "traditional": form.get("traditional", simplified),
                "pinyin": pinyin,
                "fr": fr,
                "en": en,
                "pos": w.get("pos", []),
                "radical": w.get("radical", ""),
            })

        levels[str(level)] = words
        print(f"  HSK {level}: {len(words)} mots")

    with open(OUT / "vocab_hsk.json", "w", encoding="utf-8") as f:
        json.dump(levels, f, ensure_ascii=False, separators=(",", ":"))
    print(f"-> vocab_hsk.json ecrit ({(OUT / 'vocab_hsk.json').stat().st_size // 1024} Ko)")


def build_radicals():
    print("Construction des decompositions de radicaux...")
    radicals = {}
    with open(RAW / "makemeahanzi_dictionary.txt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            char = entry["character"]
            decomposition = entry.get("decomposition", "")
            radicals[char] = {
                "decomposition": decomposition if decomposition != "？" else None,
                "radical": entry.get("radical", ""),
                "definition": entry.get("definition"),
                "etymology": entry.get("etymology"),
            }

    with open(OUT / "radicals.json", "w", encoding="utf-8") as f:
        json.dump(radicals, f, ensure_ascii=False, separators=(",", ":"))
    print(f"-> radicals.json ecrit ({len(radicals)} caracteres, {(OUT / 'radicals.json').stat().st_size // 1024} Ko)")


if __name__ == "__main__":
    dictionary = build_dictionary()
    build_vocab_hsk(dictionary)
    build_radicals()
    print("Termine.")
