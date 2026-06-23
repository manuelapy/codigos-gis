# Memória de Cálculo — Salvamento Automatizado de Estilos no QGIS

## 1. Objetivo

Este script tem como objetivo automatizar o salvamento em lote dos estilos de camadas no QGIS, permitindo registrar os estilos associados às camadas vetoriais selecionadas.

A ferramenta foi desenvolvida para facilitar a organização, preservação e reutilização de simbologias, especialmente em projetos que utilizam múltiplas camadas, múltiplos estilos por camada e arquivos no formato GeoPackage.

O algoritmo permite salvar os estilos de duas formas principais:

* diretamente no banco de dados da fonte, quando a camada está em formato `.gpkg`;
* como arquivos externos `.qml`, armazenados na mesma pasta do dado de origem.

Além disso, o script gera um relatório final com o resumo do processamento, indicando quais camadas e estilos foram salvos com sucesso e quais apresentaram erro.

---

## 2. Dados de Entrada

O algoritmo utiliza como entrada uma lista de camadas carregadas no projeto QGIS.

## 2.1 Camadas

O usuário seleciona uma ou mais camadas do projeto.

O script aceita camadas do tipo `QgsMapLayer`, mas processa apenas camadas vetoriais. Camadas raster ou outros tipos de camada são ignoradas e registradas no relatório como aviso.

## 2.2 Opção de salvamento no GeoPackage

Parâmetro booleano que define se os estilos devem ser salvos no banco de dados da fonte da camada.

Quando essa opção está ativa, o script verifica se a fonte da camada é um arquivo `.gpkg`.

Caso a camada não seja proveniente de um GeoPackage, o salvamento em banco é ignorado para essa camada.

## 2.3 Opção de gravação direta no GeoPackage

Parâmetro booleano que define se o script deve tentar uma gravação direta na tabela `layer_styles` quando o método nativo do QGIS falhar.

Essa opção funciona como uma alternativa de segurança para casos em que o método `saveStyleToDatabase()` não consegue gravar corretamente o estilo no GeoPackage.

## 2.4 Opção de exportação QML

Parâmetro booleano que define se cada estilo também deve ser exportado como arquivo `.qml`.

Quando essa opção está ativa, o script cria um arquivo `.qml` para cada estilo detectado na camada.

---

## 3. Fluxo Geral de Processamento

O processamento segue a seguinte sequência lógica:

```text
1. Receber a lista de camadas selecionadas pelo usuário.
2. Verificar se existem camadas de entrada.
3. Iterar sobre cada camada.
4. Validar se a camada é válida e vetorial.
5. Acessar o gerenciador de estilos da camada.
6. Identificar todos os estilos disponíveis.
7. Salvar cada estilo conforme as opções marcadas.
8. Restaurar o estilo original da camada.
9. Registrar mensagens de sucesso, aviso ou erro.
10. Gerar relatório final consolidado.
```

O script foi estruturado para evitar que uma falha em uma camada interrompa todo o processamento. Assim, erros são tratados individualmente e registrados no relatório.

---

## 4. Identificação dos Estilos

Para cada camada vetorial válida, o script acessa o gerenciador de estilos da camada por meio de:

```text
camada.styleManager()
```

Em seguida, identifica todos os estilos existentes na camada.

Cada estilo é ativado temporariamente para que possa ser salvo ou exportado.

O estilo que estava ativo originalmente no projeto é armazenado antes do processamento. Ao final da camada, esse estilo original é restaurado, evitando que o script altere a visualização final do projeto no painel de camadas.

---

## 5. Salvamento pelo Método Nativo do QGIS

Quando a opção de salvamento no GeoPackage está ativa, o script tenta inicialmente usar o método nativo do QGIS:

```text
saveStyleToDatabase()
```

Esse método salva o estilo no banco de dados associado à camada.

Para cada estilo, o script informa:

```text
nome do estilo
descrição automática
se o estilo deve ser usado como padrão
```

O estilo original da camada é marcado como o estilo padrão no banco de dados.

A lógica adotada é:

```text
se nome_estilo == estilo_original:
    usar_como_padrao = True
caso contrário:
    usar_como_padrao = False
```

Esse comportamento garante que, quando a camada for reaberta, o estilo principal continue sendo o mesmo que estava ativo no projeto.

---

## 6. Gravação Direta na Tabela layer_styles

Caso o método nativo do QGIS falhe, o script pode tentar gravar o estilo diretamente dentro do arquivo `.gpkg`.

Essa gravação é feita usando conexão SQLite, pois o GeoPackage é baseado em SQLite.

A tabela utilizada é:

```text
layer_styles
```

Caso essa tabela ainda não exista, o script cria a estrutura necessária automaticamente.

A tabela contém campos como:

```text
id
f_table_catalog
f_table_schema
f_table_name
f_geometry_column
styleName
styleQML
styleSLD
useAsDefault
description
owner
ui
update_time
```

O conteúdo principal salvo é o `styleQML`, que armazena a simbologia da camada em formato QML.

---

## 7. Exportação Temporária do Estilo para QML

Para gravar o estilo diretamente no GeoPackage, o script primeiro exporta o estilo ativo para um arquivo `.qml` temporário.

Esse arquivo temporário é criado apenas para capturar o conteúdo textual do estilo.

O fluxo é:

```text
1. Criar arquivo temporário com extensão .qml.
2. Salvar o estilo atual nesse arquivo.
3. Ler o conteúdo textual do arquivo.
4. Armazenar o conteúdo na variável QML.
5. Excluir o arquivo temporário.
```

Depois disso, o conteúdo QML é inserido ou atualizado na tabela `layer_styles`.

---

## 8. Atualização ou Inserção do Estilo no GeoPackage

Antes de inserir um novo estilo na tabela `layer_styles`, o script verifica se já existe um registro com:

```text
nome da tabela da camada
coluna de geometria
nome do estilo
```

Se o estilo já existir, o registro é atualizado.

Se o estilo ainda não existir, um novo registro é inserido.

Essa lógica evita duplicação desnecessária de estilos no GeoPackage.

---

## 9. Definição do Estilo Padrão

Quando o estilo processado é o estilo original da camada, o script marca esse estilo como padrão usando o campo:

```text
useAsDefault
```

Antes de definir o novo estilo padrão, o script zera o valor de `useAsDefault` para os demais estilos da mesma camada.

Isso evita que mais de um estilo seja marcado como padrão para a mesma tabela e coluna de geometria.

A lógica aplicada é:

```text
1. Identificar se o estilo atual é o estilo original.
2. Se for padrão, remover a marcação de padrão dos estilos anteriores.
3. Marcar o estilo atual como padrão.
```

---

## 10. Identificação da Tabela e da Coluna de Geometria

Para gravar corretamente o estilo no GeoPackage, o script precisa identificar:

```text
nome da tabela
nome da coluna de geometria
```

A identificação é feita em etapas:

```text
1. Tenta decodificar a URI da camada usando QgsProviderRegistry.
2. Busca informações como layerName, table ou name.
3. Busca a coluna de geometria informada na URI.
4. Se necessário, tenta extrair o layername diretamente da string de origem.
5. Consulta a tabela gpkg_geometry_columns dentro do GeoPackage.
6. Caso nada seja encontrado, usa o nome da camada como alternativa.
```

Esse procedimento aumenta a robustez do script, pois diferentes camadas GeoPackage podem apresentar suas informações de origem de formas diferentes no QGIS.

---

## 11. Exportação dos Estilos como QML

Quando a opção de exportação `.qml` está ativa, o script salva cada estilo como um arquivo externo.

O arquivo é criado na mesma pasta do dado de origem.

Para camadas GeoPackage, o nome do arquivo segue o padrão:

```text
nomeDoGeoPackage_nomeDaCamada_nomeDoEstilo.qml
```

Para outras fontes vetoriais, o padrão é:

```text
nomeDoArquivo_nomeDoEstilo.qml
```

Antes de montar o nome do arquivo, o script limpa caracteres especiais e substitui espaços por sublinhados, reduzindo o risco de erro no sistema de arquivos.

---

## 12. Critérios de Validação

Durante o processamento, o script realiza várias verificações para evitar falhas críticas.

Uma camada é ignorada quando:

```text
a camada é inválida;
a camada está inacessível;
a camada não é vetorial;
a camada não possui estilos cadastrados;
a camada não possui caminho físico identificável;
a camada não é GeoPackage e a opção de salvar em banco está ativa.
```

Um estilo pode gerar erro quando:

```text
não pode ser ativado no gerenciador de estilos;
falha no método nativo de salvamento;
falha na gravação direta na tabela layer_styles;
falha na exportação do arquivo .qml;
o QML exportado está vazio;
o arquivo .gpkg não é encontrado.
```

Os erros de estilo são registrados individualmente, sem interromper obrigatoriamente o processamento dos demais estilos e camadas.

---

## 13. Saída Gerada

O algoritmo retorna uma saída textual chamada:

```text
RELATORIO
```

Esse relatório apresenta:

```text
início do log de execução;
nome de cada camada processada;
quantidade de estilos detectados;
estilo original da camada;
resultado de cada tentativa de salvamento;
avisos encontrados;
erros por estilo;
resumo por camada;
resumo final do processamento.
```

No resumo final são apresentados:

```text
camadas processadas com sucesso;
camadas com erro crítico;
total de estilos salvos.
```

---

## 14. Interpretação do Relatório

As mensagens do relatório seguem uma estrutura padronizada.

## 14.1 Mensagens de sucesso

```text
[OK GPKG]
```

Indica que o estilo foi salvo no GeoPackage pelo método nativo do QGIS.

```text
[OK GPKG DIRETO]
```

Indica que o método nativo falhou, mas o estilo foi salvo com sucesso por gravação direta na tabela `layer_styles`.

```text
[OK QML]
```

Indica que o estilo foi exportado corretamente como arquivo `.qml`.

## 14.2 Mensagens de aviso

```text
[AVISO]
```

Indica uma situação que não impede o processamento geral, mas que precisa de atenção.

Exemplos:

```text
camada não vetorial;
fonte não é GeoPackage;
nenhum estilo encontrado;
caminho físico não identificado.
```

## 14.3 Mensagens de erro

```text
[ERRO ESTILO]
```

Indica falha ao processar um estilo específico.

```text
[ERRO CRÍTICO]
```

Indica falha mais grave no processamento da camada.

---

## 15. Exemplo de Uso

O usuário deve executar o algoritmo no QGIS e selecionar as camadas que deseja processar.

Em seguida, pode escolher uma ou mais opções de saída:

```text
Salvar no GeoPackage / banco de dados da fonte
Se falhar, forçar gravação direta no .gpkg
Exportar também como .qml
```

Uma configuração comum é:

```text
Salvar no GeoPackage: sim
Forçar gravação direta no .gpkg: sim
Exportar como .qml: não
```

Essa configuração tenta salvar os estilos no próprio GeoPackage e usa a gravação direta como alternativa caso o método nativo falhe.

---

## 16. Aplicação Prática

Este script é útil para projetos QGIS que utilizam muitas camadas e múltiplos estilos, principalmente quando há necessidade de padronizar entregas técnicas.

Ele pode ser aplicado em:

```text
organização de bancos GeoPackage;
padronização de simbologias;
preparação de arquivos para entrega;
rotinas de automação cartográfica;
produtos digitais baseados em QGIS;
projetos com múltiplas versões de estilo por camada.
```

O uso do GeoPackage como repositório de dados e estilos facilita a portabilidade do projeto, pois permite armazenar a simbologia junto à camada.

---

## 17. Observações Técnicas

O script processa apenas camadas vetoriais.

O salvamento direto no GeoPackage depende da existência de um arquivo `.gpkg` acessível no sistema de arquivos.

A exportação `.qml` depende da identificação correta do caminho físico da camada.

A gravação direta na tabela `layer_styles` deve ser usada com cuidado, pois altera diretamente o banco GeoPackage por meio de SQLite.

Recomenda-se manter cópia de segurança dos arquivos `.gpkg` antes de executar rotinas em lote, especialmente em bases com muitos estilos ou camadas importantes.

---

## 18. Resultado Esperado

Ao final da execução, espera-se que os estilos das camadas selecionadas estejam salvos no próprio GeoPackage, exportados como `.qml`, ou ambos, conforme as opções escolhidas pelo usuário.

O relatório final permite auditar o processamento e identificar rapidamente quais camadas ou estilos precisam de revisão.

---

## 19. Autoria

Script desenvolvido por Manuela Py para automação de rotinas no QGIS, com foco em organização, padronização e preservação de estilos cartográficos.
