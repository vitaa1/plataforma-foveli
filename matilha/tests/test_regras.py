"""Um grupo de testes para cada linha da tabela "Regras de negócio" do escopo do MVP."""

from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase

from matilha import regras
from matilha.models import Cliente, Movimentacao, PeriodoDobro, Recompensa

T = Movimentacao.Tipo
B = Movimentacao.Bonus

ANA = "86999990001"      # aniversário em março
BRUNO = "86999990002"    # aniversário em agosto
CARLA = "86999990003"    # aniversário em dezembro


def cadastrar(celular, aniversario, data_cadastro, nome="Cliente"):
    return Cliente.objects.create(
        celular=celular, nome=nome, aniversario=aniversario,
        data_cadastro=data_cadastro, aceite_dados=True,
    )


def comprar(celular, valor, data, canal="feirinha"):
    return regras.lancar_compra(celular, Decimal(valor), data, canal)


def bonus_de(celular, tipo):
    return list(
        Movimentacao.objects.filter(celular=celular, tipo=T.BONUS, bonus=tipo)
        .values_list("ossinhos", flat=True)
    )


def recompensa(nome):
    return Recompensa.objects.get(nome=nome)


class BaseRegras(TestCase):
    def setUp(self):
        cadastrar(ANA, date(1995, 3, 10), date(2026, 1, 5), "Ana")
        cadastrar(BRUNO, date(1990, 8, 20), date(2026, 1, 5), "Bruno")


class PontuacaoTests(BaseRegras):
    def test_arredonda_para_baixo(self):
        compra = comprar(ANA, "18.50", date(2026, 2, 1))
        self.assertEqual(compra.ossinhos, 18)

    def test_centavos_abaixo_de_um_real_nao_contam(self):
        self.assertEqual(comprar(ANA, "0.99", date(2026, 2, 1)).ossinhos, 0)

    def test_valor_zero_ou_negativo_e_recusado(self):
        with self.assertRaises(ValidationError):
            comprar(ANA, "0", date(2026, 2, 1))

    def test_canal_invalido_e_recusado(self):
        with self.assertRaises(ValidationError):
            comprar(ANA, "10", date(2026, 2, 1), canal="ifood")

    def test_saldo_e_a_soma_das_movimentacoes(self):
        comprar(ANA, "30", date(2026, 2, 1))   # 30 + 10 boas-vindas
        comprar(ANA, "25", date(2026, 2, 10))  # 25
        self.assertEqual(regras.saldo(ANA), 65)

    def test_celular_e_normalizado(self):
        compra = comprar("(86) 99999-0001", "10", date(2026, 2, 1))
        self.assertEqual(compra.celular, ANA)
        self.assertEqual(regras.normalizar_celular("+55 86 99999-0001"), ANA)

    def test_celular_invalido_e_recusado(self):
        with self.assertRaises(ValidationError):
            regras.normalizar_celular("9999-0001")


class ClienteSemCadastroTests(BaseRegras):
    def test_compras_ficam_no_numero_sem_bonus(self):
        comprar(CARLA, "40", date(2026, 2, 1))
        self.assertEqual(regras.saldo(CARLA), 40)
        self.assertFalse(Movimentacao.objects.filter(celular=CARLA, tipo=T.BONUS).exists())

    def test_ao_cadastrar_o_saldo_ja_esta_la_e_a_proxima_compra_ganha_boas_vindas(self):
        comprar(CARLA, "40", date(2026, 2, 1))
        cadastrar(CARLA, date(1999, 12, 1), date(2026, 2, 15))
        comprar(CARLA, "20", date(2026, 2, 20))
        self.assertEqual(bonus_de(CARLA, B.BOAS_VINDAS), [10])
        self.assertEqual(regras.saldo(CARLA), 70)


class RecompensasTests(BaseRegras):
    def test_tabela_do_regulamento(self):
        self.assertEqual(recompensa("Brownie tradicional").ossinhos, 80)
        for nome in ["Blondie de Ninho", "Brookie", "Brownie de Nutella"]:
            self.assertEqual(recompensa(nome).ossinhos, 110)

    def test_resgate_desconta_na_hora(self):
        comprar(ANA, "100", date(2026, 2, 1))  # 110 com boas-vindas
        regras.resgatar(ANA, recompensa("Brownie tradicional"), date(2026, 2, 2))
        self.assertEqual(regras.saldo(ANA), 30)

    def test_saldo_insuficiente_bloqueia(self):
        comprar(ANA, "60", date(2026, 2, 1))  # 70
        with self.assertRaises(ValidationError):
            regras.resgatar(ANA, recompensa("Brownie tradicional"), date(2026, 2, 2))
        self.assertEqual(regras.saldo(ANA), 70)

    def test_resgate_nao_gera_ossinhos(self):
        comprar(ANA, "100", date(2026, 2, 1))
        resgate = regras.resgatar(ANA, recompensa("Brookie"), date(2026, 2, 2))
        self.assertEqual(resgate.ossinhos, -110)
        self.assertEqual(Movimentacao.objects.filter(celular=ANA, ossinhos__gt=0).count(), 2)

    def test_recompensa_inativa_nao_pode_ser_resgatada(self):
        comprar(ANA, "200", date(2026, 2, 1))
        brookie = recompensa("Brookie")
        brookie.ativa = False
        brookie.save()
        with self.assertRaises(ValidationError):
            regras.resgatar(ANA, brookie, date(2026, 2, 2))


class BoasVindasTests(BaseRegras):
    def test_mais_10_na_primeira_compra_depois_do_cadastro(self):
        comprar(ANA, "20", date(2026, 2, 1))
        self.assertEqual(bonus_de(ANA, B.BOAS_VINDAS), [10])

    def test_so_uma_vez_por_conta(self):
        comprar(ANA, "20", date(2026, 2, 1))
        comprar(ANA, "20", date(2026, 2, 2))
        self.assertEqual(bonus_de(ANA, B.BOAS_VINDAS), [10])

    def test_compra_anterior_ao_cadastro_nao_ganha(self):
        comprar(ANA, "20", date(2026, 1, 2))  # cadastro só em 05/01
        self.assertEqual(bonus_de(ANA, B.BOAS_VINDAS), [])

    def test_volta_a_valer_se_a_compra_que_ganhou_for_estornada(self):
        primeira = comprar(ANA, "20", date(2026, 2, 1))
        regras.estornar_compra(primeira, data=date(2026, 2, 2))
        comprar(ANA, "20", date(2026, 2, 3))
        self.assertEqual(sum(bonus_de(ANA, B.BOAS_VINDAS)), 20)  # 10 estornado + 10 novo
        self.assertEqual(regras.saldo(ANA), 30)


class AniversarioTests(BaseRegras):
    def test_compra_no_mes_do_aniversario_rende_o_dobro(self):
        comprar(ANA, "20", date(2026, 2, 1))
        compra = comprar(ANA, "20", date(2026, 3, 15))
        self.assertEqual(compra.ossinhos, 40)
        self.assertTrue(compra.dobro)

    def test_so_a_partir_do_cadastro(self):
        cadastrar(CARLA, date(1999, 12, 1), date(2026, 12, 20))
        antes = comprar(CARLA, "20", date(2026, 12, 10))
        depois = comprar(CARLA, "20", date(2026, 12, 21))
        self.assertEqual(antes.ossinhos, 20)
        self.assertEqual(depois.ossinhos, 40)

    def test_cadastro_no_mes_do_aniversario_dobra_boas_vindas(self):
        cadastrar(CARLA, date(1999, 12, 1), date(2026, 12, 3))
        comprar(CARLA, "20", date(2026, 12, 5))
        self.assertEqual(bonus_de(CARLA, B.BOAS_VINDAS), [20])
        self.assertEqual(regras.saldo(CARLA), 60)

    def test_brinde_e_resgate_sem_custo_uma_vez_por_ano(self):
        comprar(ANA, "20", date(2026, 3, 5))
        brinde = recompensa("Brinde de aniversário")
        regras.resgatar(ANA, brinde, date(2026, 3, 5))
        self.assertEqual(regras.saldo(ANA), 60)  # (20 + 10) x 2, sem desconto
        with self.assertRaises(ValidationError):
            regras.resgatar(ANA, brinde, date(2026, 3, 20))

    def test_brinde_volta_no_ano_seguinte(self):
        brinde = recompensa("Brinde de aniversário")
        comprar(ANA, "20", date(2026, 3, 5))
        regras.resgatar(ANA, brinde, date(2026, 3, 5))
        comprar(ANA, "20", date(2027, 3, 5))
        regras.resgatar(ANA, brinde, date(2027, 3, 5))  # não levanta erro

    def test_brinde_fora_do_mes_e_recusado(self):
        comprar(ANA, "20", date(2026, 4, 5))
        with self.assertRaises(ValidationError):
            regras.resgatar(ANA, recompensa("Brinde de aniversário"), date(2026, 4, 5))

    def test_brinde_exige_compra_no_mes(self):
        comprar(ANA, "20", date(2026, 2, 5))
        with self.assertRaises(ValidationError):
            regras.resgatar(ANA, recompensa("Brinde de aniversário"), date(2026, 3, 5))


class PeriodoDobroTests(BaseRegras):
    def setUp(self):
        super().setUp()
        comprar(BRUNO, "10", date(2026, 2, 1))  # gasta o boas-vindas
        PeriodoDobro.objects.create(
            inicio=date(2026, 5, 10), fim=date(2026, 5, 20), motivo="Lançamento do brookie"
        )

    def test_compra_no_periodo_rende_o_dobro(self):
        self.assertEqual(comprar(BRUNO, "30", date(2026, 5, 10)).ossinhos, 60)
        self.assertEqual(comprar(BRUNO, "30", date(2026, 5, 20)).ossinhos, 60)

    def test_fora_do_periodo_nao_dobra(self):
        self.assertEqual(comprar(BRUNO, "30", date(2026, 5, 21)).ossinhos, 30)

    def test_nao_e_retroativo(self):
        antes = comprar(BRUNO, "30", date(2026, 5, 8))
        PeriodoDobro.objects.create(
            inicio=date(2026, 5, 1), fim=date(2026, 5, 9), motivo="Criado depois"
        )
        antes.refresh_from_db()
        self.assertEqual(antes.ossinhos, 30)

    def test_dobra_os_bonus_da_compra(self):
        compra = comprar(BRUNO, "30", date(2026, 5, 12))  # 100 dias depois: sentimos sua falta
        self.assertEqual(compra.ossinhos, 60)
        self.assertEqual(bonus_de(BRUNO, B.SENTIMOS_SUA_FALTA), [30])


class LimiteDoDobroTests(BaseRegras):
    def test_aniversario_e_periodo_nao_somam(self):
        comprar(ANA, "10", date(2026, 2, 1))
        PeriodoDobro.objects.create(inicio=date(2026, 3, 1), fim=date(2026, 3, 31), motivo="Março")
        self.assertEqual(comprar(ANA, "30", date(2026, 3, 10)).ossinhos, 60)

    def test_boas_vindas_no_mes_do_aniversario_rende_20(self):
        comprar(ANA, "10", date(2026, 3, 1))
        self.assertEqual(bonus_de(ANA, B.BOAS_VINDAS), [20])


class IndicacaoTests(BaseRegras):
    def test_primeira_compra_do_indicado_paga_os_dois(self):
        comprar(ANA, "10", date(2026, 2, 1))
        regras.registrar_indicacao(ANA, CARLA, date(2026, 2, 5))
        comprar(CARLA, "30", date(2026, 2, 6))
        self.assertEqual(bonus_de(ANA, B.INDICOU), [20])
        self.assertEqual(bonus_de(CARLA, B.INDICADO), [10])
        self.assertEqual(regras.saldo(CARLA), 40)

    def test_so_paga_uma_vez(self):
        regras.registrar_indicacao(ANA, CARLA, date(2026, 2, 5))
        comprar(CARLA, "30", date(2026, 2, 6))
        comprar(CARLA, "30", date(2026, 2, 7))
        self.assertEqual(bonus_de(ANA, B.INDICOU), [20])

    def test_bloqueia_a_sexta_indicacao_do_mes(self):
        for i in range(5):
            regras.registrar_indicacao(ANA, f"8698888000{i}", date(2026, 2, 5))
        with self.assertRaises(ValidationError):
            regras.registrar_indicacao(ANA, "86988880009", date(2026, 2, 28))
        regras.registrar_indicacao(ANA, "86988880009", date(2026, 3, 1))  # mês seguinte libera

    def test_quem_indicou_no_mes_do_aniversario_ganha_40(self):
        regras.registrar_indicacao(ANA, CARLA, date(2026, 3, 2))
        comprar(CARLA, "30", date(2026, 3, 3))
        self.assertEqual(bonus_de(ANA, B.INDICOU), [40])
        self.assertEqual(bonus_de(CARLA, B.INDICADO), [10])  # Carla não está em dobro

    def test_indicado_em_dobro_ganha_20(self):
        PeriodoDobro.objects.create(inicio=date(2026, 6, 1), fim=date(2026, 6, 7), motivo="Semana")
        regras.registrar_indicacao(ANA, CARLA, date(2026, 6, 1))
        comprar(CARLA, "30", date(2026, 6, 2))
        self.assertEqual(bonus_de(CARLA, B.INDICADO), [20])
        self.assertEqual(bonus_de(ANA, B.INDICOU), [40])

    def test_nao_pode_indicar_a_si_mesmo(self):
        with self.assertRaises(ValidationError):
            regras.registrar_indicacao(ANA, ANA, date(2026, 2, 5))

    def test_indicado_que_ja_comprou_e_recusado(self):
        comprar(CARLA, "10", date(2026, 2, 1))
        with self.assertRaises(ValidationError):
            regras.registrar_indicacao(ANA, CARLA, date(2026, 2, 5))

    def test_numero_ja_indicado_e_recusado(self):
        regras.registrar_indicacao(ANA, CARLA, date(2026, 2, 5))
        with self.assertRaises(ValidationError):
            regras.registrar_indicacao(BRUNO, CARLA, date(2026, 2, 6))

    def test_quem_indica_precisa_de_cadastro(self):
        with self.assertRaises(ValidationError):
            regras.registrar_indicacao(CARLA, "86988880001", date(2026, 2, 5))


class SentimosSuaFaltaTests(BaseRegras):
    def test_45_dias_ou_mais_ganha_15(self):
        comprar(BRUNO, "10", date(2026, 2, 1))
        comprar(BRUNO, "10", date(2026, 3, 18))  # 45 dias
        self.assertEqual(bonus_de(BRUNO, B.SENTIMOS_SUA_FALTA), [15])

    def test_44_dias_nao_ganha(self):
        comprar(BRUNO, "10", date(2026, 2, 1))
        comprar(BRUNO, "10", date(2026, 3, 17))  # 44 dias
        self.assertEqual(bonus_de(BRUNO, B.SENTIMOS_SUA_FALTA), [])

    def test_primeira_compra_nao_conta(self):
        comprar(BRUNO, "10", date(2026, 6, 1))
        self.assertEqual(bonus_de(BRUNO, B.SENTIMOS_SUA_FALTA), [])

    def test_compra_estornada_nao_conta_como_anterior(self):
        comprar(BRUNO, "10", date(2026, 2, 1))
        cancelada = comprar(BRUNO, "10", date(2026, 3, 1))
        regras.estornar_compra(cancelada, data=date(2026, 3, 2))
        comprar(BRUNO, "10", date(2026, 3, 20))  # 47 dias da última válida
        self.assertEqual(bonus_de(BRUNO, B.SENTIMOS_SUA_FALTA), [15])


class ValidadeTests(BaseRegras):
    def test_expira_6_meses_depois_da_ultima_compra(self):
        comprar(BRUNO, "50", date(2026, 2, 1))
        self.assertEqual(regras.validade(BRUNO), date(2026, 8, 1))

    def test_nova_compra_renova_o_saldo_todo(self):
        comprar(BRUNO, "50", date(2026, 2, 1))
        comprar(BRUNO, "10", date(2026, 7, 30))
        self.assertEqual(regras.validade(BRUNO), date(2027, 1, 30))
        self.assertEqual(regras.saldo(BRUNO), 85)  # 50 + 10 boas-vindas + 10 + 15 sentimos

    def test_resgate_renova(self):
        comprar(BRUNO, "100", date(2026, 2, 1))
        regras.resgatar(BRUNO, recompensa("Brownie tradicional"), date(2026, 5, 1))
        self.assertEqual(regras.validade(BRUNO), date(2026, 11, 1))

    def test_bonus_sozinho_nao_renova(self):
        comprar(ANA, "10", date(2026, 2, 1))
        regras.registrar_indicacao(ANA, CARLA, date(2026, 4, 1))
        comprar(CARLA, "30", date(2026, 4, 2))  # Ana ganha +20, sem comprar
        self.assertEqual(regras.validade(ANA), date(2026, 8, 1))

    def test_expiracao_zera_o_saldo(self):
        comprar(BRUNO, "50", date(2026, 2, 1))
        zerados = regras.expirar_saldos(date(2026, 8, 2))
        self.assertEqual(zerados, 1)
        self.assertEqual(regras.saldo(BRUNO), 0)
        exp = Movimentacao.objects.get(celular=BRUNO, tipo=T.EXPIRACAO)
        self.assertEqual((exp.ossinhos, exp.data), (-60, date(2026, 8, 2)))

    def test_no_ultimo_dia_ainda_vale(self):
        comprar(BRUNO, "50", date(2026, 2, 1))
        self.assertEqual(regras.expirar_saldos(date(2026, 8, 1)), 0)

    def test_compra_depois_do_vencimento_comeca_do_zero(self):
        comprar(BRUNO, "50", date(2026, 2, 1))  # 60
        comprar(BRUNO, "10", date(2026, 9, 1))  # expira os 60 antes; ganha 10 + 15
        self.assertEqual(regras.saldo(BRUNO), 25)

    def test_resgate_nao_usa_saldo_vencido(self):
        comprar(BRUNO, "100", date(2026, 2, 1))
        with self.assertRaises(ValidationError):
            regras.resgatar(BRUNO, recompensa("Brownie tradicional"), date(2026, 9, 1))
        self.assertEqual(regras.saldo(BRUNO), 0)

    def test_fim_de_mes(self):
        comprar(BRUNO, "10", date(2026, 8, 31))
        self.assertEqual(regras.validade(BRUNO), date(2027, 2, 28))

    def test_comando_diario(self):
        comprar(BRUNO, "50", date(2020, 1, 1))
        call_command("expirar_saldos", stdout=open("/dev/null", "w"))
        self.assertEqual(regras.saldo(BRUNO), 0)


class CancelamentoTests(BaseRegras):
    def test_estorno_leva_a_compra_e_os_bonus(self):
        compra = comprar(ANA, "30", date(2026, 3, 5))  # (30 + 10) x 2
        self.assertEqual(regras.saldo(ANA), 80)
        regras.estornar_compra(compra, data=date(2026, 3, 6))
        self.assertEqual(regras.saldo(ANA), 0)

    def test_estorno_tira_o_bonus_de_quem_indicou(self):
        regras.registrar_indicacao(ANA, CARLA, date(2026, 2, 5))
        compra = comprar(CARLA, "30", date(2026, 2, 6))
        regras.estornar_compra(compra, data=date(2026, 2, 7))
        self.assertEqual(regras.saldo(CARLA), 0)
        self.assertEqual(regras.saldo(ANA), 0)

    def test_nao_estorna_duas_vezes(self):
        compra = comprar(ANA, "30", date(2026, 2, 5))
        regras.estornar_compra(compra, data=date(2026, 2, 6))
        with self.assertRaises(ValidationError):
            regras.estornar_compra(compra, data=date(2026, 2, 7))

    def test_compra_estornada_nao_renova_validade(self):
        comprar(BRUNO, "50", date(2026, 2, 1))
        cancelada = comprar(BRUNO, "10", date(2026, 5, 1))
        regras.estornar_compra(cancelada, data=date(2026, 5, 2))
        self.assertEqual(regras.validade(BRUNO), date(2026, 8, 1))

    def test_so_compras_podem_ser_estornadas(self):
        comprar(ANA, "100", date(2026, 2, 1))
        resgate = regras.resgatar(ANA, recompensa("Brownie tradicional"), date(2026, 2, 2))
        with self.assertRaises(ValidationError):
            regras.estornar_compra(resgate)
