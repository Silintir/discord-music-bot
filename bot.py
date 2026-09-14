import asyncio
import logging
import os

import discord
import yt_dlp
from discord.ext import commands
from dotenv import load_dotenv


load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

YDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "default_search": "ytsearch",
}
FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


async def get_audio_info(query: str) -> dict:
    def extract() -> dict:
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(query, download=False)
            if "entries" in info:
                entries = info.get("entries") or []
                if not entries:
                    raise RuntimeError("No YouTube results found.")
                info = entries[0]
            return info

    return await asyncio.to_thread(extract)


async def ensure_voice(ctx: commands.Context) -> discord.VoiceClient:
    if ctx.guild is None:
        raise commands.CommandError("Music commands only work in a server.")

    author_voice = getattr(ctx.author, "voice", None)
    if author_voice is None or author_voice.channel is None:
        raise commands.CommandError("Join a voice channel first.")

    voice_client = ctx.guild.voice_client
    if voice_client is None:
        return await author_voice.channel.connect()
    if voice_client.channel != author_voice.channel:
        await voice_client.move_to(author_voice.channel)
    return voice_client


@bot.event
async def on_ready() -> None:
    logging.info("Logged in as %s", bot.user)


@bot.command()
async def join(ctx: commands.Context) -> None:
    voice_client = await ensure_voice(ctx)
    await ctx.send(f"Joined **{voice_client.channel}**.")


@bot.command()
async def play(ctx: commands.Context, *, query: str) -> None:
    voice_client = await ensure_voice(ctx)
    await ctx.typing()

    try:
        info = await get_audio_info(query)
    except Exception as error:
        logging.exception("YouTube extraction failed")
        await ctx.send(f"Could not load that track: {error}")
        return

    if voice_client.is_playing() or voice_client.is_paused():
        voice_client.stop()

    ffmpeg_executable = os.getenv("FFMPEG_PATH", "ffmpeg")
    source = discord.FFmpegPCMAudio(
        info["url"],
        executable=ffmpeg_executable,
        **FFMPEG_OPTIONS,
    )

    def playback_finished(error: Exception | None) -> None:
        if error:
            logging.error("Playback error: %s", error)

    voice_client.play(source, after=playback_finished)
    await ctx.send(f"Now playing **{info.get('title', query)}**")


@bot.command()
async def pause(ctx: commands.Context) -> None:
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("Playback paused.")


@bot.command()
async def resume(ctx: commands.Context) -> None:
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("Playback resumed.")


@bot.command()
async def stop(ctx: commands.Context) -> None:
    if ctx.voice_client:
        ctx.voice_client.stop()
        await ctx.send("Playback stopped.")


@bot.command()
async def leave(ctx: commands.Context) -> None:
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Disconnected.")


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError) -> None:
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Usage: `!play <YouTube URL or search terms>`")
        return
    await ctx.send(str(error))


def main() -> None:
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("Set DISCORD_TOKEN in a .env file before starting the bot.")
    bot.run(token)


if __name__ == "__main__":
    main()