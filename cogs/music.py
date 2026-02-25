import discord
from discord.ext import commands
import yt_dlp
import asyncio
import time
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
    'format': 'bestaudio[acodec=opus][ext=webm]/bestaudio[acodec=opus]/bestaudio[acodec=vorbis]/bestaudio/best',
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
    # Обмеження на використання ресурсів: 1 потік, відключення агресивного реконекту, який викликає 100% CPU loop
    'before_options': '-nostdin -loglevel quiet -threads 1 -reconnect 1 -reconnect_at_eof 1 -reconnect_delay_max 5 -analyzeduration 0 -probesize 32768',
    'options': '-vn -threads 1',
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


import random as _random


def _fmt_time(seconds: int) -> str:
    """Форматує секунди у MM:SS або HH:MM:SS."""
    if seconds < 0:
        seconds = 0
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


# ─── Режими петлі ───────────────────────────────────────
LOOP_OFF = 0
LOOP_TRACK = 1
LOOP_QUEUE = 2
LOOP_LABELS = {LOOP_OFF: "Вимкнено", LOOP_TRACK: "🔂 Трек", LOOP_QUEUE: "🔁 Черга"}
LOOP_EMOJIS = {LOOP_OFF: "➡️", LOOP_TRACK: "🔂", LOOP_QUEUE: "🔁"}

# ─── Аудіо фільтри ──────────────────────────────────────
AUDIO_FILTERS = {
    'none':      {'label': 'Без фільтру',  'options': '-vn'},
    'bass':      {'label': '🔊 Bass Boost', 'options': '-vn -af bass=g=8,acompressor=threshold=0.5:ratio=9:attack=200:release=1000'},
    'nightcore': {'label': '🌙 Nightcore',  'options': '-vn -af asetrate=44100*1.25,atempo=1.0'},
    'slowed':    {'label': '🐢 Slowed',     'options': '-vn -af atempo=0.85'},
}


class PlayerView(discord.ui.View):
    """Інтерактивна панель керування музикою."""

    def __init__(self, cog, ctx, title: str):
        super().__init__(timeout=None)
        self.cog = cog
        self.ctx = ctx
        self.title = title
        self.message = None
        self.pause_resume.emoji = "⏸️"
        # Оновлюємо емодзі петлі
        gid = ctx.guild.id
        loop_mode = cog._loop_mode.get(gid, LOOP_OFF)
        self.loop_btn.emoji = LOOP_EMOJIS[loop_mode]

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.voice or not self.ctx.voice_client:
            await interaction.response.send_message("❌ Ви не в голосовому каналі!", ephemeral=True)
            return False
        if interaction.user.voice.channel != self.ctx.voice_client.channel:
            await interaction.response.send_message("❌ Ви в іншому голосовому каналі!", ephemeral=True)
            return False
        return True

    def build_embed(self) -> discord.Embed:
        vc = self.ctx.voice_client
        if vc and vc.is_paused():
            status = "⏸️ Пауза"
        elif vc and vc.is_playing():
            status = "▶️ Відтворення"
        else:
            status = "⏹️ Зупинено"

        gid = self.ctx.guild.id
        queue = self.cog.queues.get(gid, [])
        current = self.cog._current.get(gid, {})
        duration = current.get('duration', 0)
        volume = self.cog._volume.get(gid, 50)
        loop_mode = self.cog._loop_mode.get(gid, LOOP_OFF)
        audio_filter = self.cog._audio_filter.get(gid, 'none')

        embed = discord.Embed(
            title="🎶 Зараз грає",
            description=f"**{self.title}**",
            color=discord.Color.purple()
        )

        # Прогрес-бар
        pos = self.cog._get_position(gid)
        if duration > 0:
            pos = min(pos, duration)
            progress = pos / duration
            filled = int(progress * 15)
            bar = "▓" * filled + "░" * (15 - filled)
            embed.add_field(
                name=f"{_fmt_time(pos)} {bar} {_fmt_time(duration)}",
                value=status,
                inline=False
            )
        else:
            bar = "░" * 15
            embed.add_field(
                name=f"{_fmt_time(pos)} {bar} ?:??",
                value=status,
                inline=False
            )

        # Інфо-рядок
        info_parts = [f"🔊 {volume}%"]
        if loop_mode != LOOP_OFF:
            info_parts.append(LOOP_LABELS[loop_mode])
        if audio_filter != 'none':
            info_parts.append(AUDIO_FILTERS[audio_filter]['label'])
        embed.add_field(name=" │ ".join(info_parts), value=f"**{len(queue)}** у черзі", inline=False)

        if queue:
            embed.add_field(name="Наступна", value=queue[0]['title'], inline=False)

        embed.set_footer(text="⏪⏩ Перемотка │ 🔉� Гучність │ � Петля │ 🎧 Фільтри")
        return embed

    async def update_message(self, interaction: discord.Interaction = None):
        try:
            if interaction:
                await interaction.response.edit_message(embed=self.build_embed(), view=self)
            elif self.message:
                await self.message.edit(embed=self.build_embed(), view=self)
        except Exception as e:
            pass

    # ─── Ряд 1: Перемотка, Пауза, Вперед, Скіп, Шафл ───────

    @discord.ui.button(emoji="⏪", style=discord.ButtonStyle.secondary, row=0)
    async def rewind_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        gid = self.ctx.guild.id
        pos = self.cog._get_position(gid)
        await self.cog._seek_to(self.ctx, gid, max(0, pos - 10))
        await self.update_message(interaction)

    @discord.ui.button(emoji="⏸️", style=discord.ButtonStyle.primary, row=0)
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = self.ctx.voice_client
        if not vc:
            return
        gid = self.ctx.guild.id
        current = self.cog._current.get(gid, {})
        if vc.is_playing():
            vc.pause()
            current['paused_at'] = time.time()
            button.emoji = "▶️"
        elif vc.is_paused():
            paused_at = current.get('paused_at', 0)
            if paused_at:
                current['paused_total'] = current.get('paused_total', 0) + (time.time() - paused_at)
                current['paused_at'] = 0
            vc.resume()
            button.emoji = "⏸️"
        await self.update_message(interaction)

    @discord.ui.button(emoji="⏩", style=discord.ButtonStyle.secondary, row=0)
    async def forward_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        gid = self.ctx.guild.id
        pos = self.cog._get_position(gid)
        current = self.cog._current.get(gid, {})
        duration = current.get('duration', 0)
        if duration > 0 and pos + 10 >= duration:
            vc = self.ctx.voice_client
            if vc:
                vc.stop()
            await interaction.response.send_message("⏭️ Пропущено!", ephemeral=True, delete_after=3)
            return
        await self.cog._seek_to(self.ctx, gid, pos + 10)
        await self.update_message(interaction)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary, row=0)
    async def skip_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        gid = self.ctx.guild.id
        # При skip скидаємо loop track щоб не зациклитись
        if self.cog._loop_mode.get(gid, LOOP_OFF) == LOOP_TRACK:
            self.cog._loop_mode[gid] = LOOP_OFF
            self.loop_btn.emoji = LOOP_EMOJIS[LOOP_OFF]
        vc = self.ctx.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            # Видаляємо з БД перед скіпом
            gid = self.ctx.guild.id
            current = self.cog._current.get(gid, {})
            if current and current.get('song'):
                song = current['song']
                asyncio.run_coroutine_threadsafe(
                    self.cog.bot.db.execute(
                        'DELETE FROM music_queues WHERE user_id = ? AND guild_id = ? AND url = ?',
                        (song.get('requester_id'), gid, song['url'])
                    ), 
                    self.cog.bot.loop
                )
            vc.stop()
        await interaction.response.send_message("⏭️ Пропущено!", ephemeral=True, delete_after=3)

    @discord.ui.button(emoji="🔀", style=discord.ButtonStyle.secondary, row=0)
    async def shuffle_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        gid = self.ctx.guild.id
        queue = self.cog.queues.get(gid, [])
        if len(queue) > 1:
            _random.shuffle(queue)
            await interaction.response.send_message("🔀 Перемішано!", ephemeral=True, delete_after=3)
        else:
            await interaction.response.send_message("Черга порожня.", ephemeral=True, delete_after=3)

    # ─── Ряд 2: Гучність, Петля, Фільтри, Черга, Стоп ──────

    @discord.ui.button(emoji="🔉", style=discord.ButtonStyle.secondary, row=1)
    async def vol_down(self, interaction: discord.Interaction, button: discord.ui.Button):
        gid = self.ctx.guild.id
        vol = max(10, self.cog._volume.get(gid, 50) - 20)
        self.cog._volume[gid] = vol
        vc = self.ctx.voice_client
        if vc and vc.source:
            vc.source.volume = vol / 100
        await self.update_message(interaction)

    @discord.ui.button(emoji="🔊", style=discord.ButtonStyle.secondary, row=1)
    async def vol_up(self, interaction: discord.Interaction, button: discord.ui.Button):
        gid = self.ctx.guild.id
        vol = min(200, self.cog._volume.get(gid, 50) + 20)
        self.cog._volume[gid] = vol
        vc = self.ctx.voice_client
        if vc and vc.source:
            vc.source.volume = vol / 100
        await self.update_message(interaction)

    @discord.ui.button(emoji="➡️", style=discord.ButtonStyle.secondary, row=1)
    async def loop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        gid = self.ctx.guild.id
        current_mode = self.cog._loop_mode.get(gid, LOOP_OFF)
        new_mode = (current_mode + 1) % 3
        self.cog._loop_mode[gid] = new_mode
        button.emoji = LOOP_EMOJIS[new_mode]
        label = LOOP_LABELS[new_mode]
        await interaction.response.send_message(f"Петля: **{label}**", ephemeral=True, delete_after=3)
        try:
            await self.message.edit(embed=self.build_embed(), view=self)
        except Exception:
            pass

    @discord.ui.button(emoji="🎧", style=discord.ButtonStyle.secondary, row=1)
    async def filter_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        gid = self.ctx.guild.id
        current_filter = self.cog._audio_filter.get(gid, 'none')
        # Цикл: none → bass → nightcore → slowed → none
        filters_order = ['none', 'bass', 'nightcore', 'slowed']
        idx = filters_order.index(current_filter) if current_filter in filters_order else 0
        new_filter = filters_order[(idx + 1) % len(filters_order)]
        self.cog._audio_filter[gid] = new_filter
        label = AUDIO_FILTERS[new_filter]['label']
        await interaction.response.send_message(f"🎧 Фільтр: **{label}**", ephemeral=True, delete_after=3)
        # Перезапускаємо з новим фільтром
        pos = self.cog._get_position(gid)
        await self.cog._seek_to(self.ctx, gid, pos)
        try:
            await self.message.edit(embed=self.build_embed(), view=self)
        except Exception:
            pass

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.danger, row=1)
    async def stop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        gid = self.ctx.guild.id
        await self.cog._cleanup_panel(gid)
        if gid in self.cog.queues:
            self.cog.queues[gid].clear()
        vc = self.ctx.voice_client
        if vc:
            vc.stop()
            await vc.disconnect()
        self.stop()
        try:
            # Спробуємо відповісти, якщо повідомлення ще існує (хоча _cleanup_panel його видаляє)
            await interaction.response.edit_message(embed=discord.Embed(
                title="⏹️ Зупинено",
                description="Відтворення завершено.",
                color=discord.Color.dark_grey()
            ), view=None)
        except Exception:
            pass

    async def on_timeout(self):
        pass


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queues: dict[int, list[dict]] = {}
        self.history: dict[int, list[tuple]] = {}
        self._play_lock: dict[int, asyncio.Lock] = {}
        self._now_playing: dict[int, discord.Message] = {}
        self._views: dict[int, PlayerView] = {}
        self._progress_tasks: dict[int, asyncio.Task] = {}
        self._current: dict[int, dict] = {}
        self._stream_cache: dict[str, tuple] = {}
        self._prefetched: dict[int, tuple] = {}
        self._volume: dict[int, int] = {}         # {guild_id: 0-200}
        self._loop_mode: dict[int, int] = {}      # {guild_id: LOOP_OFF/TRACK/QUEUE}
        self._audio_filter: dict[int, str] = {}   # {guild_id: 'none'/'bass'/'nightcore'/'slowed'}
        self.CACHE_TTL = 1800

    def _lock(self, guild_id: int) -> asyncio.Lock:
        if guild_id not in self._play_lock:
            self._play_lock[guild_id] = asyncio.Lock()
        return self._play_lock[guild_id]

    async def _progress_loop(self, guild_id: int):
        """Оновлює прогрес-бар кожні 10 секунд та зберігає стан у БД."""
        while guild_id in self._progress_tasks:
            await asyncio.sleep(10)
            if guild_id in self._views:
                try:
                    view = self._views[guild_id]
                    await view.update_message(None)
                    
                    # Зберігаємо ПОТОЧНУ ПОЗИЦІЮ в БД для відновлення
                    pos = self._get_position(guild_id)
                    cur = self._current.get(guild_id, {})
                    if cur and cur.get('song'):
                        song = cur['song']
                        await self.bot.db.execute('''
                            UPDATE music_current_playback 
                            SET position = ? 
                            WHERE guild_id = ?
                        ''', (pos, guild_id))
                        await self.bot.db.commit()
                except Exception as e:
                    print(f"[Music] Progress loop error for {guild_id}: {e}")
                    break
            else:
                break

    def _start_progress(self, guild_id: int):
        """Запускає фонове оновлення прогресу."""
        self._stop_progress(guild_id)
        self._progress_tasks[guild_id] = self.bot.loop.create_task(self._progress_loop(guild_id))

    def _stop_progress(self, guild_id: int):
        """Зупиняє фонове оновлення прогресу."""
        task = self._progress_tasks.pop(guild_id, None)
        if task:
            task.cancel()

    async def _cleanup_panel(self, guild_id: int):
        """Централізовано видаляє панель та зупиняє ресурси."""
        self._stop_progress(guild_id)
        
        view = self._views.pop(guild_id, None)
        if view:
            view.stop()
            
        msg = self._now_playing.pop(guild_id, None)
        if msg:
            try:
                await msg.delete()
            except Exception:
                pass
                
        self._current.pop(guild_id, None)
        
        # Видаляємо стан відтворення з БД
        await self.bot.db.execute('DELETE FROM music_current_playback WHERE guild_id = ?', (guild_id,))
        await self.bot.db.commit()
        await self.bot.change_presence(activity=discord.Activity(
            type=discord.ActivityType.watching, name="на сервер"))

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Видаляє панель, якщо бота відключили від каналу."""
        if member.id != self.bot.user.id:
            return
        
        # Якщо бот був у каналі, а тепер ні (відключення)
        if before.channel and not after.channel:
            gid = before.channel.guild.id
            if gid in self._now_playing:
                await self._cleanup_panel(gid)
            if gid in self.queues:
                self.queues[gid].clear()

    def _get_position(self, guild_id: int) -> float:
        """Повертає поточну позицію відтворення в секундах."""
        current = self._current.get(guild_id, {})
        if not current:
            return 0
        offset = current.get('offset', 0)
        start = current.get('start_time', 0)
        paused_total = current.get('paused_total', 0)
        paused_at = current.get('paused_at', 0)
        now = time.time()
        # Якщо зараз на паузі — не рахуємо час з моменту паузи
        if paused_at:
            elapsed = paused_at - start - paused_total
        else:
            elapsed = now - start - paused_total
        return offset + elapsed

    async def _seek_to(self, ctx, guild_id: int, position: float):
        """Перемотує на вказану позицію (в секундах) перезапуском FFmpeg."""
        current = self._current.get(guild_id, {})
        stream_url = current.get('stream_url')
        if not stream_url or not ctx.voice_client:
            return

        # Зберігаємо after callback
        current['seeking'] = True

        # Зупиняємо поточне відтворення (without triggering play_next)
        ctx.voice_client.stop()
        await asyncio.sleep(0.1)  # чекаємо завершення

        # Перезапускаємо з нової позиції
        audio_filter = self._audio_filter.get(guild_id, 'none')
        filter_opts = AUDIO_FILTERS.get(audio_filter, AUDIO_FILTERS['none'])['options']
        seek_opts = {
            'before_options': f'-nostdin -loglevel quiet -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -ss {int(position)}',
            'options': filter_opts,
        }
        vol = self._volume.get(guild_id, 50) / 100
        source = discord.FFmpegPCMAudio(stream_url, **seek_opts)
        player = discord.PCMVolumeTransformer(source, volume=vol)

        def after(error):
            if error:
                print(f'[Music] Playback error: {error}')
            cur = self._current.get(guild_id, {})
            if cur.get('seeking'):
                cur['seeking'] = False
                return
            asyncio.run_coroutine_threadsafe(self.play_next(ctx), self.bot.loop)

        current['offset'] = position
        current['start_time'] = time.time()
        current['paused_total'] = 0
        current['paused_at'] = 0
        current['seeking'] = False

        ctx.voice_client.play(player, after=after)

    async def _extract_stream(self, url: str) -> tuple[str, str, int]:
        """Витягує стрім-URL, назву та тривалість. Повертає (stream_url, title, duration). Кешує результат на 30 хв."""
        # Перевіряємо кеш
        cached = self._stream_cache.get(url)
        if cached:
            stream_url, title, duration, ts = cached
            if time.time() - ts < self.CACHE_TTL:
                return stream_url, title, duration
            else:
                del self._stream_cache[url]

        data = await self.bot.loop.run_in_executor(
            None, lambda: ytdl.extract_info(url, download=False)
        )
        if not data:
            raise Exception("yt-dlp повернув порожній результат")
        if 'entries' in data:
            data = data['entries'][0]
        duration = int(data.get('duration', 0) or 0)
        stream_url = data['url']
        title = data.get('title', 'Невідомий трек')

        # Зберігаємо в кеш
        self._stream_cache[url] = (stream_url, title, duration, time.time())
        return stream_url, title, duration

    async def _prefetch_next(self, guild_id: int):
        """Попередньо завантажує stream URL наступного треку в черзі."""
        queue = self.queues.get(guild_id, [])
        if not queue:
            return
        next_url = queue[0].get('url')
        if not next_url:
            return
        try:
            stream_url, title, duration = await self._extract_stream(next_url)
            self._prefetched[guild_id] = (next_url, stream_url, title, duration)
        except Exception as e:
            print(f"[Music] Prefetch error: {e}")

    async def play_next(self, ctx):
        """Бере наступний трек з черги та програє. Якщо черга пуста — нічого не робить."""
        gid = ctx.guild.id

        async with self._lock(gid):
            if not ctx.voice_client or not ctx.voice_client.is_connected():
                return

            queue = self.queues.get(gid, [])
            loop_mode = self._loop_mode.get(gid, LOOP_OFF)
            current = self._current.get(gid, {})

            # Обробка петлі
            if loop_mode == LOOP_TRACK and current.get('song'):
                # Повторюємо той самий трек
                song = current['song']
            elif loop_mode == LOOP_QUEUE and current.get('song'):
                # Додаємо поточний трек в кінець черги, беремо наступний
                queue.append(current['song'])
                if not queue:
                    return
                song = queue.pop(0)
            else:
                if not queue:
                    # Черга пуста — видаляємо панель
                    await self._cleanup_panel(gid)
                    return
                song = queue.pop(0)

            # Перевіряємо чи є prefetch
            prefetched = self._prefetched.pop(gid, None)
            if prefetched and prefetched[0] == song['url']:
                stream_url, extracted_title, duration = prefetched[1], prefetched[2], prefetched[3]
            else:
                try:
                    stream_url, extracted_title, duration = await self._extract_stream(song['url'])
                except Exception as e:
                    await ctx.send(f"❌ Не вдалося відтворити **{song['title']}**, пропускаю.")
                    print(f"[Music] Extract error: {e}")
                    self.bot.loop.create_task(self.play_next(ctx))
                    return

            title = song['title'] if song['title'] != 'Невідомий трек' else extracted_title

            # Застосовуємо фільтр
            audio_filter = self._audio_filter.get(gid, 'none')
            filter_opts = AUDIO_FILTERS.get(audio_filter, AUDIO_FILTERS['none'])['options']
            play_opts = {
                'before_options': ffmpeg_opts['before_options'],
                'options': filter_opts,
            }
            vol = self._volume.get(gid, 50) / 100
            source = discord.FFmpegPCMAudio(stream_url, **play_opts)
            player = discord.PCMVolumeTransformer(source, volume=vol)

            # Зберігаємо інформацію
            self._current[gid] = {
                'stream_url': stream_url,
                'duration': duration,
                'start_time': time.time(),
                'offset': 0,
                'paused_total': 0,
                'paused_at': 0,
                'seeking': False,
                'song': song,
            }

            # Зберігаємо СТАН в БД для відновлення (на випадок крашу)
            # Примітка: channel_id беремо з поточного з'єднання
            channel_id = ctx.voice_client.channel.id
            await self.bot.db.execute('''
                INSERT INTO music_current_playback (guild_id, channel_id, url, title, position, requester_id)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                channel_id = excluded.channel_id,
                url = excluded.url,
                title = excluded.title,
                position = excluded.position,
                requester_id = excluded.requester_id
            ''', (gid, channel_id, song['url'], title, 0.0, song.get('requester_id')))
            await self.bot.db.commit()

            # Історія
            hist = self.history.setdefault(gid, [])
            hist.append((title, song['url']))
            if len(hist) > 20:
                hist.pop(0)

            def after(error):
                if error:
                    print(f'[Music] Playback error: {error}')
                
                # Видаляємо програний трек з БД
                asyncio.run_coroutine_threadsafe(
                    self.bot.db.execute(
                        'DELETE FROM music_queues WHERE user_id = ? AND guild_id = ? AND url = ?',
                        (song.get('requester_id'), gid, song['url'])
                    ),
                    self.bot.loop
                )
                
                cur = self._current.get(gid, {})
                if cur.get('seeking'):
                    cur['seeking'] = False
                    return
                asyncio.run_coroutine_threadsafe(self.play_next(ctx), self.bot.loop)

            ctx.voice_client.play(player, after=after)
            if hasattr(ctx.voice_client, 'encoder') and ctx.voice_client.encoder:
                ctx.voice_client.encoder.set_bitrate(256)

            # Оновлюємо статус бота
            await self.bot.change_presence(activity=discord.Activity(
                type=discord.ActivityType.listening, name=title[:128]))

            # Завжди видаляємо стару панель і створюємо нову
            existing_msg = self._now_playing.pop(gid, None)
            if existing_msg:
                try:
                    await existing_msg.delete()
                except Exception:
                    pass

            view = PlayerView(self, ctx, title)
            msg = await ctx.send(embed=view.build_embed(), view=view)
            view.message = msg
            self._views[gid] = view
            self._now_playing[gid] = msg

            self._start_progress(gid)
            self.bot.loop.create_task(self._prefetch_next(gid))

    # ─── Команди ────────────────────────────────────────────

    @commands.command(name="join", aliases=["зайти"], help="Приєднати бота до голосового каналу")
    async def join(self, ctx):
        try:
            await ctx.message.delete(delay=10)
        except Exception:
            pass

        if not ctx.author.voice:
            await ctx.send("❌ Ви не в голосовому каналі!", delete_after=10)
            return False
        channel = ctx.author.voice.channel
        if ctx.voice_client:
            await ctx.voice_client.move_to(channel)
        else:
            await channel.connect()
        return True

    @commands.command(name="play", aliases=["p", "грати"], help="Відтворити пісню: !play <посилання або назва>")
    async def play(self, ctx, *, query):
        try:
            await ctx.message.delete(delay=10)
        except Exception:
            pass

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
                
                title = entry.get('title', 'Невідомий трек')
                song_data = {
                    'url': url,
                    'title': title,
                    'requester_id': ctx.author.id
                }
                queue.append(song_data)
                
                # Зберігаємо в БД
                await self.bot.db.execute('''
                    INSERT INTO music_queues (user_id, guild_id, url, title, pos)
                    VALUES (?, ?, ?, ?, (SELECT COALESCE(MAX(pos), 0) + 1 FROM music_queues WHERE user_id = ? AND guild_id = ?))
                ''', (ctx.author.id, gid, str(url), title, ctx.author.id, gid))
            
            await self.bot.db.commit()

            if is_playlist:
                await ctx.send(f"🎵 Додано **{len(entries)}** треків до черги!", delete_after=10)
            elif not ctx.voice_client.is_playing() and not ctx.voice_client.is_paused():
                # Якщо нічого не грало — play_next запуститься сам (або ми його штовхаємо)
                pass
            else:
                await ctx.send(f"✅ Додано до черги: **{entries[0]['title']}**", delete_after=10)

            if not ctx.voice_client.is_playing() and not ctx.voice_client.is_paused():
                await self.play_next(ctx)

    @commands.command(name="skip", aliases=["s", "скіп", "пропустити"], help="Пропустити поточний трек")
    async def skip(self, ctx):
        try:
            await ctx.message.delete(delay=10)
        except Exception:
            pass

        if ctx.voice_client and (ctx.voice_client.is_playing() or ctx.voice_client.is_paused()):
            ctx.voice_client.stop()
            await ctx.send("⏭️ Пропущено!", delete_after=10)
        else:
            await ctx.send("❌ Зараз нічого не грає.", delete_after=10)

    @commands.command(name="pause", aliases=["пауза"], help="Поставити на паузу")
    async def pause(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            await ctx.send("⏸️ Пауза.", delete_after=10)

    @commands.command(name="resume", aliases=["продовжити"], help="Продовжити відтворення")
    async def resume(self, ctx):
        try:
            await ctx.message.delete(delay=10)
        except Exception:
            pass
        if ctx.voice_client and ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.send("▶️ Продовжено.", delete_after=10)

    @commands.command(name="queue", aliases=["q", "черга"], help="Показати чергу або перемістити треки: !q 2 5")
    async def queue_cmd(self, ctx, *, args: str = ""):
        try:
            await ctx.message.delete(delay=10)
        except Exception:
            pass
        gid = ctx.guild.id
        queue = self.queues.get(gid, [])
        if not queue:
            return await ctx.send("Черга порожня.", delete_after=10)

        # Якщо передані аргументи — переміщуємо треки
        if args:
            # Парсимо індекси (розділені пробілом або комою)
            indices = []
            import re
            parts = re.split(r'[, \s]+', args.strip())
            for p in parts:
                if p.isdigit():
                    idx = int(p) - 1
                    if 0 <= idx < len(queue):
                        indices.append(idx)
            
            if not indices:
                return await ctx.send("❌ Невірні номери треків. Приклад: `!q 2 5`", delete_after=10)

            # Видаляємо дублікати та сортуємо за спаданням, щоб не збилися індекси при видаленні
            indices = sorted(list(set(indices)), reverse=True)
            moved_songs = []
            for idx in indices:
                moved_songs.append(queue.pop(idx))
            
            # Вставляємо в початок (у зворотному порядку, щоб зберігся порядок вибору)
            for song in moved_songs:
                queue.insert(0, song)
            
            titles = ", ".join([f"**{s['title']}**" for s in reversed(moved_songs)])
            return await ctx.send(f"✅ Переміщено на початок: {titles}", delete_after=15)

        # Якщо аргументів немає — показуємо список
        lines = [f"`{i+1}.` {s['title']}" for i, s in enumerate(queue[:20])]
        if len(queue) > 20:
            lines.append(f"\n*...і ще {len(queue) - 20} треків.*")

        embed = discord.Embed(title="🎵 Черга", description="\n".join(lines), color=discord.Color.blue())
        embed.set_footer(text="Порада: напишіть !q 2 5 щоб перемістити ці треки на початок")
        await ctx.send(embed=embed, delete_after=40)

    @commands.command(name="history", aliases=["his", "історія"], help="Останні 20 пісень. Додати: !his 1,3")
    async def history_cmd(self, ctx, *, selection: str = ""):
        try:
            await ctx.message.delete(delay=10)
        except Exception:
            pass
        gid = ctx.guild.id
        hist = self.history.get(gid, [])

        if not hist:
            return await ctx.send("📜 Історія порожня.", delete_after=10)

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

            await ctx.send("Додано:\n" + "\n".join(added), delete_after=15)

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
        await ctx.send(embed=embed, delete_after=30)

    @commands.command(name="cq", aliases=["очерга"], help="Очистити чергу (поточний трек продовжить грати)")
    async def clear_queue(self, ctx):
        try:
            await ctx.message.delete(delay=10)
        except Exception:
            pass

        gid = ctx.guild.id
        if gid in self.queues and self.queues[gid]:
            count = len(self.queues[gid])
            self.queues[gid].clear()
            
            # Також очищаємо БД
            await self.bot.db.execute('DELETE FROM music_queues WHERE guild_id = ?', (gid,))
            await self.bot.db.commit()
            
            await ctx.send(f"🗑️ Чергу очищено! Видалено **{count}** треків.", delete_after=10)
        else:
            await ctx.send("Черга вже порожня.", delete_after=10)

    @commands.command(name="loadqueue", aliases=["lq", "завантажити"], help="Відновити вашу збережену чергу")
    async def load_queue(self, ctx):
        try:
            await ctx.message.delete(delay=10)
        except Exception:
            pass

        if not ctx.voice_client:
            if not await ctx.invoke(self.join):
                return

        gid = ctx.guild.id
        uid = ctx.author.id
        
        async with self.bot.db.execute('SELECT url, title FROM music_queues WHERE user_id = ? AND guild_id = ? ORDER BY pos ASC', (uid, gid)) as cursor:
            rows = await cursor.fetchall()
            
        if not rows:
            return await ctx.send("❌ У вас немає збережених пісень для цього сервера.", delete_after=10)
            
        queue = self.queues.setdefault(gid, [])
        added_count = 0
        
        for url, title in rows:
            # Перевіряємо чи вже є в черзі
            if any(s['url'] == url for s in queue):
                continue
                
            queue.append({
                'url': url,
                'title': title,
                'requester_id': uid
            })
            added_count += 1
            
        if added_count > 0:
            await ctx.send(f"✅ Відновлено **{added_count}** треків з вашої сесії!", delete_after=10)
            if not ctx.voice_client.is_playing() and not ctx.voice_client.is_paused():
                await self.play_next(ctx)
        else:
            await ctx.send("ℹ️ Всі ваші треки вже в сьогоднішній черзі.", delete_after=10)

    @commands.command(name="playcontinue", aliases=["playc", "pc", "відновити"], help="Відновити останню сесію (канал, пісню та час)")
    async def play_continue(self, ctx):
        try:
            await ctx.message.delete(delay=10)
        except Exception:
            pass

        gid = ctx.guild.id
        
        # 1. Отримуємо збережений стан
        async with self.bot.db.execute('SELECT channel_id, url, title, position, requester_id FROM music_current_playback WHERE guild_id = ?', (gid,)) as cursor:
            playback = await cursor.fetchone()
            
        if not playback:
            return await ctx.send("❌ Немає збереженої активної сесії для цього сервера.", delete_after=10)
            
        ch_id, url, title, pos, req_id = playback
        
        # 2. Заходимо в канал
        channel = self.bot.get_channel(ch_id)
        if not channel:
            return await ctx.send("❌ Не вдалося знайти попередній голосовий канал.", delete_after=10)
            
        if not ctx.voice_client:
            await channel.connect()
        elif ctx.voice_client.channel.id != ch_id:
            await ctx.voice_client.move_to(channel)

        # 3. Відновлюємо чергу
        async with self.bot.db.execute('SELECT url, title, user_id FROM music_queues WHERE guild_id = ? ORDER BY pos ASC', (gid,)) as cursor:
            rows = await cursor.fetchall()
            
        queue = self.queues.setdefault(gid, [])
        queue.clear() # Очищаємо поточну, щоб відновити саме ту, що була
        for r_url, r_title, r_uid in rows:
            queue.append({'url': r_url, 'title': r_title, 'requester_id': r_uid})

        # 4. Запускаємо відтворення з позиції
        try:
            stream_url, ext_title, duration = await self._extract_stream(url)
            
            # Налаштовуємо поточний стан
            self._current[gid] = {
                'stream_url': stream_url,
                'duration': duration,
                'start_time': time.time(),
                'offset': pos,
                'paused_total': 0,
                'paused_at': 0,
                'seeking': False,
                'song': {'url': url, 'title': title, 'requester_id': req_id},
            }
            
            # Використовуємо внутрішній механізм перемотування для старту з потрібної секунди
            await self._seek_to(ctx, gid, pos)
            
            await ctx.send(f"▶️ Відновлено сесію: **{title}** з `{int(pos)}с`. У черзі: **{len(queue)}**.", delete_after=15)
            
            # Запускаємо панель
            if gid not in self._now_playing:
                view = PlayerView(self, ctx, title)
                msg = await ctx.send(embed=view.build_embed(), view=view)
                view.message = msg
                self._views[gid] = view
                self._now_playing[gid] = msg
                self._start_progress(gid)

        except Exception as e:
            await ctx.send(f"❌ Помилка відновлення: {e}")
            print(f"[Music] Continue error: {e}")

    @commands.command(name="volume", aliases=["vol", "гучність"], help="Змінити гучність (10-200)")
    async def volume_cmd(self, ctx, level: int = None):
        try:
            await ctx.message.delete(delay=10)
        except Exception:
            pass

        gid = ctx.guild.id
        if level is None:
            vol = self._volume.get(gid, 50)
            return await ctx.send(f"🔊 Поточна гучність: **{vol}%**", delete_after=10)
        level = max(10, min(200, level))
        self._volume[gid] = level
        vc = ctx.voice_client
        if vc and vc.source:
            vc.source.volume = level / 100
        await ctx.send(f"🔊 Гучність встановлено: **{level}%**", delete_after=10)

    @commands.command(name="stop", aliases=["leave", "зупинити", "вийти"], help="Зупинити і вийти з каналу")
    async def stop(self, ctx):
        try:
            await ctx.message.delete(delay=10)
        except Exception:
            pass

        if not ctx.voice_client:
            return await ctx.send("Я не в голосовому каналі.", delete_after=10)
        
        gid = ctx.guild.id
        await self._cleanup_panel(gid)
        if gid in self.queues:
            self.queues[gid].clear()
        
        await ctx.voice_client.disconnect()
        await ctx.send("🛑 Зупинено, вийшов з каналу.", delete_after=10)


async def setup(bot):
    await bot.add_cog(Music(bot))
