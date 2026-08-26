# Pastas de operação

## Agenda

- Entrada: `entrada/agenda/agenda.xlsx`
- Painel vigente: `../atualizados`
- Backups: `saida/backups/agenda`
- Auditoria: `saida/processados/agenda`

Na primeira aba do aplicativo, selecione manualmente o mês e o ano correspondentes ao arquivo.

## `entrada/exames`

Coloque aqui os quatro arquivos da nova competência, mantendo estes nomes:

- `imagem.xlsx`
- `laboratorio.xlsx`
- `terapia.xlsx`
- `outros.xlsx`

Os arquivos atuais podem ser substituídos pelos arquivos do próximo mês.

## `../atualizados`

Contém o painel vigente. A aplicação atualiza e renomeia esse arquivo automaticamente.

## `saida`

- `backups/exames`: versão anterior do painel, criada antes de cada atualização.
- `processados/exames`: cópia das cargas e manifesto de auditoria.
- `logs`: informações técnicas de execução.

Para executar, volte à raiz do projeto e abra `Abrir Atualizador de Paineis.cmd`.

## Cirurgias

- Entrada: `entrada/cirurgias/cirurgias.xlsx`
- Painel vigente: `../atualizados`
- Backups: `saida/backups/cirurgias`
- Auditoria: `saida/processados/cirurgias`

## 3CX

- Entrada: `entrada/3cx/queue_performance.csv`
- Painel vigente: `../atualizados`
- Backups: `saida/backups/3cx`
- Auditoria: `saida/processados/3cx`

Na aba 3CX, selecione manualmente o mês e o ano correspondentes ao CSV antes de atualizar.
