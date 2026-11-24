# Plataforma Matilha Foveli

Programa de fidelidade da Foveli: cada compra vira ossinhos, e os ossinhos viram brownies.
Django + PostgreSQL. Escopo completo no doc "Escopo do MVP — Plataforma Matilha Foveli".

## Rodar local

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # sem POSTGRES_DB, usa SQLite
python manage.py migrate      # cria as tabelas e a tabela de recompensas
python manage.py createsuperuser
python manage.py runserver    # admin em http://localhost:8000/admin
python manage.py test matilha
```

## Onde está cada coisa

- `matilha/models.py` — Clientes, Movimentações, Recompensas, Períodos de dobro, Indicações.
- `matilha/regras.py` — todas as regras de ossinhos. Único lugar onde ossinhos entram ou saem.
- `matilha/tests/test_regras.py` — um grupo de testes por regra do escopo.
- `python manage.py expirar_saldos` — zera saldos vencidos; agendar uma vez por dia no servidor.

## Decisões tomadas no código (conferir)

- Bônus de boas-vindas, aniversário e "sentimos sua falta" só valem para quem já tinha cadastro
  na data da compra. Sem cadastro, a compra rende só os ossinhos do valor.
- Indicação: quem indica precisa ter cadastro; o indicado não pode ter comprado antes.
  O limite de 5 por mês conta as indicações registradas no mês.
- O estorno também retira os +20 de quem indicou, se a compra estornada pagou a indicação.
- O estorno pode deixar o saldo negativo se os ossinhos já tiverem sido resgatados.
- O brinde de aniversário exige uma compra no mesmo mês, além de ser uma vez por ano.
- Boas-vindas volta a valer se a compra que o rendeu for estornada.
- Tipo extra de movimentação `ajuste`, para a importação da planilha (coluna Ajuste).

## Próxima etapa

Painel: login, lançar compra e lista de clientes (ordem de construção, item 2).
