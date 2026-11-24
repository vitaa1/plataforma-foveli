"""Zera os saldos vencidos. Agendar para rodar uma vez por dia (cron no servidor)."""

from django.core.management.base import BaseCommand
from django.utils import timezone

from matilha.regras import expirar_saldos


class Command(BaseCommand):
    help = "Zera os saldos de quem passou 6 meses sem compra nem resgate."

    def handle(self, *args, **options):
        zerados = expirar_saldos(timezone.localdate())
        self.stdout.write(self.style.SUCCESS(f"{zerados} saldo(s) expirado(s)."))
