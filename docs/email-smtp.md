# SMTP — envio do e-mail de convite

O backend envia o convite de conta (`gerar_email_convite` em `app/routers/usuarios.py`) por SMTP. As
credenciais vivem **só** no `.env` do servidor, em modo `600`.

| variável | o que é |
|---|---|
| `SMTP_HOST` | servidor SMTP (`smtp.gmail.com`, `smtp.office365.com`, `smtp.sendgrid.net`…) |
| `SMTP_PORT` | `587` (STARTTLS) |
| `SMTP_USER` | usuário da autenticação |
| `SMTP_PASSWORD` | senha de app / API key — **nunca a senha da conta** |
| `EMAIL_FROM` | remetente exibido (default do código: `noreply@h2ia.ufpel.edu.br`) |

## Gmail (o caminho usado hoje)

1. Crie uma conta dedicada ao sistema — não use uma conta pessoal.
2. Ative a **verificação em 2 etapas** em https://myaccount.google.com/security (sem ela o Google não
   oferece senha de app).
3. Gere uma **senha de app** em https://myaccount.google.com/apppasswords → "Outro (nome
   personalizado)" → `H2IA Tutor`. São 16 caracteres, no formato `abcd efgh ijkl mnop`.
4. Edite o `.env` no servidor e reinicie o serviço:

```bash
ssh -i <sua-chave-privada> <usuario>@<servidor>     # o endereço e a chave estão no CLAUDE.md do workspace
nano <caminho-do-backend>/.env           # SMTP_USER, SMTP_PASSWORD, EMAIL_FROM
sudo systemctl restart h2ia-backend.service
sudo systemctl is-active h2ia-backend.service
```

**Reinicie pelo systemd, nunca à mão.** A versão anterior deste guia mandava `pkill -f uvicorn` e
subir um `nohup uvicorn --host 0.0.0.0 --port 8000`, o que fazia três estragos de uma vez: matava o
processo gerido pelo systemd (deixando um uvicorn órfão sem `Restart=`), subia na **porta 8000**
enquanto o nginx faz `proxy_pass` para a **8002** (API fora do ar), e reabria a aplicação em
`0.0.0.0`, isto é, na internet em HTTP puro — exatamente o defeito de segurança corrigido em 04/08.

## Outros provedores

```bash
# Outlook / Hotmail
SMTP_HOST=smtp.office365.com
SMTP_PORT=587
SMTP_USER=seu-email@outlook.com
SMTP_PASSWORD=sua-senha-de-app

# SendGrid (crie a conta e gere uma API Key)
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USER=apikey
SMTP_PASSWORD=SUA_API_KEY
EMAIL_FROM=seu-email@seudominio.com
```

## Testar

No servidor, com os valores já no `.env` (o teste os lê de lá, para não deixar segredo no histórico
do shell):

```bash
cd /home/ubuntu/servers/Iana
DESTINO=voce@exemplo.com venv/bin/python - <<'PY'
import os, smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv
load_dotenv()

msg = MIMEText("Teste de envio do H2IA Tutor.")
msg["Subject"] = "Teste H2IA Tutor"
msg["From"] = os.environ["EMAIL_FROM"]
msg["To"] = os.environ["DESTINO"]

with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", 587))) as s:
    s.starttls()
    s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
    s.send_message(msg)
print("enviado")
PY
```
