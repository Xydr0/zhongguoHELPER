import json
from pathlib import Path
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

import colors
from db.database import add_xp, award_badge, get_user_stats, set_hsk_level

RESOURCES_PATH = Path(__file__).parent.parent / "resources.json"

HSK_ROLE_NAMES = {i: f"HSK {i}" for i in range(1, 7)}


def load_resources() -> dict:
    if not RESOURCES_PATH.exists():
        return {}
    with open(RESOURCES_PATH, encoding="utf-8") as f:
        return json.load(f)


async def get_or_create_hsk_role(guild: discord.Guild, level: int) -> discord.Role:
    name = HSK_ROLE_NAMES[level]
    role = discord.utils.get(guild.roles, name=name)
    if role is None:
        role = await guild.create_role(name=name, reason="Rôle HSK créé automatiquement par le bot (/setlevel)")
    return role


class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="setlevel", description="Définit ton niveau HSK et attribue le rôle Discord correspondant.")
    @app_commands.describe(niveau="Ton niveau HSK (1 à 6)")
    async def setlevel(self, interaction: discord.Interaction, niveau: app_commands.Range[int, 1, 6]):
        if interaction.guild is None:
            await interaction.response.send_message("Cette commande fonctionne seulement dans un serveur.", ephemeral=True)
            return

        try:
            new_role = await get_or_create_hsk_role(interaction.guild, niveau)
            other_roles = [
                r for r in interaction.user.roles
                if r.name in HSK_ROLE_NAMES.values() and r.name != new_role.name
            ]
            if other_roles:
                await interaction.user.remove_roles(*other_roles, reason="Changement de niveau HSK")
            await interaction.user.add_roles(new_role, reason="Niveau HSK défini via /setlevel")
        except discord.Forbidden:
            await interaction.response.send_message(
                "Je n'ai pas la permission de gérer les rôles ici. Vérifie que mon rôle a bien "
                "la permission **Gérer les rôles** et qu'il est positionné au-dessus des rôles HSK.",
                ephemeral=True,
            )
            return

        set_hsk_level(interaction.user.id, interaction.guild_id, niveau)

        embed = discord.Embed(
            title="🎓 Niveau HSK mis à jour",
            description=f"Tu es maintenant **HSK {niveau}** {new_role.mention}",
            color=colors.ADMIN,
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="resource", description="Renvoie un lien vers une ressource pédagogique.")
    @app_commands.describe(mot_cle="Mot-clé à chercher (ex: grammaire, dictionnaire, traits...)")
    async def resource(self, interaction: discord.Interaction, mot_cle: str):
        resources = load_resources()
        key = mot_cle.strip().lower()

        match = resources.get(key)
        if not match:
            candidates = [k for k in resources if key in k or k in key]
            if len(candidates) == 1:
                match = resources[candidates[0]]

        if not match:
            available = ", ".join(f"`{k}`" for k in sorted(resources.keys())) or "*(aucune ressource configurée)*"
            embed = discord.Embed(
                title="🈳 Ressource introuvable",
                description=f"Aucune ressource pour « {mot_cle} ».\n\n**Mots-clés disponibles :**\n{available}",
                color=colors.ADMIN,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(title=f"📚 {match['title']}", url=match["url"], color=colors.ADMIN)
        embed.add_field(name="Lien", value=match["url"], inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="givexp", description="(Admin) Ajoute ou retire de l'XP à un membre.")
    @app_commands.describe(membre="Le membre concerné", montant="Quantité d'XP (négatif pour retirer)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def givexp(self, interaction: discord.Interaction, membre: discord.Member, montant: int):
        add_xp(membre.id, interaction.guild_id, montant)
        stats = get_user_stats(membre.id, interaction.guild_id)

        embed = discord.Embed(
            title="⚙️ XP mis à jour",
            description=(
                f"{'+' if montant >= 0 else ''}{montant} XP pour {membre.mention}\n"
                f"Nouveau total : **{stats['xp']} XP**"
            ),
            color=colors.ADMIN,
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="givebadge", description="(Admin) Attribue manuellement un badge à un membre.")
    @app_commands.describe(membre="Le membre concerné", palier="Palier du badge à attribuer")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def givebadge(self, interaction: discord.Interaction, membre: discord.Member, palier: Literal[50, 100, 500]):
        newly_awarded = award_badge(membre.id, interaction.guild_id, f"words_{palier}")

        if newly_awarded:
            description = f"🏅 Badge **{palier} mots** attribué à {membre.mention} !"
        else:
            description = f"{membre.mention} avait déjà le badge **{palier} mots**."

        embed = discord.Embed(title="⚙️ Badge attribué", description=description, color=colors.ADMIN)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Admin(bot))
