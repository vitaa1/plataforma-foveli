"""Tabelas da Matilha Foveli.

O saldo nunca é gravado: é sempre a soma das movimentações de um celular.
As movimentações ficam ligadas ao celular (e não ao cadastro), para que
compras de quem ainda não se cadastrou fiquem guardadas no número.
"""

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models

validar_celular = RegexValidator(
    r"^\d{10,11}$", "Informe o celular só com números, com DDD (10 ou 11 dígitos)."
)


class Canal(models.TextChoices):
    FEIRINHA = "feirinha", "Feirinha"
    DELIVERY = "delivery", "Delivery"
    VENDA_DIRETA = "venda_direta", "Venda direta"


class Cliente(models.Model):
    celular = models.CharField(max_length=11, unique=True, validators=[validar_celular])
    nome = models.CharField(max_length=120)
    aniversario = models.DateField("data de aniversário")
    data_cadastro = models.DateField()
    aceite_dados = models.BooleanField("aceitou o uso dos dados", default=False)
    # Preenchido quando o cliente confirma o código no celular e cria a senha.
    # Clientes vindos da planilha têm cadastro, mas ainda não têm conta no site.
    conta_confirmada_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["nome"]

    def __str__(self):
        return f"{self.nome} ({self.celular})"


class Recompensa(models.Model):
    nome = models.CharField(max_length=80, unique=True)
    ossinhos = models.PositiveIntegerField()
    ativa = models.BooleanField(default=True)
    # O brinde de aniversário é registrado como resgate sem custo, uma vez por ano.
    brinde_aniversario = models.BooleanField(default=False)

    class Meta:
        ordering = ["ossinhos", "nome"]

    def __str__(self):
        return f"{self.nome} ({self.ossinhos})"


class PeriodoDobro(models.Model):
    inicio = models.DateField()
    fim = models.DateField()
    motivo = models.CharField(max_length=120)

    class Meta:
        ordering = ["-inicio"]
        verbose_name = "período de dobro"
        verbose_name_plural = "períodos de dobro"

    def __str__(self):
        return f"{self.motivo} ({self.inicio:%d/%m} a {self.fim:%d/%m/%Y})"


class Indicacao(models.Model):
    """Indicação registrada no painel; o bônus sai na primeira compra do indicado."""

    indicador = models.CharField(max_length=11, validators=[validar_celular])
    indicado = models.CharField(max_length=11, unique=True, validators=[validar_celular])
    data = models.DateField()
    registrada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT
    )
    compra = models.OneToOneField(
        "Movimentacao", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="indicacao_paga",
    )

    class Meta:
        verbose_name = "indicação"
        verbose_name_plural = "indicações"

    def __str__(self):
        return f"{self.indicador} indicou {self.indicado}"


class Movimentacao(models.Model):
    class Tipo(models.TextChoices):
        COMPRA = "compra", "Compra"
        BONUS = "bonus", "Bônus"
        RESGATE = "resgate", "Resgate"
        ESTORNO = "estorno", "Estorno"
        EXPIRACAO = "expiracao", "Expiração"
        AJUSTE = "ajuste", "Ajuste"

    class Bonus(models.TextChoices):
        BOAS_VINDAS = "boas_vindas", "Boas-vindas"
        INDICADO = "indicado", "Indicado"
        INDICOU = "indicou", "Indicou"
        SENTIMOS_SUA_FALTA = "sentimos_sua_falta", "Sentimos sua falta"

    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    celular = models.CharField(max_length=11, validators=[validar_celular], db_index=True)
    data = models.DateField()
    valor = models.DecimalField(
        "valor em reais", max_digits=8, decimal_places=2, null=True, blank=True
    )
    canal = models.CharField(max_length=12, choices=Canal.choices, blank=True)
    ossinhos = models.IntegerField()
    bonus = models.CharField(max_length=20, choices=Bonus.choices, blank=True)
    dobro = models.BooleanField("rendeu em dobro", default=False)
    # Bônus e estornos apontam para a compra que os gerou.
    compra_origem = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="derivadas"
    )
    recompensa = models.ForeignKey(Recompensa, null=True, blank=True, on_delete=models.PROTECT)
    observacao = models.CharField(max_length=200, blank=True)
    lancado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT
    )
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data", "-id"]
        verbose_name = "movimentação"
        verbose_name_plural = "movimentações"

    def __str__(self):
        return f"{self.get_tipo_display()} {self.celular} {self.ossinhos:+d} ({self.data:%d/%m/%Y})"
