"""Tabela de recompensas do regulamento (16/11/2026)."""

from django.db import migrations

RECOMPENSAS = [
    ("Brownie tradicional", 80, False),
    ("Blondie de Ninho", 110, False),
    ("Brookie", 110, False),
    ("Brownie de Nutella", 110, False),
    ("Brinde de aniversário", 0, True),
]


def criar(apps, schema_editor):
    Recompensa = apps.get_model("matilha", "Recompensa")
    for nome, ossinhos, brinde in RECOMPENSAS:
        Recompensa.objects.get_or_create(
            nome=nome, defaults={"ossinhos": ossinhos, "brinde_aniversario": brinde}
        )


def remover(apps, schema_editor):
    Recompensa = apps.get_model("matilha", "Recompensa")
    Recompensa.objects.filter(nome__in=[r[0] for r in RECOMPENSAS]).delete()


class Migration(migrations.Migration):
    dependencies = [("matilha", "0001_inicial")]
    operations = [migrations.RunPython(criar, remover)]
