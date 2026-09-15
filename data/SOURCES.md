# Sources des données

Toutes gratuites et libres de droits (usage non commercial ou commercial selon licence ci-dessous). Téléchargées le 2026-09-15 par `prepare_data.py` à partir de `data/raw/`.

| Fichier brut | Source | Licence | Attribution requise |
|---|---|---|---|
| `raw/cedict.txt.gz` | [CC-CEDICT](https://www.mdbg.net/chinese/dictionary?page=cedict) (MDBG export) | CC BY-SA 4.0 | Oui — CC-CEDICT |
| `raw/cfdict.u8` | [CFDICT](https://chine.in/mandarin/dictionnaire/CFDICT/) (Chine Informations) | CC BY-SA 3.0 | Oui — mentionner chine.in |
| `raw/hsk_old_exclusive_1..6.json` | [drkameleon/complete-hsk-vocabulary](https://github.com/drkameleon/complete-hsk-vocabulary) (HSK 2.0, wordlists/exclusive/old) | MIT | Non obligatoire mais bienvenue |
| `raw/makemeahanzi_dictionary.txt` | [skishore/makemeahanzi](https://github.com/skishore/makemeahanzi) `dictionary.txt` (dérivé d'Unihan + CJKlib) | LGPL v3+ | Oui — Unihan / CJKlib / Make Me a Hanzi |

## Fichiers générés (`prepare_data.py`)

- `dictionary.json` : fusion CFDICT (français, prioritaire) + CC-CEDICT (anglais, complément/repli si le mot n'existe pas en français), clé = caractères simplifiés.
- `vocab_hsk.json` : vocabulaire HSK 1 à 6 (mots *exclusifs* à chaque niveau, ancien barème HSK 2.0), traduction résolue via `dictionary.json`.
- `radicals.json` : décomposition en composants (IDS) + radical primaire + définition (anglais) + étymologie, pour ~9500 caractères.

## Mettre à jour les données

1. Retélécharger les fichiers listés ci-dessus dans `data/raw/` (les URLs directes sont dans `prepare_data.py`'s docstring ou l'historique de conversation).
2. Relancer `python prepare_data.py` depuis `data/`.
