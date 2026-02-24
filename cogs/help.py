import discord
from discord.ext import commands

# ─── Категорії та їхні команди ───────────────────────────────────────────────
CATEGORIES = {
    "🛡️ Модерація": {
        "emoji": "🛡️",
        "color": discord.Color.red(),
        "admin_only": True,
        "commands": [
            ("ban", "Забанити учасника"),
            ("kick", "Вигнати учасника"),
            ("mute", "Замутити учасника"),
            ("unmute", "Розмутити учасника"),
            ("clear", "Очистити повідомлення"),
            ("warn", "Видати варн"),
            ("warnings", "Переглянути варни"),
            ("clearwarns", "Видалити варни"),
        ]
    },
    "🛠️ Адмін": {
        "emoji": "🛠️",
        "color": discord.Color.orange(),
        "admin_only": True,
        "commands": [
            ("setprefix", "Змінити префікс"),
            ("additem", "Додати товар у магазин"),
            ("removeitem", "Видалити товар з магазину"),
            ("gcreate", "Створити розіграш"),
            ("ticket_setup", "Встановити панель тікетів"),
            ("setup_reactions", "Встановити реакції-ролі"),
        ]
    },
    "🤖 Автомодератор": {
        "emoji": "🤖",
        "color": discord.Color.dark_orange(),
        "admin_only": True,
        "commands": [
            ("banword add", "Додати слово до фільтру"),
            ("banword remove", "Видалити слово з фільтру"),
            ("banword list", "Список заборонених слів"),
            ("filterexclude", "Вимкнути фільтр мату в каналі"),
            ("filterinclude", "Увімкнути фільтр мату в каналі"),
            ("filterchannels", "Список каналів без фільтру"),
        ]
    },
    "📈 Рівні": {
        "emoji": "📈",
        "color": discord.Color.green(),
        "admin_only": False,
        "commands": [
            ("level", "Ваш рівень та XP"),
            ("leaderboard", "Топ учасників"),
            ("rank", "Карточка рейтингу"),
        ]
    },
    "💰 Економіка": {
        "emoji": "💰",
        "color": discord.Color.gold(),
        "admin_only": False,
        "commands": [
            ("balance", "Ваш баланс"),
            ("daily", "Щоденна нагорода"),
            ("shop", "Магазин"),
            ("buy", "Купити товар"),
            ("pay", "Переказати монети"),
            ("leaderboard_eco", "Топ багатіїв"),
        ]
    },
    "🎵 Музика": {
        "emoji": "🎵",
        "color": discord.Color.purple(),
        "admin_only": False,
        "commands": [
            ("play / p", "Відтворити пісню з YouTube"),
            ("skip / s", "Пропустити трек"),
            ("queue / q", "Черга відтворення"),
            ("history / his", "Останні 20 пісень"),
            ("pause", "Пауза"),
            ("resume", "Продовжити"),
            ("stop", "Зупинити та вийти"),
            ("join", "Зайти в канал"),
        ]
    },
    "🎲 Ігри": {
        "emoji": "🎲",
        "color": discord.Color.teal(),
        "admin_only": False,
        "commands": [
            ("coinflip", "Орел чи решка"),
            ("dice", "Кинути кубик"),
            ("rps", "Камінь-ножиці-папір"),
            ("quiz", "Вікторина"),
        ]
    },
    "🎫 Тікети": {
        "emoji": "🎫",
        "color": discord.Color.blue(),
        "admin_only": False,
        "commands": [
            ("ticket_setup", "Панель тікетів"),
        ]
    },
    "🎁 Розіграші": {
        "emoji": "🎁",
        "color": discord.Color.magenta(),
        "admin_only": False,
        "commands": [
            ("gcreate", "Створити розіграш"),
            ("groll", "Пере-вибрати переможця"),
        ]
    },
    "📊 Основне": {
        "emoji": "📊",
        "color": discord.Color.blue(),
        "admin_only": False,
        "commands": [
            ("ping", "Перевірити затримку бота"),
            ("serverinfo", "Інформація про сервер"),
        ]
    }
}

def is_admin_or_infaos(ctx):
    if ctx.author.name == "infaos" or ctx.author.display_name == "infaos":
        return True
    if ctx.guild and ctx.guild.owner_id == ctx.author.id:
        return True
    if ctx.author.guild_permissions.administrator:
        return True
    return False

class CategorySelect(discord.ui.Select):
    def __init__(self, allowed_categories):
        options = [
            discord.SelectOption(label=name, emoji=data["emoji"], description=f"{len(data['commands'])} команд")
            for name, data in CATEGORIES.items() if name in allowed_categories
        ]
        super().__init__(
            placeholder="Оберіть категорію...",
            min_values=1, max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        data = CATEGORIES[selected]
        
        lines = "\n".join(f"`!{cmd}` — {desc}" for cmd, desc in data["commands"])
        embed = discord.Embed(
            title=f"{selected}",
            description=lines,
            color=data["color"]
        )
        embed.set_footer(text="Натисніть на категорію ще раз, щоб переключити")
        await interaction.response.edit_message(embed=embed, view=self.view)

class HelpView(discord.ui.View):
    def __init__(self, allowed_categories):
        super().__init__(timeout=30)
        self.add_item(CategorySelect(allowed_categories))
        self.message = None  # зберігаємо посилання щоб видалити на таймаут

    async def on_timeout(self):
        try:
            if self.message:
                await self.message.delete()
        except Exception:
            pass

class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def get_allowed_categories(self, ctx):
        is_privileged = is_admin_or_infaos(ctx)
        allowed = []
        for name, data in CATEGORIES.items():
            if data.get("admin_only", False) and not is_privileged:
                continue
            allowed.append(name)
        return allowed

    @commands.command(name="help", aliases=["допомога", "меню", "h"], help="Інтерактивне меню команд бота")
    async def help_new(self, ctx):
        allowed = self.get_allowed_categories(ctx)
        
        embed = discord.Embed(
            title="📋 Меню команд Помічниці",
            description=(
                "Оберіть **категорію** з меню нижче, щоб переглянути список команд.\n\n"
                "**Категорії:**\n"
                + " ".join(f"`{CATEGORIES[name]['emoji']}`" for name in allowed)
            ),
            color=discord.Color.blurple()
        )
        embed.set_footer(text=f"Запит від {ctx.author.display_name} • Меню активне 30 секунд")
        if ctx.author.display_avatar:
            embed.set_thumbnail(url=ctx.author.display_avatar.url)
        
        view = HelpView(allowed)
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg  # зберігаємо посилання для видалення

    @commands.command(name="ohelp", aliases=["oldhelp"], help="Стара версія меню команд")
    async def help_old(self, ctx):
        """Стара текстова версія меню команд"""
        allowed = self.get_allowed_categories(ctx)
        embed = discord.Embed(
            title="📚 Меню Команд (повний список)",
            description="Список усіх команд за категоріями.",
            color=discord.Color.blurple()
        )
        for name in allowed:
            data = CATEGORIES[name]
            cmd_list = "\n".join(f"`!{cmd}` — {desc}" for cmd, desc in data["commands"])
            embed.add_field(name=name, value=cmd_list, inline=False)
        embed.set_footer(text=f"Викликав: {ctx.author.display_name}")
        await ctx.send(embed=embed)

async def setup(bot):
    # Вимикаємо вбудований help щоб не конфліктував
    bot.remove_command("help")
    await bot.add_cog(Help(bot))
