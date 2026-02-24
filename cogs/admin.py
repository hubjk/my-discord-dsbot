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

async def setup(bot):
    await bot.add_cog(Admin(bot))
