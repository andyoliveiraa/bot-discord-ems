import sys

with open('templates/meus_pontos.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Target in HTML
target_html = '''        <div class="form-group" style="flex:1;margin-bottom:0;">
          <label>Minutos</label>
          <input type="number" id="modal-minutos" class="form-input" min="0" max="59" value="0">
        </div>
      </div>
    </div>'''

replacement_html = '''        <div class="form-group" style="flex:1;margin-bottom:0;">
          <label>Minutos</label>
          <input type="number" id="modal-minutos" class="form-input" min="0" max="59" value="0">
        </div>
      </div>
      <div class="form-group" style="margin-bottom:1.5rem;">
        <label>Motivo</label>
        <input type="text" id="modal-motivo" class="form-input" placeholder="Escreva o motivo da alteração">
      </div>
    </div>'''

content = content.replace(target_html, replacement_html)

target_js = '''    fd.append('horas', document.getElementById('modal-horas').value);
    fd.append('minutos', document.getElementById('modal-minutos').value);'''

replacement_js = '''    fd.append('horas', document.getElementById('modal-horas').value);
    fd.append('minutos', document.getElementById('modal-minutos').value);
    fd.append('motivo', document.getElementById('modal-motivo').value || 'Não especificado');'''

content = content.replace(target_js, replacement_js)

target_js_clear = '''  document.getElementById('modal-horas').value = 0;
  document.getElementById('modal-minutos').value = 0;'''

replacement_js_clear = '''  document.getElementById('modal-horas').value = 0;
  document.getElementById('modal-minutos').value = 0;
  document.getElementById('modal-motivo').value = '';'''

content = content.replace(target_js_clear, replacement_js_clear)

with open('templates/meus_pontos.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("Updated meus_pontos.html")
