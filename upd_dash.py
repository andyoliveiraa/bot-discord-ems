import sys

with open('dashboard.py', 'r', encoding='utf-8') as f:
    content = f.read()

target = """    if action == 'add_time':
        h = int(form.get('horas', 0))
        m = int(form.get('minutos', 0))
        delta = h * 3600 + m * 60
        new_dur = duration_actual + delta
        await db.update_ponto_duration(ponto_id, new_dur)
        await db.add_time(user_id, delta)
        await db.add_log('dashboard', session['user_id'], f"Adicionou {h}h {m}m ao ponto #{ponto_id}", {'user_ponto': user_id}, cor='info')
        return jsonify({'ok': True, 'nova_duration': new_dur})

    elif action == 'remove_time':
        h = int(form.get('horas', 0))
        m = int(form.get('minutos', 0))
        delta = h * 3600 + m * 60
        new_dur = max(0, duration_actual - delta)
        removed = duration_actual - new_dur
        await db.update_ponto_duration(ponto_id, new_dur)
        await db.del_time(user_id, removed)
        await db.add_log('dashboard', session['user_id'], f"Removeu {h}h {m}m do ponto #{ponto_id}", {'user_ponto': user_id}, cor='warning')
        return jsonify({'ok': True, 'nova_duration': new_dur})"""

replacement = """    if action == 'add_time':
        h = int(form.get('horas', 0))
        m = int(form.get('minutos', 0))
        motivo = form.get('motivo', 'Não especificado')
        delta = h * 3600 + m * 60
        import datetime, json
        from pytz import timezone as tz
        agora = int(datetime.datetime.now(tz(config.get('timezone', 'UTC'))).timestamp())
        pauses_info = json.dumps({"staff": session['user_id'], "motivo": motivo, "referencia_ponto": ponto_id})
        await db.create_registry(user_id, agora, agora, 2, delta, pauses_info)
        await db.add_time(user_id, delta)
        await db.add_log('dashboard', session['user_id'], f"Adicionou {h}h {m}m ao usuário {user_id}", {'user_ponto': user_id, 'motivo': motivo}, cor='info')
        return jsonify({'ok': True})

    elif action == 'remove_time':
        h = int(form.get('horas', 0))
        m = int(form.get('minutos', 0))
        motivo = form.get('motivo', 'Não especificado')
        delta = h * 3600 + m * 60
        import datetime, json
        from pytz import timezone as tz
        agora = int(datetime.datetime.now(tz(config.get('timezone', 'UTC'))).timestamp())
        pauses_info = json.dumps({"staff": session['user_id'], "motivo": motivo, "referencia_ponto": ponto_id})
        await db.create_registry(user_id, agora, agora, 3, -delta, pauses_info)
        await db.del_time(user_id, delta)
        await db.add_log('dashboard', session['user_id'], f"Removeu {h}h {m}m do usuário {user_id}", {'user_ponto': user_id, 'motivo': motivo}, cor='warning')
        return jsonify({'ok': True})"""

content = content.replace(target, replacement)

with open('dashboard.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Updated dashboard.py")
