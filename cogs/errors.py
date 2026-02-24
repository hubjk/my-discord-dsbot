import discord
from discord.ext import commands
import traceback


class ErrorHandler(commands.Cog):
    """Глобальний обробник помилок з красивими embed."""

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        # Ігноруємо помилки, які вже оброблені локально
        if hasattr(ctx.command, 'on_error'):
            return

        error = getattr(error, 'original', error)

        # ─── Відомі помилки ─────────────────────────────────

        if isinstance(error, commands.CommandNotFound):
            return  # Тихо ігноруємо невідомі команди

        if isinstance(error, commands.MissingRequiredArgument):
            embed = discord.Embed(
                title="❌ Пропущено аргумент",
                description=f"Використання: `{ctx.prefix}{ctx.command.qualified_name} {ctx.command.signature}`",
                color=discord.Color.orange()
            )
            embed.add_field(name="Пропущено", value=f"`{error.param.name}`", inline=False)
            return await ctx.send(embed=embed, delete_after=15)

        if isinstance(error, commands.BadArgument):
            embed = discord.Embed(
                title="❌ Невірний аргумент",
                description=str(error),
                color=discord.Color.orange()
            )
            return await ctx.send(embed=embed, delete_after=15)

        if isinstance(error, commands.MissingPermissions):
            perms = ", ".join(f"`{p}`" for p in error.missing_permissions)
            embed = discord.Embed(
                title="🔒 Недостатньо прав",
                description=f"Вам потрібні права: {perms}",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed, delete_after=10)

        if isinstance(error, commands.BotMissingPermissions):
            perms = ", ".join(f"`{p}`" for p in error.missing_permissions)
            embed = discord.Embed(
                title="🤖 Боту не вистачає прав",
                description=f"Мені потрібні права: {perms}",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed, delete_after=10)

        if isinstance(error, commands.CommandOnCooldown):
            embed = discord.Embed(
                title="⏳ Зачекайте",
                description=f"Спробуйте знову через **{error.retry_after:.1f}с**",
                color=discord.Color.yellow()
            )
            return await ctx.send(embed=embed, delete_after=5)

        if isinstance(error, commands.NoPrivateMessage):
            return await ctx.send("❌ Ця команда не працює в DM.", delete_after=5)

        # ─── Невідомі помилки ───────────────────────────────

        embed = discord.Embed(
            title="💥 Щось пішло не так",
            description=f"```{type(error).__name__}: {str(error)[:200]}```",
            color=discord.Color.dark_red()
        )
        embed.set_footer(text="Якщо це повторюється — повідомте адміністратора")
        await ctx.send(embed=embed, delete_after=20)

        # Логуємо повну помилку в консоль
        print(f"\n[Error] Команда '{ctx.command}' від {ctx.author}:")
        traceback.print_exception(type(error), error, error.__traceback__)


async def setup(bot):
    await bot.add_cog(ErrorHandler(bot))
