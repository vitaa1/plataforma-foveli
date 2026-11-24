"""Admin provisório, só para consulta. Lançar compra, resgate e estorno vem na etapa 2,
com telas próprias que passam por matilha.regras (por isso tudo aqui é somente leitura
nas movimentações)."""

from django.contrib import admin

from .models import Cliente, Indicacao, Movimentacao, PeriodoDobro, Recompensa
from .regras import saldo, validade


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ["nome", "celular", "aniversario", "data_cadastro", "saldo", "expira_em"]
    search_fields = ["nome", "celular"]

    @admin.display(description="saldo")
    def saldo(self, obj):
        return saldo(obj.celular)

    @admin.display(description="expira em")
    def expira_em(self, obj):
        return validade(obj.celular)


@admin.register(Movimentacao)
class MovimentacaoAdmin(admin.ModelAdmin):
    list_display = ["data", "celular", "tipo", "bonus", "valor", "canal", "ossinhos", "lancado_por"]
    list_filter = ["tipo", "canal", "bonus"]
    search_fields = ["celular"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(Recompensa)
admin.site.register(PeriodoDobro)
admin.site.register(Indicacao)
