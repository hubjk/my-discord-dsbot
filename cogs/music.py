import discord
from discord.ext import commands
import yt_dlp as youtube_dl
import asyncio
import urllib.request
import json
import re

# Suppress noise about console usage from errors
youtube_dl.utils.bug_reports_message = lambda **kwargs: ''

ytdl_format_options = {
    'format': 'bestaudio[ext=m4a]/bestaudio[ext=mp4]/bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': False, # Changed to False for playlist support
    'nocheckcertificate': True,
    'ignoreerrors': True, # Ignore unavailable videos
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch1', # Take first search result by default
    'source_address': '0.0.0.0'
}

# Fast extractor that doesn't resolve video streams (perfect for fetching playlists instantly)
fast_ytdl_options = ytdl_format_options.copy()
fast_ytdl_options['extract_flat'] = True
fast_ytdl = youtube_dl.YoutubeDL(fast_ytdl_options)

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url: str, *, loop=None, stream=False) -> "YTDLSource":
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        
        if 'entries' in data:
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

def get_spotify_title(url):
    try:
        req = urllib.request.Request(f"https://open.spotify.com/oembed?url={url}", headers={'User-Agent': 'Mozilla/5.0'})
        response = urllib.request.urlopen(req, timeout=3)
        data = json.loads(response.read())
        title = data.get('title')
        if title:
            return title
    except Exception as e:
        print(f"[Music] Spotify oEmbed error: {e}")
    return None


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Format: {guild_id: [{'title': title, 'url': url}, ...]}
        self.queues: dict[int, list[dict]] = {}
        # History: {guild_id: [(title, url), ...]} — last 20 songs
        self.history: dict[int, list[tuple[str, str]]] = {}

    async def play_next(self, ctx):
        if ctx.guild.id in self.queues and len(self.queues[ctx.guild.id]) > 0:
            # Get the next song dict
            next_song = self.queues[ctx.guild.id].pop(0)

            try:
                # Extract Stream URL right before playing so it doesn't expire
                player = await YTDLSource.from_url(next_song['url'], loop=self.bot.loop, stream=True)
            except Exception as e:
                await ctx.send(f"❌ Не вдалося відтворити **{next_song['title']}** (переходимо до наступної).")
                # Resume play loop safely
                fut = asyncio.run_coroutine_threadsafe(self.play_next(ctx), self.bot.loop)
                try: fut.result()
                except: pass
                return
            
            # Start playing
            def after_playing(error):
                fut = asyncio.run_coroutine_threadsafe(self.play_next(ctx), self.bot.loop)
                try: fut.result()
                except: pass

            # Save to history
            gid = ctx.guild.id
            if gid not in self.history:
                self.history[gid] = []
            self.history[gid].append((player.title, player.data.get('webpage_url', player.url)))
            if len(self.history[gid]) > 20:
                self.history[gid].pop(0)

            ctx.voice_client.play(player, after=after_playing)
            await ctx.send(f'🎶 Тепер грає: **{player.title}**')
        else:
            # Queue is empty
            pass

    @commands.command(name="join", aliases=["зайти"], help="Доєднати бота до вашого голосового каналу")
    async def join(self, ctx):
        if not ctx.message.author.voice:
            await ctx.send("❌ Ви не підключені до жодного голосового каналу!")
            return False
        
        channel = ctx.message.author.voice.channel
        if ctx.voice_client is not None:
            return await ctx.voice_client.move_to(channel)
        
        await channel.connect()
        return True

    @commands.command(name="play", aliases=["p", "грати"], help="Відтворити пісню з YouTube. Приклад: !play <посилання_або_назва>")
    async def play(self, ctx, *, query):
        if not ctx.voice_client:
            success = await ctx.invoke(self.join)
            if not success:
                return

        async with ctx.typing():
            # Check for Spotify links
            if "open.spotify.com/track" in query:
                sp_title = await self.bot.loop.run_in_executor(None, get_spotify_title, query)
                if sp_title:
                    query = f"ytsearch:{sp_title}"
                else:
                    await ctx.send("❌ Не вдалося розпізнати трек зі Spotify.")
                    return

            try:
                # Add YouTube search prefix if the query is not a direct URL
                if not query.startswith("http://") and not query.startswith("https://"):
                    search_query = f"ytsearch:{query}"
                else:
                    search_query = query

                # Fast extraction (returns flat dictionaries, resolves playlists beautifully without extracting HD stream URLs)
                data = await self.bot.loop.run_in_executor(None, lambda: fast_ytdl.extract_info(search_query, download=False))
            except Exception as e:
                await ctx.send(f"❌ Помилка пошуку: ```{e}```")
                return

            if not data:
                await ctx.send("❌ Нічого не знайдено.")
                return

            # Determine if it's a playlist or a single result
            if 'entries' in data:
                # If the fallback default returned a playlist, take it all!
                entries = list(data['entries'])
                if data.get('extractor_key') == 'YoutubeSearch':
                    entries = entries[:1] # Take only the first result of a manual query
            else:
                entries = [data]

            entries = [e for e in entries if e] # ignore None
            if not entries:
                await ctx.send("❌ Нічого не знайдено або плейліст пустий/приватний.")
                return

            if ctx.guild.id not in self.queues:
                self.queues[ctx.guild.id] = []

            for entry in entries:
                # 'url' is the direct audio stream (required for FFmpeg), 'webpage_url' is the video page
                url_to_play = entry.get('url') or entry.get('webpage_url') or query
                if not url_to_play.startswith("http"):
                    continue # ytsearch entries might not have an HTTP url initially in flat mode sometimes, but usually they do.
                
                title = entry.get('title')
                if not title or title == "videoplayback":
                    title = 'Unknown Title'

                self.queues[ctx.guild.id].append({'url': url_to_play, 'title': title})

            if len(entries) > 1:
                await ctx.send(f'🎵 Додано плейліст з **{len(entries)}** треками в чергу!')
            elif ctx.voice_client.is_playing() or ctx.voice_client.is_paused():
                await ctx.send(f'🎵 Додано в чергу: **{entries[0].get("title", "Unknown")}** (Місце: {len(self.queues[ctx.guild.id])})')

            # If the bot is not doing anything, tell it to start playing the queue
            if not ctx.voice_client.is_playing() and not ctx.voice_client.is_paused():
                await self.play_next(ctx)

    @commands.command(name="queue", aliases=["q", "черга"], help="Показати чергу пісень")
    async def queue(self, ctx):
        if ctx.guild.id in self.queues and len(self.queues[ctx.guild.id]) > 0:
            queue_list = "\n".join([f"{i+1}. {song['title']}" for i, song in enumerate(self.queues[ctx.guild.id][:20])])
            if len(self.queues[ctx.guild.id]) > 20:
                queue_list += f"\n\n*...і ще {len(self.queues[ctx.guild.id]) - 20} треків.*"
            embed = discord.Embed(title="🎵 Черга відтворення", description=queue_list, color=discord.Color.blue())
            await ctx.send(embed=embed)
        else:
            await ctx.send("Черга порожня.")

    @commands.command(name="clearqueue", aliases=["cq", "очистити_чергу", "cqueue"], help="Очистити чергу пісень")
    async def clearqueue(self, ctx):
        if ctx.guild.id in self.queues and self.queues[ctx.guild.id]:
            self.queues[ctx.guild.id].clear()
            await ctx.send("🧹 Чергу успішно очищено!")
        else:
            await ctx.send("Черга і так порожня.")

    @commands.command(name="skip", aliases=["s", "пропустити"], help="Пропустити поточну пісню")
    async def skip(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop() # This triggers the `after` callback which calls `play_next`
            await ctx.send("⏭️ Пісню пропущено!")
        else:
            await ctx.send("Зараз нічого не грає.")

    @commands.command(name="stop", aliases=["leave", "зупинити", "вийти"], help="Зупинити музику та вийти з каналу")
    async def stop(self, ctx):
        if ctx.voice_client:
            # Clear queue
            if ctx.guild.id in self.queues:
                self.queues[ctx.guild.id].clear()
            
            await ctx.voice_client.disconnect()
            await ctx.send("🛑 Відтворення зупинено, я вийшов з каналу.")
        else:
            await ctx.send("Я не знаходжуся в голосовому каналі.")

    @commands.command(name="pause", aliases=["пауза"], help="Поставити музику на паузу")
    async def pause(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            await ctx.send("⏸️ Музика на паузі.")

    @commands.command(name="history", aliases=["his", "історія"], help="Показати останні 20 пісень. Додати номери щоб включити: !his 1,3")
    async def history(self, ctx, *, selection: str = ""):
        gid = ctx.guild.id
        hist = self.history.get(gid, [])
        
        if not hist:
            await ctx.send("📏 Історія пуста. Спочатку відтворіть якусь пісню через `!play`.")
            return

        # If user gave a selection like "1,3,5" — re-add those songs to queue
        if selection:
            indices = []
            for part in selection.split(','):
                try:
                    idx = int(part.strip()) - 1
                    if 0 <= idx < len(hist):
                        indices.append(idx)
                except ValueError:
                    pass

            if not indices:
                await ctx.send("❌ Невірний вибір. Введіть номери через кому: `!his 1,3`")
                return

            if not ctx.voice_client:
                success = await ctx.invoke(self.join)
                if not success:
                    return

            added = []
            for idx in indices:
                title, url = hist[idx]
                try:
                    async with ctx.typing():
                        player = await YTDLSource.from_url(url, loop=self.bot.loop, stream=True)
                    if ctx.guild.id not in self.queues:
                        self.queues[ctx.guild.id] = []
                    if ctx.voice_client.is_playing() or ctx.voice_client.is_paused():
                        self.queues[ctx.guild.id].append(player)
                        added.append(f"🎵 {player.title} → Додано в чергу")
                    else:
                        def after_playing_h(error):
                            fut = asyncio.run_coroutine_threadsafe(self.play_next(ctx), self.bot.loop)
                            try: fut.result()
                            except: pass
                        ctx.voice_client.play(player, after=after_playing_h)
                        added.append(f"🎶 {player.title} → Розпочато відтворення")
                except Exception as e:
                    added.append(f"❌ {title} → Помилка: {e}")

            await ctx.send("\n".join(added))
            return

        # No selection — show history list
        lines = []
        for i, (title, _) in enumerate(reversed(hist), 1):
            lines.append(f"`{i}.` {title}")
        embed = discord.Embed(
            title="📜 Останні 20 пісень",
            description="\n".join(lines),
            color=discord.Color.purple()
        )
        embed.set_footer(text="Щоб додати пісню, напишіть: !his 1 | Кілька одразу: !his 1,3,5")
        await ctx.send(embed=embed)

    @commands.command(name="resume", aliases=["продовжити"], help="Продовжити відтворення музики")
    async def resume(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.send("▶️ Відтворення продовжено.")

async def setup(bot):
    await bot.add_cog(Music(bot))
