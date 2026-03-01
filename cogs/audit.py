import discord
from discord.ext import commands
from datetime import datetime
import os

class Audit(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
    async def get_audit_channel(self, guild):
        """Знаходить канал логів. Бере значення з AUDIT_CHANNEL_ID в .env, або шукає канал з назвою audit-logs"""
        channel_id = os.getenv("AUDIT_CHANNEL_ID")
        if channel_id and channel_id.isdigit():
            channel = guild.get_channel(int(channel_id))
            if channel:
                return channel
                
        # Якщо в .env немає, шукаємо канал з назвою 'audit-logs' або 'логи'
        for channel in guild.text_channels:
            if channel.name in ["audit-logs", "логи", "аудит"]:
                return channel
                
        return None

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.author.bot:
            return
            
        # Ігноруємо видалені команди бота (наприклад, !play), щоб не засмічувати аудит
        if message.content.startswith('!'):
            return
            
        # Ігноруємо видалення гіфок
        if "tenor.com/view/" in message.content or "giphy.com/" in message.content:
            return
            
        channel = await self.get_audit_channel(message.guild)
        if not channel:
            return
            
        embed = discord.Embed(
            title="🗑️ Повідомлення видалено",
            description=f"**Користувач:** {message.author.mention}\n**Канал:** {message.channel.mention}",
            color=discord.Color.red(),
            timestamp=datetime.now()
        )
        # Discord ліміт 1024 символи на значення поля
        content = message.content[:1020] + "..." if len(message.content) > 1024 else message.content
        if content:
            embed.add_field(name="Вміст", value=content, inline=False)
            
        embed.set_footer(text=f"ID Користувача: {message.author.id}")
        await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if before.author.bot or before.content == after.content:
            return
        # Ігноруємо редагування команд бота (починаються з !)
        if after.content.startswith('!'):
            return
            
        # Ігноруємо автоматичні зміни гіфок алгоритмами діскорду
        if "tenor.com/view/" in before.content or "giphy.com/" in before.content:
            return
            
        channel = await self.get_audit_channel(before.guild)
        if not channel:
            return
            
        embed = discord.Embed(
            title="✏️ Повідомлення відредаговано",
            description=f"**Користувач:** {before.author.mention}\n**Канал:** {before.channel.mention}\n[Перейти до повідомлення]({after.jump_url})",
            color=discord.Color.orange(),
            timestamp=datetime.now()
        )
        
        old_content = before.content[:1020] + "..." if len(before.content) > 1024 else before.content
        new_content = after.content[:1020] + "..." if len(after.content) > 1024 else after.content
        
        if old_content:
            embed.add_field(name="До", value=old_content, inline=False)
        if new_content:
            embed.add_field(name="Після", value=new_content, inline=False)
            
        embed.set_footer(text=f"ID Користувача: {before.author.id}")
        await channel.send(embed=embed)





async def setup(bot):
    await bot.add_cog(Audit(bot))
