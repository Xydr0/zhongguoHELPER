import asyncio
import random
import re
import unicodedata

import discord
from discord import app_commands
from discord.ext import commands

import colors
from data_loader import best_translation, sentences_for_level, vocab_for_level
from db.database import add_xp, check_and_award_badges, record_quiz_answer, touch_streak

XP_CORRECT = 10
XP_WRONG = 2

SPEED_ROUNDS = 5
SPEED_TIME = 10
ANSWER_TIME = 30
TRANSLATION_ANSWER_TIME = 60

_PUNCTUATION_RE = re.compile(r"[\s，。！？、；：“”‘’（）《》,.!?;:'\"()\-]")


def normalize_answer(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = _PUNCTUATION_RE.sub("", text)
    return text.strip().lower()


def build_mcq_from_words(pool: list, correct: dict, direction: str):
    others = [w for w in pool if w["simplified"] != correct["simplified"]]
    distractors = random.sample(others, min(3, len(others)))
    candidates = [correct] + distractors
    random.shuffle(candidates)
    correct_index = candidates.index(correct)

    if direction == "zh_fr":
        question = correct["simplified"]
        options = []
        for w in candidates:
            translations, _ = best_translation(w, max_items=1)
            options.append(translations[0] if translations else w["simplified"])
    else:
        translations, _ = best_translation(correct, max_items=1)
        question = translations[0] if translations else correct["simplified"]
        options = [w["simplified"] for w in candidates]

    return question, options, correct_index


class QuizButton(discord.ui.Button):
    def __init__(self, label: str, index: int):
        super().__init__(label=label[:80] or "?", style=discord.ButtonStyle.secondary, row=index // 2)
        self.index = index

    async def callback(self, interaction: discord.Interaction):
        await self.view.handle_click(interaction, self.index)


class QuizView(discord.ui.View):
    """Vue generique a 4 boutons pour /quiz, /quizspeed et /fillblank."""

    def __init__(self, invoker_id: int, options: list, correct_index: int, timeout: float = ANSWER_TIME):
        super().__init__(timeout=timeout)
        self.invoker_id = invoker_id
        self.correct_index = correct_index
        self.answered = False
        self.on_result = None  # async def on_result(interaction_or_None, correct: bool)
        self.message: discord.Message | None = None
        for i, opt in enumerate(options):
            self.add_item(QuizButton(opt, i))

    def _style_buttons(self, chosen_index: int | None):
        for item in self.children:
            item.disabled = True
            if item.index == self.correct_index:
                item.style = discord.ButtonStyle.success
            elif chosen_index is not None and item.index == chosen_index:
                item.style = discord.ButtonStyle.danger

    async def handle_click(self, interaction: discord.Interaction, index: int):
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message("Ce quiz n'est pas pour toi !", ephemeral=True)
            return
        if self.answered:
            await interaction.response.defer()
            return
        self.answered = True
        correct = index == self.correct_index
        self._style_buttons(chosen_index=index)
        self.stop()
        if self.on_result:
            await self.on_result(interaction, correct)

    async def on_timeout(self):
        if self.answered:
            return
        self.answered = True
        self._style_buttons(chosen_index=None)
        if self.on_result:
            await self.on_result(None, False)


class Quiz(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _finish_single_round(self, interaction, embed, options, correct_index, word_simplified, niveau):
        """Cree le callback de fin de manche partage par /quiz et /fillblank."""
        view: QuizView = None  # sera assigne juste apres

        async def on_result(inter, correct_answer):
            record_quiz_answer(interaction.user.id, interaction.guild_id, word_simplified, niveau, correct_answer)
            add_xp(interaction.user.id, interaction.guild_id, XP_CORRECT if correct_answer else XP_WRONG)
            touch_streak(interaction.user.id, interaction.guild_id)
            new_badges = check_and_award_badges(interaction.user.id, interaction.guild_id)

            result_embed = embed.copy()
            if correct_answer:
                result_embed.description = "✅ Bonne réponse !"
            else:
                result_embed.description = f"❌ Mauvaise réponse. La bonne réponse était : **{options[correct_index]}**"
            if inter is None:
                result_embed.description += "\n⏱️ Temps écoulé !"
                await view.message.edit(embed=result_embed, view=view)
            else:
                await inter.response.edit_message(embed=result_embed, view=view)

            if new_badges:
                badge_text = ", ".join(f"{t} mots" for t in new_badges)
                await interaction.followup.send(f"🏅 Nouveau badge débloqué : **{badge_text}** !")

        view = QuizView(interaction.user.id, options, correct_index)
        view.on_result = on_result
        await interaction.response.send_message(embed=embed, view=view)
        view.message = await interaction.original_response()

    @app_commands.command(name="quiz", description="QCM sur le vocabulaire HSK (chinois <-> français).")
    @app_commands.describe(niveau="Niveau HSK de 1 à 6")
    async def quiz(self, interaction: discord.Interaction, niveau: app_commands.Range[int, 1, 6]):
        pool = vocab_for_level(niveau)
        if len(pool) < 4:
            await interaction.response.send_message("Pas assez de mots disponibles pour ce niveau.", ephemeral=True)
            return

        correct = random.choice(pool)
        direction = random.choice(["zh_fr", "fr_zh"])
        question, options, correct_index = build_mcq_from_words(pool, correct, direction)

        embed = discord.Embed(title=f"🎯 Quiz — HSK {niveau}", color=colors.QUIZ)
        if direction == "zh_fr":
            embed.add_field(name="Traduis ce mot :", value=f"## {question}", inline=False)
        else:
            embed.add_field(name="Quel est le mot chinois pour :", value=f"**{question}**", inline=False)
        embed.set_footer(text=f"⏱️ {ANSWER_TIME} secondes pour répondre")

        await self._finish_single_round(interaction, embed, options, correct_index, correct["simplified"], niveau)

    @app_commands.command(name="fillblank", description="Complète la phrase HSK en devinant le mot manquant.")
    @app_commands.describe(niveau="Niveau HSK de 1 à 6")
    async def fillblank(self, interaction: discord.Interaction, niveau: app_commands.Range[int, 1, 6]):
        sentences = sentences_for_level(niveau)
        if not sentences:
            await interaction.response.send_message("Pas de phrases disponibles pour ce niveau.", ephemeral=True)
            return

        sentence = random.choice(sentences)
        blanked = sentence["zh"].replace(sentence["blank"], "____", 1)

        pool_words = [s["blank"] for s in sentences if s["blank"] != sentence["blank"]]
        if len(pool_words) < 3:
            extra = [w["simplified"] for w in vocab_for_level(niveau) if w["simplified"] != sentence["blank"]]
            pool_words = list(dict.fromkeys(pool_words + extra))
        distractors = random.sample(pool_words, min(3, len(pool_words)))
        options = [sentence["blank"]] + distractors
        random.shuffle(options)
        correct_index = options.index(sentence["blank"])

        embed = discord.Embed(title=f"✏️ Complète la phrase — HSK {niveau}", color=colors.QUIZ)
        embed.add_field(name="Phrase", value=f"## {blanked}", inline=False)
        embed.add_field(name="Pinyin", value=sentence["pinyin"], inline=True)
        embed.add_field(name="Traduction", value=sentence["fr"], inline=True)
        embed.set_footer(text=f"⏱️ {ANSWER_TIME} secondes pour répondre")

        await self._finish_single_round(interaction, embed, options, correct_index, sentence["blank"], niveau)

    @app_commands.command(name="quizspeed", description=f"Série de {SPEED_ROUNDS} questions chronométrées ({SPEED_TIME}s chacune).")
    @app_commands.describe(niveau="Niveau HSK de 1 à 6")
    async def quizspeed(self, interaction: discord.Interaction, niveau: app_commands.Range[int, 1, 6]):
        pool = vocab_for_level(niveau)
        if len(pool) < 4:
            await interaction.response.send_message("Pas assez de mots disponibles pour ce niveau.", ephemeral=True)
            return

        intro = discord.Embed(
            title="🎯 Quiz rapide",
            description=f"{SPEED_ROUNDS} questions, {SPEED_TIME} secondes chacune. Prépare-toi !",
            color=colors.QUIZ,
        )
        await interaction.response.send_message(embed=intro)
        message = await interaction.original_response()
        await asyncio.sleep(2)

        score = 0
        used_words = set()

        for round_num in range(1, SPEED_ROUNDS + 1):
            candidates = [w for w in pool if w["simplified"] not in used_words] or pool
            correct = random.choice(candidates)
            used_words.add(correct["simplified"])
            direction = random.choice(["zh_fr", "fr_zh"])
            question, options, correct_index = build_mcq_from_words(pool, correct, direction)

            embed = discord.Embed(title=f"🎯 Question {round_num}/{SPEED_ROUNDS} — HSK {niveau}", color=colors.QUIZ)
            if direction == "zh_fr":
                embed.add_field(name="Traduis ce mot :", value=f"## {question}", inline=False)
            else:
                embed.add_field(name="Quel est le mot chinois pour :", value=f"**{question}**", inline=False)
            embed.set_footer(text=f"⏱️ {SPEED_TIME}s · Score actuel : {score}/{round_num - 1}")

            done = asyncio.Event()
            outcome = {"correct": False}

            view = QuizView(interaction.user.id, options, correct_index, timeout=SPEED_TIME)
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

            record_quiz_answer(interaction.user.id, interaction.guild_id, correct["simplified"], niveau, outcome["correct"])
            if outcome["correct"]:
                score += 1
            await asyncio.sleep(1.5)

        xp_gained = score * XP_CORRECT + (SPEED_ROUNDS - score) * XP_WRONG
        add_xp(interaction.user.id, interaction.guild_id, xp_gained)
        streak = touch_streak(interaction.user.id, interaction.guild_id)
        new_badges = check_and_award_badges(interaction.user.id, interaction.guild_id)

        final_embed = discord.Embed(
            title="🏁 Résultat du quiz rapide",
            description=f"Score final : **{score}/{SPEED_ROUNDS}**\n+{xp_gained} XP · Streak : {streak} jour(s) 🔥",
            color=colors.QUIZ,
        )
        await message.edit(embed=final_embed, view=None)
        if new_badges:
            badge_text = ", ".join(f"{t} mots" for t in new_badges)
            await interaction.followup.send(f"🏅 Nouveau badge débloqué : **{badge_text}** !")

    async def _translation_round(self, interaction: discord.Interaction, niveau: int, sentence: dict, to_chinese: bool):
        if to_chinese:
            title = "🇫🇷 ➜ 🀄 Traduis en chinois"
            prompt = sentence["fr"]
            target_text = sentence["zh"]
            target_label = "Chinois"
            reply_lang = "en chinois"
        else:
            title = "🀄 ➜ 🇫🇷 Traduis en français"
            prompt = f"{sentence['zh']}\n*{sentence['pinyin']}*"
            target_text = sentence["fr"]
            target_label = "Français"
            reply_lang = "en français"

        embed = discord.Embed(title=title, description=f"## {prompt}", color=colors.QUIZ)
        embed.set_footer(text=f"HSK {niveau} · Réponds {reply_lang} dans ce salon — {TRANSLATION_ANSWER_TIME}s")
        await interaction.response.send_message(embed=embed)
        message = await interaction.original_response()

        def check(m: discord.Message):
            return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id

        try:
            reply = await self.bot.wait_for("message", timeout=TRANSLATION_ANSWER_TIME, check=check)
        except asyncio.TimeoutError:
            reply = None

        correct = reply is not None and normalize_answer(reply.content) == normalize_answer(target_text)

        result_embed = discord.Embed(title=title, color=colors.QUIZ)
        if reply is None:
            result_embed.description = "⏱️ Temps écoulé, personne n'a répondu."
        elif correct:
            result_embed.description = f"✅ Bonne réponse ! +{XP_CORRECT} XP"
        else:
            result_embed.description = f"❌ Pas tout à fait.\nTa réponse : {reply.content}"
        result_embed.add_field(name=f"Traduction de référence ({target_label})", value=target_text, inline=False)
        if to_chinese:
            result_embed.add_field(name="Pinyin", value=sentence["pinyin"], inline=False)

        new_badges = []
        if reply is not None:
            record_quiz_answer(interaction.user.id, interaction.guild_id, sentence["blank"], niveau, correct)
            touch_streak(interaction.user.id, interaction.guild_id)
            if correct:
                add_xp(interaction.user.id, interaction.guild_id, XP_CORRECT)
            new_badges = check_and_award_badges(interaction.user.id, interaction.guild_id)

        await message.edit(embed=result_embed)
        if new_badges:
            badge_text = ", ".join(f"{t} mots" for t in new_badges)
            await interaction.followup.send(f"🏅 Nouveau badge débloqué : **{badge_text}** !")

    @app_commands.command(name="frtcn", description="Traduis une phrase du français vers le chinois (le bot vérifie ta réponse).")
    @app_commands.describe(niveau="Niveau HSK de 1 à 6")
    async def frtcn(self, interaction: discord.Interaction, niveau: app_commands.Range[int, 1, 6]):
        sentences = sentences_for_level(niveau)
        if not sentences:
            await interaction.response.send_message("Pas de phrases disponibles pour ce niveau.", ephemeral=True)
            return
        await self._translation_round(interaction, niveau, random.choice(sentences), to_chinese=True)

    @app_commands.command(name="cntfr", description="Traduis une phrase du chinois vers le français (le bot vérifie ta réponse).")
    @app_commands.describe(niveau="Niveau HSK de 1 à 6")
    async def cntfr(self, interaction: discord.Interaction, niveau: app_commands.Range[int, 1, 6]):
        sentences = sentences_for_level(niveau)
        if not sentences:
            await interaction.response.send_message("Pas de phrases disponibles pour ce niveau.", ephemeral=True)
            return
        await self._translation_round(interaction, niveau, random.choice(sentences), to_chinese=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(Quiz(bot))
