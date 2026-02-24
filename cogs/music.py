import discord
from discord.ext import commands
import yt_dlp
import asyncio
import urllib.request
import json

# Завантаження opus
if not discord.opus.is_loaded():
    import ctypes.util
    opus_path = ctypes.util.find_library('opus')
    if opus_path:
        discord.opus.load_opus(opus_path)
        print(f"[Music] ✅ Opus завантажено: {opus_path}")
    else:
        print("[Music] ⚠️ libopus не знайдено!")

yt_dlp.utils.bug_reports_message = lambda **kwargs: ''

ytdl_opts = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'nocheckcertificate': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch1',
    'source_address': '0.0.0.0',
}

# Для плейлистів — швидкий режим без витягування стрімів
playlist_opts = ytdl_opts.copy()
playlist_opts['extract_flat'] = True
playlist_opts['noplaylist'] = False

ffmpeg_opts = {
    'before_options': '-nostdin -loglevel quiet -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

ytdl = yt_dlp.YoutubeDL(ytdl_opts)
playlist_ytdl = yt_dlp.YoutubeDL(playlist_opts)


def get_spotify_title(url):
    """Отримує назву треку зі Spotify через oEmbed."""
    try:
        req = urllib.request.Request(
            f"https://open.spotify.com/oembed?url={url}",
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        response = urllib.request.urlopen(req, timeout=3)
        data = json.loads(response.read())
        return data.get('title')
    except Exception:
        return None


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queues: dict[int, list[dict]] = {}      # {guild_id: [{'title': ..., 'url': ...}]}
        self.history: dict[int, list[tuple]] = {}     # {guild_id: [(title, url), ...]}
        self._play_lock: dict[int, asyncio.Lock] = {} # Запобігає подвійному програванню

    def _lock(self, guild_id: int) -> asyncio.Lock:
        if guild_id not in self._play_lock:
            self._play_lock[guild_id] = asyncio.Lock()
        return self._play_lock[guild_id]

    async def _extract_stream(self, url: str) -> tuple[str, str]:
        """Витягує стрім-URL та назву треку. Повертає (stream_url, title)."""
        data = await self.bot.loop.run_in_executor(
            None, lambda: ytdl.extract_info(url, download=False)
        )
        if not data:
            raise Exception("yt-dlp повернув порожній результат")
        if 'entries' in data:
            data = data['entries'][0]
        return data['url'], data.get('title', 'Невідомий трек')

    async def play_next(self, ctx):
        """Бере наступний трек з черги та програє. Якщо черга пуста — нічого не робить."""
        gid = ctx.guild.id

        async with self._lock(gid):
            if not ctx.voice_client or not ctx.voice_client.is_connected():
                return

            queue = self.queues.get(gid, [])
            if not queue:
                return

            song = queue.pop(0)

            try:
                stream_url, extracted_title = await self._extract_stream(song['url'])
            except Exception as e:
                await ctx.send(f"❌ Не вдалося відтворити **{song['title']}**, пропускаю.")
                print(f"[Music] Extract error: {e}")
                self.bot.loop.create_task(self.play_next(ctx))
                return

            # Використовуємо назву з черги (вона правильна), а не з повторного витягування
            title = song['title'] if song['title'] != 'Невідомий трек' else extracted_title

            source = discord.FFmpegPCMAudio(stream_url, **ffmpeg_opts)
            player = discord.PCMVolumeTransformer(source, volume=0.5)

            # Зберігаємо в історію
            hist = self.history.setdefault(gid, [])
            hist.append((title, song['url']))
            if len(hist) > 20:
                hist.pop(0)

            def after(error):
                if error:
                    print(f'[Music] Playback error: {error}')
                asyncio.run_coroutine_threadsafe(self.play_next(ctx), self.bot.loop)

            ctx.voice_client.play(player, after=after)
            await ctx.send(f'🎶 Грає: **{title}**')

    # ─── Команди ────────────────────────────────────────────

    @commands.command(name="join", aliases=["зайти"], help="Приєднати бота до голосового каналу")
    async def join(self, ctx):
        if not ctx.author.voice:
            await ctx.send("❌ Ви не в голосовому каналі!")
            return False
        channel = ctx.author.voice.channel
        if ctx.voice_client:
            await ctx.voice_client.move_to(channel)
        else:
            await channel.connect()
        return True

    @commands.command(name="play", aliases=["p", "грати"], help="Відтворити пісню: !play <посилання або назва>")
    async def play(self, ctx, *, query):
        if not ctx.voice_client:
            if not await ctx.invoke(self.join):
                return

        async with ctx.typing():
            # Spotify → пошук на YouTube
            if "open.spotify.com/track" in query:
                title = await self.bot.loop.run_in_executor(None, get_spotify_title, query)
                if title:
                    query = f"ytsearch:{title}"
                else:
                    return await ctx.send("❌ Не вдалося розпізнати трек зі Spotify.")

            # Визначаємо: плейлист чи один трек
            is_playlist = "list=" in query
            try:
                if is_playlist:
                    data = await self.bot.loop.run_in_executor(
                        None, lambda: playlist_ytdl.extract_info(query, download=False)
                    )
                else:
                    data = await self.bot.loop.run_in_executor(
                        None, lambda: ytdl.extract_info(query, download=False)
                    )
            except Exception as e:
                return await ctx.send(f"❌ Помилка пошуку: ```{e}```")

            if not data:
                return await ctx.send("❌ Нічого не знайдено.")

            # Збираємо список треків
            if 'entries' in data:
                entries = [e for e in data['entries'] if e]
                if data.get('extractor_key') == 'YoutubeSearch':
                    entries = entries[:1]
            else:
                entries = [data]

            if not entries:
                return await ctx.send("❌ Нічого не знайдено або плейлист порожній.")

            gid = ctx.guild.id
            queue = self.queues.setdefault(gid, [])

            for entry in entries:
                url = entry.get('url') or entry.get('webpage_url') or query
                if not str(url).startswith("http"):
                    continue
                queue.append({
                    'url': url,
                    'title': entry.get('title', 'Невідомий трек'),
                })

            if len(entries) > 1:
                await ctx.send(f'🎵 Додано **{len(entries)}** треків до черги!')
            elif ctx.voice_client.is_playing() or ctx.voice_client.is_paused():
                await ctx.send(f'🎵 Додано в чергу: **{entries[0].get("title", "?")}** (#{len(queue)})')

            # Якщо зараз нічого не грає — стартуємо
            if not ctx.voice_client.is_playing() and not ctx.voice_client.is_paused():
                await self.play_next(ctx)

    @commands.command(name="skip", aliases=["s", "пропустити"], help="Пропустити поточну пісню")
    async def skip(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()  # Викликає after → play_next
            await ctx.send("⏭️ Пропущено!")
        else:
            await ctx.send("Зараз нічого не грає.")

    @commands.command(name="pause", aliases=["пауза"], help="Поставити на паузу")
    async def pause(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            await ctx.send("⏸️ Пауза.")

    @commands.command(name="resume", aliases=["продовжити"], help="Продовжити відтворення")
    async def resume(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.send("▶️ Продовжено.")

    @commands.command(name="queue", aliases=["q", "черга"], help="Показати чергу")
    async def queue(self, ctx):
        gid = ctx.guild.id
        queue = self.queues.get(gid, [])
        if not queue:
            return await ctx.send("Черга порожня.")

        lines = [f"`{i+1}.` {s['title']}" for i, s in enumerate(queue[:20])]
        if len(queue) > 20:
            lines.append(f"\n*...і ще {len(queue) - 20} треків.*")

        embed = discord.Embed(title="🎵 Черга", description="\n".join(lines), color=discord.Color.blue())
        await ctx.send(embed=embed)

    @commands.command(name="history", aliases=["his", "історія"], help="Останні 20 пісень. Додати: !his 1,3")
    async def history_cmd(self, ctx, *, selection: str = ""):
        gid = ctx.guild.id
        hist = self.history.get(gid, [])

        if not hist:
            return await ctx.send("📜 Історія порожня.")

        # Вибрати конкретні пісні з історії → додати в чергу
        if selection:
            if not ctx.voice_client:
                if not await ctx.invoke(self.join):
                    return

            indices = []
            for part in selection.split(','):
                try:
                    idx = int(part.strip()) - 1
                    if 0 <= idx < len(hist):
                        indices.append(idx)
                except ValueError:
                    pass

            if not indices:
                return await ctx.send("❌ Невірний вибір. Приклад: `!his 1,3`")

            queue = self.queues.setdefault(gid, [])
            added = []
            reversed_hist = list(reversed(hist))
            for idx in indices:
                title, url = reversed_hist[idx]
                queue.append({'url': url, 'title': title})
                added.append(f"🎵 {title}")

            await ctx.send("Додано:\n" + "\n".join(added))

            if ctx.voice_client and not ctx.voice_client.is_playing() and not ctx.voice_client.is_paused():
                await self.play_next(ctx)
            return

        # Показати список
        lines = [f"`{i+1}.` {title}" for i, (title, _) in enumerate(reversed(hist))]
        embed = discord.Embed(
            title="📜 Останні пісні",
            description="\n".join(lines),
            color=discord.Color.purple()
        )
        embed.set_footer(text="Додати: !his 1 | Кілька: !his 1,3,5")
        await ctx.send(embed=embed)

    @commands.command(name="cq", aliases=["очерга"], help="Очистити чергу (поточний трек продовжить грати)")
    async def clear_queue(self, ctx):
        gid = ctx.guild.id
        if gid in self.queues and self.queues[gid]:
            count = len(self.queues[gid])
            self.queues[gid].clear()
            await ctx.send(f"🗑️ Чергу очищено! Видалено **{count}** треків.")
        else:
            await ctx.send("Черга вже порожня.")

    @commands.command(name="stop", aliases=["leave", "зупинити", "вийти"], help="Зупинити і вийти з каналу")
    async def stop(self, ctx):
        if not ctx.voice_client:
            return await ctx.send("Я не в голосовому каналі.")
        if ctx.guild.id in self.queues:
            self.queues[ctx.guild.id].clear()
        await ctx.voice_client.disconnect()
        await ctx.send("🛑 Зупинено, вийшов з каналу.")


async def setup(bot):
    await bot.add_cog(Music(bot))
