import discord
from discord import app_commands
from discord.ext import commands
import re
from datetime import timedelta

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

    # ─── Нові команди муту ──────────────────────────────────────────────────

    def parse_duration(self, duration_str: str):
        """Парсить рядок часу (напр. 10m, 1h, 1d) у секунди."""
        units = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
        match = re.match(r"(\d+)([smhd])", duration_str.lower())
        if match:
            value, unit = match.groups()
            return int(value) * units[unit]
        try:
            return int(duration_str) * 60 # За замовчуванням хвилини
        except:
            return None

    async def get_or_create_mute_role(self, guild: discord.Guild):
        role = discord.utils.get(guild.roles, name="Muted")
        if not role:
            try:
                role = await guild.create_role(name="Muted", color=discord.Color.dark_grey(), reason="Роль для муту створена автоматично")
                for channel in guild.channels:
                    try:
                        await channel.set_permissions(role, send_messages=False, speak=False, add_reactions=False)
                    except discord.Forbidden:
                        continue
            except Exception as e:
                print(f"[Moderation] Не вдалося створити/налаштувати роль Muted: {e}")
        return role

    @app_commands.command(name="mute", description="Замутити учасника (через роль)")
    @app_commands.describe(member="Користувач для муту", duration="Час (напр. 10m, 1h, 1d)", reason="Причина муту")
    async def timeout(self, interaction: discord.Interaction, member: discord.Member, duration: str = "10m", reason: str = "Не вказано"):
        if not interaction.user.guild_permissions.moderate_members:
            return await interaction.response.send_message("❌ У вас немає прав для використання цієї команди.", ephemeral=True)
            
        if member == interaction.user:
            return await interaction.response.send_message("❌ Ви не можете замутити самого себе!", ephemeral=True)
        
        seconds = self.parse_duration(duration)
        if seconds is None:
            return await interaction.response.send_message("❌ Неправильний формат часу! Використовуйте: `10m`, `1h`, `1d` тощо.", ephemeral=True)
        
        role = await self.get_or_create_mute_role(interaction.guild)
        if not role:
            return await interaction.response.send_message("❌ Не вдалося знайти або створити роль Muted. Перевірте права бота.", ephemeral=True)

        try:
            # Знімаємо системний тайм-аут, якщо він є (на всяк випадок)
            try:
                await member.timeout(None, reason="Переведення муту на рольову систему")
            except:
                pass
                
            await member.add_roles(role, reason=reason)
            embed = discord.Embed(title="🤫 Учасника замучено", color=discord.Color.orange())
            embed.add_field(name="Користувач", value=f"{member.mention}", inline=True)
            embed.add_field(name="Тривалість", value=duration, inline=True)
            embed.add_field(name="Причина", value=reason, inline=False)
            embed.set_footer(text="Тепер мут працює через роль (дозволяє писати в тікетах).")
            await interaction.response.send_message(embed=embed)
            
            import asyncio
            self.bot.loop.create_task(self.unmute_timer(member, role, seconds))
        except discord.Forbidden:
            await interaction.response.send_message("❌ Недостатньо прав для муту цього учасника (роль бота нижча).", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Сталася помилка: {e}", ephemeral=True)

    async def unmute_timer(self, member: discord.Member, role: discord.Role, seconds: int):
        import asyncio
        await asyncio.sleep(seconds)
        if role in member.roles:
            try:
                await member.remove_roles(role, reason="Час муту вийшов")
            except:
                pass

    @app_commands.command(name="unmute", description="Зняти мут (через роль)")
    @app_commands.describe(member="Користувач для розмуту", reason="Причина сняття муту")
    async def untimeout(self, interaction: discord.Interaction, member: discord.Member, reason: str = "Знято модератором"):
        if not interaction.user.guild_permissions.moderate_members:
            return await interaction.response.send_message("❌ У вас немає прав для використання цієї команди.", ephemeral=True)
            
        role = discord.utils.get(interaction.guild.roles, name="Muted")
        
        has_role = role and role in member.roles
        is_timeouted = member.is_timed_out()
        
        if not has_role and not is_timeouted:
            return await interaction.response.send_message("❌ Цей учасник не замутений.", ephemeral=True)
            
        try:
            if has_role:
                await member.remove_roles(role, reason=reason)
            if is_timeouted:
                await member.timeout(None, reason=reason)
                
            embed = discord.Embed(title="🔊 Мут знято", color=discord.Color.green())
            embed.add_field(name="Користувач", value=f"{member.mention}", inline=True)
            embed.add_field(name="Модератор", value=interaction.user.mention, inline=True)
            await interaction.response.send_message(embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message("❌ Недостатньо прав для розмуту цього учасника.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Сталася помилка: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Moderation(bot))
