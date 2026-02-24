import discord
from discord.ext import commands

class CustomHelpCommand(commands.HelpCommand):
    def __init__(self):
        super().__init__(command_attrs={
            'help': 'Показує це повідомлення з усіма командами',
            'aliases': ['допомога', 'меню']
        })

    async def send_bot_help(self, mapping):
        embed = discord.Embed(
            title="📚 Меню Команд Бота",
            description="Ось список усіх доступних команд. Використовуйте `!help <команда>` для деталей.",
            color=discord.Color.blurple()
        )
        
        # Mapping містить словник {cog: [commands]}
        for cog, cmds in mapping.items():
            filtered = await self.filter_commands(cmds, sort=True)
            if filtered:
                # Отримуємо назву категорії (Cog)
                cog_name = getattr(cog, "qualified_name", "Інші команди")
                
                # Додаємо красиві емодзі до назв категорій
                emojis = {
                    "Admin": "🛠️ Адміністрування",
                    "Moderation": "🛡️ Модерація",
                    "Tickets": "🎫 Тікети",
                    "Reactions": "🎭 Ролі за реакціями",
                    "Levels": "📈 Система Рівнів",
                    "Economy": "💰 Економіка",
                    "Games": "🎲 Ігри",
                    "AIChat": "🤖 Штучний Інтелект"
                }
                
                display_name = emojis.get(cog_name, f"📁 {cog_name}")
                
                # Формуємо список команд: `!команда` - опис
                cmd_list = "\n".join([f"`{self.context.clean_prefix}{c.name}` - {c.help or 'Без опису'}" for c in filtered])
                embed.add_field(name=display_name, value=cmd_list, inline=False)

        embed.set_footer(text=f"Викликав: {self.context.author.display_name}", icon_url=self.context.author.display_avatar.url if self.context.author.display_avatar else None)
        await self.context.send(embed=embed)

    async def send_command_help(self, command):
        """Викликається коли пишуть !help <назва_команди>"""
        embed = discord.Embed(
            title=f"📖 Команда: {self.context.clean_prefix}{command.name}",
            description=command.help or "Опис відсутній",
            color=discord.Color.green()
        )
        
        if command.aliases:
            embed.add_field(name="Синоніми (можна писати замість основної назви):", value=", ".join([f"`{a}`" for a in command.aliases]), inline=False)
            
        # Додаємо інформацію про використання команди (аргументи)
        usage = f"`{self.context.clean_prefix}{command.name} {command.signature}`"
        embed.add_field(name="Як використовувати:", value=usage, inline=False)

        await self.context.send(embed=embed)
        
    async def send_cog_help(self, cog):
        """Не обов'язкове, але можна додати якщо пишуть !help <Категорія>"""
        pass

    async def send_group_help(self, group):
        """Для груп команд (наприклад !ticket open)"""
        pass
