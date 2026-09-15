import random
from datetime import date, datetime, time as dtime
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

import colors
from data_loader import (
    best_translation,
    extract_components,
    get_dictionary,
    get_radicals,
    pos_label,
    vocab_for_level,
    word_of_the_day,
)
from db.database import all_wordoftheday_configs, init_db, set_wordoftheday_config

# Poste le mot du jour a 07h00 UTC (~ 8h/9h a Paris selon l'heure d'ete).
WORD_OF_DAY_UTC_TIME = dtime(hour=7, minute=0)


def _translation_field(entry: dict, max_items: int = 5) -> tuple[str, str]:
    translations, is_fr = best_translation(entry, max_items=max_items)
    label = "📖 Traduction" if is_fr else "📖 Traduction (anglais — pas de FR disponible)"
    value = "\n".join(f"• {t}" for t in translations) or "*(aucune traduction disponible)*"
    return label, value


def build_word_embed(word: dict, niveau, *, title: str, emoji: str) -> discord.Embed:
    embed = discord.Embed(title=f"{emoji} {title}", color=colors.DICTIONARY)

    if word.get("traditional") and word["traditional"] != word["simplified"]:
        embed.add_field(name="繁 Traditionnel", value=f"**{word['traditional']}**", inline=True)
    embed.add_field(name="🔤 Pinyin", value=f"**{word.get('pinyin') or '?'}**", inline=True)
    if word.get("radical"):
        embed.add_field(name="⛩️ Radical", value=word["radical"], inline=True)

    label, value = _translation_field(word)
    embed.add_field(name=label, value=value, inline=False)

    if word.get("pos"):
        nature = ", ".join(pos_label(p) for p in word["pos"][:4])
        embed.add_field(name="🏷️ Nature grammaticale", value=nature, inline=False)

    niveau_txt = f"HSK {niveau}" if niveau != "melange" else "HSK 1-6 (mélange)"
    embed.set_footer(text=f"{niveau_txt} · complete-hsk-vocabulary")
    return embed


class Dictionary(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        init_db()

    async def cog_load(self):
        self.post_word_of_the_day.start()

    async def cog_unload(self):
        self.post_word_of_the_day.cancel()

    @app_commands.command(name="define", description="Cherche un mot dans le dictionnaire chinois-français.")
    @app_commands.describe(mot="Le mot en caractères chinois (simplifié)")
    async def define(self, interaction: discord.Interaction, mot: str):
        entry = get_dictionary().get(mot)
        if not entry:
            embed = discord.Embed(
                title="🈳 Aucun résultat",
                description=f"Rien trouvé pour **{mot}**.\nVérifie que le mot est écrit en caractères **simplifiés**.",
                color=colors.DICTIONARY,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(title=f"📖 {mot}", color=colors.DICTIONARY)
        if entry.get("traditional") and entry["traditional"] != mot:
            embed.add_field(name="繁 Traditionnel", value=f"**{entry['traditional']}**", inline=True)
        embed.add_field(name="🔤 Pinyin", value=f"**{entry.get('pinyin') or '?'}**", inline=True)

        label, value = _translation_field(entry, max_items=6)
        embed.add_field(name=label, value=value, inline=False)

        embed.set_footer(text="Source : CFDICT (fr) / CC-CEDICT (en)")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="vocab", description="Mot aléatoire d'un niveau HSK.")
    @app_commands.describe(niveau="Niveau HSK de 1 à 6")
    async def vocab(self, interaction: discord.Interaction, niveau: app_commands.Range[int, 1, 6]):
        words = vocab_for_level(niveau)
        if not words:
            await interaction.response.send_message("Aucun mot disponible pour ce niveau.", ephemeral=True)
            return
        word = random.choice(words)
        embed = build_word_embed(word, niveau, title=word["simplified"], emoji="🀄")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="wordoftheday", description="Affiche le mot du jour (le même pour tout le monde aujourd'hui).")
    @app_commands.describe(niveau="Limiter à un niveau HSK précis (optionnel, sinon mélange 1-6)")
    async def wordoftheday(
        self, interaction: discord.Interaction, niveau: Optional[app_commands.Range[int, 1, 6]] = None
    ):
        today = date.today().isoformat()
        word = word_of_the_day(today, niveau)
        embed = build_word_embed(word, niveau or "melange", title=f"Mot du jour — {word['simplified']}", emoji="📅")
        embed.set_author(name=datetime.now().strftime("%A %d %B %Y"))
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="wordofdayconfig",
        description="(Admin) Choisit le salon où poster automatiquement le mot du jour.",
    )
    @app_commands.describe(salon="Salon textuel où poster chaque jour", niveau="Niveau HSK optionnel (sinon mélange 1-6)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def wordofdayconfig(
        self,
        interaction: discord.Interaction,
        salon: discord.TextChannel,
        niveau: Optional[app_commands.Range[int, 1, 6]] = None,
    ):
        set_wordoftheday_config(interaction.guild_id, salon.id, niveau)
        suffix = f" (niveau HSK {niveau})" if niveau else " (mélange 1-6)"
        embed = discord.Embed(
            title="⚙️ Mot du jour configuré",
            description=f"Chaque jour vers 9h (heure de Paris), un mot sera posté dans {salon.mention}{suffix}.",
            color=colors.DICTIONARY,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="radical", description="Décompose un ou plusieurs caractères en radicaux.")
    @app_commands.describe(caractere="Un ou plusieurs caractères chinois")
    async def radical(self, interaction: discord.Interaction, caractere: str):
        radicals = get_radicals()
        embed = discord.Embed(title=f"🧩 Décomposition : {caractere}", color=colors.DICTIONARY)
        found_any = False

        for char in caractere:
            if char.isspace():
                continue
            entry = radicals.get(char)
            if not entry:
                embed.add_field(name=char, value="*Pas de données disponibles.*", inline=False)
                continue

            found_any = True
            lines = []
            if entry.get("radical"):
                lines.append(f"⛩️ **Radical (部首)** : {entry['radical']}")
            if entry.get("decomposition"):
                components = extract_components(entry["decomposition"])
                comp_details = []
                for c in components:
                    comp_entry = radicals.get(c)
                    if comp_entry and comp_entry.get("definition"):
                        comp_details.append(f"{c} ({comp_entry['definition']})")
                    else:
                        comp_details.append(c)
                lines.append(f"🔩 **Composants** : {entry['decomposition']} → " + " + ".join(comp_details))
            else:
                lines.append("*Décomposition détaillée non disponible.*")
            if entry.get("etymology", {}).get("hint"):
                lines.append(f"📜 **Étymologie** (en) : {entry['etymology']['hint']}")
            if entry.get("definition"):
                lines.append(f"💬 **Sens** (en) : {entry['definition']}")

            embed.add_field(name=f"　{char}", value="\n".join(lines), inline=False)

        if not found_any:
            embed.description = "Aucune donnée de décomposition trouvée pour ces caractères."
        embed.set_footer(text="Source : Make Me a Hanzi (Unihan / CJKlib)")
        await interaction.response.send_message(embed=embed)

    @tasks.loop(time=WORD_OF_DAY_UTC_TIME)
    async def post_word_of_the_day(self):
        today = date.today().isoformat()
        for row in all_wordoftheday_configs():
            word = word_of_the_day(today, row["wordoftheday_level"])
            channel = self.bot.get_channel(row["wordoftheday_channel_id"])
            if channel is None:
                continue
            embed = build_word_embed(
                word,
                row["wordoftheday_level"] or "melange",
                title=f"Mot du jour — {word['simplified']}",
                emoji="📅",
            )
            await channel.send(embed=embed)

    @post_word_of_the_day.before_loop
    async def before_post_word_of_the_day(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Dictionary(bot))
