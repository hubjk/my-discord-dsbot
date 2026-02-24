import discord
from discord.ext import commands

class Reactions(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="add_rr", help="Додати роль за реакцію (Тільки для адміністраторів)")
    @commands.has_permissions(administrator=True)
    async def add_rr(self, ctx, message_id: int, emoji: str, role: discord.Role):
        """
        Додає прив'язку: при натисканні на смайл під конкретним повідомленням видаватиметься роль.
        Використання: !add_rr 1234567890 🎮 @Геймер
        """
        # Зберігаємо в базу даних
        try:
            await self.bot.db.execute(
                'INSERT OR REPLACE INTO reaction_roles (message_id, emoji, role_id) VALUES (?, ?, ?)',
                (message_id, emoji, role.id)
            )
            await self.bot.db.commit()
            
            # Намагаємося поставити реакцію від імені бота, щоб користувачам було куди тиснути
            try:
                msg = await ctx.channel.fetch_message(message_id)
                await msg.add_reaction(emoji)
            except discord.NotFound:
                pass # Повідомлення може бути в іншому каналі, це нормально
                
            await ctx.send(f"✅ Успішно! Тепер реакція {emoji} на повідомленні `{message_id}` видаватиме роль {role.mention}.")
        except Exception as e:
            await ctx.send(f"❌ Помилка при збереженні: {e}")

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        # Ігноруємо реакції від самого бота
        if payload.user_id == self.bot.user.id:
            return
            
        emoji_name = str(payload.emoji)
        
        async with self.bot.db.execute('SELECT role_id FROM reaction_roles WHERE message_id = ? AND emoji = ?', (payload.message_id, emoji_name)) as cursor:
            result = await cursor.fetchone()
            
        if result:
            role_id = result[0]
            guild = self.bot.get_guild(payload.guild_id)
            if guild:
                role = guild.get_role(role_id)
                member = guild.get_member(payload.user_id)
                if role and member:
                    try:
                        await member.add_roles(role)
                    except discord.Forbidden:
                        print(f"Помилка: Немає прав для видачі ролі {role.name}")

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        # Ця подія спрацьовує, коли користувач прибирає свою реакцію
        emoji_name = str(payload.emoji)
        
        async with self.bot.db.execute('SELECT role_id FROM reaction_roles WHERE message_id = ? AND emoji = ?', (payload.message_id, emoji_name)) as cursor:
            result = await cursor.fetchone()
            
        if result:
            role_id = result[0]
            guild = self.bot.get_guild(payload.guild_id)
            if guild:
                role = guild.get_role(role_id)
                member = guild.get_member(payload.user_id)
                if role and member:
                    try:
                        await member.remove_roles(role)
                    except discord.Forbidden:
                        print(f"Помилка: Немає прав для забирання ролі {role.name}")

async def setup(bot):
    await bot.add_cog(Reactions(bot))
