import discord
from discord.ext import commands
import datetime

class Warnings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="warn", aliases=["попередити", "варн"], help="Видати попередження користувачу. Приклад: !warn @user <причина>")
    @commands.has_permissions(manage_messages=True)
    async def warn(self, ctx, member: discord.Member, *, reason="Причина не вказана"):
        if member.bot:
            await ctx.send("❌ Ботам не можна видавати попередження.")
            return
            
        if ctx.author.top_role <= member.top_role and ctx.guild.owner_id != ctx.author.id:
            await ctx.send("❌ Ви не можете видати попередження користувачу з вищою або рівною вашій роллю.")
            return

        # Додаємо попередження в базу
        await self.bot.db.execute(
            'INSERT INTO warnings (user_id, guild_id, moderator_id, reason) VALUES (?, ?, ?, ?)',
            (member.id, ctx.guild.id, ctx.author.id, reason)
        )
        await self.bot.db.commit()

        # Рахуємо загальну кількість попереджень
        async with self.bot.db.execute('SELECT COUNT(*) FROM warnings WHERE user_id = ? AND guild_id = ?', (member.id, ctx.guild.id)) as cursor:
            count_result = await cursor.fetchone()
            warn_count = count_result[0]

        # Логіка автоматичного покарання
        punishment_text = ""
        action_taken = False
        
        try:
            if warn_count == 3:
                # Мут на 1 годину (Таймаут)
                duration = datetime.timedelta(hours=1)
                await member.timeout(duration, reason="Автоматичний мут за 3 попередження")
                punishment_text = f"\n⚠️ **Увага:** Користувач отримав **Таймаут (Мут) на 1 годину** за накопичення 3-х попереджень."
                action_taken = True
            elif warn_count >= 5:
                # Бан
                await member.ban(reason="Автоматичний бан за рубіж у 5 попереджень")
                punishment_text = f"\n🔨 **Увага:** Користувач отримав **БАН** за досягнення ліміту у 5 попереджень."
                action_taken = True
        except discord.Forbidden:
            punishment_text = "\n⚠️ *Боту забракло прав для виконання автоматичного покарання (Мут/Бан).*"

        embed = discord.Embed(
            title="⚠️ Видано Попередження",
            color=discord.Color.orange(),
            timestamp=datetime.datetime.now()
        )
        embed.add_field(name="Користувач", value=member.mention, inline=True)
        embed.add_field(name="Модератор", value=ctx.author.mention, inline=True)
        embed.add_field(name="Причина", value=reason, inline=False)
        embed.add_field(name="Всього попереджень", value=f"**{warn_count}**", inline=False)
        
        if punishment_text:
            embed.description = punishment_text
            
        await ctx.send(embed=embed)
        
        # Спроба відправити повідомлення в ПП порушнику (якщо не забанено)
        if not action_taken or warn_count < 5:
            try:
                await member.send(f"Ви отримали попередження на сервері **{ctx.guild.name}**.\n**Причина:** {reason}\n**Це ваше {warn_count}-е попередження.** (На 3-тє дається Мут, на 5-те - Бан).")
            except discord.Forbidden:
                pass

    @commands.command(name="warnings", aliases=["попередження", "варни"], help="Перевірити кількість попереджень у користувача")
    async def check_warnings(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        
        async with self.bot.db.execute('SELECT id, moderator_id, reason, date FROM warnings WHERE user_id = ? AND guild_id = ? ORDER BY date DESC', (member.id, ctx.guild.id)) as cursor:
            warnings = await cursor.fetchall()
            
        if not warnings:
            await ctx.send(f"✅ У {member.display_name} немає попереджень!")
            return
            
        embed = discord.Embed(title=f"⚠️ Попередження користувача {member.display_name}", color=discord.Color.red())
        embed.set_thumbnail(url=member.display_avatar.url if member.display_avatar else None)
        
        for idx, w in enumerate(warnings[:10]): # Показуємо останні 10
            warn_id, mod_id, reason, date_str = w
            embed.add_field(
                name=f"#{idx+1} (ID: {warn_id}) - {date_str[:16]}", 
                value=f"**Причина:** {reason}\n**Модератор:** <@{mod_id}>", 
                inline=False
            )
            
        embed.set_footer(text=f"Всього попереджень: {len(warnings)}")
        await ctx.send(embed=embed)

    @commands.command(name="clearwarns", aliases=["знятиварни"], help="Очистити ВСІ або ОДНЕ попередження (через ID) у користувача")
    @commands.has_permissions(administrator=True)
    async def clear_warns(self, ctx, member: discord.Member, warn_id: int = None):
        if warn_id:
            # Видаляємо конкретне попередження
            async with self.bot.db.execute('DELETE FROM warnings WHERE id = ? AND user_id = ? AND guild_id = ?', (warn_id, member.id, ctx.guild.id)) as cursor:
                if cursor.rowcount > 0:
                    await ctx.send(f"✅ Попередження з ID `{warn_id}` успішно видалено у {member.mention}.")
                else:
                    await ctx.send(f"❌ Попередження з таким ID у цього користувача не знайдено.")
        else:
            # Очищуємо всі попередження
            await self.bot.db.execute('DELETE FROM warnings WHERE user_id = ? AND guild_id = ?', (member.id, ctx.guild.id))
            await ctx.send(f"✅ Всі попередження користувача {member.mention} були очищені!")
            
        await self.bot.db.commit()

async def setup(bot):
    await bot.add_cog(Warnings(bot))
