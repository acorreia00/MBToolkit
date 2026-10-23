# MBSniffer

[Português](README.md) | [English](README.en.md)

**MBSniffer** é uma aplicação para Windows destinada ao diagnóstico de comunicações **Modbus RTU** sobre **RS485** e **RS232**. Permite observar e analisar tráfego de forma passiva, localizar dispositivos Modbus no barramento e ler/escrever valores como master Modbus RTU.

## Funcionalidades

- Captura passiva Modbus RTU em RS485 2-wire e RS232;
- Identificação de pedidos, respostas, exceções, erros de CRC e dados RAW;
- Inspetor de Frame com endereços, quantidades, dados e CRC;
- Respostas de leitura com o endereço de cada registo, coil ou entrada;
- Emparelhamento pedido/resposta e medição do tempo de resposta;
- Bus Health com estatísticas, tempos de resposta, timeouts e percentagem de bytes não validados;
- Filtros de tráfego, pesquisa, realce de anomalias e exportação para CSV;
- Registo completo das capturas reais em TXT;
- **Bus Slave Finder** para pesquisa ativa de Slave IDs, com tentativas configuráveis, Device Identification (FC43/14) opcional, aviso de segurança e verificação automática de barramento livre;
- **Master** com várias janelas (uma por Slave ou zona de memória): leitura cíclica FC01–FC04, escrita FC05/06/15/16, formatos de 16 e 32 bits (incluindo float, nas 4 ordens de bytes), contadores e erros por janela, janelas destacáveis e workspace guardado em ficheiro;
- Interface em **Português** e **English**, selecionável em tempo real;
- Modos claro e escuro com preferências persistentes.

> **Atenção:** o Sniffer é passivo, mas o **Bus Slave Finder e o Master transmitem pedidos Modbus RTU**. Não deve ser utilizado num barramento que já tenha outro master ativo.

## Executar

Requer **Windows 10/11 x64**. Depois de extrair o pacote, executar:

```text
MBSniffer.bat
```

O pacote inclui também o histórico git (`.git`), as ferramentas de documentação (`tools/`) e o documento técnico em PDF.

O ficheiro de arranque verifica Python e instala `pyserial` quando necessário. Para criar o executável autónomo, utilizar `MBSniffer v3.2\build_exe.bat`.

A aplicação guarda a linguagem, o modo claro/escuro e as restantes preferências em `%APPDATA%\MBSniffer\settings.json`. A porta COM escolhida não fica guardada: sempre que iniciar o programa, deve selecionar novamente a porta que pretende utilizar.
