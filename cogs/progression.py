import asyncio
import random

import discord
from discord import app_commands
from discord.ext import commands

import colors
from cogs.quiz import ANSWER_TIME, XP_CORRECT, XP_WRONG, QuizView, build_mcq_from_words
from data_loader import best_translation, get_dictionary, vocab_for_level
from db.database import (
    BADGE_THRESHOLDS,
    add_xp,
    check_and_award_badges,
    get_badges,
    get_leaderboard,
    get_user_stats,
    record_quiz_answer,
    touch_streak,
    words_seen_count,
    words_to_review,
)

BADGE_LABELS = {
    50: "🥉 Apprenti — 50 mots vus",
    100: "🥈 Assidu — 100 mots vus",
    500: "🥇 Maître — 500 mots vus",
}

REVIEW_ROUNDS = 5


def _word_lookup(simplified: str, level: int | None) -> dict:
    if level:
        for w in vocab_for_level(level):
            if w["simplified"] == simplified:
                return w
    entry = get_dictionary().get(simplified, {})
    return {
        "simplified": simplified,
        "pinyin": entry.get("pinyin", "?"),
        "fr": entry.get("fr"),
        "en": entry.get("en"),
        "pos": [],
        "radical": "",
    }


def _guild_only(interaction: discord.Interaction) -> bool:
    return interaction.guild_id is not None


class Progression(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="score", description="Affiche ton score, ton streak et ta progression.")
    async def score(self, interaction: discord.Interaction):
        if not _guild_only(interaction):
            await interaction.response.send_message("Cette commande fonctionne seulement dans un serveur.", ephemeral=True)
            return

        stats = get_user_stats(interaction.user.id, interaction.guild_id)
        seen = words_seen_count(interaction.user.id, interaction.guild_id)

        embed = discord.Embed(title=f"📊 Score de {interaction.user.display_name}", color=colors.PROGRESSION)
        embed.add_field(name="✨ XP", value=str(stats["xp"]), inline=True)
        embed.add_field(name="🔥 Streak", value=f"{stats['streak_count']} jour(s)", inline=True)
        embed.add_field(name="🈶 Mots vus", value=str(seen), inline=True)
        if stats["hsk_level"]:
            embed.add_field(name="🎓 Niveau HSK visé", value=str(stats["hsk_level"]), inline=True)
        embed.set_footer(text="Continue les quiz pour gagner de l'XP !")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="leaderboard", description="Classement des 10 meilleurs du serveur.")
    async def leaderboard(self, interaction: discord.Interaction):
        if not _guild_only(interaction):
            await interaction.response.send_message("Cette commande fonctionne seulement dans un serveur.", ephemeral=True)
            return

        rows = get_leaderboard(interaction.guild_id, limit=10)
        if not rows:
            await interaction.response.send_message("Personne n'a encore de score sur ce serveur. Lance un `/quiz` !", ephemeral=True)
            return

        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for i, row in enumerate(rows):
            rank = medals[i] if i < 3 else f"`#{i + 1}`"
            lines.append(f"{rank} <@{row['user_id']}> — **{row['xp']} XP** (streak {row['streak_count']}🔥)")

        embed = discord.Embed(title="🏆 Classement du serveur", description="\n".join(lines), color=colors.PROGRESSION)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="streak", description="Affiche ton nombre de jours consécutifs d'activité.")
    async def streak(self, interaction: discord.Interaction):
        if not _guild_only(interaction):
            await interaction.response.send_message("Cette commande fonctionne seulement dans un serveur.", ephemeral=True)
            return

        stats = get_user_stats(interaction.user.id, interaction.guild_id)
        streak_count = stats["streak_count"]
        embed = discord.Embed(
            title=f"🔥 Streak de {interaction.user.display_name}",
            description=f"## {streak_count} jour(s) consécutif(s)",
            color=colors.PROGRESSION,
        )
        if streak_count == 0:
            embed.set_footer(text="Fais un quiz aujourd'hui pour démarrer ton streak !")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="badge", description="Affiche tes badges débloqués (paliers de mots vus).")
    async def badge(self, interaction: discord.Interaction):
        if not _guild_only(interaction):
            await interaction.response.send_message("Cette commande fonctionne seulement dans un serveur.", ephemeral=True)
            return

        earned = {row["badge_key"]: row["earned_at"] for row in get_badges(interaction.user.id, interaction.guild_id)}
        seen = words_seen_count(interaction.user.id, interaction.guild_id)

        embed = discord.Embed(title=f"🏅 Badges de {interaction.user.display_name}", color=colors.PROGRESSION)
        for threshold in BADGE_THRESHOLDS:
            key = f"words_{threshold}"
            label = BADGE_LABELS.get(threshold, f"{threshold} mots vus")
            if key in earned:
                embed.add_field(name=label, value="✅ Débloqué", inline=False)
            else:
                embed.add_field(name=label, value=f"🔒 Verrouillé ({seen}/{threshold} mots vus)", inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="review", description="Session de révision : priorise les mots que tu rates le plus souvent.")
    async def review(self, interaction: discord.Interaction):
        if not _guild_only(interaction):
            await interaction.response.send_message("Cette commande fonctionne seulement dans un serveur.", ephemeral=True)
            return

        rows = words_to_review(interaction.user.id, interaction.guild_id, limit=REVIEW_ROUNDS)
        if not rows:
            await interaction.response.send_message(
                "🎉 Aucun mot à réviser pour l'instant ! Fais quelques `/quiz` pour construire ton historique.",
                ephemeral=True,
            )
            return

        intro = discord.Embed(
            title="📚 Session de révision",
            description=f"{len(rows)} mot(s) à revoir, du plus souvent raté au moins souvent raté.",
            color=colors.PROGRESSION,
        )
        await interaction.response.send_message(embed=intro)
        message = await interaction.original_response()
        await asyncio.sleep(2)

        score = 0
        for i, row in enumerate(rows, start=1):
            level = row["level"] or 1
            word = _word_lookup(row["word_simplified"], level)
            pool = vocab_for_level(level) or [word]
            if word not in pool:
                pool = pool + [word]
            direction = random.choice(["zh_fr", "fr_zh"])
            question, options, correct_index = build_mcq_from_words(pool, word, direction)

            embed = discord.Embed(title=f"📚 Révision {i}/{len(rows)} — HSK {level}", color=colors.PROGRESSION)
            if direction == "zh_fr":
                embed.add_field(name="Traduis ce mot :", value=f"## {question}", inline=False)
            else:
                embed.add_field(name="Quel est le mot chinois pour :", value=f"**{question}**", inline=False)
            embed.set_footer(text=f"Raté {row['wrong']} fois récemment · ⏱️ {ANSWER_TIME}s")

            done = asyncio.Event()
            outcome = {"correct": False}

            view = QuizView(interaction.user.id, options, correct_index, timeout=ANSWER_TIME)
            view.message = message

            async def on_result(inter, correct_answer, embed=embed, view=view, options=options, correct_index=correct_index):
                outcome["correct"] = correct_answer
                result_embed = embed.copy()
                if correct_answer:
                    result_embed.description = "✅ Bonne réponse !"
                else:
                    result_embed.description = f"❌ Faux ! La réponse était : **{options[correct_index]}**"
                    if inter is None:
                        result_embed.description += " (temps écoulé)"
                if inter is None:
                    await view.message.edit(embed=result_embed, view=view)
                else:
                    await inter.response.edit_message(embed=result_embed, view=view)
                done.set()

            view.on_result = on_result
            await message.edit(embed=embed, view=view)
            await done.wait()

            record_quiz_answer(interaction.user.id, interaction.guild_id, word["simplified"], level, outcome["correct"])
            if outcome["correct"]:
                score += 1
            await asyncio.sleep(1.5)

        xp_gained = score * XP_CORRECT + (len(rows) - score) * XP_WRONG
        add_xp(interaction.user.id, interaction.guild_id, xp_gained)
        streak_count = touch_streak(interaction.user.id, interaction.guild_id)
        new_badges = check_and_award_badges(interaction.user.id, interaction.guild_id)

        final_embed = discord.Embed(
            title="🏁 Révision terminée",
            description=f"Score : **{score}/{len(rows)}**\n+{xp_gained} XP · Streak : {streak_count} jour(s) 🔥",
            color=colors.PROGRESSION,
        )
        await message.edit(embed=final_embed, view=None)
        if new_badges:
            badge_text = ", ".join(f"{t} mots" for t in new_badges)
            await interaction.followup.send(f"🏅 Nouveau badge débloqué : **{badge_text}** !")


async def setup(bot: commands.Bot):
    await bot.add_cog(Progression(bot))
