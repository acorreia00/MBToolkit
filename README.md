# MBSniffer

**MBSniffer** é uma ferramenta Windows para diagnóstico de comunicações **Modbus RTU** sobre **RS485** e **RS232**.

O objetivo é permitir observar, interpretar e diagnosticar tráfego Modbus RTU de forma simples, sem transformar o computador num master durante a captura passiva. A aplicação inclui também um **Bus Slave Finder** ativo para descoberta controlada de dispositivos.

## Principais funcionalidades

### Sniffer Modbus RTU passivo

Suporta três modos físicos:

- **RS485 2-wire** — uma COM observa pedidos e respostas no mesmo barramento.
- **RS232 single RX** — uma COM observa uma direção.
- **RS232 dual RX** — duas COM permitem observar as duas direções em simultâneo.

Durante a captura, o Sniffer não transmite dados pela porta série.

### Decodificação de tráfego

A tabela de tráfego apresenta:

- hora;
- Δt entre frames;
- tempo de resposta;
- COM/canal observado;
- tipo de frame;
- Slave ID;
- Function Code;
- detalhes da operação;
- estado do CRC.

São reconhecidos pedidos/respostas Modbus RTU, Exceptions, CRC errors e blocos RAW quando não é possível interpretar os bytes como um frame Modbus válido.

### Frame Inspector

Ao selecionar uma frame, o **Frame Inspector** apresenta informação estruturada:

- Slave;
- tipo;
- Function Code e nome;
- tempo de resposta;
- resultado;
- PDU Address;
- endereço 1-based;
- quantidade;
- Byte Count;
- CRC recebido;
- CRC calculado;
- dados / registers / Exception;
- Raw Hex.

O Inspector pode ser recolhido para libertar espaço para a tabela.

### Realçar resultados

A opção **Realçar resultados** é opcional e vem desligada por defeito.

Quando ativa, a tabela usa cores para facilitar o diagnóstico:

- **Verde** — transação concluída com sucesso;
- **Amarelo** — resposta lenta;
- **Vermelho** — CRC Error ou Modbus Exception;
- **Laranja** — Timeout;
- **Roxo** — RAW/UNSYNC ou RAW/UNPARSED.

Com a opção desligada, os mesmos resultados continuam visíveis, mas a tabela mantém uma apresentação neutra.

### Bus Health

O separador **Bus Health** resume a qualidade e desempenho da sessão:

- Requests;
- Responses;
- Request rate;
- Slaves ativos;
- bytes observados;
- utilização aproximada do barramento;
- response time médio;
- mínimo;
- máximo;
- P95;
- Slave mais lento;
- CRC error rate;
- timeout rate;
- Exceptions por Slave.

O layout adapta-se automaticamente ao espaço vertical disponível para impedir que as métricas ultrapassem os respetivos painéis.

### Filtros avançados

A vista de tráfego pode ser filtrada por:

- Slave;
- Requests;
- Responses;
- Exceptions;
- CRC errors;
- Timeouts;
- RAW;
- Function Code;
- tempo de resposta;
- pesquisa livre por texto.

Os filtros alteram apenas a visualização; não alteram as estatísticas da sessão nem os dados gravados em log.

### Menu de contexto

Com botão direito numa frame é possível:

- copiar Raw Hex;
- copiar a frame decodificada;
- filtrar pelo Slave;
- filtrar pelo Function Code;
- mostrar apenas a transação;
- limpar o filtro temporário de transação.

### Logs e exportação CSV

As capturas reais podem criar um log TXT completo em:

```text
MBSniffer Logs\
```

O log só é criado depois de existir tráfego real.

Também é possível exportar o histórico retido pela interface para CSV, incluindo os principais campos decodificados e o resultado/anomalia associado.

### Bus Slave Finder

O separador **Bus Slave Finder** é uma ferramenta ativa para descoberta de Slaves Modbus RTU.

Permite definir:

- COM;
- baud rates;
- parity;
- stop bits;
- intervalo de Slave IDs;
- timeout mínimo;
- fallback opcional FC04.

Por segurança, deve ser usado apenas quando não existe outro master ativo no mesmo barramento.

### Light / Dark mode

A aplicação inclui modos **Light** e **Dark**, mantendo a mesma geometria e construção visual em ambos.

As preferências relevantes ficam guardadas em:

```text
%APPDATA%\MBSniffer\settings.json
```

As portas COM não são persistidas.

### Scrollbars

As scrollbars usam um desenho minimalista:

- sem botões de seta;
- apenas cursor móvel visível;
- pista visualmente integrada no fundo;
- largura reduzida.

A roda do rato só atua quando o ponteiro está sobre uma scrollbar, evitando mudanças acidentais entre separadores.

## Simulação de desenvolvimento

A funcionalidade de simulação só aparece quando:

```python
debug_sim = 1
```

em `MBSniffer.py`.

Quando ativa, a simulação gera um cenário de diagnóstico com:

- transação normal;
- resposta lenta;
- Exception;
- CRC Error;
- Timeout;
- RAW/UNPARSED.

A simulação não abre portas série e não cria logs.

Com:

```python
debug_sim = 0
```

não existe qualquer referência ao modo de simulação na interface de ajuda.

## Execução

Depois de extrair o pacote:

```text
MBSniffer.bat
```

O launcher verifica a disponibilidade do `pyserial`.

## Criar o executável

Executar:

```text
MBSniffer\build_exe.bat
```

O executável é criado na raiz como:

```text
MBSniffer.exe
```

## Requisitos

- Windows 10/11 x64;
- Python 3.10+ para execução via BAT/Python;
- `pyserial`.

## Estrutura principal

```text
README.md
README.txt
MBSniffer.bat
MBSniffer\
├── MBSniffer.py
├── mb_config.py
├── mb_protocol.py
├── mb_diagnostics.py
├── mb_capture.py
├── mb_view.py
├── mb_gui.py
├── mb_widgets.py
├── mb_theme.py
├── mb_slave_finder.py
├── build_exe.bat
├── MBSniffer.ico
└── DEVELOPMENT_NOTES.md
```

## Histórico de versões

### v2.9

- Frame Inspector estruturado e recolhível.
- Bus Health com métricas de qualidade e desempenho.
- Filtros avançados de tráfego.
- Opção **Realçar resultados**.
- Sucesso destacado a verde e restantes resultados com cores de diagnóstico.
- Simulação de diagnóstico com sucesso, resposta lenta, Exception, CRC Error, Timeout e RAW.
- Menu de contexto por frame.
- Indicador de atividade `BUS ● RX`.
- Exportação CSV.
- Coluna `Canal` renomeada para `COM`.
- Ajuda / Ligações revista e expandida.
- Distinção explícita entre `RAW/UNSYNC` e `RAW/UNPARSED`.
- Correção da ressincronização do parser após bursts longos de ruído.
- Bus Health com layout adaptativo quando o Frame Inspector reduz o espaço disponível.
- Scrollbars simplificadas e mais discretas.
- Roda do rato limitada às próprias scrollbars para evitar mudança acidental de tabs.
- Tema Light/Dark mantido sem alterações estruturais.

### v2.8

- Separação da aplicação em módulos dedicados para protocolo, captura, interface, visualização e Bus Slave Finder.
- Bus Slave Finder integrado.
- Persistência de preferências em `%APPDATA%`.
- Light/Dark mode com geometria idêntica.
- Histórico gráfico limitado para preservar desempenho.
- Logging real criado apenas quando existe tráfego.
- Melhorias de filtros, ordenação, separação visual de transações e visualização Raw Hex.
- Melhorias de estabilidade no encerramento, reinício de COM e processamento da fila da GUI.

## Nota

O MBSniffer é uma ferramenta de diagnóstico de protocolo. Não substitui um osciloscópio ou analisador lógico quando é necessário avaliar níveis elétricos, ringing, reflexões, bias, common-mode ou integridade analógica do sinal.
