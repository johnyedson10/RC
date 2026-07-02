# RC

Sistema de relatórios mensais para publicadores e Secretário da Congregação.

## O que faz
- cadastro e login de usuário
- envio de relatório mensal
- bloqueio de mais de um relatório por mês por conta
- painel do Secretário da Congregação com lista dos relatórios
- exclusão da própria conta

## Requisitos
- Python 3.11 ou superior
- `pip`
- acesso ao Neon DB ou outro banco PostgreSQL

## Configuração
Crie um arquivo `.env` na raiz do projeto com:

```env
SECRET_KEY=coloque_uma_chave_segura_aqui
DATABASE_URL=postgresql://usuario:senha@host/banco?sslmode=require
FLASK_ENV=development
MAIL_HOST=smtp.gmail.com
MAIL_PORT=587
MAIL_USERNAME=seuemail@gmail.com
MAIL_PASSWORD=sua_senha_de_app_do_google
MAIL_FROM=seuemail@gmail.com
MAIL_USE_TLS=true
```

Para o fluxo "Esqueceu a senha?", use uma conta Google com senha de app e mantenha o e-mail cadastrado no usuário, porque o link de redefinição é enviado para esse endereço.

## Instalação
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Execução
```bash
python app.py
```

## Observação
O cadastro usa o nome normalizado, sem diferença de maiúsculas/minúsculas e sem acentos, para facilitar o login.
