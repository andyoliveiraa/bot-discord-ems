import sys

with open('pdf_helper.py', 'r', encoding='utf-8') as f:
    content = f.read()

target = '''                # Ajuste positivo por Staff
                if staff_finished == 2:
                    pdf.set_fill_color(220, 255, 220)
                    pdf.set_font("Arial", 'B', 9)
                    pdf.multi_cell(190, 6, _enc(f"  [AJUSTE POSITIVO por Staff] em {dt_in_str}"), fill=True, new_x='LMARGIN', new_y='NEXT')
                    _linha_multi(pdf,
                        f"    Staff adicionou manualmente {_fmt_dur(duration)} de trabalho a este funcionario.",
                        cor=(0, 100, 0), tamanho=8)
                    _linha(pdf, f"    Horas adicionadas: +{_fmt_dur(duration)}  ({duration}s)", cor=(0, 120, 0), tamanho=9)
                    pdf.ln(2)
                    total_seg_ajustes += duration

                # Ajuste negativo por Staff
                elif staff_finished == 3:
                    pdf.set_fill_color(255, 220, 220)
                    pdf.set_font("Arial", 'B', 9)
                    pdf.multi_cell(190, 6, _enc(f"  [AJUSTE NEGATIVO por Staff] em {dt_in_str}"), fill=True, new_x='LMARGIN', new_y='NEXT')
                    _linha_multi(pdf,
                        f"    Staff removeu manualmente {_fmt_dur(abs(duration))} de trabalho a este funcionario.",
                        cor=(150, 0, 0), tamanho=8)
                    _linha(pdf, f"    Horas removidas: {_fmt_dur(duration)}  ({duration}s)", cor=(180, 0, 0), tamanho=9)
                    pdf.ln(2)
                    total_seg_removidos += abs(duration)'''

replacement = '''                # Ajuste positivo por Staff
                if staff_finished == 2:
                    pdf.set_fill_color(220, 255, 220)
                    pdf.set_font("Arial", 'B', 9)
                    pdf.multi_cell(190, 6, _enc(f"  [AJUSTE POSITIVO por Staff] em {dt_in_str}"), fill=True, new_x='LMARGIN', new_y='NEXT')
                    
                    staff_id_str = ""
                    motivo_str = ""
                    if isinstance(pausas, dict) and "staff" in pausas:
                        staff_id_str = f" ID: {pausas.get('staff')}"
                        motivo_str = f"\\n    Motivo: {pausas.get('motivo', 'Não especificado')}"
                        
                    _linha_multi(pdf,
                        f"    Staff{staff_id_str} adicionou manualmente {_fmt_dur(duration)} de trabalho a este funcionario.{motivo_str}",
                        cor=(0, 100, 0), tamanho=8)
                    _linha(pdf, f"    Horas adicionadas: +{_fmt_dur(duration)}  ({duration}s)", cor=(0, 120, 0), tamanho=9)
                    pdf.ln(2)
                    total_seg_ajustes += duration

                # Ajuste negativo por Staff
                elif staff_finished == 3:
                    pdf.set_fill_color(255, 220, 220)
                    pdf.set_font("Arial", 'B', 9)
                    pdf.multi_cell(190, 6, _enc(f"  [AJUSTE NEGATIVO por Staff] em {dt_in_str}"), fill=True, new_x='LMARGIN', new_y='NEXT')
                    
                    staff_id_str = ""
                    motivo_str = ""
                    if isinstance(pausas, dict) and "staff" in pausas:
                        staff_id_str = f" ID: {pausas.get('staff')}"
                        motivo_str = f"\\n    Motivo: {pausas.get('motivo', 'Não especificado')}"
                        
                    _linha_multi(pdf,
                        f"    Staff{staff_id_str} removeu manualmente {_fmt_dur(abs(duration))} de trabalho a este funcionario.{motivo_str}",
                        cor=(150, 0, 0), tamanho=8)
                    _linha(pdf, f"    Horas removidas: {_fmt_dur(duration)}  ({duration}s)", cor=(180, 0, 0), tamanho=9)
                    pdf.ln(2)
                    total_seg_removidos += abs(duration)'''

content = content.replace(target, replacement)

with open('pdf_helper.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Updated pdf_helper.py")
