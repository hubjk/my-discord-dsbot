import discord
from discord.ext import commands
import re
import time
import asyncio
from datetime import timedelta

class AutoMod(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
        # Регулярний вираз для пошуку посилань (наприклад: discord.gg/, http://, https://)
        self.link_regex = re.compile(r'(https?://[^\s]+|discord\.gg/[a-zA-Z0-9]+)')
        
        # Для Анти-Спаму: зберігаємо останні повідомлення користувачів
        # Формат: {user_id: [timestamp1, timestamp2, ...]}
        self.user_messages = {}
        self.SPAM_LIMIT = 5 # 5 повідомлень
        self.SPAM_TIME = 3 # за 3 секунди
        
        # Для Вертикального Спаму: { (user_id, channel_id): [(timestamp, char, message_id), ...] }
        self.vertical_buffers = {}
        self.VERTICAL_TIMEOUT = 5 # 5 секунд між буквами
        
        # Накопичувальні покарання: { (guild_id, user_id): { 'profanity': 0, 'spam': 0, 'last': 0, 'abuser': False } }
        self.p_stats = {}
        
        # Прапорець для запобігання повторному запуску скану при реконектах
        self._startup_checked = False
        
        # Список заблокованих слів (мат / нецензурна лексика)
        # Перевірка регістро-незалежна (.lower() застосовується до повідомлення)
        self.BANNED_WORDS = [
            # === БЛЯ / БЛЯДЬ ===
            "бля", "блять", "блядь", "блядина", "бляха", "блядський",
            "blyad", "blya", "bljad",

            # === ЄБАТИ / ЙОБ ===
            "єбать", "єбан", "єбало", "єбатись", "єбана", "єбаний",
            "йобан", "йоб", "йобаний",
            "їбан", "їб", "їбати",
            "ебать", "ёбань", "ёб", "ёбаный",
            "ebat", "yobany", "yob", "eban",
            "є6ать", "е6ать", "е6ан",

            # === ПІЗДА / ПИЗДА ===
            "пізд", "піздець", "піздобол", "пізданутий",
            "пизда", "пизд", "пиздець", "пиздобол",
            "пizda", "p1zda", "пi3да",
            "pizda", "pizdec", "pezdec",

            # === ХУЙ ===
            "хуй", "хуйн", "хуєв", "хуєва", "хуйло", "хуйня",
            "хуяк", "хуяри", "хуйовий",
            "хyй", "xуй", "х.й",
            "хui", "xui", "hui", "huy",
            "х0й", "х.уй",

            # === ЗАЛУПА ===
            "залупа", "залуп", "залупись",
            "zalupa", "zalup",

            # === СУКА / СУЧ ===
            "сука", "суч", "сучка", "сучара", "сучий",
            "с#ка", "с$ка", "с#к@", "су#а",
            "suka", "suk@", "suc", "suchka", "sukin", "сукало", "сукла",

            # === ПІДОРАС / ПЕДИК ===
            "пидор", "підор", "підорас", "підарас", "педик", "педераст",
            "п1дор", "п1дарас", "пidор",
            "pidor", "pidar", "pidaras", "pidarasy", "pidory",
            "pidoras", "p1doras", "p1dar",

            # === МУДАК / МУДИЛО ===
            "мудак", "мудил", "мудило", "мудозвон",
            "mudak", "mudilo", "mudo",

            # === КУРВА ===
            "курва", "kurva",

            # === ССАТИ ===
            "ссати", "ссань", "ssaty",

            # === ЛАЙНО / ГІВНО ===
            "лайно", "гівно", "гiвно", "гiвнюк",
            "givno", "govno", "laino",

            # Ви можете додати свої слова нижче:

            # === ШЛЬОНДРА / ПОВІЯ ===
            "шльондра", "шльондри", "шлюха", "шлюхи", "шлюшний",
            "повія", "профура", "блудниця",
            "shlyukha", "shlukha",

            # === ЗАД / СРАКИ ===
            "срака", "сраки", "срати", "сранина",
            "sraka", "srat",

            # === ЙОБ (утворені форми) ===
            "нахуй", "нахуяти", "захуяти", "похуй", "похуєти",
            "nahuy", "zahuy", "pohuy",
            "отхуярити", "відхуярити",

            # === ПІЗДЕЦЬ (окремо) ===
            "піздєц", "піздьос",
            "pizdyos",

            # === ШИЗА / ДЕГЕНЕРАТ ===
            "дебіл", "дегенерат", "дебілізм",
            "debil", "degenderat",
            "ублюдок", "ублюд",
            "ublyudok",

            # === ТВАРИНА (образи) ===
            "твар", "тварюка",
            "скотина", "скот",
            "тупий", "тупорил",

            # === ПІЗДОБРАТІЯ / ЄБАНАТ ===
            "уєбан", "уебан", "єбанат", "їбанат", "йобанат",
            "єбанько", "йобаний рот",
            "залупоголовий",

            # === НАЦИСТСЬКА СИМВОЛІКА / ОБРАЗИ ===
            "хохол", "хахол", "хохляндія",
            "колорад",

            # === ГЕНІТАЛІЇ (додаткові) ===
            "пісюн", "пісюнець",
            "мошонка",
            "вагіна", "клітор",
            "pisun", "vagina", "klitor",
            "дупа", "дупця", "дупло",
            "дупай", "дупай",
            "dupa", "dupo",
            "анус", "anus",
            "манда", "манди",
            "manda",

            # === ОБРАЗИ РОДИЧІВ ===
            "твою мать", "твою маму",
            "їбав твою",
            "сука мать",

            # === ВЖИВАННЯ НАРКОТИКІВ ===
            "торчок", "наркоман", "нарик", "торч",
            "накурений", "обдовбаний",

            # === ЛАЙКИ (англійські) ===
            "fuck", "fuсk", "f**k", "fuk", "fck",
            "shit", "sh1t", "sht",
            "bitch", "b1tch", "btch",
            "ass", "asshole", "a**hole",
            "cunt", "c**t",
            "dick", "d1ck",
            "cock", "c0ck",
            "pussy",
            "bastard",
            "nigga", "nigger", "niger",
            "faggot", "fag",
            "whore",
            "retard", "сосать", "бидло", "херня", "блять", "хер",

        ]

        # Список слів-винятків (білий список) за замовчуванням
        self.DEFAULT_WHITE_WORDS = [
            # Географія та назви
            "херсон", "херсонець", "херсонський", "херсонщина",
            
            # Предмети, фрукти та UA/RU слова
            "команда", "командна", "командир", "мандарин", "мандат", "мандариновий",
            "гірлянда", "пропаганда", "еманципація", "саламандра", "панда", "контрабанда",
            "лаванда", "веранда", "фанда", "дистанція", "інстанція",
            "підозр", "підозрювати", "підозра", "підозрілий", "підозрюваний",
            "пізніше", "пізній", "пізно", "підошва", "підодіяльник", "підпис",
            "сукати", "сукуватий", "сукулент", "засукати", "підсукати", "борсука",
            "сатира", "сатир", "сатиричний", "сатисфакція",
            "писати", "написати", "описати", "підписати", "переписати", "дописати",
            "художник", "художній", "худий", "худнути", "худіти", "хустка", "хутро",
            "дупло", "дуплет", "дуплекс", "індустрія",
            "педикюр", "курватура", "херувим", "херес",
            "шабля", "ансамбля", "фагот", "дебати", "ребата",
            
            # Англійські слова (через агресивну нормалізацію 'ass', 'cock', 'dick' тощо)
            "associate", "association", "assist", "assistance", "assistant",
            "assembly", "assign", "assignment", "assume", "assumption", 
            "assurance", "assure", "assert", "assertion", "assets", "assessment",
            "massage", "passive", "classic", "glass", "grass", "massive", "brass",
            "chess", "dress", "press", "address", "pass", "passion",
            "cocktail", "peacock", "cockroach", "cockney",
            "dickens", "dictator", "dictionary", "dictation", "predict", "verdict",
            "addict", "addiction", "contradict",
            "title", "titan", "titanic", "titrate", "attitude", "entity", "identity",
            "constitute", "institution", "substitute",
            "cucumber", "cumulative", "succumb", "accumulate",
            "shell", "hello", "jellyfish", "epistle",
            
            # Кирилличні варіанти англійських запозичень
            "асоціація", "асистент", "асамблея", "асортимент", "асорті",
            "коктейль", "диктор", "диктант", "диктатура", "пасивний", "класика",
            "адреса", "пасія", "преса", "прогрес", "конгрес",
        ]

        # Кеш заборонених слів і виключених каналів (інвалідується при змінах)
        self._word_cache = {}       # {guild_id: [words]}
        self._excluded_cache = {}   # {guild_id: {channel_ids}}
        self._white_cache = {}       # {guild_id: [words]}
        
    def normalize_text(self, text):
        """Нормалізує текст: повертає два варіанти (4='а' і 4='д') для кращого розпізнавання."""
        text = text.lower()
        # Стискаємо повтори букв: 'суукка' -> 'сука', 'хуууй' -> 'хуй'
        text = re.sub(r'(.)\1+', r'\1', text)
        base_subs = [
            ('@', 'а'),  ('$', 'с'),  ('!', 'і'),  ('|', 'і'),
            ('0', 'о'),  ('1', 'і'),  ('3', 'з'),
            ('5', 'с'),  ('6', 'б'),  ('7', 'т'),  ('8', 'в'),
            ('h', 'х'),  ('e', 'є'),  ('i', 'і'),  ('y', 'й'),
            ('u', 'у'),  ('o', 'о'),  ('a', 'а'),  ('c', 'с'),
            ('p', 'р'),  ('x', 'х'),
        ]
        results = []
        for four_val in ['а', 'д']:
            t = text
            for old, new in base_subs:
                t = t.replace(old, new)
            t = t.replace('4', four_val)
            # Залишаємо тільки Кириличні та латинські літери
            t = re.sub(r'[^\u0430-\u044f\u0456\u0454\u0457\u0491a-z]', '', t)
            results.append(t)
        return results

    async def get_banned_words(self, guild_id):
        """Повертає список заборонених слів: вбудованих + з бази для цього серверу."""
        # Кеш щоб не робити запит до БД на кожне повідомлення
        if guild_id in self._word_cache:
            return self._word_cache[guild_id]
        async with self.bot.db.execute(
            'SELECT word FROM banned_words WHERE guild_id = ? OR guild_id = 0',
            (guild_id,)
        ) as cursor:
            rows = await cursor.fetchall()
        db_words = [r[0] for r in rows]
        combined = list(set(self.BANNED_WORDS + db_words))
        self._word_cache[guild_id] = combined
        return combined

    async def get_white_words(self, guild_id):
        """Повертає список білих слів (whitelist) для цього серверу."""
        if guild_id in self._white_cache:
            return self._white_cache[guild_id]
        async with self.bot.db.execute(
            'SELECT word FROM whitelisted_words WHERE guild_id = ?',
            (guild_id,)
        ) as cursor:
            rows = await cursor.fetchall()
        db_words = [r[0] for r in rows]
        # Об'єднуємо дефолтні слова з тими, що в БД
        combined = list(set(self.DEFAULT_WHITE_WORDS + db_words))
        self._white_cache[guild_id] = combined
        return combined

    async def is_excluded_channel(self, channel_id, guild_id):
        """Перевіряє чи виключений канал з фільтру."""
        if guild_id not in self._excluded_cache:
            async with self.bot.db.execute(
                'SELECT channel_id FROM automod_excluded_channels WHERE guild_id = ?',
                (guild_id,)
            ) as cursor:
                rows = await cursor.fetchall()
            self._excluded_cache[guild_id] = {r[0] for r in rows}
        return channel_id in self._excluded_cache[guild_id]

    def get_banned_norms(self, words):
        """Повертає список пар (orig_word, normalized_forms) для переданих слів."""
        return [(w, self.normalize_text(w)) for w in words]

    async def timeout_user(self, member, reason, duration_minutes=5):
        """Хелпер для тайм-ауту користувача (Мут)"""
        try:
            duration = timedelta(minutes=duration_minutes)
            await member.timeout(duration, reason=reason)
            return True
        except discord.Forbidden:
            return False

    async def _apply_punishment(self, message, violation_type) -> str:
        """
        Застосовує покарання на основі типу порушення та історії користувача.
        violation_type: 'profanity' або 'spam'
        Повертає рядок з описом покарання.
        """
        user_id = message.author.id
        gid = message.guild.id
        key = (gid, user_id)
        now = time.time()
        
        # Ініціалізація або скидання за таймером
        if key not in self.p_stats:
            self.p_stats[key] = {'profanity': 0, 'spam': 0, 'last': 0.0, 'abuser': False}
        
        stats = self.p_stats[key]
        reset_time = 3600.0 if stats['abuser'] else 1800.0 # 60хв або 30хв
        
        last_t = float(stats['last'])
        if now - last_t > reset_time:
            stats['profanity'] = 0
            stats['spam'] = 0
            # abuser залишається True поки не мине година очищення
        
        stats['last'] = now
        
        if violation_type == 'profanity':
            stats['profanity'] += 1
            count = stats['profanity']
            
            if count <= 3:
                # Просто попередження (Embed з цензурою вже відправлений в on_message)
                return f"Попередження ({count}/3)"
            
            # Рівні муту для мату (починаючи з 4-го разу)
            level = count - 3
            if level == 1:
                duration, d_str = 1, "1 хвилину"
            elif level == 2:
                duration, d_str = 5, "5 хвилин"
            else:
                duration, d_str = 10, "10 хвилин"
                stats['abuser'] = True # Мітка зловмисника
            
            success = await self.timeout_user(message.author, f"Мат (Порушення #{count})", duration)
            if success:
                return f"Мут на {d_str} (Порушення #{count})"
            return f"Попередження (Бот не зміг замутити)"

        elif violation_type == 'spam':
            stats['spam'] += 1
            count = stats['spam']
            
            if count == 1:
                return "Попередження (1/1)"
            
            # Рівні муту для спаму (починаючи з 2-го разу)
            level = count - 1
            if level == 1:
                duration, d_str = 1, "1 хвилину"
            elif level == 2:
                duration, d_str = 5, "5 хвилин"
            else:
                duration, d_str = 10, "10 хвилин"
                stats['abuser'] = True
            
            success = await self.timeout_user(message.author, f"Спам (Порушення #{count})", duration)
            if success:
                return f"Мут на {d_str} (Порушення #{count})"
            return f"Попередження (Бот не зміг замутити)"
        
        return "Попередження"

    @commands.Cog.listener()
    async def on_ready(self):
        if not self._startup_checked:
            self._startup_checked = True
            self.bot.loop.create_task(self.quiet_profanity_scan())

    async def quiet_profanity_scan(self):
        await asyncio.sleep(10)
        print("[AutoMod] Запуск тихої перевірки чатів на мати...")
        for guild in self.bot.guilds:
            try:
                banned_words = await self.get_banned_words(guild.id)
                if not banned_words:
                    continue
                banned_norms = self.get_banned_norms(banned_words)
                white_words = await self.get_white_words(guild.id)
                
                for channel in guild.text_channels:
                    if await self.is_excluded_channel(channel.id, guild.id):
                        continue
                    
                    try:
                        async for msg in channel.history(limit=50):
                            if msg.author.bot or not msg.content:
                                continue
                            
                            found_words = self._get_profanity_words(msg.content, banned_norms, white_words)
                            if found_words:
                                await msg.delete()
                                await asyncio.sleep(1.0) # Для захисту від rate limits (1с)
                    except (discord.Forbidden, discord.HTTPException):
                        pass
            except Exception as e:
                print(f"[AutoMod] Помилка тихої перевірки сервера {guild.id}: {e}")
        print("[AutoMod] Тиха перевірка чатів завершена.")

    def _get_profanity_words(self, content: str, banned_norms: list, white_words: list) -> list:
        """Повертає список знайдених матюків у тексті, або порожній список якщо текст чистий."""
        text_without_urls = re.sub(r'https?://\S+', '', content)
        message_words = re.split(r'\s+', text_without_urls.strip())
        found_words = []
        
        for msg_word in message_words:
            if not msg_word or re.match(r'^https?://', msg_word):
                continue
            stripped = re.sub(r'^[^\w\u0400-\u04ff]+|[^\w\u0400-\u04ff]+$', '', msg_word)
            if not stripped:
                continue
            
            if stripped.lower() in white_words:
                continue

            word_variants = self.normalize_text(stripped)
            
            is_whitelisted = False
            for wv in word_variants:
                for ww in white_words:
                    if not ww: continue
                    if wv == ww or wv.startswith(ww):
                        is_whitelisted = True
                        break
                if is_whitelisted:
                    break
            if is_whitelisted:
                continue

            for orig_word, ban_variants in banned_norms:
                if orig_word in found_words:
                    continue
                for wn in ban_variants:
                    for wv in word_variants:
                        if len(wn) <= 3:
                            is_match = (wv == wn)
                        else:
                            is_match = (wn in wv)

                        if is_match:
                            found_words.append(orig_word)
                            break
                    if orig_word in found_words:
                        break
        return found_words

    @commands.Cog.listener()
    async def on_message(self, message):
        # Ігноруємо приватні повідомлення та ботів
        if not message.guild or message.author.bot:
            return

        is_admin = message.author.guild_permissions.administrator or message.guild.owner_id == message.author.id
        gid = message.guild.id

        # 1. АНТИ-ЛІНК (Заборона посилань) — не для адмінів та учасників з рівнем 2+
        if not is_admin and self.link_regex.search(message.content):
            # Пропускаємо гіфки з Tenor/Giphy
            if "tenor.com/view/" in message.content or "giphy.com/" in message.content:
                pass
            else:
                # Перевіряємо рівень користувача
                allow_links = False
                levels_cog = self.bot.get_cog("Levels")
                if levels_cog:
                    try:
                        xp = await levels_cog.get_user_xp(message.author.id, gid)
                        level = levels_cog.calculate_level(xp)
                        if level >= 2:
                            allow_links = True
                    except Exception:
                        pass
    
                if not allow_links:
                    await message.delete()
                    warning = await message.channel.send(f"⚠️ {message.author.mention}, надсилати посилання можуть лише учасники з **2 рівня** і вище!")
                    await warning.delete(delay=5)
                    audit_cog = self.bot.get_cog("Audit")
                    if audit_cog:
                        channel = await audit_cog.get_audit_channel(message.guild)
                        if channel:
                            embed = discord.Embed(title="🔗 Знайдено посилання", description=f"{message.author.mention} намагався надіслати посилання в {message.channel.mention}", color=discord.Color.red())
                            embed.add_field(name="Вміст", value=message.content[:500])
                            await channel.send(embed=embed)
                    return

        # 2. ФІЛЬТР МАТУ (Заблоковані слова)
        # Пропускаємо виключені канали
        if await self.is_excluded_channel(message.channel.id, gid):
            # Все одно продовжуємо до анти-спаму
            pass
        else:
            try:
                banned_words = await self.get_banned_words(gid)
                
                # Вилучаємо посилання з перевірки, щоб випадкові букви в URL не розпізнавались як мат
                text_without_urls = re.sub(r'https?://\S+', '', message.content)
                
                # Розбиваємо на окремі слова та перевіряємо КОЖНЕ окремо (щоб "писати" не збігалось з "ссати")
                message_words = re.split(r'\s+', text_without_urls.strip())
                
                banned_norms = self.get_banned_norms(banned_words)
                white_words = await self.get_white_words(gid)
                
                found_words = self._get_profanity_words(message.content, banned_norms, white_words)

                if found_words:
                    original_content = message.content
                    await message.delete()

                    # --- Перший прохід: regex заміна знайдених слів ---
                    censored_text = original_content
                    for found_word in found_words:
                        pattern = re.compile(re.escape(found_word), re.IGNORECASE | re.UNICODE)
                        censored_text = pattern.sub(lambda m: '*' * len(m.group()), censored_text)

                    # --- Другий прохід: пословна перевірка токенів ---
                    words_out = []
                    for token in re.split(r'(\s+)', censored_text):
                        if not token.strip():
                            words_out.append(token)
                            continue
                        # Ігноруємо посилання щоб не ламати їх і не цензурувати випадково
                        if re.match(r'^https?://', token):
                            words_out.append(token)
                            continue
                        # Якщо вже весь токен з зірочок
                        if all(c == '*' for c in token if not c.isspace()):
                            words_out.append(token)
                            continue
                        # Стрипаємо пунктуацію з перевіряємої частини
                        stripped = re.sub(r'^[^\w\u0400-\u04ff]+|[^\w\u0400-\u04ff]+$', '', token)
                        if not stripped:
                            words_out.append(token)
                            continue
                        token_norms = self.normalize_text(stripped)
                        
                        # Перевірка білого списку для токена
                        is_white = False
                        if stripped.lower() in white_words:
                            is_white = True
                        else:
                            for tn in token_norms:
                                if tn in white_words:
                                    is_white = True
                                    break
                        
                        if is_white:
                            is_bad = False
                        else:
                            is_bad = False
                            for _, norms_list in banned_norms:
                                for wn in norms_list:
                                    for mv in token_norms:
                                        if len(wn) <= 3:
                                            match = (mv == wn)
                                        else:
                                            match = (wn in mv)
                                        
                                        if match:
                                            is_bad = True
                                            break
                                    if is_bad: break
                                if is_bad: break

                        if is_bad:
                            # Замінюємо тільки буквену частину зірочками
                            words_out.append(re.sub(r'\w', '*', token))
                        else:
                            words_out.append(token)
                    censored_text = ''.join(words_out)

                    # --- Embed з цензурованим текстом ---
                    embed = discord.Embed(
                        description=censored_text,
                        color=discord.Color.orange()
                    )
                    embed.set_author(
                        name=message.author.display_name,
                        icon_url=message.author.display_avatar.url if message.author.display_avatar else None
                    )
                    # --- Застосування покарання ---
                    p_msg = await self._apply_punishment(message, 'profanity')
                    embed.set_footer(text=f"⚠️ {p_msg}")
                    await message.channel.send(embed=embed)

                    # --- Логування в audit ---
                    audit_cog = self.bot.get_cog("Audit")
                    if audit_cog:
                        audit_channel = await audit_cog.get_audit_channel(message.guild)
                        if audit_channel:
                            log_embed = discord.Embed(
                                title="🚫 Фільтр мату спрацював",
                                color=discord.Color.red()
                            )
                            log_embed.add_field(name="Користувач", value=message.author.mention, inline=True)
                            log_embed.add_field(name="Канал", value=message.channel.mention, inline=True)
                            log_embed.add_field(name="Оригінальний текст", value=f"||{original_content[:500]}||", inline=False)
                            log_embed.add_field(name="Знайдені слова", value=", ".join(f"`{w}`" for w in found_words[:10]), inline=False)
                            await audit_channel.send(embed=log_embed)
                    return
            except Exception as ex:
                print(f'[AutoMod] Помилка фільтру мату: {ex}')

        # 3. АНТИ-СПАМ (Захист від флуду) — не для адмінів
        if is_admin:
            return
        user_id = message.author.id
        current_time = time.time()

        if user_id not in self.user_messages:
            self.user_messages[user_id] = []
        self.user_messages[user_id].append(current_time)
        self.user_messages[user_id] = [t for t in self.user_messages[user_id] if current_time - t <= self.SPAM_TIME]

        if len(self.user_messages[user_id]) >= self.SPAM_LIMIT:
            self.user_messages[user_id] = []
            await message.delete()
            
            p_msg = await self._apply_punishment(message, 'spam')
            
            if "Мут" in p_msg:
                await message.channel.send(f"🤫 {message.author.mention} отримав **{p_msg}** за спам.", delete_after=10)
            else:
                await message.channel.send(f"⚠️ {message.author.mention}, припиніть спамити! Наступного разу буде мут.", delete_after=10)

            audit_cog = self.bot.get_cog("Audit")
            if audit_cog:
                channel = await audit_cog.get_audit_channel(message.guild)
                if channel:
                    embed = discord.Embed(title="🚫 Анти-спам спрацював", description=f"{message.author.mention} спамив. Покарання: **{p_msg}**", color=discord.Color.orange())
                    await channel.send(embed=embed)
        # 4. ВЕРТИКАЛЬНИЙ СПАМ (літера за літерою)
        # Якщо повідомлення складається з одного символу (крім емодзі/пунктуації)
        clean_content = message.content.strip()
        v_key = (user_id, message.channel.id)
        
        # Дозволяємо адмінам спамити якщо треба (опціонально)
        if len(clean_content) == 1 and not is_admin:
            msg_time = time.time()
            if v_key not in self.vertical_buffers:
                self.vertical_buffers[v_key] = []
            
            # Очищуємо старі записи в буфері
            self.vertical_buffers[v_key] = [item for item in self.vertical_buffers[v_key] if msg_time - item[0] <= self.VERTICAL_TIMEOUT]
            
            # Додаємо поточну літеру
            self.vertical_buffers[v_key].append((msg_time, clean_content, message.id))
            
            # Збираємо слово
            sequence_text = "".join(item[1] for item in self.vertical_buffers[v_key])
            if len(sequence_text) >= 2: # Мінімум 2 літери для перевірки
                normalized_variants = self.normalize_text(sequence_text)
                banned_words = await self.get_banned_words(gid)
                banned_norms = self.get_banned_norms(banned_words)
                white_words = await self.get_white_words(gid)
                
                is_bad = False
                for _, norms_list in banned_norms:
                    for wn in norms_list:
                        for mv in normalized_variants:
                            # Для вертикального спаму завжди вимагаємо startswith або повний збіг
                            if len(wn) <= 3:
                                match = (mv == wn)
                            else:
                                match = (mv == wn or mv.startswith(wn))
                            
                            if match:
                                # Перевірка чи це не біле слово починається так само
                                is_w = False
                                for ww in white_words:
                                    if not ww: continue
                                    if mv == ww or mv.startswith(ww):
                                        is_w = True
                                        break
                                if is_w:
                                    continue
                                is_bad = True
                                break
                        if is_bad: break
                    if is_bad: break

                if is_bad:
                    # Знайшли мат розбитий на частини!
                    # Видаляємо всі повідомлення з буфера
                    msg_ids = [item[2] for item in self.vertical_buffers[v_key]]
                    self.vertical_buffers[v_key] = []
                    
                    for m_id in msg_ids:
                        try:
                            m = await message.channel.fetch_message(m_id)
                            await m.delete()
                        except: pass
                    
                    # Застосовуємо систему покарань (як для мату)
                    p_msg = await self._apply_punishment(message, 'profanity')
                    
                    warning_text = f"⚠️ {message.author.mention}, не намагайтеся обійти фільтр! **{p_msg}**"
                    await message.channel.send(warning_text, delete_after=10)
                    
                    # Логування
                    audit_cog = self.bot.get_cog("Audit")
                    if audit_cog:
                        channel = await audit_cog.get_audit_channel(message.guild)
                        if channel:
                            embed = discord.Embed(title="🚫 Вертикальний спам", color=discord.Color.red())
                            embed.add_field(name="Користувач", value=message.author.mention)
                            embed.add_field(name="Слово", value=f"`{sequence_text}`")
                            embed.add_field(name="Покарання", value=p_msg)
                            await channel.send(embed=embed)
                    return
        else:
            # Якщо повідомлення довше за 1 символ — очищуємо буфер користувача в цьому каналі
            if v_key in self.vertical_buffers:
                del self.vertical_buffers[v_key]

    # ─── Заборонені слова (БД) ────────────────────────────────────────────────

    def is_only_infaos(ctx):
        """Чекає чи користувач має ім'я infaos (тільки він має доступ)."""
        return ctx.author.name == "infaos" or ctx.author.display_name == "infaos"

    @commands.group(name="banword", aliases=["bw"], invoke_without_command=True)
    @commands.check(is_only_infaos)
    async def banword(self, ctx):
        """Управління забороненими словами. Підкоманди: add, remove, list"""
        await ctx.send("📋 Використання: `!banword add <слово>` | `!banword remove <слово>` | `!banword list`")

    @banword.command(name="add")
    @commands.check(is_only_infaos)
    async def banword_add(self, ctx, *, word: str):
        word = word.lower().strip()
        try:
            await self.bot.db.execute(
                'INSERT OR IGNORE INTO banned_words (word, guild_id) VALUES (?, ?)',
                (word, ctx.guild.id)
            )
            await self.bot.db.commit()
            self._word_cache.pop(ctx.guild.id, None)  # Інвалідуємо кеш
            await ctx.send(f"✅ Слово `{word}` додано до фільтру цього серверу.")
        except Exception as e:
            await ctx.send(f"❌ Помилка: {e}")

    @banword.command(name="remove", aliases=["del"])
    @commands.check(is_only_infaos)
    async def banword_remove(self, ctx, *, word: str):
        word = word.lower().strip()
        await self.bot.db.execute(
            'DELETE FROM banned_words WHERE word = ? AND guild_id = ?',
            (word, ctx.guild.id)
        )
        await self.bot.db.commit()
        self._word_cache.pop(ctx.guild.id, None)
        await ctx.send(f"✅ Слово `{word}` видалено з фільтру цього серверу (якщо воно було там).")

    @banword.command(name="list")
    @commands.check(is_only_infaos)
    async def banword_list(self, ctx):
        async with self.bot.db.execute(
            'SELECT word FROM banned_words WHERE guild_id = ?',
            (ctx.guild.id,)
        ) as cursor:
            rows = await cursor.fetchall()
        if not rows:
            await ctx.send("📋 На цьому сервері немає своїх заборонених слів (тільки глобальний список).")
        else:
            words = ", ".join(f"`{r[0]}`" for r in rows)
            await ctx.send(f"📋 Власні заборонені слова цього серверу:\n{words}")

    # ─── Білий список слів (Whitelist) ────────────────────────────────────────

    @commands.group(name="whitelist", aliases=["wl"], invoke_without_command=True)
    @commands.check(is_only_infaos)
    async def whitelist(self, ctx):
        """Управління білим списком слів. Підкоманди: add, remove, list"""
        await ctx.send("📋 Використання: `!whitelist add <слово>` | `!whitelist remove <слово>` | `!whitelist list`")

    @whitelist.command(name="add")
    @commands.check(is_only_infaos)
    async def whitelist_add(self, ctx, *, word: str):
        word = word.lower().strip()
        try:
            await self.bot.db.execute(
                'INSERT OR IGNORE INTO whitelisted_words (word, guild_id) VALUES (?, ?)',
                (word, ctx.guild.id)
            )
            await self.bot.db.commit()
            self._white_cache.pop(ctx.guild.id, None)  # Інвалідуємо кеш
            await ctx.send(f"✅ Слово `{word}` додано до білого списку цього серверу.")
        except Exception as e:
            await ctx.send(f"❌ Помилка: {e}")

    @whitelist.command(name="remove", aliases=["del"])
    @commands.check(is_only_infaos)
    async def whitelist_remove(self, ctx, *, word: str):
        word = word.lower().strip()
        await self.bot.db.execute(
            'DELETE FROM whitelisted_words WHERE word = ? AND guild_id = ?',
            (word, ctx.guild.id)
        )
        await self.bot.db.commit()
        self._white_cache.pop(ctx.guild.id, None)
        await ctx.send(f"✅ Слово `{word}` видалено з білого списку цього серверу (якщо воно було там).")

    @whitelist.command(name="list")
    @commands.check(is_only_infaos)
    async def whitelist_list(self, ctx):
        async with self.bot.db.execute(
            'SELECT word FROM whitelisted_words WHERE guild_id = ?',
            (ctx.guild.id,)
        ) as cursor:
            rows = await cursor.fetchall()
        if not rows:
            await ctx.send("📋 На цьому сервері немає слів у білому списку.")
        else:
            words = ", ".join(f"`{r[0]}`" for r in rows)
            await ctx.send(f"📋 Білий список слів цього серверу:\n{words}")

    # ─── Виключення каналів ───────────────────────────────────────────────────

    @commands.command(name="filterexclude", aliases=["фільтрвимк"], help="Вимкнути фільтр мату в каналі")
    @commands.check(is_only_infaos)
    async def filter_exclude(self, ctx, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        try:
            await self.bot.db.execute(
                'INSERT OR IGNORE INTO automod_excluded_channels (channel_id, guild_id) VALUES (?, ?)',
                (channel.id, ctx.guild.id)
            )
            await self.bot.db.commit()
            self._excluded_cache.pop(ctx.guild.id, None)
            await ctx.send(f"✅ Фільтр мату **вимкнено** в {channel.mention}.")
        except Exception as e:
            await ctx.send(f"❌ Помилка: {e}")

    @commands.command(name="filterinclude", aliases=["фільтрувімк"], help="Увімкнути фільтр мату в каналі")
    @commands.check(is_only_infaos)
    async def filter_include(self, ctx, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        await self.bot.db.execute(
            'DELETE FROM automod_excluded_channels WHERE channel_id = ? AND guild_id = ?',
            (channel.id, ctx.guild.id)
        )
        await self.bot.db.commit()
        self._excluded_cache.pop(ctx.guild.id, None)
        await ctx.send(f"✅ Фільтр мату **увімкнено** в {channel.mention}.")

    @commands.command(name="filterchannels", aliases=["фільтрканали"], help="Список каналів де фільтр вимкнено")
    @commands.check(is_only_infaos)
    async def filter_channels(self, ctx):
        async with self.bot.db.execute(
            'SELECT channel_id FROM automod_excluded_channels WHERE guild_id = ?',
            (ctx.guild.id,)
        ) as cursor:
            rows = await cursor.fetchall()
        if not rows:
            await ctx.send("✅ Фільтр активний у всіх каналах.")
        else:
            channels = ", ".join(f"<#{r[0]}>" for r in rows)
            await ctx.send(f"🔇 Фільтр **вимкнено** в: {channels}")


async def setup(bot):
    await bot.add_cog(AutoMod(bot))
