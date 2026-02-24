import discord
from discord.ext import commands
import asyncio
import random
import datetime

class Giveaways(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def convert_time(self, time_str):
        """Конвертує рядок часу (1m, 2h, 1d) у секунди"""
        unit = time_str[-1].lower()
        if unit not in ['s', 'm', 'h', 'd'] or not time_str[:-1].isdigit():
            return None
            
        value = int(time_str[:-1])
        if unit == 's': return value
        if unit == 'm': return value * 60
        if unit == 'h': return value * 3600
        if unit == 'd': return value * 86400
        return None

    @commands.command(name="gcreate", aliases=["розграш", "створити_розіграш"], help="Створити розіграш. Приклад: !gcreate 1h 1 VIP Роль")
    @commands.has_permissions(manage_messages=True)
    async def create_giveaway(self, ctx, duration: str, winners_count: int, *, prize: str):
        seconds = self.convert_time(duration)
        if not seconds:
            await ctx.send("❌ Невірний формат часу! Використовуйте `s` (секунди), `m` (хвилини), `h` (години), `d` (дні). Наприклад: `1h` або `30m`.")
            return

        end_time = datetime.datetime.now() + datetime.timedelta(seconds=seconds)
        end_time_unix = int(end_time.timestamp())

        embed = discord.Embed(
            title="🎉 **РОЗІГРАШ** 🎉",
            description=f"**Приз:** {prize}\n**Переможців:** {winners_count}\n\nНатисніть на 🎉 щоб прийняти участь!\n\n⏳ **Закінчується:** <t:{end_time_unix}:R> (<t:{end_time_unix}:f>)",
            color=discord.Color.gold()
        )
        embed.set_footer(text=f"Розіграш створив(ла): {ctx.author.display_name}")

        msg = await ctx.send(embed=embed)
        await msg.add_reaction("🎉")

        await ctx.message.delete()

        # Чекаємо вказаний час (не зберігаємо в БД для простоти, але при перезапуску таймер зіб'ється)
        # Для складнішої версії потрібно зберігати ID повідомлення + час завершення в SQLite
        await asyncio.sleep(seconds)

        # Оновлюємо повідомлення щоб отримати актуальні реакції
        try:
            new_msg = await ctx.channel.fetch_message(msg.id)
        except discord.NotFound:
            # Повідомлення було видалено
            return

        users = set()
        for reaction in new_msg.reactions:
            if str(reaction.emoji) == "🎉":
                async for user in reaction.users():
                    if not user.bot:
                        users.add(user)

        users = list(users)

        if len(users) == 0:
            await ctx.send(f"Разом із призом **{prize}** розіграш завершено, але ніхто не взяв участь 😔", reference=new_msg)
        else:
            winners = random.sample(users, min(len(users), winners_count))
            winners_mentions = ", ".join([w.mention for w in winners])
            
            win_embed = discord.Embed(
                title="🎉 **РОЗІГРАШ ЗАВЕРШЕНО** 🎉",
                description=f"**Приз:** {prize}\n**Переможці:** {winners_mentions}",
                color=discord.Color.green()
            )
            
            await new_msg.edit(embed=win_embed)
            await ctx.send(f"Вітаємо {winners_mentions}! Ви виграли **{prize}**! 🎁", reference=new_msg)

async def setup(bot):
    await bot.add_cog(Giveaways(bot))
