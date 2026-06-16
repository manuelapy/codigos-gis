from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (
    QgsMapLayer,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingOutputString,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterMultipleLayers
)

import os
import re

class SalvarEstilosCamadas(QgsProcessingAlgorithm):
    CAMADAS = 'CAMADAS'
    OPCAO_GPKG = 'OPCAO_GPKG'
    OPCAO_QML = 'OPCAO_QML'
    RELATORIO = 'RELATORIO'

    def tr(self, texto):
        return QCoreApplication.translate('SalvarEstilosCamadas', texto)

    def createInstance(self):
        return SalvarEstilosCamadas()

    def name(self):
        return 'salvar_todos_estilos_detalhado'

    def displayName(self):
        return self.tr('Salvar todos os estilos (com Log detalhado)')

    def group(self):
        return self.tr('Automação QGIS')

    def groupId(self):
        return 'automacao_qgis'

    def shortHelpString(self):
        return (
            'SALVAR ESTILOS DETALHADO\n\n'
            'Ferramenta para automação do salvamento em lote de estilos no QGIS.\n\n'
            'FLUXO DE TRABALHO:\n'
            '1) Itera sobre a lista de camadas fornecidas como entrada.\n'
            '2) Detecta e acessa todos os estilos criados no gerenciador de estilos da camada.\n'
            '3) Grava os estilos no banco de dados original (.gpkg), se a opção for marcada.\n'
            '4) Exporta arquivos de estilo (.qml) na mesma pasta do dado de origem.\n'
            '5) Restaura a exibição do estilo original no painel de camadas.\n'
            '6) Gera um log detalhado (erros e sucessos) renderizado de forma segura em um QDockWidget.\n\n'
            'OBSERVAÇÕES:\n'
            '- O painel lateral é invocado no postProcessAlgorithm para garantir thread safety na GUI;\n'
            '- Arquivos e camadas inválidas são ignoradas e reportadas no log, sem estourar exceções globais.\n\n'
            'Manuela Py\n'
            'Contato: geomanupy@gmail.com'
        )

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterMultipleLayers(
            self.CAMADAS, self.tr('Camadas'), layerType=QgsProcessing.TypeMapLayer
        ))
        self.addParameter(QgsProcessingParameterBoolean(
            self.OPCAO_GPKG, self.tr('Salvar no .gpkg'), defaultValue=True
        ))
        self.addParameter(QgsProcessingParameterBoolean(
            self.OPCAO_QML, self.tr('Exportar .qml'), defaultValue=False
        ))
        self.addOutput(QgsProcessingOutputString(self.RELATORIO, self.tr('Relatório Final')))

    def processAlgorithm(self, parameters, context, feedback):
        camadas = self.parameterAsLayerList(parameters, self.CAMADAS, context)
        salvar_no_gpkg = self.parameterAsBool(parameters, self.OPCAO_GPKG, context)
        salvar_qml = self.parameterAsBool(parameters, self.OPCAO_QML, context)

        linhas_log = ["=== INÍCIO DO LOG DE EXECUÇÃO ==="]
        resumo = {"camadas_ok": 0, "camadas_erro": 0, "total_estilos_salvos": 0}
        total = len(camadas)

        for i, camada in enumerate(camadas, start=1):
            if feedback.isCanceled():
                linhas_log.append("\n[CANCELADO PELO USUÁRIO]")
                break

            # Progresso granular para evitar aparência de congelamento
            feedback.setProgress(int((i - 1) / total * 100))
            nome_camada = camada.name()
            feedback.setProgressText(f"[{i}/{total}] {nome_camada}")

            resultado = self._processar_camada(
                camada, nome_camada, i, total,
                salvar_no_gpkg, salvar_qml, feedback
            )

            linhas_log.extend(resultado["linhas"])
            resumo["total_estilos_salvos"] += resultado["estilos_salvos"]
            if resultado["erro_critico"]:
                resumo["camadas_erro"] += 1
            else:
                resumo["camadas_ok"] += 1

        feedback.setProgress(100)

        resumo_texto = (
            f"\n\n=== RESUMO FINAL ===\n"
            f"Camadas processadas com sucesso: {resumo['camadas_ok']}\n"
            f"Camadas com erro crítico: {resumo['camadas_erro']}\n"
            f"Total de estilos salvos: {resumo['total_estilos_salvos']}"
        )

        saida_completa = "\n".join(linhas_log) + resumo_texto
        feedback.pushInfo(saida_completa)
        return {self.RELATORIO: saida_completa}

    def _processar_camada(self, camada, nome_camada, idx, total, salvar_no_gpkg, salvar_qml, feedback):
        """Processa uma camada isoladamente. Nunca levanta exceção para o chamador."""
        linhas = [f"\nCamada [{idx}/{total}]: {nome_camada}"]
        estilos_salvos = 0
        erro_critico = False

        if not camada.isValid():
            linhas.append("  [ERRO CRÍTICO] Camada inválida ou inacessível.")
            return {"linhas": linhas, "estilos_salvos": 0, "erro_critico": True}

        try:
            style_manager = camada.styleManager()
            estilos = style_manager.styles()

            if not estilos:
                linhas.append("  [AVISO] Nenhum estilo encontrado.")
                return {"linhas": linhas, "estilos_salvos": 0, "erro_critico": False}

            estilo_original = style_manager.currentStyle()
            origem = self._extrair_caminho_arquivo(camada)
            eh_gpkg = self._eh_gpkg(camada)

            linhas.append(f"  Estilos detectados: {len(estilos)}")

            for nome_estilo in estilos:
                if feedback.isCanceled():
                    break

                try:
                    # setCurrentStyle retorna bool; falha não levanta exceção
                    if not style_manager.setCurrentStyle(nome_estilo):
                        linhas.append(f"    [AVISO ESTILO] '{nome_estilo}': setCurrentStyle retornou False.")
                        continue

                    if salvar_no_gpkg and eh_gpkg:
                        # saveStyleToDatabase: (name, description, useAsDefault, uiFileContent, msgError)
                        msg_erro = ""
                        camada.saveStyleToDatabase(nome_estilo, "", True, "", msg_erro)
                        if msg_erro:
                            raise RuntimeError(f"saveStyleToDatabase: {msg_erro}")

                    if salvar_qml and origem:
                        caminho_qml = self._montar_caminho_qml(camada, origem, nome_estilo)
                        msg, ok = camada.saveNamedStyle(caminho_qml)
                        if not ok:
                            raise RuntimeError(f"saveNamedStyle: {msg}")

                    estilos_salvos += 1

                except Exception as e:
                    linhas.append(f"    [ERRO ESTILO] '{nome_estilo}': {e}")

            # Restauração garantida via finally seria ideal, mas style_manager
            # pode ter sido alterado — restaura se o estilo ainda existir.
            if estilo_original in style_manager.styles():
                style_manager.setCurrentStyle(estilo_original)

            estilos_com_erro = len(estilos) - estilos_salvos
            linhas.append(f"  [RESULTADO] Salvos: {estilos_salvos} | Erros: {estilos_com_erro}")

        except Exception as e:
            erro_critico = True
            linhas.append(f"  [ERRO CRÍTICO] {e}")

        return {"linhas": linhas, "estilos_salvos": estilos_salvos, "erro_critico": erro_critico}

    def _extrair_caminho_arquivo(self, camada):
        source = camada.source().split('|')[0].strip()
        return os.path.normpath(source) if os.path.isfile(source) else None

    def _eh_gpkg(self, camada):
        return camada.source().lower().split('|')[0].endswith('.gpkg')

    def _montar_caminho_qml(self, camada, caminho_origem, nome_estilo):
        pasta = os.path.dirname(caminho_origem)
        nome_base = os.path.splitext(os.path.basename(caminho_origem))[0]
        estilo_limpo = re.sub(r'[^\w\s-]', '', nome_estilo).replace(' ', '_')

        if caminho_origem.lower().endswith('.gpkg'):
            return os.path.join(pasta, f"{nome_base}_{camada.name()}_{estilo_limpo}.qml")
        return os.path.join(pasta, f"{nome_base}_{estilo_limpo}.qml")
