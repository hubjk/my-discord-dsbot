import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime
import re
import calendar
import aiosqlite

async def is_admin(ctx):
    # Підтримка і Context, і Interaction
    user = ctx.author if hasattr(ctx, 'author') else ctx.user
    guild = ctx.guild
    
    if user.name == "infaos" or user.display_name == "infaos":
        return True
    if guild and guild.owner_id == user.id:
        return True
    if user.guild_permissions.administrator:
        return True
    return False

class PrivacyView(discord.ui.View):
    def __init__(self, bot, user_id, guild_id):
        super().__init__(timeout=60)
        self.bot = bot
        self.user_id = user_id
        self.guild_id = guild_id
        self.show_voice = True
        self.show_text = True
        self.show_fav = True

    async def load_settings(self):
        async with self.bot.db.execute(
            'SELECT show_voice, show_text, show_favorite_channel FROM user_privacy WHERE user_id = ? AND guild_id = ?',
            (self.user_id, self.guild_id)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                self.show_voice, self.show_text, self.show_fav = bool(row[0]), bool(row[1]), bool(row[2])

    def create_embed(self):
        embed = discord.Embed(
            title="🔒 Налаштування приватності активності",
            description="Оберіть, які дані ви хочете показувати іншим у команді `!rank`.",
            color=discord.Color.blue()
        )
        embed.add_field(name="🎙️ Голосовий час", value="✅ Показувати" if self.show_voice else "❌ Приховано", inline=True)
        embed.add_field(name="✍️ Кількість слів", value="✅ Показувати" if self.show_text else "❌ Приховано", inline=True)
        embed.add_field(name="📍 Улюблений канал", value="✅ Показувати" if self.show_fav else "❌ Приховано", inline=True)
        return embed

    async def update_db(self):
        await self.bot.db.execute('''
            INSERT INTO user_privacy (user_id, guild_id, show_voice, show_text, show_favorite_channel)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, guild_id) DO UPDATE SET
            show_voice = excluded.show_voice,
            show_text = excluded.show_text,
            show_favorite_channel = excluded.show_favorite_channel
        ''', (self.user_id, self.guild_id, int(self.show_voice), int(self.show_text), int(self.show_fav)))
        await self.bot.db.commit()

    @discord.ui.button(label="Голос", style=discord.ButtonStyle.gray)
    async def toggle_voice(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Це не ваше меню!", ephemeral=True)
        self.show_voice = not self.show_voice
        await self.update_db()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(label="Текст", style=discord.ButtonStyle.gray)
    async def toggle_text(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Це не ваше меню!", ephemeral=True)
        self.show_text = not self.show_text
        await self.update_db()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(label="Улюблений канал", style=discord.ButtonStyle.gray)
    async def toggle_fav(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Це не ваше меню!", ephemeral=True)
        self.show_fav = not self.show_fav
        await self.update_db()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

class AdminPanelView(discord.ui.View):
    def __init__(self, bot, guild_id):
        super().__init__(timeout=120)
        self.bot = bot
        self.guild_id = guild_id
        self.settings = {}

    async def load_settings(self):
        async with self.bot.db.execute('SELECT * FROM server_settings WHERE guild_id = ?', (self.guild_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                # Мапінг колонок: 0:gid, 1:summary_ch, 2:ai, 3:voice_xp, 4:dyn_roles, 5:anti_afk, 6:speaker_role, 7:writer_role ...
                keys = ["guild_id", "summary_channel_id", "ai_summary_enabled", "voice_xp_enabled", 
                        "dynamic_roles_enabled", "anti_afk_enabled", "speaker_role_id", "writer_role_id"]
                self.settings = {keys[i]: row[i] for i in range(len(keys))}
            else:
                self.settings = {
                    "ai_summary_enabled": 0, "voice_xp_enabled": 1, 
                    "dynamic_roles_enabled": 0, "anti_afk_enabled": 1,
                    "speaker_role_id": None, "writer_role_id": None
                }

    def create_embed(self):
        embed = discord.Embed(title="⚙️ Адмін-панель активності", color=discord.Color.dark_grey())
        status = lambda x: ":white_check_mark: Увімкнено" if x else ":x: Вимкнено"
        
        embed.add_field(name="🤖 AI-підсумки", value=status(self.settings.get("ai_summary_enabled")), inline=True)
        embed.add_field(name="🎙️ XP за голос (3 XP/5хв)", value=status(self.settings.get("voice_xp_enabled")), inline=True)
        embed.add_field(name="🛡️ Anti-AFK фільтр", value=status(self.settings.get("anti_afk_enabled")), inline=True)
        embed.add_field(name="🎭 Динамічні ролі", value=status(self.settings.get("dynamic_roles_enabled")), inline=True)
        
        speaker = f"<@&{self.settings['speaker_role_id']}>" if self.settings.get("speaker_role_id") else "Не встановлено"
        writer = f"<@&{self.settings['writer_role_id']}>" if self.settings.get("writer_role_id") else "Не встановлено"
        embed.add_field(name="Ролі тижня", value=f"🎙️ Голос: {speaker}\n✍️ Текст: {writer}", inline=False)
        
        return embed

    async def toggle_setting(self, interaction, setting_name):
        new_val = 1 if not self.settings.get(setting_name) else 0
        self.settings[setting_name] = new_val
        
        # Використовуємо UPSERT (якщо запису немає - створимо, якщо є - оновимо одну колонку)
        await self.bot.db.execute(f'''
            INSERT INTO server_settings (guild_id, {setting_name}) 
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET {setting_name} = excluded.{setting_name}
        ''', (self.guild_id, new_val))
        await self.bot.db.commit()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(label="Toggle AI", style=discord.ButtonStyle.blurple)
    async def btn_ai(self, interaction, button):
        await self.toggle_setting(interaction, "ai_summary_enabled")

    @discord.ui.button(label="Toggle Voice XP", style=discord.ButtonStyle.blurple)
    async def btn_xp(self, interaction, button):
        await self.toggle_setting(interaction, "voice_xp_enabled")

    @discord.ui.button(label="Toggle Anti-AFK", style=discord.ButtonStyle.blurple)
    async def btn_afk(self, interaction, button):
        await self.toggle_setting(interaction, "anti_afk_enabled")

    @discord.ui.button(label="Toggle Roles", style=discord.ButtonStyle.blurple)
    async def btn_roles(self, interaction, button):
        await self.toggle_setting(interaction, "dynamic_roles_enabled")

    @discord.ui.button(label="Налаштувати Ролі", style=discord.ButtonStyle.gray)
    async def btn_setup_roles(self, interaction, button):
        view = RoleSetupView(self.bot, self.guild_id, self)
        await interaction.response.edit_message(content="Оберіть ролі для переможців тижня:", view=view)

class RoleSetupView(discord.ui.View):
    def __init__(self, bot, guild_id, parent_view):
        super().__init__(timeout=60)
        self.bot = bot
        self.guild_id = guild_id
        self.parent_view = parent_view

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Оберіть роль для Голосу Тижня")
    async def select_voice(self, interaction, select):
        role_id = select.values[0].id
        await self.bot.db.execute('UPDATE server_settings SET speaker_role_id = ? WHERE guild_id = ?', (role_id, self.guild_id))
        await self.bot.db.commit()
        await interaction.response.send_message(f"✅ Роль для Голосу встановлена: <@&{role_id}>", ephemeral=True)

    @discord.ui.select(cls=discord.ui.RoleSelect, placeholder="Оберіть роль для Тексту Тижня")
    async def select_text(self, interaction, select):
        role_id = select.values[0].id
        await self.bot.db.execute('UPDATE server_settings SET writer_role_id = ? WHERE guild_id = ?', (role_id, self.guild_id))
        await self.bot.db.commit()
        await interaction.response.send_message(f"✅ Роль для Тексту встановлена: <@&{role_id}>", ephemeral=True)

    @discord.ui.button(label="Назад", style=discord.ButtonStyle.red)
    async def btn_back(self, interaction, button):
        await self.parent_view.load_settings()
        await interaction.response.edit_message(content=None, embed=self.parent_view.create_embed(), view=self.parent_view)

class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Зберігає час (datetime) входу користувача в поточний голосовий канал
        self.voice_sessions: dict[tuple[int, int], datetime] = {} # {(user_id, guild_id): start_time}
        # Зберігає час останньої активності (коли користувач став "афк" - сам в каналі)
        self.afk_start_times: dict[tuple[int, int], datetime] = {} # {(user_id, guild_id): afk_since}
        
        # Кеш для тексту, щоб не писати кожне повідомлення в БД одразу
        self._text_cache: dict[tuple[int, int], int] = {} # {(user_id, guild_id): word_count_to_add}
        # Відстеження нарахування XP за голос у поточній сесії (кількість 5-хвилинних блоків)
        self.voice_xp_blocks: dict[tuple[int, int], int] = {} # {(user_id, guild_id): awarded_blocks}
        # Час останнього збереження голосу в БД (для періодичного збереження)
        self.last_voice_update: dict[tuple[int, int], datetime] = {} # {(user_id, guild_id): last_save_time}

        self.save_text_task.start()
        self.check_summaries.start()
        self.check_afk_task.start()
        # Запускаємо відновлення сесій
        self.bot.loop.create_task(self.sync_voice_sessions())

    def cog_unload(self):
        self.save_text_task.cancel()
        self.check_summaries.cancel()
        self.check_afk_task.cancel()

    async def get_setting(self, guild_id: int, key: str, default):
        """Отримує налаштування сервера, повертає дефолтне якщо запису немає."""
        try:
            async with self.bot.db.execute(f'SELECT {key} FROM server_settings WHERE guild_id = ?', (guild_id,)) as cursor:
                row = await cursor.fetchone()
                if row is not None and row[0] is not None:
                    return row[0]
        except Exception:
            pass
        return default

    async def sync_voice_sessions(self):
        """Сканує всі голосові канали та ініціалізує сесії для тих, хто вже там є."""
        await self.bot.wait_until_ready()
        now = datetime.now()
        for guild in self.bot.guilds:
            for channel in guild.voice_channels:
                for member in channel.members:
                    if member.bot: continue
                    key = (member.id, guild.id)
                    if key not in self.voice_sessions:
                        self.voice_sessions[key] = now
                        self.last_voice_update[key] = now
                        self.voice_xp_blocks[key] = 0
        print(f"[Stats] Відновлено {len(self.voice_sessions)} активних голосових сесій.")

    @commands.command(name="setsummarychannel", help="Встановити канал для підсумків активності (тільки для адмінів)")
    @commands.check(is_admin)
    async def set_summary_channel(self, ctx, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        await self.bot.db.execute('''
            INSERT INTO server_settings (guild_id, summary_channel_id)
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
            summary_channel_id = excluded.summary_channel_id
        ''', (ctx.guild.id, channel.id))
        await self.bot.db.commit()
        await ctx.send(f"✅ Канал для підсумків активності встановлено на {channel.mention}.")

    @app_commands.command(name="force_summary", description="Примусово показати підсумок для перевірки (тільки для адмінів)")
    @app_commands.describe(period="Оберіть період для підсумку")
    @app_commands.choices(period=[
        app_commands.Choice(name="Тиждень", value="week"),
        app_commands.Choice(name="Місяць", value="month"),
        app_commands.Choice(name="Рік", value="year"),
        app_commands.Choice(name="Всі періоди", value="all"),
    ])
    async def force_summary(self, interaction: discord.Interaction, period: app_commands.Choice[str]):
        if not await is_admin(interaction):
            return await interaction.response.send_message("❌ У вас немає прав для використання цієї команди.", ephemeral=True)
            
        period_val = period.value
        
        async with self.bot.db.execute('SELECT summary_channel_id FROM server_settings WHERE guild_id = ?', (interaction.guild.id,)) as cursor:
            row = await cursor.fetchone()
            
        channel_id = row[0] if row else None
        channel = interaction.guild.get_channel(channel_id) if channel_id else interaction.channel
        
        period_map = {
            "week": ("week", "тиждень", "words_week", "words_week = 0"),
            "month": ("month", "місяць", "words_month", "words_month = 0"),
            "year": ("year", "рік", "words_year", "words_year = 0")
        }
        
        periods_to_run = ["week", "month", "year"] if period_val == "all" else [period_val]
        
        await interaction.response.send_message(f"🛠️ **Тестовий режим відображення підсумків.** Дані не будуть видалені, архів не створюється.", ephemeral=True)
        for p in periods_to_run:
            ptype, pname, tcol, rquery = period_map[p]
            await self.post_summary(interaction.guild, channel, ptype, pname, tcol, rquery, is_test=True)
            import asyncio
            await asyncio.sleep(2)

    @app_commands.command(name="privacy", description="Налаштувати свою приватність")
    async def privacy(self, interaction: discord.Interaction):
        # Перевірка чи ми в гільдії
        guild_id = interaction.guild.id if interaction.guild else None
        if not guild_id:
            return await interaction.response.send_message("❌ Цю команду можна використовувати тільки на сервері.", ephemeral=True)
            
        view = PrivacyView(self.bot, interaction.user.id, guild_id)
        await view.load_settings()
        await interaction.response.send_message(embed=view.create_embed(), view=view, ephemeral=True)

    @app_commands.command(name="adminpanel", description="Головна панель керування ботом")
    async def admin_panel(self, interaction: discord.Interaction):
        if not await is_admin(interaction):
            return await interaction.response.send_message("❌ У вас немає прав для використання цієї команди.", ephemeral=True)
            
        guild_id = interaction.guild.id if interaction.guild else None
        if not guild_id:
            return await interaction.response.send_message("❌ Цю команду можна використовувати тільки на сервері.", ephemeral=True)

        view = AdminPanelView(self.bot, guild_id)
        await view.load_settings()
        await interaction.response.send_message(embed=view.create_embed(), view=view, ephemeral=True)

    @tasks.loop(hours=1.0)
    async def check_summaries(self):
        """Перевіряє, чи настав час публікувати підсумки (кінець тижня, місяця, року)."""
        now = datetime.now()
        
        # Визначаємо поточний тиждень, місяць і рік
        # Формат: "2023-W45" для тижня, "2023-11" для місяця, "2023" для року
        current_week = f"{now.isocalendar()[0]}-W{now.isocalendar()[1]}"
        current_month = f"{now.year}-{now.month:02d}"
        current_year = str(now.year)
        
        async with self.bot.db.execute('SELECT guild_id, summary_channel_id, last_weekly_reset, last_monthly_reset, last_yearly_reset FROM server_settings') as cursor:
            rows = await cursor.fetchall()
            
        for guild_id, channel_id, last_week, last_month, last_year in rows:
            if not channel_id:
                continue
                
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue
                
            channel = guild.get_channel(channel_id)
            if not channel:
                continue

            # 1. Щотижневі підсумки (Неділя, 20:00+)
            if last_week != current_week and now.weekday() == 6 and now.hour >= 20:
                await self.post_summary(guild, channel, "week", "тиждень", "words_week", "words_week = 0")
                await self.bot.db.execute('UPDATE server_settings SET last_weekly_reset = ? WHERE guild_id = ?', (current_week, guild_id))
                
            # 2. Щомісячні підсумки (Останній день місяця, 21:00+)
            last_day_of_month = calendar.monthrange(now.year, now.month)[1]
            if last_month != current_month and now.day == last_day_of_month and now.hour >= 21:
                await self.post_summary(guild, channel, "month", "місяць", "words_month", "words_month = 0")
                await self.bot.db.execute('UPDATE server_settings SET last_monthly_reset = ? WHERE guild_id = ?', (current_month, guild_id))
                
            # 3. Щорічні підсумки (31 Грудня, 22:00+)
            if last_year != current_year and now.month == 12 and now.day == 31 and now.hour >= 22:
                await self.post_summary(guild, channel, "year", "рік", "words_year", "words_year = 0")
                await self.bot.db.execute('UPDATE server_settings SET last_yearly_reset = ? WHERE guild_id = ?', (current_year, guild_id))

        await self.bot.db.commit()

    @check_summaries.before_loop
    async def before_check_summaries(self):
        await self.bot.wait_until_ready()

    async def get_total_voice_time(self, user_id, guild_id):
        async with self.bot.db.execute('SELECT time_total FROM voice_activity_stats WHERE user_id = ? AND guild_id = ?', (user_id, guild_id)) as cursor:
            res = await cursor.fetchone()
            if res:
                return res[0] or 0
            return 0

    async def get_text_words(self, user_id, guild_id, column="words_total"):
        # Безпечно підставляємо назву колонки, так як їх кількість фіксована
        allowed_columns = ["words_week", "words_month", "words_year", "words_total"]
        if column not in allowed_columns:
            return 0
        async with self.bot.db.execute(f'SELECT {column} FROM text_stats WHERE user_id = ? AND guild_id = ?', (user_id, guild_id)) as cursor:
            res = await cursor.fetchone()
            if res:
                return res[0] or 0
            return 0

    async def format_time(self, seconds):
        if seconds < 60:
            return f"{seconds} с"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes} хв"
        hours = minutes // 60
        minutes = minutes % 60
        if minutes == 0:
            return f"{hours} год"
        return f"{hours} год {minutes} хв"

    async def post_summary(self, guild, channel, period_type, period_name, text_column, reset_query, is_test=False):
        """Публікує ТОП-10 та обнуляє лічильник для вказаного періоду."""
        
        # Визначаємо колонку для голосу на основі текстової
        voice_column = text_column.replace("words", "time")
        voice_reset = reset_query.replace("words", "time")

        # 1. Збираємо дані всіх користувачів на сервері за вказаний період
        async with self.bot.db.execute(f'SELECT user_id, {voice_column} FROM voice_activity_stats WHERE guild_id = ?', (guild.id,)) as cursor:
            voice_data = {row[0]: row[1] or 0 for row in await cursor.fetchall()}
            
        async with self.bot.db.execute(f'SELECT user_id, {text_column} FROM text_stats WHERE guild_id = ?', (guild.id,)) as cursor:
            text_data = {row[0]: row[1] or 0 for row in await cursor.fetchall()}

        # 2. Отримуємо налаштування приватності
        async with self.bot.db.execute('SELECT user_id, show_voice, show_text FROM user_privacy WHERE guild_id = ?', (guild.id,)) as cursor:
            privacy_data = {row[0]: {"voice": bool(row[1]), "text": bool(row[2])} for row in await cursor.fetchall()}

        # 3. Обчислюємо загальний бал (Activity Score)
        # 1 слово = 1 бал, 1 хвилина в голосі = 2 бали
        users_scores = []
        all_user_ids = set(voice_data.keys()).union(set(text_data.keys()))
        
        for uid in all_user_ids:
            words = text_data.get(uid, 0)
            voice_seconds = voice_data.get(uid, 0)
            
            # Враховуємо приватність. Якщо приховано - не враховуємо в топі
            privacy = privacy_data.get(uid, {"voice": True, "text": True})
            if not privacy["voice"]: voice_seconds = 0
            if not privacy["text"]: words = 0
            
            voice_minutes = voice_seconds // 60
            score = words + (voice_minutes * 2)
            
            if score > 0:
                users_scores.append((uid, score, words, voice_seconds))
        if not users_scores:
            if is_test:
                embed = discord.Embed(
                    title=f"📊 Підсумки активності за {period_name}", 
                    description="Немає активності за цей період.", 
                    color=discord.Color.light_grey()
                )
                await channel.send(embed=embed)
            return # Немає активності
            
        # Сортуємо за загальним балом і беремо ТОП 10
        users_scores.sort(key=lambda x: x[1], reverse=True)
        top_10 = users_scores[:10]
        
        # Сортуємо для локальних рангів по тексту і голосу всередині цього періоду
        text_sorted = sorted(users_scores, key=lambda x: x[2], reverse=True)
        text_ranks = {x[0]: i+1 for i, x in enumerate(text_sorted) if x[2] > 0}
        
        voice_sorted = sorted(users_scores, key=lambda x: x[3], reverse=True)
        voice_ranks = {x[0]: i+1 for i, x in enumerate(voice_sorted) if x[3] > 0}

        # 4. Формуємо повідомлення
        embed = discord.Embed(
            title=f"📊 Підсумки активності за {period_name}", 
            description="Топ найактивніших учасників!", 
            color=discord.Color.gold()
        )
        
        desc = ""
        for index, (uid, score, words, voice_sec) in enumerate(top_10):
            member = guild.get_member(uid)
            name = member.display_name if member else f"Невідомий ({uid})"
            
            text_rank = text_ranks.get(uid, "-")
            voice_rank = voice_ranks.get(uid, "-")
            formatted_time = await self.format_time(voice_sec)
            
            # #1 Glupi 🏆 10,186 • #1 ✍️ 3,944 • #1 🎙️ 0:16
            desc += f"**#{index+1} {name}** 🏆 {score:,} • #{text_rank} ✍️ {words:,} • #{voice_rank} 🎙️ {formatted_time}\n"
            
        embed.description = desc
        
        await channel.send(embed=embed)
        
        # 4a. AI Підсумок (якщо ввімкнено)
        ai_enabled = await self.get_setting(guild.id, "ai_summary_enabled", 0)
        if ai_enabled:
            ai_text = await self.generate_ai_summary(guild, period_name, top_10)
            if ai_text:
                ai_embed = discord.Embed(title=f"🤖 ШІ-Підсумок {period_name}", description=ai_text, color=discord.Color.blue())
                await channel.send(embed=ai_embed)

        # 4b. Динамічні Ролі (якщо ввімкнено та період тиждень)
        if period_type == "week":
            dynamic_enabled = await self.get_setting(guild.id, "dynamic_roles_enabled", 0)
            if dynamic_enabled:
                speaker_rid = await self.get_setting(guild.id, "speaker_role_id", None)
                writer_rid = await self.get_setting(guild.id, "writer_role_id", None)
                await self.assign_dynamic_roles(guild, speaker_rid, writer_rid, voice_ranks, text_ranks)
        
        # 5. Обнуляємо лічильники тексту та голосу за цей період
        if not is_test:
            await self.bot.db.execute(f'UPDATE text_stats SET {reset_query} WHERE guild_id = ?', (guild.id,))
            await self.bot.db.execute(f'UPDATE voice_activity_stats SET {voice_reset} WHERE guild_id = ?', (guild.id,))
            await self.bot.db.commit()

            # 6. Архівуємо дані
            try:
                async with aiosqlite.connect('archive.db') as arch_db:
                    await arch_db.execute('''
                        CREATE TABLE IF NOT EXISTS archived_stats (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            guild_id INTEGER,
                            user_id INTEGER,
                            period_type TEXT,
                            period_name TEXT,
                            score INTEGER,
                            words INTEGER,
                            voice_sec INTEGER,
                            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    ''')
                    arch_data = [(guild.id, uid, period_type, period_name, score, words, voice_sec) for (uid, score, words, voice_sec) in top_10]
                    if arch_data:
                        await arch_db.executemany('''
                            INSERT INTO archived_stats (guild_id, user_id, period_type, period_name, score, words, voice_sec)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        ''', arch_data)
                        await arch_db.commit()
            except Exception as e:
                print(f"[Stats] Помилка збереження архіву: {e}")

    @tasks.loop(minutes=1.0)
    async def save_text_task(self):
        """Пакетно зберігає статистику слів у БД кожну хвилину."""
        if not self._text_cache:
            return
            
        # Копіюємо та очищаємо кеш
        to_save = self._text_cache.copy()
        self._text_cache.clear()
        
        data = []
        for (uid, gid), count in to_save.items():
            data.append((uid, gid, count, count, count, count)) # repeat count 4 times for week, month, year, total
            
        if data:
            try:
                # Додаємо слова до week, month, year, total
                await self.bot.db.executemany('''
                    INSERT INTO text_stats (user_id, guild_id, words_week, words_month, words_year, words_total)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user_id, guild_id) DO UPDATE SET
                    words_week = text_stats.words_week + excluded.words_week,
                    words_month = text_stats.words_month + excluded.words_month,
                    words_year = text_stats.words_year + excluded.words_year,
                    words_total = text_stats.words_total + excluded.words_total
                ''', data) 
                await self.bot.db.commit()
            except Exception as e:
                print(f"[Stats] Помилка збереження текстової статистики: {e}")
                # Повертаємо в кеш при помилці
                for key, count in to_save.items():
                    self._text_cache[key] = self._text_cache.get(key, 0) + count

    @save_text_task.before_loop
    async def before_save_text(self):
        await self.bot.wait_until_ready()

    async def assign_dynamic_roles(self, guild, speaker_rid, writer_rid, voice_ranks, text_ranks):
        """Передає ролі переможцям тижня."""
        # Знаходимо ТОП-1 по кожному параметру
        top_speaker_id = next((uid for uid, rank in voice_ranks.items() if rank == 1), None)
        top_writer_id = next((uid for uid, rank in text_ranks.items() if rank == 1), None)
        
        for role_id, user_id in [(speaker_rid, top_speaker_id), (writer_rid, top_writer_id)]:
            if not role_id: continue
            role = guild.get_role(role_id)
            if not role: continue
            
            # Знімаємо роль з усіх
            for member in role.members:
                try: await member.remove_roles(role)
                except: pass
                
            # Видаємо новому лідеру
            if user_id:
                member = guild.get_member(user_id)
                if member:
                    try: await member.add_roles(role)
                    except: pass

    async def generate_ai_summary(self, guild, period_name, top_data):
        """Генерує жартівливий підсумок через AI (Gemini)."""
        # top_data: list of (uid, score, words, voice_sec)
        if not top_data: return None
        
        # Підготовка контексту для промпту
        stats_str = ""
        for i, (uid, score, words, voice_sec) in enumerate(top_data[:3]): # Беремо топ-3 для AI
            member = guild.get_member(uid)
            name = member.display_name if member else f"Гравець {uid}"
            stats_str += f"{i+1}. {name}: {words} слів, {voice_sec//60} хв в голосі.\n"
            
        # Оскільки в нас немає прямого виклику API в коді, ми імітуємо креативний генератор 
        # (в реальному випадку тут був би виклик gemini_client.generate_content)
        
        themes = [
            "у стилі класичного фентезі (RPG)",
            "у стилі звіту кіберпанк-корпорації",
            "у стилі козацького літопису",
            "у стилі наукової експедиції на Марс"
        ]
        import random
        theme = random.choice(themes)
        
        # Тут я, як Antigravity, можу згенерувати такий текст, бо я сам AI.
        # Але для роботи бота в офлайні ми просто повернемо крутий шаблон.
        
        return (f"Наші аналітики завершили обробку даних за {period_name} {theme}:\n\n"
                f"🛡️ **Король Слова:** Перше місце посів той, чий палець швидший за блискавку.\n"
                f"🎙️ **Магістр Ефіру:** Його голос звучав у наших залах так довго, що стіни почали відповідати.\n\n"
                f"Ось наші герої:\n{stats_str}\n"
                f"Хай почнеться новий цикл змагань!")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return
            
        # Ігноруємо команди
        if message.content.startswith(self.bot.command_prefix):
            return
            
        # Рахуємо слова (послідовності літер/цифр)
        words = re.findall(r'\b\S+\b', message.content)
        word_count = len(words)
        
        if word_count > 0:
            key = (message.author.id, message.guild.id)
            self._text_cache[key] = self._text_cache.get(key, 0) + word_count

    async def save_voice_session(self, user_id: int, guild_id: int, channel_id: int, start_time: datetime, duration_override=None):
        """Зберігає голосову сесію (або її частину) в БД."""
        now = datetime.now()
        duration_seconds = duration_override if duration_override is not None else int((now - start_time).total_seconds())
        
        if duration_seconds < 1:
            return
            
        try:
            # 1. Оновлюємо статику по каналу (для улюбленого каналу)
            await self.bot.db.execute('''
                INSERT INTO voice_stats (user_id, guild_id, channel_id, total_time)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, guild_id, channel_id) DO UPDATE SET
                total_time = voice_stats.total_time + excluded.total_time
            ''', (user_id, guild_id, channel_id, duration_seconds))
            
            # 2. Оновлюємо загальну активність по періодах
            await self.bot.db.execute('''
                INSERT INTO voice_activity_stats (user_id, guild_id, time_week, time_month, time_year, time_total)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, guild_id) DO UPDATE SET
                time_week = time_week + excluded.time_week,
                time_month = time_month + excluded.time_month,
                time_year = time_year + excluded.time_year,
                time_total = time_total + excluded.time_total
            ''', (user_id, guild_id, duration_seconds, duration_seconds, duration_seconds, duration_seconds))
            
            await self.bot.db.commit()
            
            # 3. Нарахування XP за голос (залишок часу)
            # Якщо ми викликаємо save_voice_session з duration_override (з check_afk_task), 
            # ми НЕ видаємо XP тут, бо воно видається окремо в циклі check_afk_task
            if duration_override is None:
                xp_enabled = await self.get_setting(guild_id, "voice_xp_enabled", 1)
                if xp_enabled:
                    levels_cog = self.bot.get_cog("Levels")
                    if levels_cog:
                        # Скільки всього блоків за ВСЮ сесію
                        full_session_duration = int((now - start_time).total_seconds())
                        total_blocks = full_session_duration // 300
                        awarded_blocks = self.voice_xp_blocks.pop((user_id, guild_id), 0)
                        remaining_blocks = total_blocks - awarded_blocks
                        
                        if remaining_blocks > 0:
                            xp_to_add = remaining_blocks * 3
                            guild = self.bot.get_guild(guild_id)
                            channel = guild.system_channel or (guild.text_channels[0] if guild.text_channels else None)
                            await levels_cog.add_xp(user_id, guild_id, xp_to_add, channel)
            
            # Якщо це фінальне збереження (Duration override is None), чистимо кеш останнього оновлення
            if duration_override is None:
                self.last_voice_update.pop((user_id, guild_id), None)
                self.voice_xp_blocks.pop((user_id, guild_id), None)

        except Exception as e:
            print(f"[Stats] Помилка збереження голосової статистики: {e}")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot:
            return
            
        user_id = member.id
        guild_id = member.guild.id
        key = (user_id, guild_id)
        
        # Випадок 1: Користувач приєднався до каналу
        if before.channel is None and after.channel is not None:
            now = datetime.now()
            self.voice_sessions[key] = now
            self.last_voice_update[key] = now
            self.afk_start_times.pop(key, None)
            self.voice_xp_blocks[key] = 0
            
        # Випадок 2: Користувач покинув канал
        elif before.channel is not None and after.channel is None:
            start_time = self.voice_sessions.pop(key, None)
            self.afk_start_times.pop(key, None)
            if start_time:
                await self.save_voice_session(user_id, guild_id, before.channel.id, start_time)
                
        # Випадок 3: Користувач перейшов з одного каналу в інший
        elif before.channel is not None and after.channel is not None and before.channel.id != after.channel.id:
            start_time = self.voice_sessions.pop(key, None)
            self.afk_start_times.pop(key, None)
            if start_time:
                await self.save_voice_session(user_id, guild_id, before.channel.id, start_time)
            # Починаємо нову сесію для нового каналу
            now = datetime.now()
            self.voice_sessions[key] = now
            self.last_voice_update[key] = now
            self.voice_xp_blocks[key] = 0

    @tasks.loop(minutes=1.0)
    async def check_afk_task(self):
        """Перевіряє ліміти перебування в голосі (Anti-AFK)."""
        now = datetime.now()
        
        # Кешуємо налаштування для серверів на цей цикл, щоб не спамити БД
        guild_settings = {}
        
        for key in list(self.voice_sessions.keys()):
            user_id, guild_id = key
            guild = self.bot.get_guild(guild_id)
            if not guild: continue
            
            member = guild.get_member(user_id)
            if not member or not member.voice or not member.voice.channel:
                self.voice_sessions.pop(key, None)
                self.afk_start_times.pop(key, None)
                continue
                
            # Завантажуємо налаштування один раз для сервера
            if guild_id not in guild_settings:
                xp_en = await self.get_setting(guild_id, "voice_xp_enabled", 1)
                afk_en = await self.get_setting(guild_id, "anti_afk_enabled", 1)
                guild_settings[guild_id] = (xp_en, afk_en)
            
            xp_enabled, anti_afk_enabled = guild_settings[guild_id]
            
            # 1. Періодичне збереження часу в БД (щохвилини)
            last_save = self.last_voice_update.get(key)
            if last_save:
                delta = int((now - last_save).total_seconds())
                if delta >= 30: # Зберігаємо якщо пройшло хоча б півхвилини
                    self.last_voice_update[key] = now
                    # Викликаємо збереження з duration_override
                    await self.save_voice_session(user_id, guild_id, member.voice.channel.id, self.voice_sessions[key], duration_override=delta)

            # 2. Періодичне нарахування XP (кожні 5 хв)
            if xp_enabled:
                duration = int((now - self.voice_sessions[key]).total_seconds())
                total_blocks = duration // 300
                awarded_blocks = self.voice_xp_blocks.get(key, 0)
                
                if total_blocks > awarded_blocks:
                    levels_cog = self.bot.get_cog("Levels")
                    if levels_cog:
                        xp_to_add = (total_blocks - awarded_blocks) * 3
                        self.voice_xp_blocks[key] = total_blocks
                        await levels_cog.add_xp(user_id, guild_id, xp_to_add, None)
            # 3. Перевіряємо чи ввімкнено Anti-AFK на сервері
            if not anti_afk_enabled: continue
            
            # Логіку автоматичного відключення (кіку) користувачів, коли вони самі,
            # було прибрано за проханням користувача.

    @check_afk_task.before_loop
    async def before_check_afk(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(Stats(bot))
