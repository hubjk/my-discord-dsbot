import discord
from discord.ext import commands
import random
import time

WORK_COOLDOWN = 3600       # 1 година
DAILY_COOLDOWN = 86400     # 24 години
DAILY_REWARD_MIN = 200
DAILY_REWARD_MAX = 500
WORK_REWARD_MIN = 50
WORK_REWARD_MAX = 200

class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ─── Хелпери ─────────────────────────────────────────────────────────────

    async def get_or_create_user(self, user_id, guild_id):
        async with self.bot.db.execute(
            'SELECT balance FROM users WHERE user_id = ? AND guild_id = ?',
            (user_id, guild_id)
        ) as cursor:
            result = await cursor.fetchone()
        if result is None:
            await self.bot.db.execute(
                'INSERT INTO users (user_id, guild_id, balance) VALUES (?, ?, ?)',
                (user_id, guild_id, 0)
            )
            await self.bot.db.commit()
            return 0
        return result[0]

    async def get_cooldown(self, user_id, guild_id, col):
        """Повертає timestamps останньої дії для конкретної колонки (last_work / last_daily)."""
        async with self.bot.db.execute(
            f'SELECT {col} FROM users WHERE user_id = ? AND guild_id = ?',
            (user_id, guild_id)
        ) as cursor:
            row = await cursor.fetchone()
        return row[0] if row and row[0] else 0

    async def set_cooldown(self, user_id, guild_id, col):
        await self.bot.db.execute(
            f'UPDATE users SET {col} = ? WHERE user_id = ? AND guild_id = ?',
            (int(time.time()), user_id, guild_id)
        )
        await self.bot.db.commit()

    # ─── Команди ─────────────────────────────────────────────────────────────

    @commands.command(name="work", aliases=["робота", "працювати"], help="Заробити монети (кулдаун 1 год)")
    async def work(self, ctx):
        uid, gid = ctx.author.id, ctx.guild.id
        await self.get_or_create_user(uid, gid)

        last = await self.get_cooldown(uid, gid, 'last_work')
        remaining = WORK_COOLDOWN - (time.time() - last)
        if remaining > 0:
            m, s = int(remaining) // 60, int(remaining) % 60
            await ctx.send(f"⏳ Ти вже працював нещодавно! Відпочинь ще **{m}хв {s}с**.")
            return

        earned = random.randint(WORK_REWARD_MIN, WORK_REWARD_MAX)
        await self.bot.db.execute(
            'UPDATE users SET balance = balance + ? WHERE user_id = ? AND guild_id = ?',
            (earned, uid, gid)
        )
        await self.set_cooldown(uid, gid, 'last_work')

        jobs = [
            "розвантажив вагони", "написав код для бота",
            "продав старий комп'ютер", "помив вікна",
            "попрацював барістою", "зібрав врожай",
            "провів лекцію", "доставив посилки",
        ]
        await ctx.send(f"💼 {ctx.author.mention} {random.choice(jobs)} і заробив **{earned} 🪙 монет**!")

    @commands.command(name="daily", aliases=["щоденна", "дейлі"], help="Щоденна нагорода (скидається о 00:00)")
    async def daily(self, ctx):
        from datetime import datetime, timezone
        uid, gid = ctx.author.id, ctx.guild.id
        await self.get_or_create_user(uid, gid)

        last_ts = await self.get_cooldown(uid, gid, 'last_daily')
        today = datetime.now().date()

        if last_ts:
            last_date = datetime.fromtimestamp(last_ts).date()
            if last_date >= today:
                # Рахуємо скільки до 00:00 наступного дня
                from datetime import timedelta
                tomorrow = datetime.combine(today + timedelta(days=1), datetime.min.time())
                remaining = int((tomorrow - datetime.now()).total_seconds())
                h, m = remaining // 3600, (remaining % 3600) // 60
                await ctx.send(f"⏳ Ти вже отримав щоденну нагороду сьогодні! Повертайся о **00:00** (через **{h}год {m}хв**).")
                return

        reward = random.randint(DAILY_REWARD_MIN, DAILY_REWARD_MAX)
        await self.bot.db.execute(
            'UPDATE users SET balance = balance + ? WHERE user_id = ? AND guild_id = ?',
            (reward, uid, gid)
        )
        await self.set_cooldown(uid, gid, 'last_daily')

        embed = discord.Embed(
            title="🎁 Щоденна нагорода",
            description=f"{ctx.author.mention}, ти отримав **{reward} 🪙 монет**!\nПовертайся завтра о **00:00** за новою нагородою.",
            color=discord.Color.gold()
        )
        await ctx.send(embed=embed)

    @commands.command(name="balance", aliases=["bal", "баланс", "кошелек"], help="Перевірити баланс")
    async def balance(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        bal = await self.get_or_create_user(member.id, ctx.guild.id)

        embed = discord.Embed(title=f"💰 Баланс {member.display_name}", color=discord.Color.gold())
        embed.add_field(name="Гаманець:", value=f"**{bal} 🪙 монет**")
        if member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(name="pay", aliases=["переказ", "перерахувати"], help="Переказати монети іншому (комісія 5%). Приклад: !pay @user 100")
    async def pay(self, ctx, member: discord.Member, amount: int):
        if member == ctx.author:
            await ctx.send("❌ Не можна переказати монети собі!")
            return
        if amount <= 0:
            await ctx.send("❌ Сума має бути більше 0.")
            return

        fee = max(1, round(amount * 0.05))  # 5% комісія, мінімум 1 монета
        total_cost = amount + fee

        uid, gid = ctx.author.id, ctx.guild.id
        balance = await self.get_or_create_user(uid, gid)

        if balance < total_cost:
            await ctx.send(
                f"💸 Недостатньо коштів!\n"
                f"Потрібно: **{amount} 🪙** + комісія **{fee} 🪙** = **{total_cost} 🪙**\n"
                f"У вас: **{balance} 🪙**"
            )
            return

        await self.get_or_create_user(member.id, gid)
        await self.bot.db.execute(
            'UPDATE users SET balance = balance - ? WHERE user_id = ? AND guild_id = ?',
            (total_cost, uid, gid)
        )
        await self.bot.db.execute(
            'UPDATE users SET balance = balance + ? WHERE user_id = ? AND guild_id = ?',
            (amount, member.id, gid)
        )
        await self.bot.db.commit()

        await ctx.send(
            f"✅ {ctx.author.mention} переказав **{amount} 🪙** → {member.mention}\n"
            f"💸 Комісія: **{fee} 🪙** (5%) | Списано всього: **{total_cost} 🪙**"
        )

    @commands.command(name="leaderboard_eco", aliases=["лідери_еко", "топ_монет", "richest"], help="Топ 10 найбагатших учасників")
    async def leaderboard_eco(self, ctx):
        async with self.bot.db.execute(
            'SELECT user_id, balance FROM users WHERE guild_id = ? ORDER BY balance DESC LIMIT 10',
            (ctx.guild.id,)
        ) as cursor:
            rows = await cursor.fetchall()

        if not rows:
            await ctx.send("📊 Поки що нема даних.")
            return

        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for i, (uid, bal) in enumerate(rows):
            member = ctx.guild.get_member(uid)
            name = member.display_name if member else f"Користувач #{uid}"
            medal = medals[i] if i < 3 else f"`{i+1}.`"
            lines.append(f"{medal} **{name}** — {bal} 🪙")

        embed = discord.Embed(
            title="💰 Топ 10 найбагатших",
            description="\n".join(lines),
            color=discord.Color.gold()
        )
        await ctx.send(embed=embed)

    @commands.command(name="shop", aliases=["магазин", "крамниця"], help="Магазин сервера")
    async def shop(self, ctx):
        async with self.bot.db.execute(
            'SELECT id, name, price, role_name FROM shop_items WHERE guild_id = ?',
            (ctx.guild.id,)
        ) as cursor:
            items = await cursor.fetchall()

        embed = discord.Embed(
            title="🛒 Магазин сервера",
            description="Використовуйте `!buy [id]` для покупки",
            color=discord.Color.green()
        )
        if not items:
            embed.description = "Магазин поки що порожній! Адміністратори можуть додати товари командою `!additem`."
        else:
            for item_id, name, price, role_name in items:
                embed.add_field(
                    name=f"{name} (ID: **{item_id}**)",
                    value=f"Ціна: **{price} 🪙**\nДає роль: `@{role_name}`",
                    inline=False
                )
        await ctx.send(embed=embed)

    @commands.command(name="buy", aliases=["купити"], help="Купити товар в магазині. Приклад: !buy vip")
    async def buy(self, ctx, item_id: str):
        item_id = item_id.lower()

        async with self.bot.db.execute(
            'SELECT name, price, role_name FROM shop_items WHERE id = ? AND guild_id = ?',
            (item_id, ctx.guild.id)
        ) as cursor:
            item = await cursor.fetchone()

        if not item:
            await ctx.send("❌ Такого товару не існує! Введіть `!shop` щоб побачити список товарів.")
            return

        name, price, role_name = item
        balance = await self.get_or_create_user(ctx.author.id, ctx.guild.id)

        if balance < price:
            await ctx.send(f"💸 У вас недостатньо коштів! Потрібно: **{price} 🪙**, у вас: **{balance} 🪙**.")
            return

        role = discord.utils.get(ctx.guild.roles, name=role_name)
        if not role:
            await ctx.send(f"⚠️ Помилка: На сервері не знайдено роль `{role_name}`. Попросіть адміністратора її створити.")
            return

        if role in ctx.author.roles:
            await ctx.send("❌ Ви вже маєте цю роль!")
            return

        try:
            await ctx.author.add_roles(role)
            await self.bot.db.execute(
                'UPDATE users SET balance = balance - ? WHERE user_id = ? AND guild_id = ?',
                (price, ctx.author.id, ctx.guild.id)
            )
            await self.bot.db.commit()
            await ctx.send(f"🎉 Вітаємо, {ctx.author.mention}! Ви придбали **{name}** за {price} 🪙!")
        except discord.Forbidden:
            await ctx.send("❌ У бота немає прав видавати цю роль. Його роль має бути вище в ієрархії.")

    @commands.command(name="additem", help="Додати товар в магазин. Роль ПОВИННА існувати. Приклад: !additem vip 500 VIP Преміум VIP")
    @commands.has_permissions(administrator=True)
    async def add_item(self, ctx, item_id: str, price: int, role_name: str, *, display_name: str):
        item_id = item_id.lower()
        role = discord.utils.get(ctx.guild.roles, name=role_name)

        if not role:
            await ctx.send(f"❌ Роль `{role_name}` не знайдена на сервері. Спочатку створіть роль, потім додавайте товар.")
            return

        try:
            await self.bot.db.execute(
                'INSERT INTO shop_items (id, guild_id, name, price, role_name) VALUES (?, ?, ?, ?, ?)',
                (item_id, ctx.guild.id, display_name, price, role_name)
            )
            await self.bot.db.commit()
            await ctx.send(f"✅ Товар **{display_name}** додано до магазину! ID: `{item_id}` | Ціна: {price} 🪙 | Роль: @{role_name}")
        except Exception:
            await ctx.send(f"❌ Помилка: товар з ID `{item_id}` вже існує.")

    @commands.command(name="removeitem", help="Видалити товар з магазину за ID")
    @commands.has_permissions(administrator=True)
    async def remove_item(self, ctx, item_id: str):
        item_id = item_id.lower()
        async with self.bot.db.execute(
            'DELETE FROM shop_items WHERE id = ? AND guild_id = ?',
            (item_id, ctx.guild.id)
        ) as cursor:
            deleted = cursor.rowcount > 0
        await self.bot.db.commit()

        if deleted:
            await ctx.send(f"✅ Товар з ID `{item_id}` видалено з магазину.")
        else:
            await ctx.send(f"❌ Товар з ID `{item_id}` не знайдено.")

async def setup(bot):
    await bot.add_cog(Economy(bot))
