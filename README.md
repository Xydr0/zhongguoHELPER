# 中国HELPER — Bot Discord de révision HSK

Bot Discord (discord.py, slash commands) pour aider les étudiants de LLCER Chinois à réviser
le vocabulaire HSK 1 à 6 au quotidien. 100% gratuit : aucune API payante, aucune dépendance
tierce payante, base de données SQLite locale.

## Fonctionnalités

### 📖 Dictionnaire
| Commande | Description |
|---|---|
| `/define <mot>` | Cherche un mot (français en priorité, anglais en repli) |
| `/vocab <niveau>` | Mot aléatoire d'un niveau HSK (1-6) |
| `/wordoftheday [niveau]` | Le mot du jour (identique pour tout le monde) |
| `/wordofdayconfig <salon> [niveau]` | *(Admin)* Poste automatiquement le mot du jour chaque matin |
| `/radical <caractère(s)>` | Décomposition en radicaux/composants |

### 🎯 Quiz
| Commande | Description |
|---|---|
| `/quiz <niveau>` | QCM à 4 choix, chinois ↔ français |
| `/quizspeed <niveau>` | 5 questions chronométrées (10s chacune) |
| `/fillblank <niveau>` | Phrase à trous, 4 choix |
| `/frtcn <niveau>` | Traduis en chinois — le bot vérifie ta réponse dans le salon |
| `/cntfr <niveau>` | Traduis en français — le bot vérifie ta réponse dans le salon |

### 📈 Progression
| Commande | Description |
|---|---|
| `/score` | Ton XP, ton streak, tes mots vus |
| `/leaderboard` | Top 10 du serveur |
| `/streak` | Jours consécutifs d'activité |
| `/review` | Révision espacée : priorise tes mots les plus ratés |
| `/badge` | Badges débloqués (50 / 100 / 500 mots vus) |

### ⚙️ Admin
| Commande | Description |
|---|---|
| `/setlevel <niveau>` | Attribue le rôle Discord `HSK <niveau>` (créé automatiquement si absent) |
| `/resource <mot-clé>` | Lien vers une ressource pédagogique (`resources.json`, éditable) |
| `/givexp <membre> <montant>` | *(Admin)* Ajoute/retire de l'XP |
| `/givebadge <membre> <palier>` | *(Admin)* Attribue un badge manuellement |

Les commandes marquées *(Admin)* nécessitent la permission Discord **Gérer le serveur**.

## Installation locale

### 1. Prérequis
- Python 3.11 ou supérieur
- Une application Discord avec un bot (créée sur le [Developer Portal](https://discord.com/developers/applications))

### 2. Créer et inviter le bot

1. [discord.com/developers/applications](https://discord.com/developers/applications) → **New Application**
2. Onglet **Bot** → **Reset Token** pour récupérer le token, et active **Message Content Intent**
   (nécessaire pour que `/frtcn` et `/cntfr` lisent tes réponses dans le salon — activé par
   défaut tant que le bot est sur moins de 100 serveurs)
3. Onglet **OAuth2 → URL Generator** :
   - Scopes : `bot`, `applications.commands`
   - Permissions bot : `Send Messages`, `Embed Links`, `Read Message History`, `Manage Roles`
     (nécessaire pour `/setlevel`)
4. Ouvre l'URL générée pour inviter le bot sur ton serveur de test.
5. **Important pour `/setlevel`** : dans les paramètres du serveur → Rôles, place le rôle du
   bot **au-dessus** des rôles `HSK 1`...`HSK 6` (le bot ne peut pas gérer un rôle placé
   au-dessus du sien).

### 3. Configurer le projet

```bash
cd chinese-bot
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

pip install -r requirements.txt
copy .env.example .env          # Windows — sinon: cp .env.example .env
```

Édite `.env` :
```
DISCORD_TOKEN=ton-token-ici
GUILD_ID=id-de-ton-serveur-de-test   # optionnel mais recommandé en dev (sync instantanée)
```

Les données (`data/*.json`) sont déjà générées et incluses dans le dépôt. Pour les
régénérer après une mise à jour des sources (voir `data/SOURCES.md`) :
```bash
cd data && python prepare_data.py
```

### 4. Lancer le bot

```bash
python bot.py
```

## Déploiement sur Render (gratuit)

Render ne propose pas de "Background Worker" gratuit — seulement des **Web Services**
gratuits, qui doivent écouter sur un port HTTP. Le bot inclut donc un petit serveur HTTP
(`start_health_server` dans `bot.py`) qui répond "OK" sur `/`, juste pour satisfaire cette
contrainte : il n'affecte en rien le fonctionnement Discord.

### Étapes

1. Pousse ce dépôt sur GitHub (déjà fait si tu es arrivé jusqu'ici 🙂).
2. Sur [render.com](https://render.com) → **New** → **Web Service** → connecte ton dépôt GitHub.
3. Configuration :
   - **Runtime** : Python 3
   - **Build Command** : `pip install -r requirements.txt`
   - **Start Command** : `python bot.py`
   - **Instance Type** : Free
4. Onglet **Environment** → ajoute les variables :
   - `DISCORD_TOKEN` = ton token
   - `GUILD_ID` = id de ton serveur (optionnel)
   - Ne définis pas `PORT` toi-même, Render le fournit automatiquement.
5. Déploie. Dans les logs, tu dois voir `Connecte en tant que ...` et `commande(s) synchronisee(s)`.

### ⚠️ Limites du tier gratuit à connaître

- **Mise en veille** : un Web Service gratuit s'endort après 15 minutes sans trafic HTTP, ce
  qui déconnecterait le bot de Discord. Solution gratuite : configure un moniteur externe
  (ex. [UptimeRobot](https://uptimerobot.com), gratuit) qui ping l'URL Render du service
  toutes les ~10 minutes, pour qu'il ne s'endorme jamais.
- **Stockage éphémère** : le disque d'un service gratuit est réinitialisé à chaque redéploiement
  ou redémarrage — la base SQLite (`db/bot.sqlite3`, donc les scores/streaks/badges/config du
  mot du jour) **sera perdue** à chaque redéploiement. Render ne propose de disque persistant
  que sur les plans payants. Si la persistance des scores est importante pour toi :
  - héberge plutôt le bot en local (sur un PC/Raspberry Pi allumé en continu), où
    `db/bot.sqlite3` persiste normalement sans limite, **ou**
  - accepte cette limite sur Render tant que tu ne redéploies pas souvent (un simple
    redémarrage dû à un crash ne perd rien ; seul un nouveau déploiement réinitialise le disque).

## Structure du projet

```
chinese-bot/
├── bot.py                 Point d'entrée, chargement des cogs, serveur de sante Render
├── colors.py               Palette de couleurs des embeds (une par categorie de cog)
├── data_loader.py          Chargement en memoire des donnees generees (data/*.json)
├── resources.json           Liens pedagogiques pour /resource (editable a la main)
├── cogs/
│   ├── dictionary.py       /define /vocab /wordoftheday /wordofdayconfig /radical
│   ├── quiz.py             /quiz /quizspeed /fillblank /frtcn /cntfr
│   ├── progression.py      /score /leaderboard /streak /review /badge
│   └── admin.py            /setlevel /resource /givexp /givebadge
├── data/
│   ├── raw/                Sources brutes telechargees (non versionnees, voir SOURCES.md)
│   ├── prepare_data.py     Script de generation des fichiers ci-dessous
│   ├── dictionary.json     CFDICT (fr) + CC-CEDICT (en), fusionnes
│   ├── vocab_hsk.json      Vocabulaire HSK 1-6 avec traduction resolue
│   ├── radicals.json       Decomposition en radicaux (Make Me a Hanzi)
│   ├── sentences.json      Banc de phrases pour /fillblank /frtcn /cntfr
│   └── SOURCES.md          Provenance et licences des donnees
├── db/
│   └── database.py         SQLite : utilisateurs, scores, streaks, historique, badges
├── .env                    Token et config (jamais commite)
└── requirements.txt
```

## Licences des données

Voir [`data/SOURCES.md`](data/SOURCES.md) pour le détail des licences (CC-CEDICT, CFDICT,
complete-hsk-vocabulary, Make Me a Hanzi) et leurs conditions d'attribution.
