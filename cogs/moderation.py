import discord
from discord.ext import commands

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        pass # Cog is loaded notification handled in main.py

    @commands.command(name="kick", help="Кікнути учасника з сервера", aliases=["вигнати"])
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason="Не вказано"):
        if member == ctx.author:
            await ctx.send("❌ Ви не можете кікнути самого себе!")
            return
        
        try:
            await member.kick(reason=reason)
            embed = discord.Embed(title="👢 Користувача вигнано", color=discord.Color.orange())
            embed.add_field(name="Користувач", value=f"{member.mention} ({member.id})", inline=False)
            embed.add_field(name="Модератор", value=ctx.author.mention, inline=False)
            embed.add_field(name="Причина", value=reason, inline=False)
            await ctx.send(embed=embed)
        except discord.Forbidden:
            await ctx.send("❌ У мене немає прав для кіку цього користувача або його роль вища за мою.")
        except Exception as e:
            await ctx.send(f"❌ Сталася помилка: {e}")

    @commands.command(name="ban", help="Забанити учасника на сервері", aliases=["забанити"])
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason="Не вказано"):
        if member == ctx.author:
            await ctx.send("❌ Ви не можете забанити самого себе!")
            return
            
        try:
            await member.ban(reason=reason)
            embed = discord.Embed(title="🔨 Користувача забанено", color=discord.Color.red())
            embed.add_field(name="Користувач", value=f"{member.mention} ({member.id})", inline=False)
            embed.add_field(name="Модератор", value=ctx.author.mention, inline=False)
            embed.add_field(name="Причина", value=reason, inline=False)
            await ctx.send(embed=embed)
        except discord.Forbidden:
            await ctx.send("❌ У мене немає прав для бану цього користувача або його роль вища за мою.")
        except Exception as e:
            await ctx.send(f"❌ Сталася помилка: {e}")

    @commands.command(name="clear", aliases=["purge", "очистити"], help="Очистити вказану кількість повідомлень")
    @commands.has_permissions(manage_messages=True)
    async def clear(self, ctx, amount: int = 5):
        if amount <= 0:
            await ctx.send("❌ Кількість повідомлень має бути більшою за 0.")
            return
        
        # +1 щоб видалити також саме повідомлення з командою
        deleted = await ctx.channel.purge(limit=amount + 1)
        await ctx.send(f"✅ Видалено {len(deleted) - 1} повідомлень.", delete_after=5)

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if hasattr(ctx.command, 'on_error'):
            return # Якщо команда має власний обробник
            
        if isinstance(error, commands.MissingPermissions):
            missing = ", ".join(error.missing_permissions)
            await ctx.send(f"❌ У вас немає необхідних прав для використання цієї команди (потрібно: `{missing}`).")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ Пропущено обов'язковий аргумент: `{error.param.name}`. Подивіться `!help {ctx.command}`")

async def setup(bot):
    await bot.add_cog(Moderation(bot))
