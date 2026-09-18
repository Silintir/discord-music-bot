# Discord Music Bot

A small Discord bot that streams audio from a YouTube URL or search using
`yt-dlp` and FFmpeg.

## Setup

1. Install [FFmpeg](https://ffmpeg.org/download.html) and make sure `ffmpeg`
   is available on `PATH`. Alternatively, set `FFMPEG_PATH` in `.env`.
2. Create an application and bot in the
   [Discord Developer Portal](https://discord.com/developers/applications).
3. On the bot page, enable the **Message Content Intent**.
4. Invite the bot with the `bot` scope and these permissions:
   **View Channels**, **Send Messages**, **Connect**, and **Speak**.
5. Install dependencies into the existing local virtual environment:

   ```powershell
   .\venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

6. Copy `.env.example` to `.env` and put the bot token in `DISCORD_TOKEN`.
7. Start the bot using the local virtual environment:

   ```powershell
   .\venv\Scripts\python.exe .\bot.py
   ```

## Commands

- `!join` - join your current voice channel
- `!play <URL or search>` - play a track or an entire YouTube playlist
- `!skip` - skip to the next playlist track
- `!pause` - pause playback
- `!resume` - resume playback
- `!stop` - stop playback
- `!leave` - disconnect from voice