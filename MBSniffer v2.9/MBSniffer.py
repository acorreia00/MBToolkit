#!/usr/bin/env python3
# MBSniffer v2.9
"""MBSniffer launcher."""

# Simulação:
#   0 = simulação inativa (o botão não aparece no GUI)
#   1 = simulação ativa  (o botão aparece no GUI)
#
# Mantido neste ficheiro para preservar o mesmo ponto de configuração usado
# antes da modularização.
debug_sim = 0

import mb_config

# Apply the launcher switch before importing GUI/capture modules, which read
# the value during import.
mb_config.debug_sim = debug_sim

from mb_config import set_windows_app_user_model_id
from mb_gui import SnifferApp


def main():
    set_windows_app_user_model_id()
    SnifferApp().mainloop()


if __name__ == "__main__":
    main()
