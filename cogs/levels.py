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
        new_xp = current_xp + xp_to_add
        new_level = self.calculate_level(new_xp)
        
        # Оновлюємо кеш та позначаємо що треба зберегти в БД
        self._xp_cache[(user_id, guild_id)] = new_xp
        self._dirty_users.add((user_id, guild_id))
        
        # Відправляємо повідомлення про новий рівень одразу
        if new_level > current_level:
            await message.channel.send(f"🎉 Вітаємо, {message.author.mention}! Ти досяг **{new_level} рівня**!")

    @commands.command(name="rank", aliases=["рівень", "ранг"], help="Дізнатись свій або чужий рівень")
    async def rank(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        
        # Спочатку перевіряємо чи є незбережений досвід у кеші
        xp = await self.get_user_xp(member.id, ctx.guild.id)
            
        if xp == 0:
            await ctx.send(f"У {member.display_name} ще немає досвіду!")
            return
            
        level = self.calculate_level(xp)
        next_level_xp = self.calculate_xp_for_level(level + 1)
        
        embed = discord.Embed(title=f"Статистика {member.display_name}", color=discord.Color.blue())
        if member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)
        
        embed.add_field(name="Рівень", value=f"**{level}**", inline=True)
        embed.add_field(name="Досвід", value=f"**{xp} / {next_level_xp} XP**", inline=True)
        
        # Простий прогрес-бар
        progress = xp / next_level_xp
        filled = int(progress * 10)
        bar = "🟩" * filled + "⬛" * (10 - filled)
        embed.add_field(name="Прогрес до наступного рівня", value=bar, inline=False)
        
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

async def setup(bot):
    await bot.add_cog(Levels(bot))
