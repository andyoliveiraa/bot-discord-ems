import sys

with open('ponto.py', 'r', encoding='utf-8') as f:
    content = f.read()

new_command = '''    @commands.slash_command(name='pdf_detalhado', description='[ADM] Gera um PDF ultra-detalhado da semana ATUAL (sem encerrar).', contexts={discord.InteractionContextType.guild})
    @has_staff_role()
    async def pdf_detalhado(self, ctx: discord.ApplicationContext):
        await ctx.defer(ephemeral=True)
        from pdf_helper import gerar_pdf_detalhado_ativa
        try:
            pdf_path = await gerar_pdf_detalhado_ativa(db, config, ctx.guild)
            if pdf_path:
                await ctx.respond(
                    content='\U0001f4c4 **Relatório Detalhado da Semana Ativa (Gerado a Pedido):**',
                    file=discord.File(pdf_path),
                    ephemeral=True
                )
            else:
                await ctx.respond('\u26a0\ufe0f Não há dados ou erro ao gerar o PDF.', ephemeral=True)
        except Exception as e:
            await ctx.respond(f'\u274c Erro ao gerar PDF detalhado: `{e}`', ephemeral=True)

'''

# We want to insert it before the resetarsemana command
target = "    @commands.slash_command(name='resetarsemana'"

parts = content.split(target)
if len(parts) == 2:
    new_content = parts[0] + new_command + target + parts[1]
    with open('ponto.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("Command inserted successfully.")
else:
    print("Could not find insertion point. Found", len(parts), "parts.")
