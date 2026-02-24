import discord
from discord.ext import commands
import os
import io

# Спроба імпортувати Pillow для створення картинок
try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

class Welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def get_welcome_channel(self, guild):
        """Знаходить канал для привітань з `.env` або за назвою."""
        from dotenv import load_dotenv
        load_dotenv(override=True) # Оновлюємо змінні середовища з файлу
        
        channel_id = os.getenv("WELCOME_CHANNEL_ID")
        if channel_id and channel_id.isdigit():
            channel = guild.get_channel(int(channel_id))
            if channel:
                return channel
                
        # Пошук за назвою
        for channel in guild.text_channels:
            if channel.name in ["welcome", "вітальне", "головний", "чат", "general"]:
                return channel
                
        return None

    async def generate_welcome_image(self, member):
        """Генерує картинку привітання за допомогою Pillow"""
        if not HAS_PILLOW:
            return None
            
        # Створюємо базовий фон (чорний з градієнтом або просто темний)
        width, height = 800, 250
        background = Image.new("RGB", (width, height), (30, 33, 36))
        draw = ImageDraw.Draw(background)
        
        # Малюємо декоративні елементи (рамку)
        draw.rectangle([10, 10, width-10, height-10], outline=(114, 137, 218), width=3)
        
        # Завантажуємо аватар користувача
        if member.display_avatar:
            avatar_bytes = await member.display_avatar.read()
            avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
            avatar = avatar.resize((150, 150))
            
            # Робимо аватар круглим
            mask = Image.new("L", avatar.size, 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.ellipse((0, 0) + avatar.size, fill=255)
            
            # Вставляємо аватар на фон
            background.paste(avatar, (50, 50), mask)
            
        # Пишемо текст. (Без спеціального шрифту використовуємо дефолтний, але він маленький.
        # Тому просто будемо імітувати великий текст малюючи кілька разів, або якщо є шрифт, використовуємо його)
        try:
            # Спробуємо завантажити стандартний системний шрифт, якщо він є (Linux)
            font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 40)
            font_text = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 25)
        except OSError:
            # Якщо немає, використовуємо дефолтний (буде дрібний)
            font_title = ImageFont.load_default()
            font_text = ImageFont.load_default()

        # Текст
        draw.text((230, 80), "ВІТАЄМО НА СЕРВЕРІ!", fill=(255, 255, 255), font=font_title)
        draw.text((230, 140), f"{member.name}", fill=(114, 137, 218), font=font_title)
        draw.text((230, 190), f"Ти наш {member.guild.member_count}-й учасник", fill=(200, 200, 200), font=font_text)
        
        # Зберігаємо результат в пам'ять
        buffer = io.BytesIO()
        background.save(buffer, format="PNG")
        buffer.seek(0)
        
        return buffer

    @commands.Cog.listener()
    async def on_member_join(self, member):
        channel = await self.get_welcome_channel(member.guild)
        if not channel:
            print(f"Помилка: Не знайдено канал для привітань на сервері {member.guild.name}")
            return
            
        print(f"Спроба надіслати привітання в канал: {channel.name} ({channel.id})")

        # Намагаємося згенерувати картинку
        image_buffer = None
        try:
            image_buffer = await self.generate_welcome_image(member)
        except Exception as e:
            print(f"Помилка генерації картинки привітання: {e}")
        
        if image_buffer:
            file = discord.File(fp=image_buffer, filename="welcome.png")
            await channel.send(f"Раді вітати, {member.mention}!", file=file)
        else:
            print("Картинка не згенерувалася, надсилаємо Embed...")
            # Фолбек на Embed, якщо картинка не згенерувалася
            embed = discord.Embed(
                title=f"👋 Вітаємо на сервері, {member.name}!",
                description=f"Привіт, {member.mention}! Ми раді бачити тебе на **{member.guild.name}**.\nТи **{member.guild.member_count}-й** учасник на нашому сервері!",
                color=discord.Color.from_rgb(100, 255, 100)
            )
            
            if member.display_avatar:
                embed.set_thumbnail(url=member.display_avatar.url)
                
            if member.guild.icon:
                embed.set_footer(text=f"Сервер: {member.guild.name}", icon_url=member.guild.icon.url)
            else:
                embed.set_footer(text=f"Сервер: {member.guild.name}")

            await channel.send(f"Раді вітати, {member.mention}!", embed=embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        channel = await self.get_welcome_channel(member.guild)
        if not channel:
            return
            
        embed = discord.Embed(
            title="📤 Учасник покинув сервер",
            description=f"Прощавай, {member.mention} ({member.name})...",
            color=discord.Color.dark_red()
        )
        if member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)
            
        embed.set_footer(text=f"На сервері залишилось: {member.guild.member_count} учасників")
        await channel.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Welcome(bot))
