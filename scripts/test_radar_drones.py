#!/usr/bin/env python3
"""Regression fixtures are synthetic; never published to the site."""
from datetime import datetime
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo
import atualizar_radar_drones as radar

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))
OBJECT = "Contratação de serviços de pulverização agrícola com drone para aplicação de herbicidas em pastagens."
BASE = {"numeroControlePNCP": "12345678000190-1-000001/2026", "objetoCompra": OBJECT,
        "dataEncerramentoProposta": "2026-10-20T09:00:00", "situacaoCompraId": 1,
        "unidadeOrgao": {"ufSigla": "GO", "municipioNome": "Goianésia"}}


class DroneRadarTests(unittest.TestCase):
    def test_real_service_variations(self):
        for text in (
            OBJECT,
            "Contratação de empresa especializada em pulverização agrícola por drones em pastagens",
            "Prestação de serviços de semeadura com drones para recuperação de áreas degradadas",
            "Serviços de distribuição de fertilizantes sólidos por aeronave remotamente pilotada em lavouras",
            "Credenciamento para serviços de aplicação de fungicidas com RPA agrícola",
            "Contratação de serviços com drone agrícola para adubação de pastagens",
            "Serviços de aplicação agrícola por drone em propriedades rurais",
        ):
            with self.subTest(text=text):
                self.assertTrue(radar.drone_services(text))

    def test_false_positives(self):
        for text in (
            "Aquisição de drone agrícola para pulverização e serviços em pastagens",
            "Contratação de serviços de manutenção de drone agrícola para pulverização",
            "Curso de pulverização agrícola com drones para prestação de serviços",
            "Serviços de mapeamento com drone agrícola e análise de pulverização",
            "Aquisição de sementes, adubos e defensivos para drone agrícola",
            "Notícia: drone agrícola melhora pulverização em fazendas",
            "Prestação de serviços de filmagem com drone de pulverização agrícola",
            "Serviços de pulverização por drone para combate à dengue",
            "Serviços de pulverização agrícola por avião",
            "Serviços de locação de drone agrícola sem operador para pulverização",
            "Contratação de empresa para serviços de treinamento em pulverização agrícola por drone",
            "Serviços de manutenção de equipamentos: drone agrícola para pulverização",
            "Serviços de pulverização agrícola; outras demandas não relacionadas " + "x" * 200 + " drone",
        ):
            with self.subTest(text=text):
                self.assertFalse(radar.drone_services(text))

    def test_deadlines(self):
        for deadline in (None, "", "2026-10-20", "2026-10-07T08:00:00", "malformed"):
            row = {**BASE, "dataEncerramentoProposta": deadline}
            self.assertIsNone(radar.candidate(row, "PNCP", NOW))
        self.assertTrue(radar.candidate(BASE, "PNCP", NOW)["prazo_final"].endswith("-03:00"))

    def test_bad_status_and_control(self):
        for extra in ({"situacaoCompraNome": "Revogada"}, {"situacaoCompraId": 2},
                      {"contratacaoExcluida": True}, {"numeroControlePNCP": ""}):
            self.assertIsNone(radar.candidate({**BASE, **extra}, "PNCP", NOW))

    def test_compras_deadline_precedence(self):
        row = {**BASE, "dataEncerramentoPropostaPncp": "2026-10-01T09:00:00"}
        self.assertIsNone(radar.candidate(row, "Compras.gov.br", NOW))

    def test_incomplete_docs_never_formal(self):
        for status in ("parcial", "indisponivel", "nao_analisada"):
            item = radar.candidate(BASE, "PNCP", NOW)
            result = radar.classify(item, {"status": status}, OBJECT)
            self.assertEqual(result["classificacao"], "analise_pendente")

    def test_complete_but_unrelated_document_stays_pending(self):
        item = radar.candidate(BASE, "PNCP", NOW)
        self.assertEqual(radar.classify(item, {"status": "completa"}, "Ata de compra de material escolar")["classificacao"], "analise_pendente")

    def test_confirmed_service_formal_not_eligibility(self):
        result = radar.classify(radar.candidate(BASE, "PNCP", NOW), {"status": "completa"}, OBJECT)
        self.assertEqual(result["classificacao"], "oportunidade_formal")
        self.assertIn("não comprovada", result["pontos_pendentes"][0])

    def test_required_caar_course_does_not_change_principal_object(self):
        document = OBJECT + " O piloto deverá comprovar curso CAAR. Deve realizar mapeamento prévio para planejar a aplicação."
        result = radar.classify(radar.candidate(BASE, "PNCP", NOW), {"status": "completa"}, document)
        self.assertEqual(result["classificacao"], "oportunidade_formal")

    def test_independent_service_clause_with_operator_training(self):
        document = "Prestação de serviços de pulverização agrícola por drone em lavoura. O operador deverá apresentar curso CAAR."
        result = radar.classify(radar.candidate(BASE, "PNCP", NOW), {"status": "completa"}, document)
        self.assertEqual(result["classificacao"], "oportunidade_formal")

    def test_simultaneous_drone_requirement_partner(self):
        text = OBJECT + " Deverá disponibilizar no mínimo dois drones simultaneamente."
        result = radar.classify(radar.candidate(BASE, "PNCP", NOW), {"status": "completa"}, text)
        self.assertEqual(result["classificacao"], "parceria")

    def test_dedup_current_pncp_wins(self):
        cg = radar.candidate(BASE, "Compras.gov.br", NOW)
        pn = radar.candidate(BASE, "PNCP", NOW)
        self.assertEqual(radar.deduplicate([cg, pn])[0]["fonte"], "PNCP")
        self.assertEqual(len(radar.deduplicate([cg, pn])), 1)

    def test_full_api_empty_is_complete_only_all_groups_queried(self):
        cfg = {"fontes": {"pncp": {"modalidades": [6, 8], "dias_publicacao": 30, "max_paginas": 5, "limite_segundos": 15}}, "timeout_segundos": 1, "tentativas": 1}
        with patch.object(radar.Fetcher, "get", return_value={"data": [], "totalPaginas": 0}), patch.object(radar.time, "sleep"):
            rows, diag = radar.scan_source("PNCP", cfg, NOW)
        self.assertEqual(diag["paginas_consultadas"], 2)
        self.assertEqual(diag["status"], "completa_no_recorte")

    def test_unread_annex_prevents_complete_status(self):
        item = radar.candidate(BASE, "PNCP", NOW)
        class StubFetcher:
            def get(self, url, **kwargs):
                if not kwargs.get("as_json", True):
                    return b"PK zip content"
                return [{"sequencialDocumento": 1, "titulo": "Edital.zip"}]
        documents, text = radar.collect_documents(item, {"max_anexos_por_processo": 8, "max_paginas_pdf": 100}, StubFetcher())
        self.assertEqual(documents["status"], "indisponivel")
        self.assertIn("formato", documents["falhas"][0])
        self.assertEqual(radar.classify(item, documents, text)["classificacao"], "analise_pendente")

    def test_all_pages_visited_when_within_cap(self):
        cfg = {"fontes": {"pncp": {"modalidades": [6], "dias_publicacao": 30, "max_paginas": 5, "limite_segundos": 15}}, "timeout_segundos": 1, "tentativas": 1}
        with patch.object(radar.Fetcher, "get", return_value={"data": [], "totalPaginas": 4}), patch.object(radar.time, "sleep"):
            _, diag = radar.scan_source("PNCP", cfg, NOW)
        self.assertEqual([q["pagina"] for q in diag["consultas"]], [1, 4, 3, 2])
        self.assertTrue(diag["cobertura_completa"])

    def test_unknown_pagination_never_complete(self):
        cfg = {"fontes": {"pncp": {"modalidades": [6], "dias_publicacao": 30, "max_paginas": 5, "limite_segundos": 15}}, "timeout_segundos": 1, "tentativas": 1}
        with patch.object(radar.Fetcher, "get", return_value={"data": [BASE]}), patch.object(radar.time, "sleep"):
            _, diag = radar.scan_source("PNCP", cfg, NOW)
        self.assertEqual(diag["status"], "parcial")

    def test_cap_and_failure_mark_partial(self):
        cfg = {"fontes": {"pncp": {"modalidades": [6, 8], "dias_publicacao": 30, "max_paginas": 2, "limite_segundos": 15}}, "timeout_segundos": 1, "tentativas": 1}
        with patch.object(radar.Fetcher, "get", return_value={"data": [BASE], "totalPaginas": 10}), patch.object(radar.time, "sleep"):
            _, diag = radar.scan_source("PNCP", cfg, NOW)
        self.assertEqual(diag["status"], "parcial")
        self.assertFalse(diag["cobertura_completa"])
        with patch.object(radar.Fetcher, "get", side_effect=RuntimeError("HTTP 429")), patch.object(radar.time, "sleep"):
            _, diag = radar.scan_source("PNCP", cfg, NOW)
        self.assertEqual(diag["status"], "falha")
        self.assertEqual(len(diag["falhas"]), 2)


if __name__ == "__main__":
    unittest.main()
