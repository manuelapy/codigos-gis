# Memória de Cálculo — Declividade Efetiva do Talvegue

## 1. Objetivo

Este script tem como objetivo calcular a **declividade efetiva do talvegue** pelo método de **Taylor-Schwarz**, a partir de uma camada vetorial de linhas representando o talvegue e de um Modelo Digital de Elevação — MDE.

O resultado principal é a declividade equivalente do talvegue, expressa em:

* `m/m`, no campo `declividade_efetiva`;
* `%`, no campo `declividade_efe_perc`.

Além disso, o script gera uma camada de pontos de amostragem com altitude extraída do MDE e uma tabela de resumo por talvegue.

---

## 2. Dados de Entrada

O algoritmo utiliza os seguintes dados de entrada:

### 2.1 Camada do talvegue

Camada vetorial do tipo linha, representando o eixo do talvegue a ser analisado.

Recomenda-se que essa camada esteja em um Sistema de Referência de Coordenadas projetado, com unidade em metros, para que os comprimentos calculados sejam coerentes.

### 2.2 Campo identificador do talvegue

Campo opcional utilizado para identificar cada talvegue no resultado final.

Caso esse campo não seja informado ou esteja vazio, o script utiliza o ID interno da feição como identificador.

### 2.3 Modelo Digital de Elevação — MDE

Raster utilizado para extrair a altitude dos pontos distribuídos ao longo do talvegue.

A altitude é extraída da banda 1 do raster.

### 2.4 Intervalo de amostragem

Distância utilizada para gerar os pontos ao longo do talvegue.

Por exemplo, um intervalo de `50 m` cria pontos a cada 50 metros ao longo da linha, além do ponto inicial e do ponto final da geometria.

---

## 3. Procedimento de Cálculo

## 3.1 Geração dos pontos de amostragem

Para cada linha de talvegue, o script calcula o comprimento total da geometria e gera pontos ao longo dela conforme o intervalo definido pelo usuário.

As distâncias consideradas seguem a lógica:

```text
0, intervalo, 2 x intervalo, 3 x intervalo, ..., comprimento final do talvegue
```

O ponto final da linha sempre é incluído, mesmo que o comprimento total não seja múltiplo exato do intervalo de amostragem.

---

## 3.2 Extração das altitudes

Para cada ponto gerado ao longo do talvegue, o script extrai a altitude correspondente no MDE.

Quando o SRC da camada de talvegue é diferente do SRC do MDE, o ponto é reprojetado temporariamente para o SRC do raster apenas para realizar a amostragem da altitude.

Caso o ponto esteja fora da área do MDE ou sobre uma célula sem valor válido, a altitude é registrada como nula e o trecho correspondente poderá ser ignorado no cálculo da declividade efetiva.

---

## 3.3 Definição dos trechos

Após a geração dos pontos, o script calcula os trechos entre pontos consecutivos.

Para cada trecho são considerados:

```text
Li = comprimento do trecho
Zi = altitude do ponto inicial
Zi+1 = altitude do ponto final
ΔH = diferença absoluta de altitude entre os pontos
Ii = declividade do trecho
```

A declividade de cada trecho é calculada por:

```text
Ii = ΔH / Li
```

Onde:

```text
Ii = declividade do trecho em m/m
ΔH = diferença de altitude entre os pontos, em metros
Li = comprimento do trecho, em metros
```

O script utiliza o valor absoluto da diferença de altitude, evitando que a direção da linha gere declividades negativas.

---

## 4. Método de Taylor-Schwarz

A declividade efetiva do talvegue é calculada pelo método de Taylor-Schwarz, que considera o comprimento de cada trecho e sua respectiva declividade.

A fórmula utilizada é:

```text
S = (L / Σ(Li / √Ii))²
```

Onde:

```text
S = declividade efetiva do talvegue
L = comprimento total do talvegue
Li = comprimento de cada trecho
Ii = declividade de cada trecho
Σ = somatório dos trechos válidos
```

Na prática, o script calcula o somatório:

```text
Σ(Li / √Ii)
```

Depois aplica:

```text
declividade_efetiva = (comprimento_total / soma_li_sobre_raiz_ii)²
```

---

## 5. Critérios de Validação dos Trechos

Nem todos os trechos são utilizados no somatório final do método Taylor-Schwarz.

Um trecho é ignorado quando:

* um dos pontos do trecho não possui altitude válida;
* o ponto está fora da cobertura do MDE;
* o valor extraído do MDE é NoData;
* a declividade calculada do trecho é igual a zero;
* o comprimento do trecho é nulo ou inválido.

Os trechos ignorados são contabilizados no campo:

```text
trechos_ignorados
```

O total de trechos avaliados é registrado no campo:

```text
trechos_totais
```

Quando mais de 30% dos trechos são ignorados, o script emite um alerta ao usuário, indicando possível problema na cobertura do MDE, na geometria do talvegue ou no intervalo de amostragem.

---

## 6. Conversão para Porcentagem

A declividade efetiva é inicialmente calculada em `m/m`.

Para facilitar a interpretação, o script também calcula a declividade em porcentagem:

```text
declividade_efe_perc = declividade_efetiva x 100
```

Exemplo:

```text
declividade_efetiva = 0,025 m/m
declividade_efe_perc = 2,5 %
```

---

## 7. Saídas Geradas

## 7.1 Pontos de amostragem

Camada pontual contendo os pontos criados ao longo do talvegue.

Campos gerados:

```text
talvegue
id_feicao
id_parte
ordem
distancia_acumulada
altitude
```

Essa saída permite verificar visualmente onde as altitudes foram coletadas e validar a distribuição dos pontos ao longo da linha.

---

## 7.2 Resumo por talvegue

Tabela sem geometria contendo o resultado consolidado por talvegue.

Campos gerados:

```text
talvegue
tamanho_talvegue
declividade_efetiva
declividade_efe_perc
trechos_ignorados
trechos_totais
```

O campo `tamanho_talvegue` representa o comprimento total considerado para o talvegue.

O campo `declividade_efetiva` apresenta a declividade calculada pelo método Taylor-Schwarz em `m/m`.

O campo `declividade_efe_perc` apresenta a mesma declividade convertida para porcentagem.

---

## 7.3 Resultados globais

Além da tabela por talvegue, o algoritmo também retorna dois valores globais:

```text
Declividade equivalente global
Comprimento total global
```

A declividade global é calculada considerando o conjunto de todos os talvegues processados.

---

## 8. Observações Técnicas

O cálculo depende diretamente da qualidade do MDE, da geometria da linha do talvegue e do intervalo de amostragem adotado.

Intervalos muito grandes podem simplificar excessivamente o perfil longitudinal do talvegue. Intervalos muito pequenos podem aumentar o processamento e capturar ruídos do MDE.

Recomenda-se utilizar dados em SRC projetado, preferencialmente em metros, e garantir que o MDE cubra integralmente a área do talvegue analisado.

---

## 9. Interpretação do Resultado

A declividade efetiva representa uma declividade equivalente ponderada ao longo do talvegue, considerando os diferentes trechos do perfil longitudinal.

Esse valor é útil em análises hidrológicas e geomorfológicas, especialmente quando se deseja representar o comportamento médio do talvegue sem depender apenas da diferença entre a cota inicial e a cota final.

Quanto maior o valor de `declividade_efetiva`, maior é a inclinação equivalente do talvegue.

Quanto menor o valor, mais suave é o perfil longitudinal analisado.

---

## 10. Autoria

Script desenvolvido para processamento automatizado no QGIS, com aplicação em análises hidrológicas, drenagem e caracterização morfométrica de talvegues.
