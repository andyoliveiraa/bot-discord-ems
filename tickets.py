import discord
from discord.ext import commands
from discord.commands import Option
from discord.ui import Button, View, Modal, InputText
import datetime
import time
from pytz import timezone
import io
import os
import secrets
import asyncio

from db import Database, get_configs

db = Database('db.sqlite3')

def obter_timezone():
    cfg = get_configs()
    tz_str = cfg.get("timezone", "Europe/Lisbon")
    try:
        return timezone(tz_str)
    except Exception:
        return timezone("Europe/Lisbon")

def get_admin_roles(guild: discord.Guild):
    cfg = get_configs()
    admin_roles = []
    
    # Cargo configurado para tickets, se existir
    ticket_role_id = cfg.get("ticket_admin_role_id")
    if ticket_role_id:
        r = guild.get_role(int(ticket_role_id))
        if r: admin_roles.append(r)
        
    # Cargo geral de staff
    staff_role_id = cfg.get("staff_role_id")
    if staff_role_id:
        r = guild.get_role(int(staff_role_id))
        if r: admin_roles.append(r)
        
    return admin_roles

def get_online_admins(guild: discord.Guild):
    admin_roles = get_admin_roles(guild)
    online_admins = []
    seen = set()
    
    for member in guild.members:
        if member.bot or member.id in seen:
            continue
            
        is_admin = member.guild_permissions.administrator
        if not is_admin and admin_roles:
            is_admin = any(r in member.roles for r in admin_roles)
            
        if is_admin:
            if member.status != discord.Status.offline:
                online_admins.append(member)
                seen.add(member.id)
                
    return online_admins

async def gerar_transcript_html(channel: discord.TextChannel):
    mensagens = [msg async for msg in channel.history(limit=None, oldest_first=True)]
    
    html = """
    <!DOCTYPE html>
    <html lang="pt-PT">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Transcrito - {channel_name}</title>
        <style>
            body { font-family: 'Inter', 'Whitney', 'Helvetica Neue', Helvetica, Arial, sans-serif; background-color: #36393f; color: #dcddde; margin: 0; padding: 20px; }
            .header { text-align: center; margin-bottom: 30px; padding-bottom: 20px; border-bottom: 1px solid #202225; }
            .header h1 { color: #ffffff; margin: 0 0 10px 0; }
            .header p { color: #b9bbbe; margin: 0; }
            .message-group { display: flex; margin-bottom: 20px; margin-top: 17px; }
            .avatar { width: 40px; height: 40px; border-radius: 50%; margin-right: 16px; object-fit: cover; cursor: pointer; }
            .message-content { flex: 1; overflow: hidden; }
            .message-header { display: flex; align-items: baseline; margin-bottom: 2px; }
            .username { font-size: 1rem; font-weight: 500; color: #ffffff; margin-right: 0.25rem; }
            .timestamp { font-size: 0.75rem; color: #72767d; margin-left: 0.25rem; }
            .message-text { font-size: 0.95rem; line-height: 1.375rem; color: #dcddde; white-space: pre-wrap; word-wrap: break-word; }
            .embed { border-left: 4px solid #202225; background: #2f3136; padding: 10px; margin-top: 10px; border-radius: 4px; }
            .embed-title { font-weight: bold; color: #ffffff; margin-bottom: 5px; }
            .embed-desc { font-size: 0.9em; color: #b9bbbe; }
            .system-message { color: #8ea1e1; font-style: italic; text-align: center; margin: 20px 0; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🎫 Transcrito de Ticket</h1>
            <p><strong>Canal:</strong> #{channel_name}</p>
            <p><strong>Servidor:</strong> {guild_name}</p>
            <p><strong>Data de Geração:</strong> {date}</p>
        </div>
        <div class="messages">
    """
    
    html = html.replace("{channel_name}", channel.name)
    html = html.replace("{guild_name}", channel.guild.name)
    html = html.replace("{date}", datetime.datetime.now(obter_timezone()).strftime("%d/%m/%Y %H:%M:%S"))
    
    for msg in mensagens:
        if msg.type == discord.MessageType.default or msg.type == discord.MessageType.reply:
            avatar_url = msg.author.display_avatar.url if msg.author.display_avatar else "https://cdn.discordapp.com/embed/avatars/0.png"
            time_str = msg.created_at.astimezone(obter_timezone()).strftime("%d/%m/%Y %H:%M")
            content = msg.clean_content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            
            html += f"""
            <div class="message-group">
                <img src="{avatar_url}" alt="Avatar" class="avatar">
                <div class="message-content">
                    <div class="message-header">
                        <span class="username">{msg.author.display_name}</span>
                        <span class="timestamp">{time_str}</span>
                    </div>
                    <div class="message-text">{content}</div>
            """
            
            for embed in msg.embeds:
                if embed.title or embed.description:
                    e_title = embed.title.replace("<", "&lt;") if embed.title else ""
                    e_desc = embed.description.replace("<", "&lt;").replace("\n", "<br>") if embed.description else ""
                    html += f"""
                    <div class="embed">
                        <div class="embed-title">{e_title}</div>
                        <div class="embed-desc">{e_desc}</div>
                    </div>
                    """
            
            html += """
                </div>
            </div>
            """
        else:
            time_str = msg.created_at.astimezone(obter_timezone()).strftime("%d/%m/%Y %H:%M")
            html += f"""
            <div class="system-message">
                [{time_str}] Mensagem de sistema gerada.
            </div>
            """
            
    html += """
        </div>
    </body>
    </html>
    """
    
    return io.BytesIO(html.encode('utf-8'))

# ==========================================
# VIEWS E MODALS
# ==========================================

class TicketModal(Modal):
    def __init__(self, category_name: str, bot: commands.Bot) -> None:
        super().__init__(title=f"Novo Ticket: {category_name}", timeout=600)
        self.category_name = category_name
        self.bot = bot
        
        self.add_item(InputText(label="Assunto do Atendimento", placeholder="Ex: Problema técnico, Dúvida, etc.", style=discord.InputTextStyle.short, required=True, max_length=100))
        self.add_item(InputText(label="Descreva detalhadamente a sua situação", placeholder="Forneça o máximo de detalhes possível para que a staff possa ajudá-lo rapidamente...", style=discord.InputTextStyle.long, required=True, max_length=1500))

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        assunto = self.children[0].value
        detalhes = self.children[1].value
        
        cfg = get_configs()
        cat_id = cfg.get("ticket_category_id")
        guild = interaction.guild
        
        category = None
        if cat_id:
            category = guild.get_channel(int(cat_id))
            
        if not category:
            try:
                category = await guild.create_category("📁 ATENDIMENTOS")
            except:
                pass
                
        # Gerar ID do ticket
        ticket_id = f"{interaction.user.name[:5]}-{secrets.token_hex(2)}"
        emoji_prefix = "🎫"
        if "Suporte" in self.category_name: emoji_prefix = "🔴"
        elif "Denúncia" in self.category_name: emoji_prefix = "🛡️"
        elif "Recrutamento" in self.category_name: emoji_prefix = "💼"
        elif "Parcerias" in self.category_name: emoji_prefix = "🤝"
        
        channel_name = f"{emoji_prefix}-{ticket_id}"
        
        admin_roles = get_admin_roles(guild)
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True, manage_permissions=True, manage_messages=True)
        }
        
        for r in admin_roles:
            overwrites[r] = discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_messages=True)
            
        try:
            ticket_channel = await guild.create_text_channel(name=channel_name, category=category, overwrites=overwrites, reason=f"Ticket criado por {interaction.user}")
        except Exception as e:
            return await interaction.followup.send(f"❌ Ocorreu um erro ao criar o canal do ticket: {e}", ephemeral=True)
            
        # Registar no BD
        await db.create_ticket(ticket_channel.id, interaction.user.id, self.category_name, assunto, detalhes)
        
        # Procurar staff online
        online_admins = get_online_admins(guild)
        online_text = ""
        ping_text = ""
        
        if online_admins:
            admin_mentions = [a.mention for a in online_admins][:10] # max 10
            online_text = "🟢 **Staff Online Disponível:**\n" + "\n".join([f"• {m}" for m in admin_mentions])
            ping_text = " ".join(admin_mentions)
        else:
            online_text = "⚠️ **Nenhuma staff online no momento.**\nA sua solicitação foi registada e entraremos em contacto assim que possível."
            
        embed = discord.Embed(
            title=f"🎫 Ticket #{ticket_id.split('-')[-1].upper()}",
            description=f"Olá {interaction.user.mention}! Bem-vindo ao seu atendimento de **{self.category_name}**.\n\nA nossa equipa irá ajudá-lo(a) em breve. Por favor, aguarde.",
            color=discord.Color.blue()
        )
        embed.add_field(name="Assunto", value=assunto, inline=False)
        embed.add_field(name="Detalhes", value=f"```{detalhes}```", inline=False)
        embed.add_field(name="Disponibilidade da Equipa", value=online_text, inline=False)
        embed.set_footer(text=f"{cfg.get('server_name', 'Server')} • Central de Ajuda", icon_url=guild.icon.url if guild.icon else None)
        
        view = TicketControlButtons(self.bot)
        msg = await ticket_channel.send(content=f"{interaction.user.mention} {ping_text}", embed=embed, view=view)
        
        # Opcional: apagar a mensagem com o texto de ping e deixar apenas o embed para ficar limpo (mantém o ping nas notificações)
        await interaction.followup.send(f"✅ **O seu ticket foi criado:** {ticket_channel.mention}", ephemeral=True)


class TicketPanelButtons(View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Suporte Geral", emoji="🔴", style=discord.ButtonStyle.blurple, custom_id="ticket_panel_suporte")
    async def btn_suporte(self, button: Button, interaction: discord.Interaction):
        await interaction.response.send_modal(TicketModal("Suporte Geral", self.bot))
        
    @discord.ui.button(label="Denúncia", emoji="🛡️", style=discord.ButtonStyle.danger, custom_id="ticket_panel_denuncia")
    async def btn_denuncia(self, button: Button, interaction: discord.Interaction):
        await interaction.response.send_modal(TicketModal("Denúncia / Report", self.bot))
        
    @discord.ui.button(label="Recrutamento", emoji="💼", style=discord.ButtonStyle.success, custom_id="ticket_panel_recrutamento")
    async def btn_recrutamento(self, button: Button, interaction: discord.Interaction):
        await interaction.response.send_modal(TicketModal("Recrutamento", self.bot))
        
    @discord.ui.button(label="Parcerias / Outros", emoji="🤝", style=discord.ButtonStyle.secondary, custom_id="ticket_panel_parcerias")
    async def btn_parcerias(self, button: Button, interaction: discord.Interaction):
        await interaction.response.send_modal(TicketModal("Parcerias / Outros", self.bot))


class TicketControlButtons(View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    async def is_staff(self, interaction: discord.Interaction):
        admin_roles = get_admin_roles(interaction.guild)
        if interaction.user.guild_permissions.administrator: return True
        return any(r in interaction.user.roles for r in admin_roles)

    @discord.ui.button(label="Assumir", emoji="👤", style=discord.ButtonStyle.primary, custom_id="ticket_claim")
    async def claim_button(self, button: Button, interaction: discord.Interaction):
        if not await self.is_staff(interaction):
            return await interaction.response.send_message("❌ Apenas membros da administração podem assumir tickets.", ephemeral=True)
            
        ticket_data = await db.get_ticket(interaction.channel_id)
        if not ticket_data:
            return await interaction.response.send_message("❌ Este canal não está registado como um ticket ativo.", ephemeral=True)
            
        if ticket_data[5] == 'claimed':
            if ticket_data[6] == interaction.user.id:
                return await interaction.response.send_message("✅ Já assumiste este ticket.", ephemeral=True)
            return await interaction.response.send_message("❌ Este ticket já foi assumido por outro staff.", ephemeral=True)
            
        await interaction.response.defer()
        await db.claim_ticket(interaction.channel_id, interaction.user.id)
        
        try:
            await interaction.channel.edit(name=f"atendido-{interaction.user.name[:10]}")
        except:
            pass
            
        embed = discord.Embed(description=f"👤 **Este ticket foi assumido por {interaction.user.mention}** e será atendido em breve.", color=discord.Color.green())
        await interaction.followup.send(embed=embed)
        
        # Desabilita o botão de assumir (opcional) ou atualiza a view
        button.disabled = True
        button.label = "Assumido"
        await interaction.message.edit(view=self)

    @discord.ui.button(label="Fechar", emoji="🔒", style=discord.ButtonStyle.danger, custom_id="ticket_close")
    async def close_button(self, button: Button, interaction: discord.Interaction):
        if not await self.is_staff(interaction):
            # Se não é staff, verificar se é o criador
            ticket_data = await db.get_ticket(interaction.channel_id)
            if not ticket_data or ticket_data[1] != interaction.user.id:
                return await interaction.response.send_message("❌ Não tens permissão para fechar este ticket.", ephemeral=True)
                
        await interaction.response.send_message("🔒 A encerrar ticket e a gerar transcrito... (O canal será apagado em 5 segundos)")
        
        # Desabilita botões
        for child in self.children: child.disabled = True
        await interaction.message.edit(view=self)
        
        # Gerar Transcrito
        transcript = await gerar_transcript_html(interaction.channel)
        
        ticket_data = await db.get_ticket(interaction.channel_id)
        creator_id = ticket_data[1] if ticket_data else None
        
        cfg = get_configs()
        log_channel_id = cfg.get("ticket_log_channel_id")
        
        file = discord.File(transcript, filename=f"transcript-{interaction.channel.name}.html")
        
        log_embed = discord.Embed(title=f"📁 Transcrito: {interaction.channel.name}", color=discord.Color.red())
        log_embed.add_field(name="Fechado por", value=interaction.user.mention)
        if creator_id: log_embed.add_field(name="Criador", value=f"<@{creator_id}>")
        
        # Enviar logs
        if log_channel_id:
            log_channel = interaction.guild.get_channel(int(log_channel_id))
            if log_channel:
                try:
                    await log_channel.send(embed=log_embed, file=file)
                except Exception as e:
                    print(f"Erro ao enviar log do ticket: {e}")
                    
        # Tentar enviar ao criador
        if creator_id:
            creator = interaction.guild.get_member(creator_id) or self.bot.get_user(creator_id)
            if creator:
                try:
                    transcript.seek(0)
                    user_file = discord.File(transcript, filename=f"transcript-{interaction.channel.name}.html")
                    await creator.send("🎫 O seu ticket de suporte foi encerrado. Aqui está o transcrito da conversa para os seus registos.", file=user_file)
                except:
                    pass
                    
        await db.close_ticket(interaction.channel_id, interaction.user.id)
        
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except:
            pass

    @discord.ui.button(label="Transcrito", emoji="📁", style=discord.ButtonStyle.secondary, custom_id="ticket_transcript")
    async def transcript_button(self, button: Button, interaction: discord.Interaction):
        if not await self.is_staff(interaction):
            return await interaction.response.send_message("❌ Apenas membros da administração podem gerar transcritos manuais.", ephemeral=True)
            
        await interaction.response.defer()
        transcript = await gerar_transcript_html(interaction.channel)
        file = discord.File(transcript, filename=f"transcript-manual-{interaction.channel.name}.html")
        await interaction.followup.send("📁 **Transcrito gerado com sucesso.**", file=file)
        
    @discord.ui.button(label="Apagar", emoji="❌", style=discord.ButtonStyle.secondary, custom_id="ticket_delete")
    async def delete_button(self, button: Button, interaction: discord.Interaction):
        if not await self.is_staff(interaction):
            return await interaction.response.send_message("❌ Apenas membros da administração podem forçar a exclusão.", ephemeral=True)
            
        await interaction.response.send_message("❌ O canal será apagado instantaneamente.")
        await db.close_ticket(interaction.channel_id, interaction.user.id)
        await asyncio.sleep(2)
        try:
            await interaction.channel.delete()
        except:
            pass


# ==========================================
# COG PRINCIPAL
# ==========================================

class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        # Garantir que botões persistem reinícios
        self.bot.add_view(TicketPanelButtons(self.bot))
        self.bot.add_view(TicketControlButtons(self.bot))
        print("🎫 Sistema de Tickets Premium carregado!")

    @commands.slash_command(name="ticket_painel", description="[ADM] Cria o painel interativo de tickets no canal", contexts={discord.InteractionContextType.guild})
    @commands.has_permissions(administrator=True)
    async def ticket_painel(self, ctx: discord.ApplicationContext):
        cfg = get_configs()
        embed = discord.Embed(
            title=f"🎫 Central de Suporte - {cfg.get('server_name', 'Corporação')}",
            description=(
                "**Precisa de ajuda ou deseja fazer uma denúncia?**\n"
                "Seja bem-vindo ao suporte da nossa comunidade. Selecione uma das opções abaixo para abrir um atendimento privado.\n\n"
                "**Categorias Disponíveis:**\n"
                "🔴 **Suporte Geral:** Dúvidas, problemas técnicos ou auxílio no servidor.\n"
                "🛡️ **Denúncia:** Reportar infrações de regras ou comportamentos inadequados.\n"
                "💼 **Recrutamento:** Questões sobre candidaturas e vagas.\n"
                "🤝 **Parcerias / Outros:** Negócios, parcerias ou assuntos diversos."
            ),
            color=discord.Color.from_rgb(47, 49, 54) # Cor premium estilo Discord
        )
        embed.set_footer(text="A nossa equipa está pronta para ajudar.")
        if ctx.guild.icon:
            embed.set_thumbnail(url=ctx.guild.icon.url)

        await ctx.send(embed=embed, view=TicketPanelButtons(self.bot))
        await ctx.respond("✅ Painel criado com sucesso!", ephemeral=True)

    @commands.slash_command(name="ticket_config", description="[ADM] Configurar canais e cargos do sistema de tickets", contexts={discord.InteractionContextType.guild})
    @commands.has_permissions(administrator=True)
    async def ticket_config(self, ctx: discord.ApplicationContext,
                            categoria: Option(discord.CategoryChannel, "Categoria onde os tickets serão criados", required=False),
                            log_channel: Option(discord.TextChannel, "Canal onde os transcritos serão guardados", required=False),
                            admin_role: Option(discord.Role, "Cargo da staff de atendimento", required=False)):
        
        await ctx.defer(ephemeral=True)
        import sqlite3
        import json
        conn = sqlite3.connect('db.sqlite3')
        cursor = conn.cursor()
        
        updates = []
        if categoria:
            cursor.execute("INSERT INTO configuracoes (chave, valor) VALUES (?, ?) ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor", ("ticket_category_id", str(categoria.id)))
            updates.append(f"📁 Categoria definida para: {categoria.name}")
        if log_channel:
            cursor.execute("INSERT INTO configuracoes (chave, valor) VALUES (?, ?) ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor", ("ticket_log_channel_id", str(log_channel.id)))
            updates.append(f"📝 Canal de Logs definido para: {log_channel.mention}")
        if admin_role:
            cursor.execute("INSERT INTO configuracoes (chave, valor) VALUES (?, ?) ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor", ("ticket_admin_role_id", str(admin_role.id)))
            updates.append(f"🛡️ Cargo de Staff definido para: {admin_role.name}")
            
        conn.commit()
        conn.close()
        
        if updates:
            await ctx.followup.send("✅ **Configurações de Ticket Atualizadas:**\n" + "\n".join(updates))
        else:
            await ctx.followup.send("⚠️ Nenhuma alteração fornecida.")

    @commands.slash_command(name="add_user", description="[STAFF] Adicionar um utilizador a este ticket", contexts={discord.InteractionContextType.guild})
    async def add_user(self, ctx: discord.ApplicationContext, utilizador: Option(discord.Member, "Membro a adicionar", required=True)):
        ticket = await db.get_ticket(ctx.channel.id)
        if not ticket:
            return await ctx.respond("❌ Este comando apenas pode ser usado dentro de um ticket ativo.", ephemeral=True)
            
        admin_roles = get_admin_roles(ctx.guild)
        if not ctx.author.guild_permissions.administrator and not any(r in ctx.author.roles for r in admin_roles):
            return await ctx.respond("❌ Apenas membros da administração podem gerir utilizadores.", ephemeral=True)
            
        await ctx.channel.set_permissions(utilizador, read_messages=True, send_messages=True, attach_files=True, embed_links=True)
        await ctx.respond(f"✅ O utilizador {utilizador.mention} foi adicionado a este atendimento.")

    @commands.slash_command(name="remove_user", description="[STAFF] Remover um utilizador deste ticket", contexts={discord.InteractionContextType.guild})
    async def remove_user(self, ctx: discord.ApplicationContext, utilizador: Option(discord.Member, "Membro a remover", required=True)):
        ticket = await db.get_ticket(ctx.channel.id)
        if not ticket:
            return await ctx.respond("❌ Este comando apenas pode ser usado dentro de um ticket ativo.", ephemeral=True)
            
        admin_roles = get_admin_roles(ctx.guild)
        if not ctx.author.guild_permissions.administrator and not any(r in ctx.author.roles for r in admin_roles):
            return await ctx.respond("❌ Apenas membros da administração podem gerir utilizadores.", ephemeral=True)
            
        await ctx.channel.set_permissions(utilizador, read_messages=False, send_messages=False)
        await ctx.respond(f"✅ O utilizador {utilizador.mention} foi removido deste atendimento.")

    @commands.slash_command(name="rename_ticket", description="[STAFF] Renomear o canal do ticket atual", contexts={discord.InteractionContextType.guild})
    async def rename_ticket(self, ctx: discord.ApplicationContext, novo_nome: Option(str, "Novo nome para o canal", required=True)):
        ticket = await db.get_ticket(ctx.channel.id)
        if not ticket:
            return await ctx.respond("❌ Este comando apenas pode ser usado dentro de um ticket ativo.", ephemeral=True)
            
        admin_roles = get_admin_roles(ctx.guild)
        if not ctx.author.guild_permissions.administrator and not any(r in ctx.author.roles for r in admin_roles):
            return await ctx.respond("❌ Apenas membros da administração podem gerir o canal.", ephemeral=True)
            
        try:
            await ctx.channel.edit(name=novo_nome)
            await ctx.respond(f"✅ Nome do canal alterado para: `#{(novo_nome).lower().replace(' ', '-')}`")
        except Exception as e:
            await ctx.respond(f"❌ Erro ao renomear o canal: {e}", ephemeral=True)

    @commands.slash_command(name="ticket_online", description="[STAFF] Lista toda a equipa de atendimento que está online", contexts={discord.InteractionContextType.guild})
    async def ticket_online(self, ctx: discord.ApplicationContext):
        await ctx.defer()
        online_admins = get_online_admins(ctx.guild)
        
        if not online_admins:
            return await ctx.followup.send("⚠️ Nenhuma equipa de atendimento online no momento.")
            
        desc = ""
        for m in online_admins:
            status_emoji = "🟢" if m.status == discord.Status.online else "🟡" if m.status == discord.Status.idle else "🔴"
            desc += f"{status_emoji} {m.mention} - `{m.display_name}`\n"
            
        embed = discord.Embed(title="👥 Status da Equipa de Atendimento", description=desc, color=discord.Color.blue())
        embed.set_footer(text=f"Total: {len(online_admins)} ativos")
        await ctx.followup.send(embed=embed)

    @commands.slash_command(name="ticket_stats", description="[STAFF] Visualiza as estatísticas globais do sistema de tickets", contexts={discord.InteractionContextType.guild})
    async def ticket_stats(self, ctx: discord.ApplicationContext):
        await ctx.defer()
        ativas = await db.get_active_ticket_count()
        assumidas = await db.get_claimed_ticket_count()
        
        embed = discord.Embed(title="📊 Estatísticas de Atendimentos", color=discord.Color.purple())
        embed.add_field(name="Tickets Abertos (Geral)", value=f"`{ativas}`", inline=True)
        embed.add_field(name="Tickets Assumidos", value=f"`{assumidas}`", inline=True)
        embed.add_field(name="Aguardando Atendimento", value=f"`{ativas - assumidas}`", inline=True)
        
        await ctx.followup.send(embed=embed)

def setup(bot):
    bot.add_cog(Tickets(bot))
