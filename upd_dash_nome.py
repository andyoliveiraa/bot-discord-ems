import sys

with open('dashboard.py', 'r', encoding='utf-8') as f:
    content = f.read()

target1 = '''        pauses_info = json.dumps({"staff": session['user_id'], "motivo": motivo, "referencia_ponto": ponto_id})
        await db.create_registry(user_id, agora, agora, 2, delta, pauses_info)'''

repl1 = '''        func_staff = await db.get_funcionario(session['user_id'])
        staff_nome = func_staff[2] if func_staff else str(session['user_id'])
        pauses_info = json.dumps({"staff": session['user_id'], "staff_nome": staff_nome, "motivo": motivo, "referencia_ponto": ponto_id})
        await db.create_registry(user_id, agora, agora, 2, delta, pauses_info)'''

target2 = '''        pauses_info = json.dumps({"staff": session['user_id'], "motivo": motivo, "referencia_ponto": ponto_id})
        await db.create_registry(user_id, agora, agora, 3, -delta, pauses_info)'''

repl2 = '''        func_staff = await db.get_funcionario(session['user_id'])
        staff_nome = func_staff[2] if func_staff else str(session['user_id'])
        pauses_info = json.dumps({"staff": session['user_id'], "staff_nome": staff_nome, "motivo": motivo, "referencia_ponto": ponto_id})
        await db.create_registry(user_id, agora, agora, 3, -delta, pauses_info)'''

content = content.replace(target1, repl1)
content = content.replace(target2, repl2)

with open('dashboard.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Updated dashboard.py with staff_nome")
