from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (
    QgsMapLayer,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingOutputString,
    QgsProcessingParameterBoolean,
    QgsProcessingParameterMultipleLayers,
    QgsProviderRegistry
)

import os
import re
import sqlite3
import tempfile
from datetime import datetime


class SalvarEstilosCamadas(QgsProcessingAlgorithm):
    CAMADAS = 'CAMADAS'
    OPCAO_GPKG = 'OPCAO_GPKG'
    OPCAO_QML = 'OPCAO_QML'
    OPCAO_GPKG_DIRETO = 'OPCAO_GPKG_DIRETO'
    RELATORIO = 'RELATORIO'

    def tr(self, texto):
        return QCoreApplication.translate('SalvarEstilosCamadas', texto)

    def createInstance(self):
        return SalvarEstilosCamadas()

    def name(self):
        return 'salvar_todos_estilos_corrigido'

    def displayName(self):
        return self.tr('Salvar todos os estilos - corrigido')

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
            self.CAMADAS,
            self.tr('Camadas'),
            layerType=QgsProcessing.TypeMapLayer
        ))

        self.addParameter(QgsProcessingParameterBoolean(
            self.OPCAO_GPKG,
            self.tr('Salvar no GeoPackage / banco de dados da fonte'),
            defaultValue=True
        ))

        self.addParameter(QgsProcessingParameterBoolean(
            self.OPCAO_GPKG_DIRETO,
            self.tr('Se falhar, forçar gravação direta no .gpkg'),
            defaultValue=True
        ))

        self.addParameter(QgsProcessingParameterBoolean(
            self.OPCAO_QML,
            self.tr('Exportar também como .qml'),
            defaultValue=False
        ))

        self.addOutput(QgsProcessingOutputString(
            self.RELATORIO,
            self.tr('Relatório Final')
        ))

    def processAlgorithm(self, parameters, context, feedback):
        camadas = self.parameterAsLayerList(parameters, self.CAMADAS, context)
        salvar_no_gpkg = self.parameterAsBool(parameters, self.OPCAO_GPKG, context)
        salvar_qml = self.parameterAsBool(parameters, self.OPCAO_QML, context)
        forcar_gpkg_direto = self.parameterAsBool(parameters, self.OPCAO_GPKG_DIRETO, context)

        linhas_log = ['=== INÍCIO DO LOG DE EXECUÇÃO ===']

        resumo = {
            'camadas_ok': 0,
            'camadas_erro': 0,
            'total_estilos_salvos': 0
        }

        total = len(camadas)

        if total == 0:
            linhas_log.append('[AVISO] Nenhuma camada foi informada.')
            saida = '\n'.join(linhas_log)
            return {self.RELATORIO: saida}

        for i, camada in enumerate(camadas, start=1):
            if feedback.isCanceled():
                linhas_log.append('\n[CANCELADO PELO USUÁRIO]')
                break

            progresso = int((i - 1) / total * 100)
            feedback.setProgress(progresso)
            feedback.setProgressText(f'[{i}/{total}] {camada.name()}')

            resultado = self._processar_camada(
                camada=camada,
                idx=i,
                total=total,
                salvar_no_gpkg=salvar_no_gpkg,
                salvar_qml=salvar_qml,
                forcar_gpkg_direto=forcar_gpkg_direto,
                feedback=feedback
            )

            linhas_log.extend(resultado['linhas'])
            resumo['total_estilos_salvos'] += resultado['estilos_salvos']

            if resultado['erro_critico']:
                resumo['camadas_erro'] += 1
            else:
                resumo['camadas_ok'] += 1

        feedback.setProgress(100)

        resumo_texto = (
            '\n\n=== RESUMO FINAL ===\n'
            f'Camadas processadas com sucesso: {resumo["camadas_ok"]}\n'
            f'Camadas com erro crítico: {resumo["camadas_erro"]}\n'
            f'Total de estilos salvos: {resumo["total_estilos_salvos"]}'
        )

        saida_completa = '\n'.join(linhas_log) + resumo_texto
        feedback.pushInfo(saida_completa)

        return {self.RELATORIO: saida_completa}

    def _processar_camada(
        self,
        camada,
        idx,
        total,
        salvar_no_gpkg,
        salvar_qml,
        forcar_gpkg_direto,
        feedback
    ):
        linhas = [f'\nCamada [{idx}/{total}]: {camada.name()}']
        estilos_salvos = 0
        erro_critico = False

        if not camada or not camada.isValid():
            linhas.append('  [ERRO CRÍTICO] Camada inválida ou inacessível.')
            return {
                'linhas': linhas,
                'estilos_salvos': 0,
                'erro_critico': True
            }

        if camada.type() != QgsMapLayer.VectorLayer:
            linhas.append('  [AVISO] A camada não é vetorial. Ignorada.')
            return {
                'linhas': linhas,
                'estilos_salvos': 0,
                'erro_critico': False
            }

        try:
            gerenciador_estilos = camada.styleManager()
            estilos = list(gerenciador_estilos.styles())

            if not estilos:
                linhas.append('  [AVISO] Nenhum estilo encontrado.')
                return {
                    'linhas': linhas,
                    'estilos_salvos': 0,
                    'erro_critico': False
                }

            estilo_original = gerenciador_estilos.currentStyle()
            caminho_origem = self._extrair_caminho_arquivo(camada)
            eh_gpkg = self._eh_gpkg(camada)

            linhas.append(f'  Estilos detectados: {len(estilos)}')
            linhas.append(f'  Estilo original/padrão no projeto: {estilo_original}')

            if salvar_no_gpkg and not eh_gpkg:
                linhas.append('  [AVISO] A fonte da camada não é .gpkg. Salvamento no GeoPackage ignorado.')

            if salvar_no_gpkg and eh_gpkg and not caminho_origem:
                linhas.append('  [AVISO] Caminho físico do .gpkg não encontrado.')

            for ordem, nome_estilo in enumerate(estilos, start=1):
                if feedback.isCanceled():
                    break

                try:
                    feedback.setProgressText(f'[{idx}/{total}] {camada.name()} | estilo: {nome_estilo}')

                    if not gerenciador_estilos.setCurrentStyle(nome_estilo):
                        linhas.append(f'    [AVISO ESTILO] {nome_estilo}: não foi possível ativar o estilo.')
                        continue

                    usar_como_padrao = nome_estilo == estilo_original
                    salvou_alguma_saida = False

                    if salvar_no_gpkg and eh_gpkg:
                        ok_nativo, msg_nativo = self._salvar_estilo_banco_nativo(
                            camada=camada,
                            nome_estilo=nome_estilo,
                            usar_como_padrao=usar_como_padrao
                        )

                        if ok_nativo:
                            linhas.append(f'    [OK GPKG] {nome_estilo}: salvo pelo método nativo.')
                            salvou_alguma_saida = True
                        else:
                            linhas.append(f'    [AVISO GPKG] {nome_estilo}: método nativo falhou: {msg_nativo}')

                            if forcar_gpkg_direto and caminho_origem:
                                ok_direto, msg_direto = self._salvar_estilo_gpkg_direto(
                                    camada=camada,
                                    caminho_gpkg=caminho_origem,
                                    nome_estilo=nome_estilo,
                                    usar_como_padrao=usar_como_padrao
                                )

                                if ok_direto:
                                    linhas.append(f'    [OK GPKG DIRETO] {nome_estilo}: gravado na tabela layer_styles.')
                                    salvou_alguma_saida = True
                                else:
                                    raise RuntimeError(f'falha no método direto: {msg_direto}')
                            else:
                                raise RuntimeError(msg_nativo)

                    if salvar_qml and caminho_origem:
                        caminho_qml = self._montar_caminho_qml(
                            camada=camada,
                            caminho_origem=caminho_origem,
                            nome_estilo=nome_estilo
                        )

                        ok_qml, msg_qml = self._salvar_qml(
                            camada=camada,
                            caminho_qml=caminho_qml
                        )

                        if ok_qml:
                            linhas.append(f'    [OK QML] {nome_estilo}: {caminho_qml}')
                            salvou_alguma_saida = True
                        else:
                            raise RuntimeError(f'falha ao exportar .qml: {msg_qml}')

                    if not salvar_no_gpkg and not salvar_qml:
                        linhas.append(f'    [AVISO ESTILO] {nome_estilo}: nenhuma opção de saída marcada.')
                    elif salvou_alguma_saida:
                        estilos_salvos += 1

                except Exception as e:
                    linhas.append(f'    [ERRO ESTILO] {nome_estilo}: {e}')

            if estilo_original in gerenciador_estilos.styles():
                gerenciador_estilos.setCurrentStyle(estilo_original)

            estilos_com_erro = len(estilos) - estilos_salvos
            linhas.append(f'  [RESULTADO] Salvos: {estilos_salvos} | Erros: {estilos_com_erro}')

        except Exception as e:
            erro_critico = True
            linhas.append(f'  [ERRO CRÍTICO] {e}')

        return {
            'linhas': linhas,
            'estilos_salvos': estilos_salvos,
            'erro_critico': erro_critico
        }

    def _salvar_estilo_banco_nativo(self, camada, nome_estilo, usar_como_padrao):
        try:
            descricao = f'Estilo {nome_estilo} salvo automaticamente pelo QGIS'

            retorno = camada.saveStyleToDatabase(
                nome_estilo,
                descricao,
                usar_como_padrao,
                ''
            )

            if retorno is None:
                return True, 'método executado sem retorno explícito'

            if isinstance(retorno, bool):
                if retorno:
                    return True, 'salvo'
                return False, 'saveStyleToDatabase retornou False'

            if isinstance(retorno, tuple):
                textos = []
                booleanos = []

                for item in retorno:
                    if isinstance(item, bool):
                        booleanos.append(item)
                    elif item is not None:
                        textos.append(str(item))

                if booleanos:
                    ok = any(booleanos)
                    mensagem = ' | '.join(textos) if textos else 'sem mensagem'
                    return ok, mensagem

                mensagem = ' | '.join(textos) if textos else 'retorno em tupla sem bool'
                return True, mensagem

            return bool(retorno), str(retorno)

        except Exception as e:
            return False, str(e)

    def _salvar_estilo_gpkg_direto(self, camada, caminho_gpkg, nome_estilo, usar_como_padrao):
        if not caminho_gpkg or not os.path.isfile(caminho_gpkg):
            return False, 'arquivo .gpkg não encontrado'

        try:
            qml = self._exportar_estilo_qml_para_texto(camada)

            if not qml.strip():
                return False, 'QML exportado vazio'

            nome_tabela, coluna_geometria = self._obter_dados_camada_gpkg(camada, caminho_gpkg)

            if not nome_tabela:
                return False, 'não foi possível identificar o nome da tabela no GeoPackage'

            if not coluna_geometria:
                coluna_geometria = ''

            descricao = f'Estilo {nome_estilo} salvo automaticamente pelo QGIS'
            agora = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')

            conexao = sqlite3.connect(caminho_gpkg, timeout=30)

            try:
                cursor = conexao.cursor()

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS layer_styles (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        f_table_catalog TEXT,
                        f_table_schema TEXT,
                        f_table_name TEXT,
                        f_geometry_column TEXT,
                        styleName TEXT,
                        styleQML TEXT,
                        styleSLD TEXT,
                        useAsDefault INTEGER,
                        description TEXT,
                        owner TEXT,
                        ui TEXT,
                        update_time TEXT
                    )
                """)

                if usar_como_padrao:
                    cursor.execute("""
                        UPDATE layer_styles
                        SET useAsDefault = 0
                        WHERE f_table_name = ?
                          AND COALESCE(f_geometry_column, '') = COALESCE(?, '')
                    """, (nome_tabela, coluna_geometria))

                cursor.execute("""
                    SELECT id
                    FROM layer_styles
                    WHERE f_table_name = ?
                      AND COALESCE(f_geometry_column, '') = COALESCE(?, '')
                      AND styleName = ?
                    ORDER BY id
                    LIMIT 1
                """, (nome_tabela, coluna_geometria, nome_estilo))

                existente = cursor.fetchone()

                if existente:
                    id_estilo = existente[0]

                    cursor.execute("""
                        UPDATE layer_styles
                        SET
                            styleQML = ?,
                            styleSLD = ?,
                            useAsDefault = ?,
                            description = ?,
                            owner = ?,
                            ui = ?,
                            update_time = ?
                        WHERE id = ?
                    """, (
                        qml,
                        '',
                        1 if usar_como_padrao else 0,
                        descricao,
                        '',
                        '',
                        agora,
                        id_estilo
                    ))
                else:
                    cursor.execute("""
                        INSERT INTO layer_styles (
                            f_table_catalog,
                            f_table_schema,
                            f_table_name,
                            f_geometry_column,
                            styleName,
                            styleQML,
                            styleSLD,
                            useAsDefault,
                            description,
                            owner,
                            ui,
                            update_time
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        '',
                        '',
                        nome_tabela,
                        coluna_geometria,
                        nome_estilo,
                        qml,
                        '',
                        1 if usar_como_padrao else 0,
                        descricao,
                        '',
                        '',
                        agora
                    ))

                conexao.commit()

            finally:
                conexao.close()

            return True, 'gravado diretamente no GeoPackage'

        except Exception as e:
            return False, str(e)

    def _exportar_estilo_qml_para_texto(self, camada):
        caminho_temp = None

        try:
            arquivo_temp = tempfile.NamedTemporaryFile(
                suffix='.qml',
                delete=False
            )

            caminho_temp = arquivo_temp.name
            arquivo_temp.close()

            ok, msg = self._salvar_qml(camada, caminho_temp)

            if not ok:
                raise RuntimeError(msg)

            with open(caminho_temp, 'r', encoding='utf-8') as arquivo:
                return arquivo.read()

        finally:
            if caminho_temp and os.path.exists(caminho_temp):
                try:
                    os.remove(caminho_temp)
                except Exception:
                    pass

    def _salvar_qml(self, camada, caminho_qml):
        try:
            retorno = camada.saveNamedStyle(caminho_qml)

            if isinstance(retorno, tuple):
                mensagens = []
                booleanos = []

                for item in retorno:
                    if isinstance(item, bool):
                        booleanos.append(item)
                    elif item is not None:
                        mensagens.append(str(item))

                if booleanos:
                    ok = any(booleanos)
                    msg = ' | '.join(mensagens) if mensagens else ''
                    return ok, msg

                return True, ' | '.join(mensagens)

            if isinstance(retorno, bool):
                return retorno, '' if retorno else 'saveNamedStyle retornou False'

            return True, str(retorno)

        except Exception as e:
            return False, str(e)

    def _obter_dados_camada_gpkg(self, camada, caminho_gpkg):
        nome_tabela = None
        coluna_geometria = None
        source = camada.source()

        try:
            info_uri = QgsProviderRegistry.instance().decodeUri(
                camada.providerType(),
                source
            )

            nome_tabela = (
                info_uri.get('layerName')
                or info_uri.get('table')
                or info_uri.get('name')
            )

            coluna_geometria = (
                info_uri.get('geometryColumn')
                or info_uri.get('geometrycolumn')
            )

        except Exception:
            pass

        if not nome_tabela:
            padrao = re.search(r'\|layername=([^|]+)', source, flags=re.IGNORECASE)
            if padrao:
                nome_tabela = padrao.group(1)

        if not coluna_geometria:
            try:
                coluna_geometria = camada.dataProvider().geometryColumnName()
            except Exception:
                coluna_geometria = None

        try:
            conexao = sqlite3.connect(caminho_gpkg)
            cursor = conexao.cursor()

            if nome_tabela and not coluna_geometria:
                cursor.execute("""
                    SELECT column_name
                    FROM gpkg_geometry_columns
                    WHERE table_name = ?
                    LIMIT 1
                """, (nome_tabela,))

                linha = cursor.fetchone()
                if linha:
                    coluna_geometria = linha[0]

            if not nome_tabela:
                nome_camada = camada.name()

                cursor.execute("""
                    SELECT table_name, column_name
                    FROM gpkg_geometry_columns
                    WHERE table_name = ?
                    LIMIT 1
                """, (nome_camada,))

                linha = cursor.fetchone()

                if linha:
                    nome_tabela = linha[0]
                    coluna_geometria = linha[1]

            conexao.close()

        except Exception:
            pass

        if not nome_tabela:
            nome_tabela = camada.name()

        return nome_tabela, coluna_geometria

    def _extrair_caminho_arquivo(self, camada):
        source = camada.source().split('|')[0].strip()
        source = os.path.normpath(source)

        if os.path.isfile(source):
            return source

        return None

    def _eh_gpkg(self, camada):
        source = camada.source().lower().split('|')[0].strip()
        return source.endswith('.gpkg')

    def _montar_caminho_qml(self, camada, caminho_origem, nome_estilo):
        pasta = os.path.dirname(caminho_origem)
        nome_base = os.path.splitext(os.path.basename(caminho_origem))[0]
        nome_camada = self._limpar_nome_arquivo(camada.name())
        estilo_limpo = self._limpar_nome_arquivo(nome_estilo)

        if caminho_origem.lower().endswith('.gpkg'):
            nome_arquivo = f'{nome_base}_{nome_camada}_{estilo_limpo}.qml'
        else:
            nome_arquivo = f'{nome_base}_{estilo_limpo}.qml'

        return os.path.join(pasta, nome_arquivo)

    def _limpar_nome_arquivo(self, texto):
        texto = str(texto).strip()
        texto = re.sub(r'[^\w\s-]', '', texto, flags=re.UNICODE)
        texto = re.sub(r'\s+', '_', texto)
        return texto
