import discord
from discord.ext import commands
import random
import asyncio

class Games(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def get_balance(self, user_id, guild_id):
        # Хелпер для отримання балансу
        async with self.bot.db.execute('SELECT balance FROM users WHERE user_id = ? AND guild_id = ?', (user_id, guild_id)) as cursor:
            result = await cursor.fetchone()
        return result[0] if result else 0

    async def update_balance(self, user_id, guild_id, amount):
        # Хелпер для зміни балансу (+ чи -)
        async with self.bot.db.execute('UPDATE users SET balance = balance + ? WHERE user_id = ? AND guild_id = ?', (amount, user_id, guild_id)):
            pass
        await self.bot.db.commit()

    @commands.command(name="coinflip", aliases=["монетка", "cf"], help="Підкинути монетку на ставку (!cf <ставка>)")
    async def coinflip(self, ctx, bet: int):
        if bet <= 0:
            await ctx.send("❌ Ставка має бути більше нуля!")
            return
            
        balance = await self.get_balance(ctx.author.id, ctx.guild.id)
        if balance < bet:
            await ctx.send(f"💸 Недостатньо коштів! У вас лише {balance} 🪙.")
            return

        # Граємо
        await ctx.send(f"🪙 {ctx.author.mention} підкидає монетку зі ставкою **{bet} 🪙**...")
        await asyncio.sleep(1.5) # Невеличка інтрига
        
        outcome = random.choice(["win", "lose"])
        
        if outcome == "win":
            # У разі перемоги користувач отримує x2 своєї ставки (тобто чистий плюс дорівнює ставці)
            await self.update_balance(ctx.author.id, ctx.guild.id, bet)
            await ctx.send(f"🎉 Вітаємо! Випав Орел і ви виграли **{bet * 2} 🪙**! (Чистий прибуток: {bet})")
        else:
            # У разі поразки віднімаємо ставку
            await self.update_balance(ctx.author.id, ctx.guild.id, -bet)
            await ctx.send(f"💀 На жаль випала Решка. Ви програли свої **{bet} 🪙**. Спробуйте ще раз!")

    @commands.command(name="slots", aliases=["казино", "слоти"], help="Зіграти в ігрові автомати (!slots <ставка>)")
    async def slots(self, ctx, bet: int):
        if bet <= 0:
            await ctx.send("❌ Ставка має бути більше нуля!")
            return
            
        balance = await self.get_balance(ctx.author.id, ctx.guild.id)
        if balance < bet:
            await ctx.send(f"💸 Недостатньо коштів! У вас лише {balance} 🪙.")
            return

        emojis = ["🍎", "🍊", "🍇", "🍒", "💎", "7️⃣"]
        
        # Анімація слотів
        msg = await ctx.send("🎰 **Крутимо слоти...** 🎰\n[ ⬛ | ⬛ | ⬛ ]")
        await asyncio.sleep(1)
        
        slot1 = random.choice(emojis)
        await msg.edit(content=f"🎰 **Крутимо слоти...** 🎰\n[ {slot1} | ⬛ | ⬛ ]")
        await asyncio.sleep(1)
        
        slot2 = random.choice(emojis)
        await msg.edit(content=f"🎰 **Крутимо слоти...** 🎰\n[ {slot1} | {slot2} | ⬛ ]")
        await asyncio.sleep(1)
        
        slot3 = random.choice(emojis)
        
        # Оцінка результату
        if slot1 == slot2 == slot3:
            # Джекпот x5
            winnings = bet * 5
            await self.update_balance(ctx.author.id, ctx.guild.id, winnings - bet) # Чистий плюс
            result_text = f"🎰 **ДЖЕКПОТ!!!** 🎰\n[ {slot1} | {slot2} | {slot3} ]\n\n💰 Ви виграли **{winnings} 🪙** (x5)!"
            color = discord.Color.gold()
        elif slot1 == slot2 or slot2 == slot3 or slot1 == slot3:
            # Дві однакові x2
            winnings = bet * 2
            await self.update_balance(ctx.author.id, ctx.guild.id, winnings - bet)
            result_text = f"🎰 **Перемога!** 🎰\n[ {slot1} | {slot2} | {slot3} ]\n\n💵 Ви виграли **{winnings} 🪙** (x2)."
            color = discord.Color.green()
        else:
            # Програш
            await self.update_balance(ctx.author.id, ctx.guild.id, -bet)
            result_text = f"🎰 **Програш...** 🎰\n[ {slot1} | {slot2} | {slot3} ]\n\n💀 Ви програли **{bet} 🪙**."
            color = discord.Color.red()

        embed = discord.Embed(description=result_text, color=color)
        await msg.edit(content=None, embed=embed)

async def setup(bot):
    await bot.add_cog(Games(bot))
