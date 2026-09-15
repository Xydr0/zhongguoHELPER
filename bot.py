import asyncio
import logging
import os
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("chinese-bot")

intents = discord.Intents.default()

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    log.info("Connecte en tant que %s (id: %s)", bot.user, bot.user.id)

    if GUILD_ID:
        guild = discord.Object(id=int(GUILD_ID))
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        log.info("%d commande(s) synchronisee(s) sur le serveur %s", len(synced), GUILD_ID)
    else:
        synced = await bot.tree.sync()
        log.info("%d commande(s) synchronisee(s) globalement (peut prendre jusqu'a 1h a apparaitre)", len(synced))


@bot.tree.command(name="ping", description="Verifie que le bot repond.")
async def ping(interaction: discord.Interaction):
    latency_ms = round(bot.latency * 1000)
    await interaction.response.send_message(f"Pong ! ({latency_ms} ms)")


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    if isinstance(error, discord.app_commands.MissingPermissions):
        message = "Tu n'as pas la permission d'utiliser cette commande."
    else:
        message = "Une erreur est survenue pendant l'execution de la commande."
        log.exception("Erreur commande %s", interaction.command.name if interaction.command else "?", exc_info=error)

    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


async def load_cogs():
    cogs_dir = Path(__file__).parent / "cogs"
    if not cogs_dir.exists():
        return
    for file in sorted(cogs_dir.glob("*.py")):
        if file.stem.startswith("_"):
            continue
        extension = f"cogs.{file.stem}"
        try:
            await bot.load_extension(extension)
            log.info("Cog charge : %s", extension)
        except Exception:
            log.exception("Echec du chargement du cog : %s", extension)


async def main():
    if not TOKEN:
        raise SystemExit(
            "DISCORD_TOKEN manquant. Copie .env.example vers .env et renseigne ton token."
        )
    async with bot:
        await load_cogs()
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
