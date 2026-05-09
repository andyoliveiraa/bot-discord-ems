# 🤖 Bot de Pica-Ponto para Corporações/Empresas (FiveM/MTA) no Discord

Bot de registo de horas de serviço desenvolvido para servidores de roleplay. Permite que os funcionários/membros registem a entrada e saída do turno diretamente pelo Discord, com suporte a pausas, relatórios semanais, logs automáticos e muito mais.

---

## 📋 Funcionalidades

- ⏰ Registo de entrada e saída de serviço via comando `/ponto`
- ⏸️ Sistema de pausa e retoma do turno em tempo real
- 📊 Contabilização automática de horas (descontando pausas)
- 🏆 Ranking semanal de horas trabalhadas
- 📝 Histórico detalhado de pontos por dia (`/pontosreg`)
- 🔔 Logs automáticos no canal de staff em cada evento relevante
- 🔄 Encerramento automático do ponto após 24h de inatividade (com DM ao funcionário)
- ➕ Adição/Remoção manual de horas por staff
- 📅 Relatório semanal com horas por dia por funcionário (`/semana`)
- 🔁 Reset semanal com backup da base de dados (`/resetarsemana`)
- ⚙️ Totalmente configurável via `config.json`

> **🧠 Recomenda-se utilizar o bot em apenas um servidor por vez, pois foi desenvolvido para funcionar em instância única.**

---

## 🚀 Instalação

### Pré-requisitos
- Python 3.8 ou superior
- Um bot criado no [Portal de Desenvolvedores do Discord](https://discord.com/developers/applications)

### Passo a Passo

1. Clone o repositório:
```bash
git clone https://github.com/andyoliveiraa/bot-discord.git
cd bot-discord
```

2. Instale as dependências:
```bash
pip install -r requirements.txt
```

3. Configure o arquivo `config.json`:
```json
{
    "server_name": "Nome do Seu Servidor",
    "token": "Token do bot do Discord",
    "owner_id": SEU_ID_DISCORD,
    "log_channel_id": ID_CANAL_LOGS,
    "staff_role_id": ID_CARGO_STAFF,
    "ponto_role_id": ID_CARGO_ACESSO_PONTO,
    "nome_corp": "NOME_DA_CORPORAÇÃO",
    "timezone": "Europe/Lisbon"
}
```

| Campo | Descrição |
|---|---|
| `server_name` | Nome do servidor (aparece nos embeds) |
| `token` | Token do bot no Discord Developer Portal |
| `owner_id` | ID do dono do bot (acesso ao `/backup`) |
| `log_channel_id` | ID do canal onde os logs serão enviados |
| `staff_role_id` | ID do cargo com acesso aos comandos de staff |
| `ponto_role_id` | ID do cargo necessário para usar `/ponto` e `/pontosreg` |
| `nome_corp` | Nome da corporação (aparece no painel de ponto) |
| `timezone` | Fuso horário (ex: `Europe/Lisbon`, `America/Sao_Paulo`) |

4. Execute o bot:
```bash
python main.py
```

---

## 📝 Comandos

### 🟢 Comandos para Funcionários
> Requerem o cargo definido em `ponto_role_id`

| Comando | Descrição |
|---|---|
| `/ponto` | Inicia o teu turno. Cria um painel pessoal com botões de **Pausar** e **Finalizar**. Se já tens um ponto ativo, atualiza o painel no canal atual. |
| `/pontosreg` | Mostra o histórico completo de pontos da semana (privado, só tu vês). Lista os turnos por dia com horários de entrada/saída, duração e pausas realizadas. |

---

### 🔴 Comandos de Staff
> Requerem o cargo definido em `staff_role_id`

| Comando | Descrição |
|---|---|
| `/addtempo` | Adiciona horas e minutos ao total semanal de um funcionário. Requer selecionar o utilizador, quantidade de horas/minutos e um motivo. O funcionário recebe uma DM a informar da alteração. |
| `/deltempo` | Remove horas e minutos do total semanal de um funcionário. Funciona da mesma forma que `/addtempo`, mas subtrai o tempo. |
| `/resetar_usuario` | Zera completamente as horas semanais de um funcionário específico. |
| `/resetar_todos` | Zera as horas e apaga todos os registos de todos os funcionários. Pede dupla confirmação antes de executar. |
| `/ranking` | Exibe o ranking das top 10 pessoas com mais horas na semana atual. |
| `/semana` | Gera o **relatório semanal** de horas (apenas membros com cargo `ponto_role_id`), com detalhe por dia, e envia um backup da base de dados. **Os dados não são apagados.** |
| `/resetarsemana` | Executa o encerramento completo da semana: relatório de horas por funcionário + backup da base de dados + **reset de todos os dados**. Requer confirmação. |

---

### 🔒 Comandos do Dono (Developer)

| Comando | Descrição |
|---|---|
| `/backup` | Envia o ficheiro `db.sqlite3` como anexo no chat. Apenas o utilizador com o `owner_id` configurado tem acesso. |

---

## ⏸️ Sistema de Ponto em Detalhe

### Fluxo normal
1. Funcionário usa `/ponto` → bot inicia o turno e publica uma mensagem com o painel.
2. Ao pausar, o tempo para de contar. O embed é atualizado com o horário da pausa.
3. Ao retomar, o tempo volta a contar. O tempo pausado é descontado no total.
4. Ao finalizar, o turno é encerrado, as horas contabilizadas e um log é enviado ao canal de staff.

### Encerramento automático
Se um funcionário ficar com o ponto aberto por mais de **24 horas**, o bot fecha automaticamente o ponto:
- ❌ As horas **não são contabilizadas** (prevenção de abuso)
- 📩 O funcionário recebe uma **DM** de aviso
- 📋 Um log de inatividade é enviado no canal de staff

### Encerramento forçado pela Staff
A staff pode clicar no botão **Finalizar** no painel de qualquer funcionário para encerrar o turno remotamente. O funcionário recebe uma DM e as horas **não são contabilizadas**.

---

## 🔧 Suporte

Para dúvidas, podes contactar: **andyydias** no Discord.

---

## ⚠️ Observações

- Sinta-se livre para modificar e utilizar o bot como quiser.
- A base de dados é armazenada localmente em `db.sqlite3`.
- Ideal para servidores de roleplay que querem um sistema eficiente de gestão de presenças com funcionalidades avançadas.
