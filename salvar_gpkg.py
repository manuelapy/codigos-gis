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
import traceback

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
        self.addParameter(QgsProcessingParameterMultipleLayers(self.CAMADAS, self.tr('Camadas'), layerType=QgsProcessing.TypeMapLayer))
        self.addParameter(QgsProcessingParameterBoolean(self.OPCAO_GPKG, self.tr('Salvar no .gpkg'), defaultValue=True))
        self.addParameter(QgsProcessingParameterBoolean(self.OPCAO_QML, self.tr('Exportar .qml'), defaultValue=False))
        self.addOutput(QgsProcessingOutputString(self.RELATORIO, self.tr('Relatório Final')))

    def processAlgorithm(self, parameters, context, feedback):
        camadas = self.parameterAsLayerList(parameters, self.CAMADAS, context)
        salvar_no_gpkg = self.parameterAsBool(parameters, self.OPCAO_GPKG, context)
        salvar_qml = self.parameterAsBool(parameters, self.OPCAO_QML, context)

        relatorio = []
        resumo_final = {"camadas_ok": 0, "camadas_erro": 0, "total_estilos_salvos": 0}
        
        relatorio.append("=== INÍCIO DO LOG DE EXECUÇÃO ===")

        for i, camada in enumerate(camadas, start=1):
            if feedback.isCanceled(): break
            
            nome_camada = camada.name()
            feedback.setProgressText(f"Processando: {nome_camada}")
            
            estilos_camada_sucesso = 0
            estilos_camada_erro = 0
            
            try:
                if not camada.isValid():
                    raise Exception("Camada inválida ou inacessível.")

                style_manager = camada.styleManager()
                # CORREÇÃO: Utilizar styles() ao invés de listStyles()
                estilos = style_manager.styles()
                estilo_original = style_manager.currentStyle()
                origem = self._extrair_caminho_arquivo(camada)

                relatorio.append(f"\nCamada [{i}/{len(camadas)}]: {nome_camada}")
                relatorio.append(f"  - Estilos detectados: {len(estilos)}")

                for nome_estilo in estilos:
                    try:
                        style_manager.setCurrentStyle(nome_estilo)
                        
                        if salvar_no_gpkg and self._eh_gpkg(camada):
                            camada.saveStyleToDatabase(nome_estilo, "", True, "")
                        
                        if salvar_qml and origem:
                            caminho_qml = self._montar_caminho_qml(camada, origem, nome_estilo)
                            camada.saveNamedStyle(caminho_qml)
                            
                        estilos_camada_sucesso += 1
                        resumo_final["total_estilos_salvos"] += 1
                        
                    except Exception as e:
                        estilos_camada_erro += 1
                        relatorio.append(f"    [ERRO ESTILO] {nome_estilo}: {str(e)}")

                # Restaura o estilo original
                style_manager.setCurrentStyle(estilo_original)
                relatorio.append(f"  [RESULTADO] Salvos: {estilos_camada_sucesso} | Erros: {estilos_camada_erro}")
                resumo_final["camadas_ok"] += 1

            except Exception as e:
                resumo_final["camadas_erro"] += 1
                relatorio.append(f"  [ERRO CRÍTICO CAMADA]: {str(e)}")

        log_final = "\n".join(relatorio)
        resumo_texto = (
            f"\n\n=== RESUMO FINAL ===\n"
            f"Camadas processadas com sucesso: {resumo_final['camadas_ok']}\n"
            f"Camadas com erro crítico: {resumo_final['camadas_erro']}\n"
            f"Total de estilos salvos (Geral): {resumo_final['total_estilos_salvos']}"
        )
        
        saida_completa = log_final + resumo_texto
        feedback.pushInfo(saida_completa)

        return {self.RELATORIO: saida_completa}

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