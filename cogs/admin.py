import discord
from discord.ext import commands

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="ping", help="Перевірити затримку бота", aliases=["пінг"])
    async def ping(self, ctx):
        latency = round(self.bot.latency * 1000)
        await ctx.send(f"🏓 Pong! Затримка: `{latency}мс`")

    @commands.command(name="serverinfo", help="Показати інформацію про сервер", aliases=["сервер"])
    async def serverinfo(self, ctx):
        guild = ctx.guild
        embed = discord.Embed(title=f"Інформація про {guild.name}", color=discord.Color.blue())
        
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
            
        owner = guild.owner
        if not owner: # З версії 2.0 owner може бути None якщо бот не бачить учасника
            owner = await guild.fetch_member(guild.owner_id) if guild.owner_id else None
            
        embed.add_field(name="👑 Власник", value=owner.mention if owner else "Невідомо", inline=True)
        embed.add_field(name="👥 Кількість учасників", value=str(guild.member_count), inline=True)
        embed.add_field(name="📅 Створено", value=guild.created_at.strftime("%d.%m.%Y"), inline=True)
        
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        embed.add_field(name="💬 Канали", value=f"Текстові: {text_channels}\nГолосові: {voice_channels}", inline=True)
        
        embed.add_field(name="🎭 Ролі", value=str(len(guild.roles)), inline=True)
        
        await ctx.send(embed=embed)
        await ctx.send(embed=embed)

    @discord.app_commands.command(name="set_command_channel", description="Встановити канал для звичайних команд бота (з !)")
    @discord.app_commands.default_permissions(administrator=True)
    async def set_command_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        guild_id = interaction.guild_id
        await self.bot.db.execute('''
            INSERT INTO server_settings (guild_id, command_channel_id) 
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
            command_channel_id = excluded.command_channel_id
        ''', (guild_id, channel.id))
        await self.bot.db.commit()
        await interaction.response.send_message(f"✅ Усі команди з `!` тепер можна використовувати **тільки** у каналі {channel.mention}.", ephemeral=True)

    @discord.app_commands.command(name="clear_command_channel", description="Дозволити використання звичайних команд (з !) у всіх каналах")
    @discord.app_commands.default_permissions(administrator=True)
    async def clear_command_channel(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id
        await self.bot.db.execute('''
            UPDATE server_settings SET command_channel_id = NULL WHERE guild_id = ?
        ''', (guild_id,))
        await self.bot.db.commit()
        await interaction.response.send_message("✅ Обмеження знято. Команди тепер можна використовувати в будь-якому каналі.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Admin(bot))
