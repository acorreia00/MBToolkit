# MBSniffer

[Português](README.md) | [English](README.en.md)

**MBSniffer** é uma aplicação para Windows destinada ao diagnóstico de comunicações **Modbus RTU** sobre **RS485** e **RS232**. Permite observar e analisar tráfego de forma passiva e inclui uma ferramenta ativa para localizar dispositivos Modbus no barramento.

## Funcionalidades

- captura passiva Modbus RTU em RS485 2-wire e RS232;
- identificação de pedidos, respostas, exceções, erros de CRC e dados RAW;
- Inspetor de Frame com endereços, quantidades, dados e CRC;
- emparelhamento pedido/resposta e medição do tempo de resposta;
- Bus Health com estatísticas, tempos de resposta, timeouts e percentagem de bytes não validados;
- filtros de tráfego, pesquisa, realce de anomalias e exportação para CSV;
- registo completo das capturas reais em TXT;
- **Bus Slave Finder** para pesquisa ativa de Slave IDs, com aviso de segurança;
- modos claro e escuro com preferências persistentes.

> **Atenção:** o Sniffer é passivo, mas o **Bus Slave Finder transmite pedidos Modbus RTU**. Não deve ser utilizado num barramento que já tenha outro master ativo.

## Executar

Requer **Windows 10/11 x64**. Depois de extrair o pacote, executar:

```text
MBSniffer.bat
```

O ficheiro de arranque verifica Python e instala `pyserial` quando necessário. Para criar o executável autónomo, utilizar `MBSniffer v2.9\build_exe.bat`.

As preferências são guardadas em `%APPDATA%\MBSniffer\settings.json`. As portas COM não são persistidas.
