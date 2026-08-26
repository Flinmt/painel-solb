# Atualizador de Painéis

Aplicativo Windows para atualização incremental de dashboards Excel. Os módulos disponíveis são
Agenda, Exames, Cirurgias, Atendimentos, Comparativo e 3CX.

As bases brutas preservam a origem recebida. Nos dados tratados, todos os módulos desconsideram
profissionais ou pacientes contendo `TESTE` e o marcador exato `Profissional`, ignorando caixa e
espaços extras.

## O que o módulo Agenda faz

1. Recebe `dados/entrada/agenda/agenda.xlsx` e a competência escolhida na tela.
2. Valida usuários, quantidades e percentuais do relatório.
3. Substitui o mês selecionado na tabela histórica da aba `INPUT`, sem duplicação.
4. Preserva categorias operacionais como `WEB`, `BIODATA` e usuários de suporte.
5. Atualiza tabelas dinâmicas, gráficos e segmentações pelo Microsoft Excel.
6. Cria backup e arquiva a entrada, os dados tratados e o manifesto da execução.

O arquivo da Agenda não informa mês e ano. Confira os seletores de competência antes de
processar.

## O que o módulo Exames faz

1. Recebe os arquivos de Imagem, Laboratório, Terapia e Outros.
2. Confirma que os quatro arquivos possuem a mesma competência.
3. Substitui essa competência nas abas `DADOS BRUTOS` e `DADOS TRATADOS`.
4. Padroniza as categorias históricas.
5. Atualiza tabelas dinâmicas, gráficos e segmentações pelo Microsoft Excel.
6. Cria backup e arquivos de auditoria antes de publicar o painel atualizado.
7. Publica `dados/saida/compartilhados/exames/exames-consolidado.xlsx`, com manifesto e hashes,
   para uso da aba Comparativo.
8. Renomeia o painel para o mês e ano processados.

A atualização é idempotente: processar novamente o mesmo mês substitui esse mês, sem duplicá-lo.

## O que o módulo Cirurgias faz

1. Recebe `dados/entrada/cirurgias/cirurgias.xlsx`.
2. Valida que o arquivo contém uma única competência.
3. Preserva todos os registros em `DADOS BRUTOS` e filtra testes somente no tratado.
4. Gera `Mês`, `Ano` e `QTD = 1` sem depender da configuração regional do Windows.
5. Substitui a competência nas abas `DADOS BRUTOS` e `DADOS TRATADOS`.
6. Atualiza as tabelas dinâmicas, gráficos e filtros do painel.
7. Cria backup e auditoria em `dados/saida`.

## O que o módulo Atendimentos faz

1. Recebe `dados/entrada/atendimentos/atendimentos.xlsx`.
2. Valida que o arquivo contém uma única competência.
3. Preserva os registros recebidos na tabela `DADOS BRUTOS`.
4. Descarta médicos e pacientes de teste somente de `DADOS TRATADOS`.
5. Gera `Mês`, `Ano` e `Quantidade = 1` para alimentar o dashboard.
6. Substitui a competência existente sem duplicar registros.
7. Atualiza tabelas dinâmicas, gráficos e segmentações, com backup e auditoria.

## O que o módulo Comparativo faz

1. Recebe `atendimentos.xlsx` e `cirurgias.xlsx` em `dados/entrada/comparativo`.
2. Usa automaticamente o consolidado publicado pela aba Exames.
3. Confirma pelo conteúdo, manifesto e hash que as três fontes pertencem à mesma competência.
4. Consolida consultas e retornos, exames de ressonância e cirurgias por profissional.
5. Gera `Profissional`, `Mês`, `Consultas`, `Exames`, `Cirurgias` e `Ano`.
6. Substitui a competência na aba `TRATADO`, sem duplicar o mês.
7. Atualiza tabelas dinâmicas, gráficos e segmentações do Painel Comparativo.
8. Cria backup e auditoria antes de publicar o painel atualizado.

## O que o módulo 3CX faz

1. Recebe `dados/entrada/3cx/queue_performance.csv` e a competência escolhida na tela.
2. Processa somente a fila `8019 SOLB CALLCENTER`.
3. Gera o resumo de chamadas e o detalhamento dos profissionais ativos.
4. Substitui o mês selecionado nas tabelas `Tabela1` e `Tabela2`, sem duplicação.
5. Atualiza tabelas dinâmicas, gráficos e segmentações do painel.
6. Cria backup e arquiva o CSV, o resumo, o detalhamento e o manifesto da execução.

O CSV da 3CX não informa mês e ano. Confira cuidadosamente os seletores de competência antes de
processar. O histórico das outras competências não é alterado.

## Uso pelo aplicativo

1. Feche o painel no Excel.
2. Coloque `imagem.xlsx`, `laboratorio.xlsx`, `terapia.xlsx` e `outros.xlsx` em
   `dados/entrada/exames`.
3. Dê duplo clique em `Abrir Atualizador de Paineis.cmd` na raiz do projeto.
4. Confirme o painel e os quatro arquivos localizados automaticamente.
5. Clique em **Processar e atualizar painel**.
6. Confira o resumo e use **Abrir painel** quando desejar.

Para atualizar o Comparativo, execute primeiro a aba **Exames** na mesma competência. Se o
consolidado estiver ausente, alterado ou for de outro mês, o aplicativo bloqueará a atualização.

Para atualizar a 3CX, substitua `dados/entrada/3cx/queue_performance.csv`, abra a aba **3CX**,
selecione o mês e o ano do relatório e clique em **Processar e atualizar painel**.

Para atualizar a Agenda, substitua `dados/entrada/agenda/agenda.xlsx`, abra a primeira aba,
selecione o mês e o ano do relatório e clique em **Processar e atualizar painel**.

Os painéis vigentes ficam em `atualizados`. Os backups ficam em
`dados/saida/backups/exames`. Cada carga processada, acompanhada de manifesto e hashes dos
arquivos de origem, fica em `dados/saida/processados/exames`. Os logs não registram dados de
pacientes.

## Organização operacional

```text
atualizados/                # painéis vigentes selecionados e atualizados pelo aplicativo
dados/
├── entrada/             # arquivos mensais fornecidos pelo usuário
└── saida/
    ├── backups/         # painel anterior a cada atualização
    ├── compartilhados/  # consolidado assinado usado entre módulos
    ├── processados/     # cargas e manifestos de auditoria
    └── logs/            # registros técnicos sem dados de pacientes
```

## Desenvolvimento

Requisitos: Windows, Python 3.12 ou superior e Microsoft Excel instalado.

```powershell
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check src tests
python -m atualizador_paineis
```

Para gerar o executável:

```powershell
.\build.ps1
```

O executável será criado na raiz do projeto, pronto para localizar o painel nessa mesma pasta.

## Inclusão de novos painéis

Cada novo painel deve implementar o contrato `PanelModule`, declarar suas entradas e manter suas
regras dentro de `src/atualizador_paineis/paineis`. Depois, basta adicioná-lo em
`paineis/registry.py`: a interface cria automaticamente uma nova aba no menu principal. Backup,
logs, navegação e publicação segura são serviços compartilhados.
