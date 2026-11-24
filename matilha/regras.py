"""Regras da Matilha Foveli (regulamento + decisões do escopo do MVP).

Este é o único lugar onde ossinhos entram ou saem. O painel e a importação
da planilha devem chamar estas funções, nunca criar Movimentacao à mão.
"""

import calendar
import re
from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max, Sum

from .models import Canal, Cliente, Indicacao, Movimentacao, PeriodoDobro, Recompensa

T = Movimentacao.Tipo
B = Movimentacao.Bonus

BOAS_VINDAS = 10
INDICADO = 10
INDICOU = 20
SENTIMOS_SUA_FALTA = 15
DIAS_SENTIMOS_SUA_FALTA = 45
MESES_VALIDADE = 6
INDICACOES_POR_MES = 5


# ---------------------------------------------------------------- utilitários

def normalizar_celular(celular: str) -> str:
    numeros = re.sub(r"\D", "", celular or "")
    if numeros.startswith("55") and len(numeros) in (12, 13):
        numeros = numeros[2:]
    if not re.fullmatch(r"\d{10,11}", numeros):
        raise ValidationError("Celular inválido: use só números, com DDD.")
    return numeros


def somar_meses(d: date, meses: int) -> date:
    mes = d.month - 1 + meses
    ano = d.year + mes // 12
    mes = mes % 12 + 1
    dia = min(d.day, calendar.monthrange(ano, mes)[1])
    return date(ano, mes, dia)


def ossinhos_do_valor(valor: Decimal) -> int:
    """R$ 1 = 1 ossinho, arredondado para baixo (R$ 18,50 rende 18)."""
    return int(Decimal(valor) // 1)


def cliente_cadastrado(celular: str, em: date):
    """Cliente cujo cadastro já existia na data informada, ou None."""
    return Cliente.objects.filter(celular=celular, data_cadastro__lte=em).first()


def compras_validas(celular: str):
    """Compras do celular que não foram estornadas."""
    return (
        Movimentacao.objects.filter(celular=celular, tipo=T.COMPRA)
        .exclude(derivadas__tipo=T.ESTORNO)
        .distinct()
    )


# ---------------------------------------------------------------- consultas

def saldo(celular: str) -> int:
    total = Movimentacao.objects.filter(celular=celular).aggregate(s=Sum("ossinhos"))["s"]
    return total or 0


def validade(celular: str):
    """Data até a qual o saldo vale. Compra ou resgate renovam; bônus sozinho não."""
    if saldo(celular) <= 0:
        return None
    ultima_compra = compras_validas(celular).aggregate(d=Max("data"))["d"]
    ultimo_resgate = (
        Movimentacao.objects.filter(celular=celular, tipo=T.RESGATE).aggregate(d=Max("data"))["d"]
    )
    datas = [d for d in (ultima_compra, ultimo_resgate) if d]
    if not datas:
        return None
    return somar_meses(max(datas), MESES_VALIDADE)


def em_dobro(celular: str, em: date) -> bool:
    """Mês do aniversário (a partir do cadastro) ou período de dobro. Nunca passa do dobro."""
    cliente = cliente_cadastrado(celular, em)
    if cliente and cliente.aniversario.month == em.month:
        return True
    return PeriodoDobro.objects.filter(inicio__lte=em, fim__gte=em).exists()


# ---------------------------------------------------------------- validade

def expirar(celular: str, hoje: date):
    """Zera o saldo se o prazo passou. Devolve a movimentação de expiração, se houver."""
    vence = validade(celular)
    if vence is None or hoje <= vence:
        return None
    return Movimentacao.objects.create(
        tipo=T.EXPIRACAO,
        celular=celular,
        data=vence + timedelta(days=1),
        ossinhos=-saldo(celular),
        observacao=f"Saldo expirado (6 meses sem compra, venceu em {vence:%d/%m/%Y})",
    )


def expirar_saldos(hoje: date) -> int:
    """Rodar uma vez por dia. Devolve quantos saldos foram zerados."""
    celulares = Movimentacao.objects.values_list("celular", flat=True).distinct()
    zerados = 0
    for celular in celulares:
        with transaction.atomic():
            if expirar(celular, hoje):
                zerados += 1
    return zerados


# ---------------------------------------------------------------- compra

@transaction.atomic
def lancar_compra(celular, valor, data: date, canal: str, usuario=None) -> Movimentacao:
    celular = normalizar_celular(celular)
    valor = Decimal(valor)
    if valor <= 0:
        raise ValidationError("O valor da compra deve ser maior que zero.")
    if canal not in Canal.values:
        raise ValidationError("Canal inválido.")

    expirar(celular, data)

    cliente = cliente_cadastrado(celular, data)
    dobro = em_dobro(celular, data)
    mult = 2 if dobro else 1

    # Bônus que dependem do histórico, calculados antes de gravar a compra.
    ganha_boas_vindas = False
    ganha_sentimos_falta = False
    if cliente:
        ganha_boas_vindas = not (
            Movimentacao.objects.filter(celular=celular, bonus=B.BOAS_VINDAS)
            .exclude(compra_origem__derivadas__tipo=T.ESTORNO)
            .exists()
        )
        anterior = compras_validas(celular).filter(data__lte=data).aggregate(d=Max("data"))["d"]
        ganha_sentimos_falta = bool(
            anterior and (data - anterior).days >= DIAS_SENTIMOS_SUA_FALTA
        )
    indicacao = None
    if not compras_validas(celular).exists():
        indicacao = Indicacao.objects.filter(indicado=celular, compra__isnull=True).first()

    compra = Movimentacao.objects.create(
        tipo=T.COMPRA,
        celular=celular,
        data=data,
        valor=valor,
        canal=canal,
        ossinhos=ossinhos_do_valor(valor) * mult,
        dobro=dobro,
        lancado_por=usuario,
    )

    def bonus(cel, tipo_bonus, pontos, dobra):
        Movimentacao.objects.create(
            tipo=T.BONUS,
            celular=cel,
            data=data,
            bonus=tipo_bonus,
            ossinhos=pontos * (2 if dobra else 1),
            dobro=dobra,
            compra_origem=compra,
            lancado_por=usuario,
        )

    if ganha_boas_vindas:
        bonus(celular, B.BOAS_VINDAS, BOAS_VINDAS, dobro)
    if ganha_sentimos_falta:
        bonus(celular, B.SENTIMOS_SUA_FALTA, SENTIMOS_SUA_FALTA, dobro)
    if indicacao:
        bonus(celular, B.INDICADO, INDICADO, dobro)
        bonus(indicacao.indicador, B.INDICOU, INDICOU, em_dobro(indicacao.indicador, data))
        indicacao.compra = compra
        indicacao.save(update_fields=["compra"])

    return compra


@transaction.atomic
def estornar_compra(compra: Movimentacao, usuario=None, data: date | None = None):
    """Retira os ossinhos da compra e de todos os bônus que ela gerou."""
    if compra.tipo != T.COMPRA:
        raise ValidationError("Só compras podem ser estornadas.")
    if compra.derivadas.filter(tipo=T.ESTORNO).exists():
        raise ValidationError("Esta compra já foi estornada.")

    data = data or date.today()
    por_celular = {compra.celular: compra.ossinhos}
    for b in compra.derivadas.filter(tipo=T.BONUS):
        por_celular[b.celular] = por_celular.get(b.celular, 0) + b.ossinhos

    estornos = []
    for celular, pontos in por_celular.items():
        estornos.append(
            Movimentacao.objects.create(
                tipo=T.ESTORNO,
                celular=celular,
                data=data,
                ossinhos=-pontos,
                compra_origem=compra,
                observacao=f"Estorno da compra de {compra.data:%d/%m/%Y}",
                lancado_por=usuario,
            )
        )
    return estornos


# ---------------------------------------------------------------- resgate

def resgatar(celular, recompensa: Recompensa, data: date, usuario=None) -> Movimentacao:
    celular = normalizar_celular(celular)
    # A expiração é gravada mesmo que o resgate seja recusado logo depois.
    with transaction.atomic():
        expirar(celular, data)
    with transaction.atomic():
        return _resgatar(celular, recompensa, data, usuario)


def _resgatar(celular, recompensa, data, usuario):
    if not recompensa.ativa:
        raise ValidationError("Esta recompensa não está ativa.")

    if recompensa.brinde_aniversario:
        cliente = cliente_cadastrado(celular, data)
        if not cliente:
            raise ValidationError("O brinde de aniversário é só para clientes cadastrados.")
        if cliente.aniversario.month != data.month:
            raise ValidationError("O brinde de aniversário só vale no mês do aniversário.")
        if Movimentacao.objects.filter(
            celular=celular, tipo=T.RESGATE, recompensa__brinde_aniversario=True,
            data__year=data.year,
        ).exists():
            raise ValidationError("O brinde de aniversário já foi entregue este ano.")
        if not compras_validas(celular).filter(
            data__year=data.year, data__month=data.month
        ).exists():
            raise ValidationError("O brinde vai junto com uma compra no mês do aniversário.")
    else:
        disponivel = saldo(celular)
        if disponivel < recompensa.ossinhos:
            raise ValidationError(
                f"Saldo insuficiente: {disponivel} ossinhos, precisa de {recompensa.ossinhos}."
            )

    return Movimentacao.objects.create(
        tipo=T.RESGATE,
        celular=celular,
        data=data,
        ossinhos=-recompensa.ossinhos,
        recompensa=recompensa,
        lancado_por=usuario,
    )


# ---------------------------------------------------------------- indicação

@transaction.atomic
def registrar_indicacao(indicador, indicado, data: date, usuario=None) -> Indicacao:
    indicador = normalizar_celular(indicador)
    indicado = normalizar_celular(indicado)
    if indicador == indicado:
        raise ValidationError("O cliente não pode indicar a si mesmo.")
    if not Cliente.objects.filter(celular=indicador).exists():
        raise ValidationError("Quem indicou precisa estar cadastrado.")
    if compras_validas(indicado).exists():
        raise ValidationError("O indicado já fez compra; a indicação vale só para clientes novos.")
    if Indicacao.objects.filter(indicado=indicado).exists():
        raise ValidationError("Este número já foi indicado por alguém.")
    no_mes = Indicacao.objects.filter(
        indicador=indicador, data__year=data.year, data__month=data.month
    ).count()
    if no_mes >= INDICACOES_POR_MES:
        raise ValidationError(f"Limite de {INDICACOES_POR_MES} indicações por mês atingido.")
    return Indicacao.objects.create(
        indicador=indicador, indicado=indicado, data=data, registrada_por=usuario
    )
