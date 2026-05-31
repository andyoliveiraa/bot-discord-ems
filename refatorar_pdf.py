import sys

with open('pdf_helper.py', 'r', encoding='utf-8') as f:
    content = f.read()

parts = content.split('# ── Criar PDF ──────────────────────────────────────────────────────────────')
header = parts[0]
body = parts[1]

# We modify header to replace generating PDF logic with a call to _construir_pdf
new_header = header + """
    return await _construir_pdf(dados_funcs, inicio_str, fim_str, gerado_em, str(semana_id), tz_obj)

async def _construir_pdf(dados_funcs, inicio_str, fim_str, gerado_em, semana_id, tz_obj):
    try:
        from fpdf import FPDF
    except ImportError:
        return None

# ── Criar PDF ──────────────────────────────────────────────────────────────"""

new_content = new_header + body

with open('pdf_helper.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print("Done")
