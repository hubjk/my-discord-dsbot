import discord
from discord.ext import commands
import asyncio

class TicketCloseView(discord.ui.View):
    def __init__(self):
        # timeout=None означає, що кнопка не пропаде з часом
        super().__init__(timeout=None)
        
    @discord.ui.button(label="Закрити тікет", style=discord.ButtonStyle.red, custom_id="close_ticket_btn", emoji="🔒")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Зберігаємо лог та закриваємо тікет через 5 секунд...", ephemeral=False)
        
        # Збереження історії повідомлень (транскрипт)
        import io
        transcript = f"Лoг тікета: {interaction.channel.name}\nЗакрито користувачем: {interaction.user.display_name}\n\n"
        
        # Проходимося по повідомленнях з кінця в початок
        messages = [message async for message in interaction.channel.history(limit=None, oldest_first=True)]
        for msg in messages:
            time_str = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
            transcript += f"[{time_str}] {msg.author.display_name}: {msg.content}\n"
            if msg.attachments:
                transcript += f"  [Вкладення]: {', '.join([a.url for a in msg.attachments])}\n"
                
        # Створюємо файл в пам'яті
        file_bytes = io.BytesIO(transcript.encode('utf-8'))
        discord_file = discord.File(fp=file_bytes, filename=f"transcript_{interaction.channel.name}.txt")
        
        # Намагаємося відправити лог в приватні повідомлення тому, хто закрив
        try:
            await interaction.user.send(f"Тікет `{interaction.channel.name}` закрито. Ось лог розмови:", file=discord_file)
        except discord.Forbidden:
            pass # Якщо приватні закриті - нічого не робимо
            
        await asyncio.sleep(5)
        # Видаляємо канал
        await interaction.channel.delete()

class TicketCreateView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        
    @discord.ui.button(label="Створити тікет", style=discord.ButtonStyle.blurple, custom_id="create_ticket_btn", emoji="🎫")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        user = interaction.user
        
        # Перевіряємо чи вже є категорія "Тікети", якщо ні - створюємо
        category = discord.utils.get(guild.categories, name="Тікети")
        if not category:
            category = await guild.create_category("Тікети")
            
        # Перевіряємо чи вже існує тікет цього користувача
        safe_name = "".join(c for c in user.name if c.isalnum() or c in ('-', '_')).lower()
        if not safe_name:
            safe_name = str(user.id)
        existing = discord.utils.get(category.channels, name=f"тікет-{safe_name}") if category else None
        if existing:
            await interaction.response.send_message(
                f"❌ У вас вже є відкритий тікет: {existing.mention}\nЗакрийте попередній перш ніж відкривати новий.",
                ephemeral=True
            )
            return
        
        # Не знайдено — створюємо новий тікет
        # Налаштовуємо права доступу: всім не можна читати, юзеру можна
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }
        
        mute_role = discord.utils.get(guild.roles, name="Muted")
        if mute_role:
            # Для ролі Muted скасовуємо заборону на написання повідомлень
            # (оскільки read_messages вже контролюється role доступом юзера, 
            # нам важливо тільки дати йому можливість говорити в цьому каналі)
            overwrites[mute_role] = discord.PermissionOverwrite(send_messages=True)
        
        ticket_channel = await guild.create_text_channel(
            name=f"тікет-{safe_name}",
            category=category,
            overwrites=overwrites
        )
        
        # Відповідаємо користувачу (повідомлення бачить тільки він), що канал створено
        await interaction.response.send_message(f"Ваш тікет створено: {ticket_channel.mention}", ephemeral=True)
        
        # Відправляємо перше повідомлення в сам канал тікета з кнопкою Закрити
        embed = discord.Embed(
            title="Новий тікет",
            description=f"Вітаємо, {user.mention}!\nОпишіть вашу проблему, і адміністрація сервру скоро вам відповість.",
            color=discord.Color.green()
        )
        await ticket_channel.send(content=user.mention, embed=embed, view=TicketCloseView())

class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Реєструємо Views, щоб кнопки працювали навіть після перезапуску бота
        self.bot.add_view(TicketCreateView())
        self.bot.add_view(TicketCloseView())

    @commands.command(name="ticket_setup", help="Створити панель створення тікетів (лише для адміністраторів)")
    @commands.has_permissions(administrator=True)
    async def ticket_setup(self, ctx):
        embed = discord.Embed(
            title="🎫 Звернення до підтримки",
            description="Якщо у вас виникли питання, скарги або пропозиції, натисніть кнопку нижче, щоб створити приватний тікет. Його побачите лише ви та адміністрація.",
            color=discord.Color.blue()
        )
        embed.set_footer(text="Відкривайте тікет лише за необхідністю.")
        await ctx.send(embed=embed, view=TicketCreateView())

async def setup(bot):
    await bot.add_cog(Tickets(bot))
