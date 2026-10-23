# MBToolkit

> Até à v3.2 chamava-se **MBSniffer**.

[Português](README.md) | [English](README.en.md)

**MBToolkit** é uma aplicação para Windows destinada ao diagnóstico de comunicações **Modbus RTU** sobre **RS485** e **RS232**. Permite observar e analisar tráfego de forma passiva, localizar dispositivos Modbus no barramento e ler/escrever valores como master Modbus RTU.

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
- **Master** com várias janelas (uma por Slave ou zona de memória): leitura cíclica FC01–FC04, escrita FC05/06/15/16, formatos de 16, 32 e 64 bits (incluindo float e double, nas 4 ordens de bytes) também por endereço, escala para unidades de engenharia, contadores e erros por janela, janelas com nome próprio e destacáveis, workspaces guardados num menu, "Abrir no Master" a partir do Sniffer e do Finder e religação automática da porta;
- **Slave** (simulador) com vários Slave IDs e tabelas (Coils, Discrete Inputs, Holding e Input Registers) que respondem a um master real em FC01–FC06/15/16, com exceções como num equipamento real, edição de valores, destaque das escritas do master e simulação de falhas por Slave ID (atraso, sem resposta, Exception, CRC errado, probabilidade);
- Interface em **Português** e **English**, selecionável em tempo real;
- Modos claro e escuro com preferências persistentes.

> **Atenção:** o Sniffer é passivo, mas o **Bus Slave Finder e o Master transmitem pedidos Modbus RTU**. Não deve ser utilizado num barramento que já tenha outro master ativo. O **Slave** responde no barramento: nenhum equipamento real pode usar os mesmos Slave IDs.

## Executar

Requer **Windows 10/11 x64**. Depois de extrair o pacote, executar:

```text
MBToolkit.bat
```

O pacote inclui também o histórico git (`.git`), as ferramentas de documentação (`tools/`) e o documento técnico em PDF.

O ficheiro de arranque verifica Python e instala `pyserial` quando necessário. Para criar o executável autónomo, utilizar `MBToolkit v3.4\build_exe.bat`.

A aplicação guarda a linguagem, o modo claro/escuro e as restantes preferências em `%APPDATA%\MBToolkit\settings.json`. A porta COM escolhida não fica guardada: sempre que iniciar o programa, deve selecionar novamente a porta que pretende utilizar.
