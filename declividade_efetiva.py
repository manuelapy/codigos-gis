# -*- coding: utf-8 -*-
"""
Declividade Equivalente do Talvegue - Taylor-Schwarz

Script Processing para QGIS.

Entradas:
- Camada vetorial de linhas do talvegue;
- Campo identificador opcional;
- MDE;
- Intervalo de amostragem.

Saídas:
- Pontos de amostragem com altitude;
- Resumo por talvegue;
- Declividade equivalente global;
- Comprimento total global.

Observação:
O cálculo dos trechos é mantido apenas internamente, pois é necessário
para o método de Taylor-Schwarz. A camada de saída de trechos foi removida.
"""

import math
from dataclasses import dataclass
from typing import Optional

from qgis.PyQt.QtCore import QCoreApplication, QVariant
from qgis.core import (
    QgsCoordinateTransform,
    QgsFeature,
    QgsFeatureSink,
    QgsField,
    QgsFields,
    QgsGeometry,
    QgsProcessing,
    QgsProcessingAlgorithm,
    QgsProcessingException,
    QgsProcessingOutputNumber,
    QgsProcessingParameterFeatureSink,
    QgsProcessingParameterField,
    QgsProcessingParameterNumber,
    QgsProcessingParameterRasterLayer,
    QgsProcessingParameterVectorLayer,
    QgsProject,
    QgsWkbTypes,
)


@dataclass
class PontoAmostrado:
    ponto: object
    altitude: Optional[float]
    distancia: float


@dataclass
class ResultadoTalvegue:
    comprimento_total: float = 0.0
    soma_li_sobre_raiz_ii: float = 0.0
    trechos_totais: int = 0
    trechos_ignorados: int = 0

    @property
    def declividade_efetiva(self):
        if self.comprimento_total <= 0 or self.soma_li_sobre_raiz_ii <= 0:
            return None
        return (self.comprimento_total / self.soma_li_sobre_raiz_ii) ** 2


class DeclividadeTaylorSchwarzAlgorithm(QgsProcessingAlgorithm):

    TALVEGUE = 'TALVEGUE'
    CAMPO_ID_TALVEGUE = 'CAMPO_ID_TALVEGUE'
    MDE = 'MDE'
    INTERVALO = 'INTERVALO'

    SAIDA_PONTOS = 'SAIDA_PONTOS'
    SAIDA_RESUMO = 'SAIDA_RESUMO'

    DECLIVIDADE_EQUIVALENTE = 'DECLIVIDADE_EQUIVALENTE'
    COMPRIMENTO_TOTAL = 'COMPRIMENTO_TOTAL'

    TOLERANCIA_DISTANCIA = 1e-9
    LIMITE_ALERTA_TRECHOS_IGNORADOS = 0.30

    def tr(self, texto):
        return QCoreApplication.translate('Processing', texto)

    def createInstance(self):
        return DeclividadeTaylorSchwarzAlgorithm()

    def name(self):
        return 'declividade_taylor_schwarz'

    def displayName(self):
        return self.tr('Declividade Equivalente do Talvegue (Taylor-Schwarz)')

    def group(self):
        return self.tr('Hidrologia')

    def groupId(self):
        return 'hidrologia_scripts'

    def shortHelpString(self):
        return self.tr(
            'Calcula a declividade equivalente do talvegue pelo método '
            'Taylor-Schwarz.\n\n'
            'Saídas geradas:\n'
            '- Pontos de amostragem com altitude extraída do MDE;\n'
            '- Resumo por talvegue com declividade efetiva em m/m e em %;\n'
            '- Declividade equivalente global e comprimento total global.\n\n'
            'Use preferencialmente uma camada de talvegue em SRC projetado '
            'com unidade em metros.\n\n'
            'Desenvolvido por Manuela Py.\n\n'
            'geomanupy@gmail.com'
        )

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.TALVEGUE,
                self.tr('Camada do talvegue (linhas)'),
                types=[QgsProcessing.TypeVectorLine]
            )
        )

        self.addParameter(
            QgsProcessingParameterField(
                self.CAMPO_ID_TALVEGUE,
                self.tr('Campo identificador do talvegue (opcional)'),
                parentLayerParameterName=self.TALVEGUE,
                optional=True
            )
        )

        self.addParameter(
            QgsProcessingParameterRasterLayer(
                self.MDE,
                self.tr('Modelo Digital de Elevação (MDE)')
            )
        )

        self.addParameter(
            QgsProcessingParameterNumber(
                self.INTERVALO,
                self.tr('Intervalo de amostragem (unidade do SRC da camada)'),
                type=QgsProcessingParameterNumber.Double,
                defaultValue=50.0,
                minValue=0.0001
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.SAIDA_PONTOS,
                self.tr('Pontos de amostragem (altitude)')
            )
        )

        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.SAIDA_RESUMO,
                self.tr('Resumo por talvegue')
            )
        )

        self.addOutput(
            QgsProcessingOutputNumber(
                self.DECLIVIDADE_EQUIVALENTE,
                self.tr('Declividade equivalente global (m/m)')
            )
        )

        self.addOutput(
            QgsProcessingOutputNumber(
                self.COMPRIMENTO_TOTAL,
                self.tr('Comprimento total de todos os talvegues')
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        talvegue = self.parameterAsVectorLayer(parameters, self.TALVEGUE, context)
        campo_id = self.parameterAsString(parameters, self.CAMPO_ID_TALVEGUE, context)
        mde = self.parameterAsRasterLayer(parameters, self.MDE, context)
        intervalo = self.parameterAsDouble(parameters, self.INTERVALO, context)

        campo_id = campo_id.strip() if campo_id else ''

        self._validar_entradas(talvegue, mde, intervalo)

        sink_pontos, destino_pontos, campos_pontos = self._criar_saida_pontos(
            parameters,
            context,
            talvegue
        )
        sink_resumo, destino_resumo, campos_resumo = self._criar_saida_resumo(
            parameters,
            context,
            talvegue
        )

        provedor_raster = mde.dataProvider()
        transformador, precisa_transformar = self._criar_transformador(talvegue, mde, feedback)

        total_feicoes = talvegue.featureCount()
        if total_feicoes == 0:
            raise QgsProcessingException(self.tr('A camada de talvegue não possui feições.'))

        ordem_ponto = 0
        comprimento_global = 0.0
        soma_global = 0.0

        for indice_feicao, feicao in enumerate(talvegue.getFeatures()):
            if feedback.isCanceled():
                break

            nome_talvegue = self._obter_nome_talvegue(feicao, campo_id)
            resultado_feicao = ResultadoTalvegue()

            for indice_parte, linha in enumerate(self._obter_partes(feicao, nome_talvegue, feedback)):
                resultado_parte, ordem_ponto = self._processar_linha(
                    linha=linha,
                    feicao=feicao,
                    nome_talvegue=nome_talvegue,
                    indice_parte=indice_parte,
                    intervalo=intervalo,
                    provedor_raster=provedor_raster,
                    transformador=transformador,
                    precisa_transformar=precisa_transformar,
                    sink_pontos=sink_pontos,
                    campos_pontos=campos_pontos,
                    ordem_ponto=ordem_ponto,
                    feedback=feedback
                )

                resultado_feicao.comprimento_total += resultado_parte.comprimento_total
                resultado_feicao.soma_li_sobre_raiz_ii += resultado_parte.soma_li_sobre_raiz_ii
                resultado_feicao.trechos_totais += resultado_parte.trechos_totais
                resultado_feicao.trechos_ignorados += resultado_parte.trechos_ignorados

            self._gravar_resumo(
                sink=sink_resumo,
                campos=campos_resumo,
                nome_talvegue=nome_talvegue,
                resultado=resultado_feicao,
                feedback=feedback
            )

            comprimento_global += resultado_feicao.comprimento_total
            soma_global += resultado_feicao.soma_li_sobre_raiz_ii

            if total_feicoes > 0:
                feedback.setProgress(int(100 * (indice_feicao + 1) / total_feicoes))

        if comprimento_global <= 0 or soma_global <= 0:
            raise QgsProcessingException(
                self.tr(
                    'Não foi possível calcular a declividade equivalente. '
                    'Verifique a cobertura do MDE, o SRC das camadas e o intervalo de amostragem.'
                )
            )

        declividade_global = (comprimento_global / soma_global) ** 2

        feedback.pushInfo(
            self.tr('Comprimento total dos talvegues: {0:.2f}').format(comprimento_global)
        )
        feedback.pushInfo(
            self.tr('Declividade equivalente global: {0:.6f} m/m ({1:.4f}%)').format(
                declividade_global,
                declividade_global * 100
            )
        )

        return {
            self.SAIDA_PONTOS: destino_pontos,
            self.SAIDA_RESUMO: destino_resumo,
            self.DECLIVIDADE_EQUIVALENTE: declividade_global,
            self.COMPRIMENTO_TOTAL: comprimento_global
        }

    def _validar_entradas(self, talvegue, mde, intervalo):
        if talvegue is None:
            raise QgsProcessingException(self.tr('Camada de talvegue inválida.'))
        if mde is None:
            raise QgsProcessingException(self.tr('Camada de MDE inválida.'))
        if intervalo <= 0:
            raise QgsProcessingException(self.tr('O intervalo de amostragem deve ser maior que zero.'))

    def _criar_saida_pontos(self, parameters, context, talvegue):
        campos = QgsFields()
        campos.append(QgsField('talvegue', QVariant.String))
        campos.append(QgsField('id_feicao', QVariant.Int))
        campos.append(QgsField('id_parte', QVariant.Int))
        campos.append(QgsField('ordem', QVariant.Int))
        campos.append(QgsField('distancia_acumulada', QVariant.Double))
        campos.append(QgsField('altitude', QVariant.Double))

        sink, destino = self.parameterAsSink(
            parameters,
            self.SAIDA_PONTOS,
            context,
            campos,
            QgsWkbTypes.Point,
            talvegue.sourceCrs()
        )

        if sink is None:
            raise QgsProcessingException(self.invalidSinkError(parameters, self.SAIDA_PONTOS))

        return sink, destino, campos

    def _criar_saida_resumo(self, parameters, context, talvegue):
        campos = QgsFields()
        campos.append(QgsField('talvegue', QVariant.String))
        campos.append(QgsField('tamanho_talvegue', QVariant.Double))
        campos.append(QgsField('declividade_efetiva', QVariant.Double))
        campos.append(QgsField('declividade_efe_perc', QVariant.Double))
        campos.append(QgsField('trechos_ignorados', QVariant.Int))
        campos.append(QgsField('trechos_totais', QVariant.Int))

        sink, destino = self.parameterAsSink(
            parameters,
            self.SAIDA_RESUMO,
            context,
            campos,
            QgsWkbTypes.NoGeometry,
            talvegue.sourceCrs()
        )

        if sink is None:
            raise QgsProcessingException(self.invalidSinkError(parameters, self.SAIDA_RESUMO))

        return sink, destino, campos

    def _criar_transformador(self, talvegue, mde, feedback):
        crs_talvegue = talvegue.sourceCrs()
        crs_mde = mde.crs()
        precisa_transformar = crs_talvegue != crs_mde
        transformador = QgsCoordinateTransform(crs_talvegue, crs_mde, QgsProject.instance())

        if precisa_transformar:
            feedback.pushInfo(
                self.tr(
                    'SRC do talvegue ({0}) diferente do SRC do MDE ({1}). '
                    'Os pontos serão reprojetados para amostragem.'
                ).format(crs_talvegue.authid(), crs_mde.authid())
            )

        return transformador, precisa_transformar

    def _obter_nome_talvegue(self, feicao, campo_id):
        if not campo_id:
            return str(feicao.id())

        valor = feicao[campo_id]
        if valor is None or str(valor).strip() == '':
            return str(feicao.id())

        return str(valor)

    def _obter_partes(self, feicao, nome_talvegue, feedback):
        geometria = feicao.geometry()

        if geometria is None or geometria.isEmpty():
            feedback.pushWarning(
                self.tr('Talvegue {0} (feição {1}): geometria vazia ignorada.').format(
                    nome_talvegue,
                    feicao.id()
                )
            )
            return []

        partes = geometria.asMultiPolyline() if geometria.isMultipart() else [geometria.asPolyline()]
        partes_validas = []

        for indice, linha in enumerate(partes):
            if len(linha) < 2:
                feedback.pushWarning(
                    self.tr(
                        'Talvegue {0} (feição {1}, parte {2}): linha com menos de 2 vértices ignorada.'
                    ).format(nome_talvegue, feicao.id(), indice)
                )
                continue

            partes_validas.append(linha)

        return partes_validas

    def _processar_linha(
        self,
        linha,
        feicao,
        nome_talvegue,
        indice_parte,
        intervalo,
        provedor_raster,
        transformador,
        precisa_transformar,
        sink_pontos,
        campos_pontos,
        ordem_ponto,
        feedback
    ):
        geometria_linha = QgsGeometry.fromPolylineXY(linha)
        comprimento_trechonha = geometria_linha.length()

        if comprimento_trechonha <= 0:
            return ResultadoTalvegue(), ordem_ponto

        distancias = self._gerar_distancias(comprimento_trechonha, intervalo)
        if len(distancias) < 2:
            return ResultadoTalvegue(), ordem_ponto

        pontos = []

        for distancia in distancias:
            ponto_geom = geometria_linha.interpolate(distancia)

            if ponto_geom is None or ponto_geom.isEmpty():
                continue

            ponto_xy = ponto_geom.asPoint()
            ponto_amostra = self._preparar_ponto_amostra(
                ponto=ponto_xy,
                distancia=distancia,
                feicao=feicao,
                nome_talvegue=nome_talvegue,
                indice_parte=indice_parte,
                transformador=transformador,
                precisa_transformar=precisa_transformar,
                feedback=feedback
            )

            if ponto_amostra is None:
                continue

            altitude = self._amostrar_altitude(
                ponto=ponto_amostra,
                distancia=distancia,
                feicao=feicao,
                nome_talvegue=nome_talvegue,
                indice_parte=indice_parte,
                provedor_raster=provedor_raster,
                feedback=feedback
            )

            pontos.append(PontoAmostrado(ponto=ponto_xy, altitude=altitude, distancia=distancia))

            ordem_ponto = self._gravar_ponto(
                sink=sink_pontos,
                campos=campos_pontos,
                ponto=ponto_xy,
                nome_talvegue=nome_talvegue,
                id_feicao=feicao.id(),
                indice_parte=indice_parte,
                ordem_ponto=ordem_ponto,
                distancia=distancia,
                altitude=altitude
            )

        return self._calcular_resultado_taylor_schwarz(
            pontos=pontos,
            feicao=feicao,
            nome_talvegue=nome_talvegue,
            indice_parte=indice_parte,
            feedback=feedback
        ), ordem_ponto

    def _gerar_distancias(self, comprimento_trechonha, intervalo):
        distancias = []
        distancia = 0.0

        while distancia < comprimento_trechonha:
            distancias.append(distancia)
            distancia += intervalo

        distancias.append(comprimento_trechonha)
        return self._remover_distancias_repetidas(distancias)

    def _remover_distancias_repetidas(self, distancias):
        distancias_filtradas = [distancias[0]]

        for distancia in distancias[1:]:
            if distancia - distancias_filtradas[-1] > self.TOLERANCIA_DISTANCIA:
                distancias_filtradas.append(distancia)

        return distancias_filtradas

    def _preparar_ponto_amostra(
        self,
        ponto,
        distancia,
        feicao,
        nome_talvegue,
        indice_parte,
        transformador,
        precisa_transformar,
        feedback
    ):
        if not precisa_transformar:
            return ponto

        try:
            return transformador.transform(ponto)
        except Exception as erro:
            feedback.pushWarning(
                self.tr(
                    'Talvegue {0} (feição {1}, parte {2}): falha ao reprojetar '
                    'ponto na distância {3:.2f}. Detalhe: {4}'
                ).format(nome_talvegue, feicao.id(), indice_parte, distancia, erro)
            )
            return None

    def _amostrar_altitude(
        self,
        ponto,
        distancia,
        feicao,
        nome_talvegue,
        indice_parte,
        provedor_raster,
        feedback
    ):
        valor_z, sucesso = provedor_raster.sample(ponto, 1)

        if not sucesso or valor_z is None:
            feedback.pushWarning(
                self.tr(
                    'Talvegue {0} (feição {1}, parte {2}): ponto na distância '
                    '{3:.2f} está fora do MDE ou em NoData.'
                ).format(nome_talvegue, feicao.id(), indice_parte, distancia)
            )
            return None

        return float(valor_z)

    def _gravar_ponto(
        self,
        sink,
        campos,
        ponto,
        nome_talvegue,
        id_feicao,
        indice_parte,
        ordem_ponto,
        distancia,
        altitude
    ):
        feicao_saida = QgsFeature(campos)
        feicao_saida.setGeometry(QgsGeometry.fromPointXY(ponto))
        feicao_saida.setAttributes([
            nome_talvegue,
            id_feicao,
            indice_parte,
            ordem_ponto,
            distancia,
            altitude
        ])
        sink.addFeature(feicao_saida, QgsFeatureSink.FastInsert)
        return ordem_ponto + 1

    def _calcular_resultado_taylor_schwarz(self, pontos, feicao, nome_talvegue, indice_parte, feedback):
        resultado = ResultadoTalvegue()

        for indice in range(len(pontos) - 1):
            ponto_montante = pontos[indice]
            ponto_jusante = pontos[indice + 1]

            comprimento_trecho = ponto_jusante.distancia - ponto_montante.distancia
            if comprimento_trecho <= 0:
                continue

            resultado.comprimento_total += comprimento_trecho
            resultado.trechos_totais += 1

            if ponto_montante.altitude is None or ponto_jusante.altitude is None:
                resultado.trechos_ignorados += 1
                continue

            delta_h = abs(ponto_montante.altitude - ponto_jusante.altitude)
            declividade_trecho = delta_h / comprimento_trecho

            if declividade_trecho <= 0:
                resultado.trechos_ignorados += 1
                feedback.pushWarning(
                    self.tr(
                        'Talvegue {0}, trecho {1} (feição {2}, parte {3}) '
                        'com declividade nula. Trecho excluído do somatório.'
                    ).format(nome_talvegue, indice, feicao.id(), indice_parte)
                )
                continue

            resultado.soma_li_sobre_raiz_ii += comprimento_trecho / math.sqrt(declividade_trecho)

        return resultado

    def _gravar_resumo(self, sink, campos, nome_talvegue, resultado, feedback):
        declividade = resultado.declividade_efetiva
        declividade_perc = declividade * 100 if declividade is not None else None

        if declividade is None:
            feedback.pushWarning(
                self.tr(
                    'Talvegue {0}: não foi possível calcular a declividade efetiva.'
                ).format(nome_talvegue)
            )

        self._alertar_trechos_ignorados(nome_talvegue, resultado, feedback)

        feicao_resumo = QgsFeature(campos)
        feicao_resumo.setAttributes([
            nome_talvegue,
            resultado.comprimento_total if resultado.comprimento_total > 0 else None,
            declividade,
            declividade_perc,
            resultado.trechos_ignorados,
            resultado.trechos_totais
        ])
        sink.addFeature(feicao_resumo, QgsFeatureSink.FastInsert)

    def _alertar_trechos_ignorados(self, nome_talvegue, resultado, feedback):
        if resultado.trechos_totais <= 0 or resultado.trechos_ignorados <= 0:
            return

        fracao = resultado.trechos_ignorados / resultado.trechos_totais
        if fracao <= self.LIMITE_ALERTA_TRECHOS_IGNORADOS:
            return

        feedback.pushWarning(
            self.tr(
                'Talvegue {0}: {1} de {2} trechos ({3:.0f}%) foram ignorados '
                'por NoData ou declividade nula.'
            ).format(
                nome_talvegue,
                resultado.trechos_ignorados,
                resultado.trechos_totais,
                fracao * 100
            )
        )
