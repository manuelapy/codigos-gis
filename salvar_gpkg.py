

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
