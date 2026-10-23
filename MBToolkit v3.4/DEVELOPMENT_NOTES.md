# MBToolkit — Development Notes

## Versão atual

**3.4**

Este ficheiro é a passagem de testemunho para quem desenvolve: contém **apenas
as regras e decisões em vigor**. O histórico completo, com o detalhe e o porquê
de cada decisão versão a versão, está em `CHANGELOG.md` (na mesma pasta).

- `README.txt` é para o utilizador final e deve continuar curto.
- `README.md` / `README.en.md` são a página do repositório.
- `MBToolkit_vX.Y_Technical_Code_Documentation.pdf` (raiz do repositório) explica
  o código todo da versão mais recente.
- O ZIP de entrega leva só os ficheiros da aplicação, a documentação e
  `tools/`; nada de git/GitHub (secção 2).

---

## 0. Nome do produto

- Desde a v3.3 o produto chama-se **MBToolkit** (`APP_NAME`). Até à v3.2
  chamava-se MBSniffer (`LEGACY_APP_NAME`); o histórico no `CHANGELOG.md` usa o
  nome antigo e não é alterado.
- O separador "Sniffer" mantém o nome (é a função de captura passiva).
- Preferências em `%APPDATA%\MBToolkit`. Se a pasta ainda não existir,
  `get_settings_file()` copia uma vez `%APPDATA%\MBSniffer` (settings.json e
  Workspaces) e não apaga a pasta antiga.
- Workspaces com `format = "MBSniffer Master workspace"` continuam a abrir
  (`MASTER_WORKSPACE_FORMATS`).
- Logs novos em `MBToolkit Logs`; os antigos ficam em `MBSniffer Logs`.
- Ícone: `MBToolkit.ico`, desenhado por `tools/make_icon.py` (formas
  supersampled, tamanhos 16–256 px; até 32 px só o símbolo, sem texto). Para o
  refazer: `python -B tools/make_icon.py --ico "MBToolkit vX.Y/MBToolkit.ico"
  --png tools/MBToolkit_icon_1024.png`.

## 1. Regras de release

- Usar a última versão (pasta `MBToolkit vX.Y` mais recente / último ZIP) como
  fonte de verdade.
- Não remover funcionalidades existentes ao implementar um pedido novo.
- **Não mudar a versão** (`APP_VERSION` em `mb_config.py`) sem pedido explícito
  do utilizador. Correções sem pedido de versão ficam registadas como
  "versão mantém-se X.Y".
- Ao mudar de versão, atualizar: `APP_VERSION`, cabeçalho de `MBToolkit.py`,
  título de `build_exe.bat`, `APPDIR` e título de `MBToolkit.bat`, caminhos em
  `README.md` / `README.en.md`, `README.txt` (regenerado) e o nome da pasta
  (`git mv "MBToolkit vA.B" "MBToolkit vX.Y"`).
- Correr os testes (`run_tests.bat` ou `python -m unittest discover -s tests`)
  antes de entregar. O `build_exe.bat` cancela o build se algum falhar.
- Validar os ficheiros guardados e o conteúdo do ZIP final, não só o código
  editado em memória.
- Ordem de uma release: código → testes → capturas da interface → PDF → ZIP.
- **Nunca fazer `git commit` nem `git push`**: os commits são sempre feitos pelo
  utilizador. A entrega termina no ZIP, criado a partir da pasta de trabalho
  como está (`git mv`/`git rm` para manter o repositório coerente são
  aceitáveis).
- O repositório git e o GitHub são geridos só pelo utilizador; a release não
  trata de nada relacionado com git além de manter a pasta coerente.
- Cada alteração acrescenta uma secção no fim de `CHANGELOG.md`. Se a alteração
  muda uma regra em vigor, atualizar também este ficheiro.
- **Em cada release, gerar de novo o PDF técnico** (secção 3).

## 2. Pacote de entrega

Nome: `MBToolkit_vX.Y_Package.zip`, guardado ao lado da pasta do projeto (pasta
`Modbus Sniffer`). Leva os ficheiros da aplicação, a documentação e as
ferramentas; **nada relacionado com git ou GitHub** (pedido do utilizador, v3.2):

```
MBToolkit_vX.Y_Package.zip
├── tools/                (gerador do PDF, construtor do pacote, fontes, capturas)
├── MBToolkit_vX.Y_Technical_Code_Documentation.pdf
├── README.txt            (utilizador final, curto, regenerado em cada release)
├── README.md             (PT, seletor de idioma no topo, sem histórico de versões)
├── README.en.md          (EN, igual ao anterior)
├── MBToolkit.bat         (lança "MBToolkit vX.Y\MBToolkit.py")
└── MBToolkit vX.Y/       (nome exato, sem sufixos)
    ├── MBToolkit.py
    ├── mb_config.py
    ├── mb_protocol.py
    ├── mb_capture.py
    ├── mb_diagnostics.py
    ├── mb_view.py
    ├── mb_slave_finder.py
    ├── mb_master.py
    ├── mb_master_ui.py
    ├── mb_i18n.py
    ├── mb_theme.py
    ├── mb_widgets.py
    ├── mb_gui.py
    ├── MBToolkit.ico
    ├── build_exe.bat
    ├── run_tests.bat
    ├── tests/test_regression.py
    ├── tests/test_master.py
    ├── DEVELOPMENT_NOTES.md
    └── CHANGELOG.md
```

- Criado com `python -B tools/build_package.py --version X.Y`, a partir da
  pasta de trabalho tal como está.
- Nunca entram: `.git`, `__pycache__`, `*.pyc`, `build/`, `*.spec`,
  `MBToolkit.exe`, `MBToolkit Logs/`.

## 3. PDF técnico

- Ficheiro: `MBToolkit_vX.Y_Technical_Code_Documentation.pdf` na raiz do
  repositório. Há sempre só um, o da versão mais recente (o anterior é removido
  com `git mv`/`git rm` na mesma release).
- Gerado com `tools/build_technical_pdf.py` (mesmo formato, esquema de cores e
  estrutura do PDF original da v3.0). O texto escrito à mão está em
  `tools/technical_doc_content.py`; inventário de funções, constantes, hashes,
  testes e anexo com o código são extraídos automaticamente do código.
- Atualizar sempre em `tools/technical_doc_content.py`: `VERSION_HISTORY`,
  `VERSION_CHANGES` e qualquer capítulo, descrição de função, classe de testes
  ou diagrama cujo comportamento mudou.
- Como o PDF vai dentro do ZIP, a capa não pode citar o hash do ZIP: cita o
  "Source snapshot SHA-256", um hash de todos os ficheiros documentados
  (README, `MBToolkit.bat` e a pasta `MBToolkit vX.Y`). Confirmar com
  `python -B tools/build_package.py --version X.Y --snapshot-hash`.
- Requisitos: Python com `pymupdf`, `pygments` e `pillow`, e Google Chrome ou
  Microsoft Edge (usado em modo headless para converter HTML em PDF). As fontes
  DejaVu estão em `tools/fonts`.
- Comandos (na raiz do repositório; `-B` evita criar `__pycache__`):

  ```
  python -B tools/capture_ui_screenshots.py --app-dir "MBToolkit vX.Y" --out tools/screenshots
  python -B tools/build_technical_pdf.py --source-dir . --version X.Y --screenshots tools/screenshots --output MBToolkit_vX.Y_Technical_Code_Documentation.pdf
  ```

- O gerador corre os testes do código documentado; se algum falhar, o PDF diz
  isso a vermelho e o comando termina com código 2. Nesse caso não entregar.

## 4. Produto e modos físicos

Aplicação Windows (Tk) para diagnóstico Modbus RTU.

- **Sniffer**: passivo e só de leitura. Nunca chama `Serial.write()`. RTS/DTR
  ficam a False e sem controlo de fluxo.
- **Bus Slave Finder**: ativo e deliberadamente separado; atua como master
  temporário e só envia pedidos de leitura.
- **Master**: ativo; lê em ciclo e escreve valores como master Modbus RTU
  (secção 13). Os três (Sniffer, Finder e Master) excluem-se mutuamente.
- Modos: RS485 2-wire (uma COM, canal `BUS`); RS232 single RX (uma COM, `A→B`);
  RS232 dual RX (duas COM, `A→B` e `B→A`). Em RS232 o TX do sniffer fica
  desligado; RS232 não é TTL/UART.

## 5. Arquitetura

`SnifferApp(MasterMixin, SlaveMixin, SlaveFinderMixin, CaptureMixin, ViewMixin, tk.Tk)` em
`mb_gui.py`. `MasterMixin` e `SlaveMixin` herdam `TableUiMixin` (`mb_table_ui.py`).

| Módulo | Responsabilidade |
|---|---|
| `MBToolkit.py` | Arranque, AppUserModelID, cria `SnifferApp`. |
| `mb_config.py` | Versão, constantes, exceções Modbus, `settings.json`, pastas. |
| `mb_protocol.py` | CRC, parser/ressincronização, `SessionMetrics`, simulação. Sem Tk. |
| `mb_capture.py` | Portas COM, threads de leitura, simulação, `process_queue()`, fecho. |
| `mb_view.py` | Tabela, Raw Hex, filtros, separadores, estatísticas, logs, CSV. |
| `mb_diagnostics.py` | Nomes de funções, CRC no Inspector, payload, classificação de resultados. |
| `mb_slave_finder.py` | Sondas, tempos, TX/RX ativos e interface do Finder. |
| `mb_master.py` | Master: tramas, formatos de dados e `MasterEngine` (escalonador). Sem widgets. |
| `mb_master_ui.py` | Separador Master: janelas, escrita, workspace (`MasterMixin`). |
| `mb_slave.py` | Slave: `SlaveStore`, `handle_request()`, `SlaveEngine`, falhas. Sem widgets. |
| `mb_slave_ui.py` | Separador Slave: tabelas simuladas, valores, falhas, workspace (`SlaveMixin`). |
| `mb_table_ui.py` | Código comum às grelhas do Master e do Slave (`TableUiMixin`) e workspaces. |
| `mb_i18n.py` | Traduções PT→EN, Ajuda em inglês, textos com valores. |
| `mb_theme.py` | Tema `clam` fixo; Light/Dark só muda cores. |
| `mb_widgets.py` | `RefreshButton`, `ToggleSwitch`. |

Regras:

- As threads de série nunca tocam no Tk; tudo passa por `event_queue`.
  `process_queue()` trata no máximo 200 eventos por ciclo (10 ms com fila
  cheia, 50 ms em repouso) e nunca pode morrer com uma exceção.
- Não juntar tudo num ficheiro; só criar módulo novo com responsabilidade clara.
- Fecho: cancelar I/O antes do `join`, `join` sempre com timeout finito.

## 6. Comportamento Modbus

- CRC16 Modbus por tabela (`_CRC16_TABLE`).
- Formatos reconhecidos: FC01–04, 05, 06, 07, 08, 15, 16, 22, 23 e exceções.
  FC desconhecidos só são aceites (UNKNOWN/OK) quando ocupam o burst inteiro com
  CRC válido; nunca durante a ressincronização.
- Ressincronização em todo o burst (sem limite de 32 bytes), só com formatos
  conhecidos.
- RAW/UNSYNC (bytes antes de uma trama válida recuperada) ≠ RAW/UNPARSED
  (resto que não foi possível interpretar). RAW nunca inventa Slave/FC.
- Frame gap Auto: 3,5 caracteres até 19200 bit/s; 1,750 ms fixo acima.
- Se o burst acabar no início de uma trama conhecida incompleta, o reader
  espera até `SNIFFER_SPLIT_FRAME_HOLD_MS` (40 ms) antes de o fechar.
- Cada trama tem a hora do bloco de bytes (leitura) onde começa
  (`parse_burst(..., chunk_times)`).
- Emparelhamento FIFO por (Slave, FC base), porque o RTU não tem ID de
  transação. Pedidos pendentes expiram após o Pending timeout (1–300 s, por
  defeito 10 s). O timeout marca o REQUEST original; não se inventam tramas.
- Broadcast (Slave 0): nunca fica pendente nem conta como timeout.
- `REQ/RESP` (FC05/06/08/22): `SessionMetrics` decide REQUEST/RESPONSE pelo
  pedido pendente, bytes iguais (05/06/22) e canal oposto (dual RX).
- Texto de exceção curto: `Exception 0x02 — Illegal Data Address`.
- Os Detalhes da RESPONSE mostram só informação da própria resposta (ByteCount,
  Registos, Bits); o endereço/Qty fica no REQUEST. O Frame Inspector mostra o
  PDU Address de cada valor de leitura emparelhado.
- Terminologia: `PDU Address` = endereço zero-based no pedido; `1-based` =
  PDU Address + 1; `Qty` = quantidade pedida.

## 7. Interface

- Tema `clam` escolhido uma vez; Light/Dark só muda cores, nunca a geometria.
  Mudar de tema não mexe em portas, sessão nem captura.
- Mudar de idioma só muda texto; a geometria é congelada com as legendas PT.
  Larguras das colunas mantêm-se na mudança de idioma.
- Português (PT-PT) é a língua canónica. **Nenhuma ramificação
  `if self.current_language == "English"` no código**: textos fixos usam
  `self.tr("texto PT")`, textos com valores usam
  `self.trf("modelo PT {valor}", valor=...)`, e o par PT→EN vai para
  `mb_i18n.PT_TO_EN`. Há um teste que garante isto.
- Ajuda em PT (`mb_gui.py`) e EN (`mb_i18n.english_help_blocks`) têm de dizer o
  mesmo. Qualquer referência à Simulação fica dentro de `if debug_sim == 1`.
- Tabela Tráfego: colunas compactas e centradas, exceto `Detalhes` (à esquerda,
  ocupa o resto, quebra em linhas de continuação). Sem scroll horizontal.
  Separadores de transação só entre pares completos visíveis, nunca no fim.
- Histórico visível limitado: `MAX_UI_FRAMES = 20000` (poda em blocos de 2000),
  `MAX_RAW_TEXT_LINES = 20000`. Poda com deque; nunca percorrer a Treeview toda.
- Tráfego novo é inserido incrementalmente. Reconstruir a tabela inteira só em
  mudanças de filtro/ordem, poda, mudança de largura de coluna ou filtro
  `Timeouts`. Timeouts e sucessos mudam só a tag das linhas existentes.
- Filtros e ordenação são só de apresentação: não alteram estatísticas,
  emparelhamento, log em disco nem captura.
- `Realçar resultados` (desligado por defeito) só muda cores. Prioridade:
  CRC > Timeout > Exception > RAW > Lenta (≥ 500 ms). Sucesso = verde.
- Roda do rato só faz scroll em Treeview/Text/scrollbars; nunca muda de separador.
- `self.busy` impede captura, simulação e Finder em simultâneo.

## 8. Logs, CSV e preferências

- Logs só de capturas reais e só quando chega tráfego, em
  `<pasta da aplicação>/MBToolkit Logs/MBToolkit_AAAAMMDD_HHMMSS.txt` (hora de
  início). Pasta da aplicação = pasta do `MBToolkit.bat` (modo BAT) ou do
  `MBToolkit.exe`. Simulação e Reiniciar COM nunca criam log.
- O log em disco é sempre completo; filtros, ordem e poda da interface não o
  afetam. Separadores e quebras de linha são só da interface.
- CSV exporta o histórico retido (até 20 000 frames), em UTF-8 com BOM.
- Preferências em `%APPDATA%\MBToolkit\settings.json` (escrita atómica, tudo
  validado ao ler, falhas nunca impedem o arranque). Não se guardam portas COM,
  geometria da janela, resultados nem a confirmação de segurança do Finder.

## 9. COM

- Estado: `Aberta` (handle do MBToolkit), `Detetada` (o Windows lista-a, pode
  estar ocupada), `Não detetada`, `Não selecionada`, `COM B - Não Utilizada`.
  A verificação nunca abre a porta; atualiza a cada ~1 s.
- `Reiniciar COM` fecha e reabre o handle do MBToolkit (não reinicia o driver).
  Durante a captura continua a mesma sessão/log e escreve `# COM restart:`.
  Eventos de leitores antigos são ignorados pela geração (`reader_generation`).
- Dois botões ↻ no Sniffer e um no Finder chamam o mesmo `refresh_ports()`.

## 10. Bus Slave Finder

- Exige a confirmação "não existe outro master ativo" e, antes da primeira
  transmissão, escuta o barramento 1 s (`DISCOVERY_IDLE_CHECK_SECONDS`):
  qualquer byte aborta sem transmitir.
- Sonda FC03, Address 0, Qty 1; FC04 fallback opcional. Resposta normal ou
  Exception com CRC válido = slave encontrado. Ecos e tráfego alheio ignorados.
- `Tentativas` (1–3, por defeito 1) por FC sem resposta.
- Timeout adaptado ao baud, com mínimo configurável (10–2000 ms, por defeito
  100 ms). Settings da v3.0 com 40 ms migram para 100 ms.
- Escrita: `write_timeout` 1,5 s, uma repetição após timeout de escrita, sem
  `ser.flush()`. Falhas de porta/driver nunca são tratadas como "sem resposta".
- Device Identification (FC43/14, Basic) opcional, só para slaves encontrados;
  segue `More Follows` até 8 páginas; falha não anula a descoberta.
- Não depende de `debug_sim` e não cria logs.

## 11. Simulação

- Só existe com `debug_sim = 1` (`MBToolkit.py`); com 0 o botão nem é criado.
- Gera sempre o mesmo cenário de diagnóstico no canal `SIM`: resposta normal,
  resposta lenta, Exception, CRC errado, timeout e um bloco RAW/UNPARSED.
- Nunca escreve logs.

## 12. Distribuição

- `MBToolkit.bat`: encontra Python 3 (ou instala 3.13 via WinGet), verifica
  tkinter, instala `pyserial` se faltar e arranca com `pythonw.exe`.
- `build_exe.bat`: corre os testes, depois PyInstaller one-file/windowed com o
  ícone (`--icon` e `--add-data`). O `MBToolkit.exe` fica na raiz da extração;
  ficheiros de trabalho em `MBToolkit vX.Y\build`.
- Manter o AppUserModelID e o carregamento explícito do ícone na janela Tk.

## 13. Master (poll)

- Uma ligação série serve todas as janelas, um pedido de cada vez
  (`MasterEngine` numa thread). Prioridade: escritas → "Ler 1x" → janela com o
  próximo prazo mais antigo. Uma janela volta a estar pronta `scan_ms` depois de
  o pedido anterior começar (0 = contínuo).
- Entre pedidos fica sempre o "Atraso entre pedidos", nunca menos que t3.5. O
  timeout e o tempo de resposta contam a partir do fim da transmissão.
- Ligar exige a confirmação de segurança e escuta o barramento
  `DISCOVERY_IDLE_CHECK_SECONDS`; qualquer byte aborta sem transmitir. Ligado,
  põe `busy = True` e bloqueia Sniffer, Simulação e Finder.
- Reutiliza `write_discovery_request()`, `bus_activity_detected()` e
  `open_discovery_serial_port()` do Finder (mesmas regras de escrita robusta).
- Janelas: Slave 1–247, FC01–FC04, endereço 0–65535, quantidade até 2000 bits /
  125 registos, scan 0–3 600 000 ms, base 0/1, máx. 32 janelas. As alterações
  só valem com "Aplicar" (fica com o estilo primário, azul, enquanto os campos
  diferem do que está aplicado); mudar a zona de memória repõe os contadores.
- A tabela tem altura = quantidade, entre 3 e 15 linhas, e seleção múltipla:
  Ctrl/Shift+clique e arrastar com o rato (`_table_drag_*`; o ttk não tem
  seleção por arrasto). Arrastar para fora faz scroll; Ctrl+arrastar junta à
  seleção anterior.
- Aspeto das tabelas: linhas alternadas (tag `odd`, `TABLE_STRIPE_LIGHT` /
  `TABLE_STRIPE_DARK`) e moldura de 1 px (`tk.Frame` com `highlightthickness=1`
  na cor `border` da paleta), recoloridas em `_table_configure_tree_tags()`.
- Quando a última leitura falhou (ou ao desligar), as linhas ficam com a tag
  `stale` (cor `disabled` da paleta) até chegar uma leitura correta.
- Formatos (chaves em `mb_master.REGISTER_FORMATS`): `int16`, `uint16`, `hex16`,
  `bin16`; `int32`/`uint32`/`float32` × `ABCD`, `CDAB`, `BADC`, `DCBA`;
  `int64`/`uint64`/`float64` × `ABCDEFGH`, `GHEFCDAB`, `BADCFEHG`, `HGFEDCBA`
  (letras = bytes no fio: registo n = A B, n+1 = C D, …). Valores de 2 ou 4
  registos aparecem na linha do primeiro.
- Formato por endereço: `MasterWindow.formats` (PDU Address do início do valor
  → formato); o resto usa `MasterWindow.fmt`. `register_groups()` divide a
  janela em valores; um valor por defeito cortado por um formato próprio, ou
  que passa do fim, mostra "—". `apply_format_to_rows()` aplica a seleção:
  formatos de 2/4 registos exigem registos seguidos em múltiplos do tamanho e
  apagam os formatos próprios que se sobreponham.
- Menu de clique direito (por janela): Formato ▸ (16 bits, 32 bits ▸, 64 bits
  ▸), Repor formato da janela, Copiar (Ctrl+C, texto separado por tabs) e Base
  de endereços ▸ 0/1. A Base deixou de estar na linha de configuração; mudá-la
  é imediato (não precisa de "Aplicar").
- Escala por endereço: `MasterWindow.scales` (PDU Address do início do valor →
  `validate_scale()`: dois pontos bruto/engenharia, casas decimais 0–6 e
  unidade). `format_window_values(..., scales)` mostra o valor escalado; Hex e
  Binary ficam em bruto. Na escrita, o valor é escrito em unidades e
  `raw_text_for_scaled()` converte para bruto (arredondado nos inteiros).
- "Abrir no Master": `master_definition_from_record()` tira Slave/FC/endereço/
  quantidade de um REQUEST ou da resposta emparelhada (só FC01–FC04);
  `master_open_definition()` cria a janela, mostra o separador Master e copia
  porta/baud/parity/stop para a ligação só se o Master não estiver ligado.
  Entradas: menu de contexto do Tráfego (índice `TRAFFIC_MENU_OPEN_IN_MASTER`
  em `mb_view.py`) e clique direito / duplo clique nos resultados do Finder.
- Religar: o `MasterEngine` recebe `reopen` (abre a mesma porta com os mesmos
  parâmetros). Uma falha da porta durante a sessão fecha-a, envia
  `master_reconnecting` e tenta reabrir a cada
  `MASTER_RECONNECT_INTERVAL_SECONDS` (2 s) até conseguir
  (`master_reconnected`) ou até "Desligar". Não repete a verificação de
  barramento livre.
- Escrita: só a partir de janelas FC01 (FC05/FC15) e FC03 (FC06/FC16), com o
  formato do valor clicado; formatos de 32/64 bits obrigam a FC16. Slave 0 = broadcast (não espera resposta). Uma
  escrita aceite pede logo "Ler 1x" da janela.
- Eco do adaptador RS485: ignorado nas leituras; em FC05/06 a resposta é um eco
  exato, por isso um eco do adaptador não se distingue da resposta do slave.
- Resultados chegam ao Tk como eventos `master_ready`, `master_result`,
  `master_stopped`; respostas de uma definição entretanto alterada são
  ignoradas.
- Cabeçalho de cada janela: nome (`MasterWindow.title`, vazio = "Janela N";
  duplo clique ou "Renomear" para mudar), resumo Slave/FC/endereço/quantidade e
  botões "Renomear", "Destacar"/"Ancorar" e "✕" (fechar). O fecho fica no
  cabeçalho para nunca depender da largura da janela (escala do Windows).
- A grelha calcula as colunas a partir da largura pedida pelas janelas (cresce
  com a escala do Windows), nunca abaixo de 600 px por coluna.
- Destacar: a janela é reconstruída num `Toplevel`; fechar esse Toplevel volta
  a ancorá-la. O estado vive em `MasterWindow`, não nos widgets.
- Widgets criados depois do arranque recebem a etiqueta do guarda da roda do
  rato (`_table_install_wheel_tags`): a roda percorre a grelha de janelas e
  nunca altera Comboboxes/Spinboxes.
- Workspaces: menu "Workspace" (Guardar workspace…, Abrir workspace ▸, Apagar
  workspace ▸, Abrir pasta dos workspaces). Cada workspace é um ficheiro
  `<nome>.mbsw` em `%APPDATA%\MBToolkit\Workspaces` (`get_workspaces_folder()`,
  ao lado do `settings.json`). Os nomes são validados como nomes de ficheiro do
  Windows. O menu é reconstruído sempre que se abre.
- Formato `.mbsw` (JSON, `format = "MBToolkit Master workspace"`, versão 1):
  ligação (incluindo a porta) e janelas com nome, formatos e nomes dos
  endereços. Entradas inválidas são ignoradas com aviso.
- Alterações ao workspace aberto (janelas, nomes, formatos, base, pausa,
  "Aplicar") marcam-no como "(alterado)" (`master_workspace_dirty`); abrir ou
  guardar limpa a marca. Fechar todas as janelas deixa de ter workspace aberto.
- `settings.json` guarda os parâmetros de ligação do Master (sem a porta) e
  `master.last_workspace`, reaberto ao arrancar (sem ligar ao barramento).
- Ao fechar o programa (`master_confirm_close()`, chamado no início de
  `on_close`): só com um workspace guardado e alterado pergunta
  Sim/Não/Cancelar; janelas sem workspace fecham sem perguntar.

## 14. Código comum às grelhas (`mb_table_ui.py`)

- O Master e o Slave partilham o mesmo aspeto e comportamento das janelas:
  cabeçalho (nome, resumo, Renomear / Destacar / ✕), tabela Endereço/Nome/Valor
  com moldura de 1 px, linhas alternadas, seleção por arrasto, Ctrl+C, menu de
  clique direito (Formato ▸, Repor, Escala…, Remover escala, Copiar, Base ▸),
  diálogo de escala, diálogo de texto, grelha que se reorganiza pela largura,
  guarda da roda do rato e menu Workspace.
- Tudo isso vive em `TableUiMixin` (métodos `_table_*`). Um "pane" é o dict de
  widgets de uma janela; uma "window" é o modelo (`MasterWindow` /
  `SlaveWindow`) com `address`, `qty`, `base`, `fmt`, `formats`, `scales`,
  `names` e `group_of_row()`. Melhorias às janelas fazem-se aqui, para servirem
  aos dois separadores.
- Funções de módulo: `parse_int_field`, `validate_workspace_name`,
  `workspace_path(name, folder)`, `list_workspaces(folder)`,
  `apply_format_to_rows`, `validated_names/formats/scales`.
  `mb_master_ui.py` reexporta as que os testes do Master usam.
- Uma linha escrita pelo master (Slave) tem só a tag `written`: a tag `odd`
  ganharia à cor de destaque.

## 15. Slave (simulador)

- Cada janela é uma tabela de um Slave simulado: Slave ID 1–247, tabela
  (`coils`, `discrete`, `holding`, `input`), endereço e quantidade
  (1–`SLAVE_MAX_QTY` = 2000), base 0/1, formato; máx. 32 janelas. Só existem
  os endereços definidos pelas janelas (`SlaveStore.set_areas()`, chamado ao
  criar, aplicar ou fechar janelas). Janelas sobre os mesmos endereços partilham
  os valores.
- `SlaveStore` (com lock): valores por (Slave ID, tabela) e endereço, a
  começar em 0; áreas definidas; falhas ativas por Slave ID.
- `handle_request(store, frame)` é uma função pura do store e da trama:
  Slave ID não simulado → `ignored`; função não suportada → Exception 01;
  endereços fora das áreas → 02; comprimento, quantidade (limites Modbus), valor
  FC05 ≠ FF00/0000 ou byte count errado → 03. Escritas FC05/06 respondem com
  eco, FC15/16 com endereço+quantidade. Broadcast (Slave 0): escrita em todos os
  Slave IDs que cobrem os endereços, sem resposta; leituras broadcast ignoradas.
- `SlaveEngine` (thread): lê a porta; `request_length()` dá o tamanho de
  FC01–06 (8) e FC15/16 (9 + byte count), por isso responde logo que o pedido
  está completo e com CRC certo. Bytes que não formam pedido são largados um a
  um; após `SLAVE_RESYNC_SILENCE_MS` (40 ms) de silêncio o resto é resolvido e
  uma trama com CRC certo de função desconhecida recebe Exception 01. Antes de
  responder espera t3.5; depois espera o eco da própria resposta (adaptador
  RS485) e retira-o. Eventos: `slave_ready`, `slave_request`, `slave_stopped`,
  `slave_reconnecting`, `slave_reconnected` (religação igual ao Master).
- Falhas por Slave ID (`validate_fault()`): atraso 0–10000 ms, não responder,
  Exception (01, 02, 03, 04, 06), CRC errado, probabilidade 1–100 % sorteada a
  cada pedido. Quando a falha acontece: não responder > Exception > executar; o
  CRC errado e o atraso aplicam-se ao que for enviado. Só falhas ativas ficam
  guardadas; aparecem a vermelho no cabeçalho das janelas desse Slave ID.
- Valores: duplo clique altera localmente (bits alternam; registos com o
  formato/escala do valor; `slave_set_value()`), sem passar pelo barramento.
  Escritas do master destacam as linhas `SLAVE_HIGHLIGHT_SECONDS` (1,5 s); um
  temporizador de 250 ms retira o destaque.
- Contadores: na barra de ligação pedidos, respostas, exceções, broadcasts e
  pedidos para outros IDs; em cada janela, pedidos e exceções sobre os seus
  endereços e o último pedido.
- Ligar exige a confirmação de que nenhum equipamento usa os Slave IDs
  simulados (não há verificação de barramento livre: o Slave escuta tráfego de
  outros por natureza). `busy = True` bloqueia Sniffer, Simulação, Finder e
  Master; o Master também bloqueia o Slave. `_master/_slave_finish_session()`
  ignoram um evento de paragem tardio (já terminado).
- Workspace do Slave: menu próprio, ficheiros `.mbsw` em
  `%APPDATA%\MBToolkit\Workspaces\Slave` (`get_slave_workspaces_folder()`),
  `format = "MBToolkit Slave workspace"`, versão 1. Guarda só configuração
  (ligação, janelas, nomes, formatos, escalas, falhas dos Slave IDs em uso);
  abrir repõe os valores a 0. `settings.json` → secção `slave` (baud, parity,
  stop, `last_workspace`) e separador "Slave". `slave_confirm_close()` corre em
  `on_close` a seguir ao do Master.
- Testes: `tests/test_slave.py` (handler, falhas, Master↔Slave por uma ligação
  série em memória `BusEnd`, janelas e settings).
