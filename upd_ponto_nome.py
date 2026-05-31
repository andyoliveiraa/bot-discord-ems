import sys

with open('ponto.py', 'r', encoding='utf-8') as f:
    content = f.read()

target1 = '''import json
        pauses_info = json.dumps({"staff": ctx.author.id, "motivo": motivo})
        await db.create_registry(usuario.id, agora, agora, 2, total, pauses_info)'''

repl1 = '''import json
        pauses_info = json.dumps({"staff": ctx.author.id, "staff_nome": ctx.author.display_name, "motivo": motivo})
        await db.create_registry(usuario.id, agora, agora, 2, total, pauses_info)'''

target2 = '''import json
        pauses_info = json.dumps({"staff": ctx.author.id, "motivo": motivo})
        await db.create_registry(usuario.id, agora, agora, 3, -total, pauses_info)'''

repl2 = '''import json
        pauses_info = json.dumps({"staff": ctx.author.id, "staff_nome": ctx.author.display_name, "motivo": motivo})
        await db.create_registry(usuario.id, agora, agora, 3, -total, pauses_info)'''

content = content.replace(target1, repl1)
content = content.replace(target2, repl2)

with open('ponto.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Updated ponto.py with staff_nome")
