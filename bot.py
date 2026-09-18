import asyncio
from collections import defaultdict, deque
from dataclasses import dataclass
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
    "quiet": True,
    "default_search": "ytsearch",
}
FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


@dataclass
class Track:
    title: str
    url: str


queues: dict[int, deque[Track]] = defaultdict(deque)
playback_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


async def get_tracks(query: str) -> list[Track]:
    def extract() -> list[Track]:
        options = {**YDL_OPTIONS, "extract_flat": "in_playlist"}
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(query, download=False)
            entries = info.get("entries") if info else None
            if entries:
                return [
                    Track(
                        title=entry.get("title") or "Unknown title",
                        url=entry.get("webpage_url") or entry.get("url"),
                    )
                    for entry in entries
                    if entry and (entry.get("webpage_url") or entry.get("url"))
                ]
            if not info:
                return []
            return [
                Track(
                    title=info.get("title") or query,
                    url=info.get("webpage_url") or query,
                )
            ]

    return await asyncio.to_thread(extract)


async def get_audio_info(query: str) -> dict:
    def extract() -> dict:
        options = {**YDL_OPTIONS, "noplaylist": True}
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(query, download=False)
            if "entries" in info:
                entries = info.get("entries") or []
                if not entries:
                    raise RuntimeError("No YouTube results found.")
                info = entries[0]
            return info

    return await asyncio.to_thread(extract)


async def play_next(
    guild_id: int,
    voice_client: discord.VoiceClient,
    channel: discord.abc.Messageable,
) -> None:
    async with playback_locks[guild_id]:
        if not voice_client.is_connected() or voice_client.is_playing():
            return

        while queues[guild_id]:
            track = queues[guild_id].popleft()
            try:
                info = await get_audio_info(track.url)
                source = discord.FFmpegPCMAudio(
                    info["url"],
                    executable=os.getenv("FFMPEG_PATH", "ffmpeg"),
                    **FFMPEG_OPTIONS,
                )
            except Exception as error:
                logging.exception("Could not prepare track: %s", track.title)
                await channel.send(f"Skipping **{track.title}**: {error}")
                continue

            loop = asyncio.get_running_loop()

            def playback_finished(error: Exception | None) -> None:
                if error:
                    logging.error("Playback error: %s", error)
                asyncio.run_coroutine_threadsafe(
                    play_next(guild_id, voice_client, channel), loop
                )

            voice_client.play(source, after=playback_finished)
            await channel.send(f"Now playing **{info.get('title', track.title)}**")
            return


async def ensure_voice(ctx: commands.Context) -> discord.VoiceClient:
    if ctx.guild is None:
        raise commands.CommandError("Music commands only work in a server.")

    author_voice = getattr(ctx.author, "voice", None)
    if author_voice is None or author_voice.channel is None:
        raise commands.CommandError("Join a voice channel first.")

    voice_client = ctx.guild.voice_client
    if voice_client is None:
        return await author_voice.channel.connect(self_deaf=True)
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
        tracks = await get_tracks(query)
    except Exception as error:
        logging.exception("YouTube extraction failed")
        await ctx.send(f"Could not load that URL or search: {error}")
        return

    if not tracks:
        await ctx.send("No playable tracks were found.")
        return

    guild_id = ctx.guild.id
    queues[guild_id].clear()
    queues[guild_id].extend(tracks)
    if voice_client.is_playing() or voice_client.is_paused():
        voice_client.stop()
    else:
        await play_next(guild_id, voice_client, ctx.channel)

    if len(tracks) > 1:
        await ctx.send(f"Loaded **{len(tracks)} tracks** from the playlist.")


@bot.command()
async def skip(ctx: commands.Context) -> None:
    if ctx.voice_client and (ctx.voice_client.is_playing() or ctx.voice_client.is_paused()):
        ctx.voice_client.stop()
        await ctx.send("Skipped.")


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
        if ctx.guild:
            queues[ctx.guild.id].clear()
        ctx.voice_client.stop()
        await ctx.send("Playback stopped.")


@bot.command()
async def leave(ctx: commands.Context) -> None:
    if ctx.voice_client:
        if ctx.guild:
            queues[ctx.guild.id].clear()
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