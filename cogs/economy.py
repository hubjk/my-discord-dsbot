import discord
from discord.ext import commands
from discord import app_commands
import random
import time
from datetime import datetime, timedelta

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

    # ─── Slash Команди ─────────────────────────────────────────────────────────────

    @app_commands.command(name="work", description="Заробити монети (кулдаун 1 год)")
    async def work(self, interaction: discord.Interaction):
        uid, gid = interaction.user.id, interaction.guild_id
        await self.get_or_create_user(uid, gid)

        last = await self.get_cooldown(uid, gid, 'last_work')
        remaining = WORK_COOLDOWN - (time.time() - last)
        if remaining > 0:
            m, s = int(remaining) // 60, int(remaining) % 60
            await interaction.response.send_message(f"⏳ Ти вже працював нещодавно! Відпочинь ще **{m}хв {s}с**.", ephemeral=True)
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
        await interaction.response.send_message(f"💼 {interaction.user.mention} {random.choice(jobs)} і заробив **{earned} 🪙 монет**!", ephemeral=True)

    @app_commands.command(name="daily", description="Щоденна нагорода (скидається о 00:00)")
    async def daily(self, interaction: discord.Interaction):
        uid, gid = interaction.user.id, interaction.guild_id
        await self.get_or_create_user(uid, gid)

        last_ts = await self.get_cooldown(uid, gid, 'last_daily')
        today = datetime.now().date()

        if last_ts:
            last_date = datetime.fromtimestamp(last_ts).date()
            if last_date >= today:
                # Рахуємо скільки до 00:00 наступного дня
                tomorrow = datetime.combine(today + timedelta(days=1), datetime.min.time())
                remaining = int((tomorrow - datetime.now()).total_seconds())
                h, m = remaining // 3600, (remaining % 3600) // 60
                await interaction.response.send_message(f"⏳ Ти вже отримав щоденну нагороду сьогодні! Повертайся о **00:00** (через **{h}год {m}хв**).", ephemeral=True)
                return

        reward = random.randint(DAILY_REWARD_MIN, DAILY_REWARD_MAX)
        await self.bot.db.execute(
            'UPDATE users SET balance = balance + ? WHERE user_id = ? AND guild_id = ?',
            (reward, uid, gid)
        )
        await self.set_cooldown(uid, gid, 'last_daily')

        embed = discord.Embed(
            title="🎁 Щоденна нагорода",
            description=f"{interaction.user.mention}, ти отримав **{reward} 🪙 монет**!\nПовертайся завтра о **00:00** за новою нагородою.",
            color=discord.Color.gold()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="balance", description="Перевірити баланс (свій або чужий)")
    async def balance(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user
        bal = await self.get_or_create_user(member.id, interaction.guild_id)

        embed = discord.Embed(title=f"💰 Баланс {member.display_name}", color=discord.Color.gold())
        embed.add_field(name="Гаманець:", value=f"**{bal} 🪙 монет**")
        if member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="pay", description="Переказати монети іншому (комісія 5%)")
    async def pay(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        if member == interaction.user:
            await interaction.response.send_message("❌ Не можна переказати монети собі!", ephemeral=True)
            return
        if amount <= 0:
            await interaction.response.send_message("❌ Сума має бути більше 0.", ephemeral=True)
            return

        fee = max(1, round(amount * 0.05))  # 5% комісія, мінімум 1 монета
        total_cost = amount + fee

        uid, gid = interaction.user.id, interaction.guild_id
        balance = await self.get_or_create_user(uid, gid)

        if balance < total_cost:
            await interaction.response.send_message(
                f"💸 Недостатньо коштів!\n"
                f"Потрібно: **{amount} 🪙** + комісія **{fee} 🪙** = **{total_cost} 🪙**\n"
                f"У вас: **{balance} 🪙**", 
                ephemeral=True
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

        await interaction.response.send_message(
            f"✅ {interaction.user.mention} переказав **{amount} 🪙** → {member.mention}\n"
            f"💸 Комісія: **{fee} 🪙** (5%) | Списано всього: **{total_cost} 🪙**"
        )

    @app_commands.command(name="leaderboard_eco", description="Топ 10 найбагатших учасників")
    async def leaderboard_eco(self, interaction: discord.Interaction):
        async with self.bot.db.execute(
            'SELECT user_id, balance FROM users WHERE guild_id = ? ORDER BY balance DESC LIMIT 10',
            (interaction.guild_id,)
        ) as cursor:
            rows = await cursor.fetchall()

        if not rows:
            await interaction.response.send_message("📊 Поки що нема даних.", ephemeral=True)
            return

        medals = ["🥇", "🥈", "🥉"]
        lines = []
        for i, (uid, bal) in enumerate(rows):
            member = interaction.guild.get_member(uid)
            name = member.display_name if member else f"Користувач #{uid}"
            medal = medals[i] if i < 3 else f"`{i+1}.`"
            lines.append(f"{medal} **{name}** — {bal} 🪙")

        embed = discord.Embed(
            title="💰 Топ 10 найбагатших",
            description="\n".join(lines),
            color=discord.Color.gold()
        )
        # Leaderboards can be public since it's fun to look at, but optional
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="shop", description="Магазин сервера")
    async def shop(self, interaction: discord.Interaction):
        async with self.bot.db.execute(
            'SELECT id, name, price, role_name FROM shop_items WHERE guild_id = ?',
            (interaction.guild_id,)
        ) as cursor:
            items = await cursor.fetchall()

        embed = discord.Embed(
            title="🛒 Магазин сервера",
            description="Використовуйте `/buy` для покупки",
            color=discord.Color.green()
        )
        if not items:
            embed.description = "Магазин поки що порожній! Адміністратори можуть додати товари командою `/additem`."
        else:
            for item_id, name, price, role_name in items:
                embed.add_field(
                    name=f"{name} (ID: **{item_id}**)",
                    value=f"Ціна: **{price} 🪙**\nДає роль: `@{role_name}`",
                    inline=False
                )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="buy", description="Купити товар в магазині")
    async def buy(self, interaction: discord.Interaction, item_id: str):
        item_id = item_id.lower()

        async with self.bot.db.execute(
            'SELECT name, price, role_name FROM shop_items WHERE id = ? AND guild_id = ?',
            (item_id, interaction.guild_id)
        ) as cursor:
            item = await cursor.fetchone()

        if not item:
            await interaction.response.send_message("❌ Такого товару не існує! Введіть `/shop` щоб побачити список товарів.", ephemeral=True)
            return

        name, price, role_name = item
        balance = await self.get_or_create_user(interaction.user.id, interaction.guild_id)

        if balance < price:
            await interaction.response.send_message(f"💸 У вас недостатньо коштів! Потрібно: **{price} 🪙**, у вас: **{balance} 🪙**.", ephemeral=True)
            return

        role = discord.utils.get(interaction.guild.roles, name=role_name)
        if not role:
            await interaction.response.send_message(f"⚠️ Помилка: На сервері не знайдено роль `{role_name}`. Попросіть адміністратора її створити.", ephemeral=True)
            return

        if role in interaction.user.roles:
            await interaction.response.send_message("❌ Ви вже маєте цю роль!", ephemeral=True)
            return

        try:
            await interaction.user.add_roles(role)
            await self.bot.db.execute(
                'UPDATE users SET balance = balance - ? WHERE user_id = ? AND guild_id = ?',
                (price, interaction.user.id, interaction.guild_id)
            )
            await self.bot.db.commit()
            await interaction.response.send_message(f"🎉 Вітаємо, {interaction.user.mention}! Ви придбали **{name}** за {price} 🪙!")
        except discord.Forbidden:
            await interaction.response.send_message("❌ У бота немає прав видавати цю роль. Його роль має бути вище в ієрархії.", ephemeral=True)

    @app_commands.command(name="additem", description="Додати товар в магазин (Лише адміністратори)")
    @app_commands.default_permissions(administrator=True)
    async def add_item(self, interaction: discord.Interaction, item_id: str, price: int, role: discord.Role, display_name: str):
        item_id = item_id.lower()
        role_name = role.name

        try:
            await self.bot.db.execute(
                'INSERT INTO shop_items (id, guild_id, name, price, role_name) VALUES (?, ?, ?, ?, ?)',
                (item_id, interaction.guild_id, display_name, price, role_name)
            )
            await self.bot.db.commit()
            await interaction.response.send_message(f"✅ Товар **{display_name}** додано до магазину! ID: `{item_id}` | Ціна: {price} 🪙 | Роль: {role.mention}", ephemeral=True)
        except Exception:
            await interaction.response.send_message(f"❌ Помилка: товар з ID `{item_id}` вже існує.", ephemeral=True)

    @app_commands.command(name="removeitem", description="Видалити товар з магазину за ID (Лише адміністратори)")
    @app_commands.default_permissions(administrator=True)
    async def remove_item(self, interaction: discord.Interaction, item_id: str):
        item_id = item_id.lower()
        async with self.bot.db.execute(
            'DELETE FROM shop_items WHERE id = ? AND guild_id = ?',
            (item_id, interaction.guild_id)
        ) as cursor:
            deleted = cursor.rowcount > 0
        await self.bot.db.commit()

        if deleted:
            await interaction.response.send_message(f"✅ Товар з ID `{item_id}` видалено з магазину.", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ Товар з ID `{item_id}` не знайдено.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Economy(bot))
