import sys

with open('ponto.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace addtempo
target_add = 'await db.create_registry(usuario.id, agora, agora, 2, total, "[]")'
replacement_add = 'import json\n        pauses_info = json.dumps({"staff": ctx.author.id, "motivo": motivo})\n        await db.create_registry(usuario.id, agora, agora, 2, total, pauses_info)'

# Replace deltempo
target_del = 'await db.create_registry(usuario.id, agora, agora, 3, -total, "[]")'
replacement_del = 'import json\n        pauses_info = json.dumps({"staff": ctx.author.id, "motivo": motivo})\n        await db.create_registry(usuario.id, agora, agora, 3, -total, pauses_info)'

content = content.replace(target_add, replacement_add)
content = content.replace(target_del, replacement_del)

with open('ponto.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Modificado addtempo e deltempo")
