import sys

with open('pdf_helper.py', 'r', encoding='utf-8') as f:
    content = f.read()

target1 = '''                    if isinstance(pausas, dict) and "staff" in pausas:
                        staff_id_str = f" ID: {pausas.get('staff')}"
                        motivo_str = f"\\n    Motivo: {pausas.get('motivo', 'Não especificado')}"'''

repl1 = '''                    if isinstance(pausas, dict) and "staff" in pausas:
                        staff_nome = pausas.get('staff_nome')
                        if staff_nome:
                            staff_id_str = f" {staff_nome} (ID: {pausas.get('staff')})"
                        else:
                            staff_id_str = f" ID: {pausas.get('staff')}"
                        motivo_str = f"\\n    Motivo: {pausas.get('motivo', 'Não especificado')}"'''

# Since this pattern occurs twice (for staff_finished==2 and staff_finished==3), we can replace both at once.
content = content.replace(target1, repl1)

with open('pdf_helper.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Updated pdf_helper.py with staff_nome")
