import discord
from discord.ext import commands
from discord import app_commands
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

    @app_commands.command(name="coinflip", description="Підкинути монетку на ставку")
    async def coinflip(self, interaction: discord.Interaction, bet: int):
        if bet <= 0:
            await interaction.response.send_message("❌ Ставка має бути більше нуля!", ephemeral=True)
            return
            
        balance = await self.get_balance(interaction.user.id, interaction.guild_id)
        if balance < bet:
            await interaction.response.send_message(f"💸 Недостатньо коштів! У вас лише {balance} 🪙.", ephemeral=True)
            return

        # Граємо
        await interaction.response.send_message(f"🪙 {interaction.user.mention} підкидає монетку зі ставкою **{bet} 🪙**...", ephemeral=True)
        await asyncio.sleep(1.5) # Невеличка інтрига
        
        outcome = random.choice(["win", "lose"])
        
        if outcome == "win":
            # У разі перемоги користувач отримує x2 своєї ставки (тобто чистий плюс дорівнює ставці)
            await self.update_balance(interaction.user.id, interaction.guild_id, bet)
            await interaction.edit_original_response(content=f"🎉 Вітаємо! Випав Орел і ви виграли **{bet * 2} 🪙**! (Чистий прибуток: {bet})")
        else:
            # У разі поразки віднімаємо ставку
            await self.update_balance(interaction.user.id, interaction.guild_id, -bet)
            await interaction.edit_original_response(content=f"💀 На жаль випала Решка. Ви програли свої **{bet} 🪙**. Спробуйте ще раз!")

    @app_commands.command(name="slots", description="Зіграти в ігрові автомати")
    async def slots(self, interaction: discord.Interaction, bet: int):
        if bet <= 0:
            await interaction.response.send_message("❌ Ставка має бути більше нуля!", ephemeral=True)
            return
            
        balance = await self.get_balance(interaction.user.id, interaction.guild_id)
        if balance < bet:
            await interaction.response.send_message(f"💸 Недостатньо коштів! У вас лише {balance} 🪙.", ephemeral=True)
            return

        emojis = ["🍎", "🍊", "🍇", "🍒", "💎", "7️⃣"]
        
        # Анімація слотів (ephemeral = True щоб не смітити в чат)
        await interaction.response.send_message("🎰 **Крутимо слоти...** 🎰\n[ ⬛ | ⬛ | ⬛ ]", ephemeral=True)
        await asyncio.sleep(1)
        
        slot1 = random.choice(emojis)
        await interaction.edit_original_response(content=f"🎰 **Крутимо слоти...** 🎰\n[ {slot1} | ⬛ | ⬛ ]")
        await asyncio.sleep(1)
        
        slot2 = random.choice(emojis)
        await interaction.edit_original_response(content=f"🎰 **Крутимо слоти...** 🎰\n[ {slot1} | {slot2} | ⬛ ]")
        await asyncio.sleep(1)
        
        slot3 = random.choice(emojis)
        
        # Оцінка результату
        if slot1 == slot2 == slot3:
            # Джекпот x5
            winnings = bet * 5
            await self.update_balance(interaction.user.id, interaction.guild_id, winnings - bet) # Чистий плюс
            result_text = f"🎰 **ДЖЕКПОТ!!!** 🎰\n[ {slot1} | {slot2} | {slot3} ]\n\n💰 Ви виграли **{winnings} 🪙** (x5)!"
            color = discord.Color.gold()
        elif slot1 == slot2 or slot2 == slot3 or slot1 == slot3:
            # Дві однакові x2
            winnings = bet * 2
            await self.update_balance(interaction.user.id, interaction.guild_id, winnings - bet)
            result_text = f"🎰 **Перемога!** 🎰\n[ {slot1} | {slot2} | {slot3} ]\n\n💵 Ви виграли **{winnings} 🪙** (x2)."
            color = discord.Color.green()
        else:
            # Програш
            await self.update_balance(interaction.user.id, interaction.guild_id, -bet)
            result_text = f"🎰 **Програш...** 🎰\n[ {slot1} | {slot2} | {slot3} ]\n\n💀 Ви програли **{bet} 🪙**."
            color = discord.Color.red()

        embed = discord.Embed(description=result_text, color=color)
        # Очищуємо текст і замінюємо його красивим ембедом
        await interaction.edit_original_response(content="", embed=embed)

async def setup(bot):
    await bot.add_cog(Games(bot))
