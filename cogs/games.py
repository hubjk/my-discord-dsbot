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
        await self.bot.db.execute('UPDATE users SET balance = balance + ? WHERE user_id = ? AND guild_id = ?', (amount, user_id, guild_id))
        await self.bot.db.commit()

    async def place_bet(self, interaction: discord.Interaction, bet: int) -> bool:
        """Перевіряє і знімає ставку перед початком гри. Повертає True, якщо успішно."""
        if bet <= 0:
            await interaction.response.send_message("❌ Ставка має бути більше нуля!", ephemeral=True)
            return False
            
        balance = await self.get_balance(interaction.user.id, interaction.guild_id)
        if balance < bet:
            await interaction.response.send_message(f"💸 Недостатньо коштів! У вас лише {balance} 🪙.", ephemeral=True)
            return False
            
        # Одразу знімаємо ставку, щоб запобігти абузам, коли юзер швидко вводить кілька команд
        await self.update_balance(interaction.user.id, interaction.guild_id, -bet)
        return True

    @app_commands.command(name="coinflip", description="Підкинути монетку на ставку")
    async def coinflip(self, interaction: discord.Interaction, bet: int):
        if not await self.place_bet(interaction, bet):
            return

        # Граємо
        await interaction.response.send_message(f"🪙 {interaction.user.mention} підкидає монетку зі ставкою **{bet} 🪙**...", ephemeral=True)
        await asyncio.sleep(1.5) # Невеличка інтрига
        
        outcome = random.choice(["win", "lose"])
        
        if outcome == "win":
            # Ставку вже було знято, тому для виграшу x2 додаємо `bet * 2`
            await self.update_balance(interaction.user.id, interaction.guild_id, bet * 2)
            await interaction.edit_original_response(content=f"🎉 Вітаємо! Випав Орел і ви виграли **{bet * 2} 🪙**! (Чистий прибуток: {bet})")
        else:
            # При програші нічого не віднімаємо, бо ставку вже зняли
            await interaction.edit_original_response(content=f"💀 На жаль випала Решка. Ви програли свої **{bet} 🪙**. Спробуйте ще раз!")

    @app_commands.command(name="slots", description="Зіграти в ігрові автомати")
    async def slots(self, interaction: discord.Interaction, bet: int):
        if not await self.place_bet(interaction, bet):
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
            await self.update_balance(interaction.user.id, interaction.guild_id, winnings)
            result_text = f"🎰 **ДЖЕКПОТ!!!** 🎰\n[ {slot1} | {slot2} | {slot3} ]\n\n💰 Ви виграли **{winnings} 🪙** (x5)!"
            color = discord.Color.gold()
        elif slot1 == slot2 or slot2 == slot3 or slot1 == slot3:
            # Дві однакові x2
            winnings = bet * 2
            await self.update_balance(interaction.user.id, interaction.guild_id, winnings)
            result_text = f"🎰 **Перемога!** 🎰\n[ {slot1} | {slot2} | {slot3} ]\n\n💵 Ви виграли **{winnings} 🪙** (x2)."
            color = discord.Color.green()
        else:
            # Програш (ставку вже знято на початку)
            result_text = f"🎰 **Програш...** 🎰\n[ {slot1} | {slot2} | {slot3} ]\n\n💀 Ви програли **{bet} 🪙**."
            color = discord.Color.red()

        embed = discord.Embed(description=result_text, color=color)
        # Очищуємо текст і замінюємо його красивим ембедом
        await interaction.edit_original_response(content="", embed=embed)

async def setup(bot):
    await bot.add_cog(Games(bot))
