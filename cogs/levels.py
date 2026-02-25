import discord
from discord.ext import commands, tasks
import random
import time

class Levels(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cooldowns: dict[int, float] = {}
        self.COOLDOWN_TIME = 5 # Кулдаун між нарахуваннями досвіду (в секундах)
        
        # In-memory cache для зменшення кількості запитів до БД
        self._xp_cache: dict[tuple[int, int], int] = {}    # {(user_id, guild_id): xp}
        self._dirty_users: set[tuple[int, int]] = set()  # {(user_id, guild_id)}
        
        # Запускаємо фоновий процес збереження
        self.save_xp_task.start()

    def cog_unload(self):
        self.save_xp_task.cancel()

    @tasks.loop(minutes=1.0)
    async def save_xp_task(self):
        """Зберігає змінений досвід у БД раз на хвилину батчем."""
        if not self._dirty_users:
            return
            
        users_to_save = list(self._dirty_users)
        self._dirty_users.clear()
        
        data = []
        for uid, gid in users_to_save:
            xp = self._xp_cache.get((uid, gid), 0)
            level = self.calculate_level(xp)
            data.append((uid, gid, xp, level))
            
        if data:
            try:
                # Використовуємо UPSERT (оновлюємо якщо запис вже є)
                await self.bot.db.executemany('''
                    INSERT INTO users (user_id, guild_id, xp, level)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id, guild_id) DO UPDATE SET
                    xp=excluded.xp, level=excluded.level
                ''', data)
                await self.bot.db.commit()
            except Exception as e:
                print(f"[Levels] Помилка пакетного збереження XP: {e}")
                # Повертаємо користувачів назад у чергу для збереження наступного разу
                for item in users_to_save:
                    self._dirty_users.add(item)

    @save_xp_task.before_loop
    async def before_save_xp(self):
        await self.bot.wait_until_ready()

    async def get_user_xp(self, user_id: int, guild_id: int) -> int:
        """Отримує XP з кешу, або з БД якщо в кеші немає."""
        key = (user_id, guild_id)
        if key in self._xp_cache:
            return self._xp_cache[key]
            
        async with self.bot.db.execute('SELECT xp FROM users WHERE user_id = ? AND guild_id = ?', (user_id, guild_id)) as cursor:
            result = await cursor.fetchone()
            
        xp = int(result[0]) if result else 0
        self._xp_cache[key] = xp
        return xp

    def calculate_level(self, xp):
        """Проста формула: Кожен рівень вимагає все більше XP (наприклад: Рівень 1 = 100 XP, Рівень 2 = ~282 XP)."""
        return int((xp / 100) ** (1/1.5))
        
    def calculate_xp_for_level(self, level):
        """Повертає необхідну кількість XP для певного рівня."""
        return int(100 * (level ** 1.5))

    async def add_xp(self, user_id: int, guild_id: int, xp_to_add: int, channel=None):
        """Програмне додавання XP (наприклад, за голос або івенти)."""
        current_xp = await self.get_user_xp(user_id, guild_id)
        current_level = self.calculate_level(current_xp)
        
        new_xp = current_xp + xp_to_add
        new_level = self.calculate_level(new_xp)
        
        self._xp_cache[(user_id, guild_id)] = new_xp
        self._dirty_users.add((user_id, guild_id))
        
        if new_level > current_level and channel:
            member = channel.guild.get_member(user_id)
            if member:
                await channel.send(f"🎉 Вітаємо, {member.mention}! Твоя активність підняла тебе до **{new_level} рівня**!")
        
        # Перевірка досягнень при додаванні XP
        await self.check_achievements(user_id, guild_id, new_xp, channel)
        return new_level > current_level

    async def check_achievements(self, user_id, guild_id, xp, channel=None):
        """Перевіряє та видає досягнення на основі XP та інших метрик."""
        # Список досягнень за XP
        thresholds = [
            (1000, "novice", "🐣 Новачок"),
            (10000, "active", "🔥 Активіст"),
            (50000, "expert", "🎓 Експерт"),
            (200000, "legend", "👑 Легенда")
        ]
        
        for threshold, ach_id, name in thresholds:
            if xp >= threshold:
                # Перевіряємо чи вже є таке досягнення
                async with self.bot.db.execute(
                    'SELECT 1 FROM achievements WHERE user_id = ? AND guild_id = ? AND achievement_id = ?',
                    (user_id, guild_id, ach_id)
                ) as cursor:
                    if not await cursor.fetchone():
                        await self.bot.db.execute(
                            'INSERT INTO achievements (user_id, guild_id, achievement_id) VALUES (?, ?, ?)',
                            (user_id, guild_id, ach_id)
                        )
                        await self.bot.db.commit()
                        if channel:
                            member = channel.guild.get_member(user_id)
                            embed = discord.Embed(
                                title="🏆 Нове досягнення!",
                                description=f"{member.mention} отримав медаль: **{name}**",
                                color=discord.Color.gold()
                            )
                            await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message):
        # Ігноруємо ботів і приватні повідомлення
        if message.author.bot or not message.guild:
            return
            
        # Ігноруємо команди, щоб не фармили XP командами (окрім AI)
        if message.content.startswith(self.bot.command_prefix):
            return

        user_id = message.author.id
        guild_id = message.guild.id
        current_time = time.time()
        
        # Перевіряємо кулдаун (Анти-фарм)
        last_msg_time = self.cooldowns.get(user_id, 0)
        if current_time - last_msg_time < self.COOLDOWN_TIME:
            return
            
        self.cooldowns[user_id] = current_time
        
        # Отримуємо поточний досвід
        current_xp = await self.get_user_xp(user_id, guild_id)
        current_level = self.calculate_level(current_xp)
        
        # Додаємо випадкову кількість XP
        xp_to_add = random.randint(15, 25)
        await self.add_xp(user_id, guild_id, xp_to_add, message.channel)

    @commands.command(name="rank", aliases=["рівень", "ранг"], help="Дізнатись свій або чужий рівень")
    async def rank(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        uid = member.id
        gid = ctx.guild.id
        
        # Спочатку перевіряємо чи є незбережений досвід у кеші
        xp = await self.get_user_xp(uid, gid)
            
        if xp == 0:
            await ctx.send(f"У {member.display_name} ще немає досвіду!")
            return
            
        level = self.calculate_level(xp)
        next_level_xp = self.calculate_xp_for_level(level + 1)
        current_level_xp = self.calculate_xp_for_level(level)
        
        # Обчислюємо прогрес для бару
        xp_in_level = xp - current_level_xp
        needed_for_next = next_level_xp - current_level_xp
        progress = max(0.0, min(1.0, xp_in_level / needed_for_next))
        
        embed = discord.Embed(
            title=f"✨ Картка активності: {member.display_name}", 
            color=discord.Color.from_rgb(255, 215, 0) # Золотий
        )
        if member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)
        
        # 1. Секція Рівня
        embed.add_field(
            name="📊 Рівень та Досвід", 
            value=f"**Рівень:** `{level}`\n**XP:** `{xp:,} / {next_level_xp:,}`", 
            inline=True
        )
        
        # 2. Секція Досягнень
        async with self.bot.db.execute('SELECT achievement_id FROM achievements WHERE user_id = ? AND guild_id = ?', (uid, gid)) as cursor:
            achs = await cursor.fetchall()
        
        if achs:
            ach_map = {"novice": "🐣", "active": "🔥", "expert": "🎓", "legend": "👑"}
            icons = " ".join([ach_map.get(a[0], "🏅") for a in achs])
            embed.add_field(name="🏆 Медалі", value=icons, inline=True)
        else:
            embed.add_field(name="🏆 Медалі", value="*Шлях тільки починається*", inline=True)

        # 3. Секція Активності (Текст + Голос)
        activity_stats = ""
        try:
            stats_cog = self.bot.get_cog("Stats")
            if stats_cog:
                async with self.bot.db.execute('SELECT show_voice, show_text, show_favorite_channel FROM user_privacy WHERE user_id = ? AND guild_id = ?', (uid, gid)) as cursor:
                    priv_row = await cursor.fetchone()
                show_voice, show_text, show_fav = (bool(priv_row[0]), bool(priv_row[1]), bool(priv_row[2])) if priv_row else (True, True, True)

                if show_text:
                    words = await stats_cog.get_text_words(uid, gid, "words_total")
                    words += stats_cog._text_cache.get((uid, gid), 0)
                    activity_stats += f"✍️ **Слів:** `{words:,}`\n"
                
                if show_voice:
                    v_sec = await stats_cog.get_total_voice_time(uid, gid)
                    sess = stats_cog.voice_sessions.get((uid, gid))
                    if sess:
                        import datetime
                        v_sec += int((datetime.datetime.now() - sess).total_seconds())
                    
                    time_str = await stats_cog.format_time(v_sec)
                    activity_stats += f"🎙️ **Голос:** `{time_str}`"
                    
                    if show_fav:
                        async with self.bot.db.execute('SELECT channel_id FROM voice_stats WHERE user_id = ? AND guild_id = ? ORDER BY total_time DESC LIMIT 1', (uid, gid)) as cursor:
                            fav_row = await cursor.fetchone()
                        if fav_row:
                            fav_ch = ctx.guild.get_channel(fav_row[0])
                            if fav_ch:
                                activity_stats += f" \n📍 *{fav_ch.name}*"

        except Exception as e:
            print(f"[Levels rank] Error: {e}")

        if activity_stats:
            embed.add_field(name="⚡ Активність", value=activity_stats, inline=True)

        # Прогрес-бар
        filled = int(progress * 12)
        bar = "▰" * filled + "▱" * (12 - filled)
        percent = int(progress * 100)
        embed.add_field(name=f"🚀 Прогрес до {level+1} рівня — {percent}%", value=f"`{bar}`", inline=False)
        
        embed.set_footer(text=f"ID: {uid} • Сьогодні ви чудові!")
        await ctx.send(embed=embed)

    @commands.command(name="top", aliases=["leaderboard", "лідери"], help="Список найактивніших учасників сервера")
    async def top(self, ctx):
        async with self.bot.db.execute('SELECT user_id, xp, level FROM users WHERE guild_id = ? ORDER BY xp DESC LIMIT 10', (ctx.guild.id,)) as cursor:
            top_users = await cursor.fetchall()
            
        if not top_users:
            await ctx.send("Тут ще ніхто нічого не писав. Будьте першим!")
            return
            
        embed = discord.Embed(title="🏆 Топ найактивніших учасників", color=discord.Color.gold())
        
        description = ""
        for index, (user_id, xp, level) in enumerate(top_users, start=1):
            member = ctx.guild.get_member(user_id)
            name = member.display_name if member else f"Невідомий користувач ({user_id})"
            
            medal = "🥇" if index == 1 else "🥈" if index == 2 else "🥉" if index == 3 else f"{index}."
            description += f"{medal} **{name}** — Рівень: {level} | {xp} XP\n"
            
        embed.description = description
        await ctx.send(embed=embed)

    @commands.command(name="compare", aliases=["порівняти"], help="Порівняти свій рівень з іншим учасником")
    async def compare(self, ctx, member: discord.Member):
        if member == ctx.author:
            return await ctx.send("Ви не можете порівнювати себе з самим собою!")
            
        xp1 = await self.get_user_xp(ctx.author.id, ctx.guild.id)
        xp2 = await self.get_user_xp(member.id, ctx.guild.id)
        
        level1 = self.calculate_level(xp1)
        level2 = self.calculate_level(xp2)
        
        embed = discord.Embed(title="📊 Порівняння учасників", color=discord.Color.blue())
        
        val1 = f"Рівень: **{level1}**\nXP: **{xp1}**"
        val2 = f"Рівень: **{level2}**\nXP: **{xp2}**"
        
        embed.add_field(name=ctx.author.display_name, value=val1, inline=True)
        embed.add_field(name="VS", value="⚡", inline=True)
        embed.add_field(name=member.display_name, value=val2, inline=True)
        
        diff = abs(xp1 - xp2)
        leader = ctx.author if xp1 > xp2 else member
        embed.set_footer(text=f"{leader.display_name} попереду на {diff} XP")
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Levels(bot))
