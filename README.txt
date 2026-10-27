MBTOOLKIT v3.4
================

MBToolkit é uma ferramenta Windows para diagnóstico de Modbus RTU.

- Sniffer: passivo; não transmite dados.
- Bus Slave Finder: ativo; transmite pedidos Modbus RTU de leitura.
- Master: ativo; lê e escreve valores como master Modbus RTU.
- Slave: ativo; simula equipamentos Modbus RTU e responde a um master real.

NOVIDADES v3.4
--------------
- Novo separador Slave: o MBToolkit faz de um ou mais equipamentos Modbus RTU
  e responde aos pedidos de um master real (PLC, SCADA, Modbus Poll).
- Cada janela é uma tabela de um Slave simulado: Slave ID, Coils, Discrete
  Inputs, Holding ou Input Registers, endereço e quantidade (até 2000).
  Vários Slave IDs, cada um com várias janelas.
- Responde a FC01–FC06, FC15 e FC16, com Exception 01/02/03 como um
  equipamento real; broadcast executado sem resposta; ignora o eco do
  adaptador RS485.
- Duplo clique num valor altera-o; as escritas do master ficam destacadas a
  amarelo por instantes.
- Simulação de falhas por Slave ID ("Falhas…"): atraso, não responder,
  Exception à escolha, CRC errado e probabilidade (%). A falha ativa aparece a
  vermelho no cabeçalho das janelas.
- Formatos, escala, nomes, Copiar, Base, renomear, destacar e fechar janelas
  como no Master. Menu Workspace próprio (só configuração; os valores começam
  a 0), guardado em %APPDATA%\MBToolkit\Workspaces\Slave.
- Sniffer, Finder, Master e Slave nunca funcionam ao mesmo tempo.
- Valores automáticos no Slave (clique direito → "Valor automático…"):
  contador, rampa, senoide e aleatório nos registos; alternar 0/1 e aleatório
  nas Coils e Discrete Inputs. Aparecem a azul e ficam no workspace.
- "Abrir no Slave": a partir do Tráfego do Sniffer e do clique direito numa
  janela do Master.
- Os workspaces do Master passam para %APPDATA%\MBToolkit\Workspaces\Master
  (movidos automaticamente no primeiro arranque).

BASE FUNCIONAL DA v3.3
- O programa passa a chamar-se MBToolkit (antes MBSniffer), com ícone novo,
  mais nítido em todos os tamanhos.
- Na primeira vez que arranca, copia as preferências e os workspaces de
  %APPDATA%\MBSniffer para %APPDATA%\MBToolkit. A pasta antiga fica intacta.
- Os logs novos ficam em "MBToolkit Logs"; os antigos continuam em
  "MBSniffer Logs".
- Workspaces guardados com o MBSniffer continuam a abrir.

BASE FUNCIONAL DA v3.2
- Novo separador Master: várias janelas, uma por Slave ou zona de memória.
- Cada janela: Slave ID, função FC01–FC04, endereço, quantidade, scan rate,
  base 0/1 e formato; botões Aplicar, Pausar, Ler 1x e Duplicar; no cabeçalho,
  Renomear, Destacar e ✕ (fechar).
- Formatos 16 bits (com/sem sinal, hex, binário), 32 bits (com/sem sinal e
  float) e 64 bits (com/sem sinal e double), nas 4 ordens de bytes; formato
  próprio por endereço com clique direito.
- O último workspace reabre ao arrancar; ao fechar com alterações por guardar,
  pergunta se quer guardar.
- Escala por endereço (bruto → unidades de engenharia, com unidade).
- "Abrir no Master" a partir do Tráfego do Sniffer e do Bus Slave Finder.
- Se o adaptador USB for desligado, o Master volta a ligar sozinho quando ele
  regressa.
- Escrita por duplo clique (FC05/06/15/16), incluindo broadcast (Slave 0).
- Contadores Tx/Err/Timeouts, tempo de resposta e último erro por janela.
- Menu Workspace: guarda a ligação, as janelas, os formatos e os nomes com um
  nome à escolha e lista os workspaces guardados para abrir ou apagar.
- O ZIP passa a incluir o histórico git, a pasta tools e o PDF técnico.

BASE FUNCIONAL DA v3.1
- Pedidos broadcast (Slave 0) deixam de contar como timeout.
- Escritas FC05/FC06/FC08/FC22 passam a ser identificadas como pedido e resposta,
  com tempo de resposta, emparelhamento e timeout.
- Frames partidos pelo adaptador USB já não aparecem como RAW.
- A tabela deixa de abrandar quando há muitos timeouts.
- Respostas FC01/FC02 mostram os bits; o Frame Inspector mostra o endereço de
  cada registo, coil ou entrada.
- Bus Slave Finder: opção "Tentativas" (1 a 3), timeout mínimo por defeito de
  100 ms e verificação automática de barramento livre antes de transmitir.

BASE FUNCIONAL DA v3.0
- Seletor de Linguagem no topo da aplicação: Português ou English, em tempo real.

BASE FUNCIONAL DA v2.9
- Frame Inspector estruturado e recolhível.
- Bus Health com métricas de qualidade/desempenho.
- Filtros avançados de Tráfego.
- Opção "Realçar resultados".
- Menu de contexto por frame.
- Indicador BUS RX.
- Exportação da sessão para CSV.
- Simulação de diagnóstico com anomalias em todas as execuções; "Realçar resultados" controla apenas as cores.
- Correção de ressincronização do parser após bursts longos de ruído.
- Frame gap Auto alinhado com Modbus RTU: acima de 19200 bit/s usa t3.5 fixo de 1,750 ms.
- Device Identification (FC43/14) opcional no Bus Slave Finder.
- Tema/layout Light/Dark da v2.8 mantido.

TRÁFEGO E FILTROS
-----------------
O separador Tráfego apresenta:

    Hora | Δt | Resp. | COM | Tipo | Slave | FC | Detalhes | CRC

Filtros disponíveis:

- Slave, através do cabeçalho "Slave";
- Tipo: Requests, Responses, Exceptions, CRC errors, Timeouts ou RAW;
- FC em hexadecimal;
- tempo de resposta acima de X ms;
- pesquisa livre em Details, Raw, Slave, FC, Tipo e COM/canal.

"Limpar filtros" repõe todos os filtros de Tráfego.

REALÇAR RESULTADOS
-----------------
A opção vem desligada por defeito. Quando ativa, os resultados recebem cor:

- CRC error;
- Timeout;
- Modbus Exception;
- resposta lenta (>= 500 ms);
- RAW/UNSYNC — bytes anteriores a um ponto onde o parser conseguiu recuperar sincronismo;
- RAW/UNPARSED — bytes restantes quando não foi possível encontrar um frame Modbus válido;
- transação normal concluída com sucesso — verde.

Numa transação normal concluída com sucesso, o REQUEST e a RESPONSE correspondente
ficam verdes. Requests pendentes continuam neutros. Respostas lentas mantêm a cor
de resposta lenta para que o resultado de diagnóstico não seja escondido.

Se debug_sim=1, "Simulação" gera sempre uma demonstração com resposta normal,
resposta lenta, Exception, CRC error, Timeout e RAW. "Realçar resultados" altera
apenas as cores dessas mesmas linhas, permitindo comparar diretamente a tabela
com o destaque desligado e ligado.


CÓDIGO DE CORES
---------------
Com "Realçar resultados" ativo:

- Verde — transação normal concluída com sucesso;
- Amarelo — resposta lenta (>= 500 ms);
- Vermelho — CRC Error ou Modbus Exception;
- Laranja — Timeout;
- Roxo — RAW/UNSYNC ou RAW/UNPARSED.

O Frame Inspector apresenta sempre a classificação no campo "Resultado", por
exemplo "Resultado: ✓ Sucesso". Com o destaque desligado o texto fica neutro;
com o destaque ligado o próprio campo usa a cor correspondente. O nome das
cores por extenso fica documentado apenas em Ajuda / Ligações.

FRAME INSPECTOR
---------------
Ao selecionar um frame, o painel inferior apresenta:

- Slave;
- Tipo;
- Function Code + nome;
- PDU Address;
- endereço 1-based;
- Qty;
- ByteCount;
- tempo de resposta;
- Resultado;
- CRC recebido;
- CRC calculado;
- dados / registos / bits / Exception — nas respostas de leitura emparelhadas,
  com o PDU Address de cada valor (por exemplo "100=42, 101=43");
- Raw Hex.

O painel pode ser "Recolher" / "Expandir" para libertar espaço para Tráfego.

MENU DE CONTEXTO
----------------
Botão direito numa frame:

- Copiar Raw Hex;
- Copiar frame descodificado;
- Filtrar por este Slave;
- Filtrar por este FC;
- Mostrar apenas esta transação;
- Limpar filtro de transação.

BUS HEALTH
----------
O separador Bus Health inclui:

- Requests e Responses;
- Request rate;
- Slaves ativos;
- bytes observados;
- utilização aproximada do bus;
- response time médio, mínimo, máximo e P95;
- Slave mais lento;
- percentagem de bytes não validados;
- timeout rate;
- Exceptions por Slave.

A percentagem de bytes não validados é calculada sobre os bytes observados que
pertencem a frames com CRC inválido ou a blocos RAW. É um indicador de captura
não validada, não uma prova isolada de ruído/EMI. Parâmetros série errados, uma
captura incompleta ou funções não suportadas pelo parser também podem gerar RAW.

A utilização do barramento é uma estimativa baseada nos bytes observados e nos
parâmetros série configurados. Não substitui um osciloscópio/analisador lógico.

O Bus Health adapta automaticamente a disposição das métricas à altura disponível. Com menos espaço vertical, as métricas reorganizam-se em duas colunas dentro de cada retângulo; quando volta a existir espaço, regressam ao formato vertical normal. Assim nenhuma linha fica por cima da borda inferior.


INDICADOR BUS
-------------
"BUS ● RX" pulsa brevemente quando o Sniffer recebe tráfego.
Em repouso mostra "BUS ○".

EXPORTAR CSV
------------
"Exportar CSV" grava os frames atualmente retidos pela interface, incluindo:

    Time, Delta ms, Response ms, Channel, Type, Slave, FC, Details, CRC,
    Raw, PDU Address, 1-based Address, Qty, Byte Count, Timed out, Anomaly

A interface mantém no máximo 20 000 frames para preservar desempenho.
O log TXT de uma captura real continua a ser o registo completo em disco.

PARSER / RESSINCRONIZAÇÃO
-------------------------
Quando perde sincronismo, o parser procura no restante burst o próximo frame
Modbus com estrutura reconhecida e CRC válido. A pesquisa percorre todo o burst,
mas deixa de testar por força bruta centenas de comprimentos em cada posição.
Assim recupera frames válidos após ruído longo sem bloquear a receção durante
vários segundos.

Se os bytes imediatamente anteriores ao ponto recuperado tiverem exatamente a
estrutura de um frame Modbus conhecido mas CRC inválido, são classificados como
CRC ERROR. Ruído sem uma estrutura de frame reconhecível continua como RAW.

Durante a ressincronização não são aceites frames apenas por coincidência de CRC.
Isto reduz fortemente falsos frames ocasionais em sequências de ruído aleatório.

FRAME GAP AUTO
--------------
Em modo Auto, o Sniffer calcula t3.5 a partir de 3,5 tempos de carácter até
19200 bit/s, inclusive. Acima de 19200 bit/s utiliza o valor fixo recomendado
de 1,750 ms. O modo Manual não é alterado.

Os adaptadores USB entregam os bytes em blocos e podem partir um frame em dois.
Quando um burst termina com o início de um frame ainda incompleto, o Sniffer
espera até 40 ms pelo resto antes de o processar.

PEDIDOS BROADCAST E ESCRITAS SIMPLES
------------------------------------
Pedidos para o Slave 0 (broadcast) não têm resposta: não ficam pendentes e não
contam como timeout.

Em FC05, FC06, FC08 e FC22 o pedido e a resposta têm o mesmo formato. O Sniffer
trata como RESPONSE a trama que corresponde a um pedido pendente do mesmo Slave
e FC; caso contrário é um REQUEST.

MASTER
------
Atenção: o Master transmite no barramento. Só deve ser ligado quando não existe
outro master ativo. Ao ligar, escuta o barramento durante 1 s e não transmite
se detetar tráfego. Enquanto está ligado, o Sniffer e o Bus Slave Finder ficam
bloqueados.

1. Escolher a porta COM, baud rate, parity, stop bits, timeout de resposta e
   atraso entre pedidos.
2. Confirmar que não existe outro master e carregar em "Ligar".
3. Em cada janela definir Slave, FC, endereço, quantidade e scan rate e
   carregar em "Aplicar". "Nova janela" acrescenta outra (máx. 32).

Todas as janelas usam a mesma porta, à vez. As escritas e "Ler 1x" passam à
frente das leituras cíclicas.

Duplo clique num valor (janelas FC01/FC03) abre a escrita; duplo clique num
nome permite dar um nome ao endereço. Vários valores separados por ";" são
escritos em endereços seguidos com FC15/FC16.

O "Formato" da janela é o formato por defeito. Clique direito num ou mais
endereços (arrastar com o rato, ou Ctrl/Shift, para selecionar vários):
- Formato: só desses endereços. 32 bits exigem 2 registos seguidos e 64 bits 4
  (ou um múltiplo, aplicado em grupos).
- Repor formato da janela.
- Escala…: converte o valor bruto em unidades (Bruto mín./máx. → Eng.
  mín./máx., casas decimais e unidade). Escreve-se em unidades. "Remover
  escala" volta ao valor bruto.
- Copiar (também Ctrl+C): endereços, nomes e valores para colar no Excel.
- Base de endereços: 0 = PDU Address; 1 = numeração a partir de 1, como em
  muitos manuais.

"Aplicar" fica azul enquanto houver campos alterados por aplicar. Quando uma
leitura falha, os valores ficam a cinzento até voltar a haver uma leitura boa.

No cabeçalho de cada janela: "Renomear" dá-lhe um nome (também com duplo
clique no nome), "Destacar" abre-a fora do separador ("Ancorar" devolve-a)
e "✕" fecha-a.

Menu "Workspace": "Guardar workspace…" grava tudo com um nome; "Abrir
workspace" e "Apagar workspace" mostram a lista dos workspaces guardados.
Ficam em %APPDATA%\MBToolkit\Workspaces\Master, junto das preferências.
O último workspace reabre ao arrancar (sem ligar). Com alterações por guardar
aparece "(alterado)" e, ao fechar o programa, a pergunta "Guardar alterações?".
Janelas sem workspace fecham sem perguntar.

"Abrir no Master": clique direito num pedido de leitura (ou na resposta) no
Tráfego do Sniffer, ou clique direito / duplo clique num Slave encontrado pelo
Bus Slave Finder. Cria a janela com o mesmo Slave, função, endereço e
quantidade e copia os parâmetros série para o Master.

Se a porta COM falhar durante a ligação (adaptador USB desligado), o Master
tenta reabri-la a cada 2 s e retoma as leituras sozinho. "Desligar" para.

BUS SLAVE FINDER / DEVICE IDENTIFICATION
----------------------------------------
O Bus Slave Finder localiza Slaves através de FC03 e, opcionalmente,
FC04 fallback.

"Tentativas" (1 a 3) repete cada pedido sem resposta antes de passar ao Slave
seguinte. O timeout mínimo vem a 100 ms por defeito.

Antes de transmitir, a pesquisa escuta o barramento durante 1 s. Se receber
qualquer byte, não transmite e avisa que pode existir outro master ativo.

A opção "Device Identification (FC43/14)" vem desligada por defeito. Quando
ativada, é enviada apenas depois de um Slave já ter sido encontrado. O Finder
tenta ler Basic Device Identification e apresenta, quando disponíveis:

    VendorName | ProductCode | MajorMinorRevision

Se FC43/14 não for suportado, devolver uma Modbus Exception ou não responder a
essa função não invalida o Slave que já tinha sido encontrado.

MODO CLARO / ESCURO
-----------------
O seletor global fica no canto superior direito.

Os modos claro e escuro usam exatamente a mesma construção da interface; mudar o seletor
altera apenas cores. A escolha fica guardada automaticamente.

PREFERÊNCIAS GUARDADAS
----------------------
Ficheiro único:

    %APPDATA%\MBToolkit\settings.json

São guardados:

- modo claro/escuro;
- último separador principal;
- modo físico;
- Baud, Data bits, Parity e Stop bits;
- Frame gap Auto/Manual e Gap manual;
- Pending timeout;
- deslocamento automático;
- Separar transações;
- Realçar resultados;
- opções do Bus Slave Finder, incluindo Tentativas, FC04 fallback e Device Identification.

Não são guardados:

- COM A / COM B / COM do Bus Slave Finder;
- confirmação de segurança do Bus Slave Finder;
- tamanho/posição da janela;
- tráfego, estatísticas ou resultados.

EXECUTAR
--------
Depois de extrair o ZIP:

    MBToolkit.bat

O BAT verifica/instala automaticamente o pyserial.

BUILD DO EXE
------------
Executar:

    MBToolkit v3.4\build_exe.bat

Antes do build, os testes de regressão são executados automaticamente. Se algum teste falhar, o build é cancelado.

O resultado é criado diretamente na raiz:

    MBToolkit.exe

TESTES DE REGRESSÃO
-------------------
Podem ser executados manualmente através de:

    MBToolkit v3.4\run_tests.bat

A suite verifica CRC, parser/ressincronização, Function Codes suportados, pairing, broadcast, escritas FC05/FC06, frames partidos, timeouts, frame gap Auto, Bus Slave Finder (tentativas e barramento livre), Device Identification FC43/14 e traduções.

LOGS
----
Capturas reais só criam um ficheiro quando existe tráfego.

Pasta:

    MBToolkit Logs\

fica ao lado de MBToolkit.bat / MBToolkit.exe.

REQUISITOS
----------
Windows 10/11 x64.
Python 3.10+ quando executado através do BAT/Python.

BARRAS DE DESLOCAMENTO
----------
As barras de deslocamento usam um desenho minimalista de 6 px, sem botões de seta. A pista
tem a mesma cor do fundo do conteúdo e fica visualmente invisível; apenas o
cursor móvel fica aparente.

A roda do rato desloca as tabelas, o Raw Hex / Log, a Ajuda e as barras de
deslocamento. Fora destas áreas não faz nada e nunca muda de separador.
