"""
main.pyw — Ponto de entrada do Dashboard de Telemetria do Assetto Corsa Competizione (ACC)
==========================================================================================
Fluxo de inicialização:
  1. ACCTelemetryProvider  — Abre a memória compartilhada do ACC (acpmf_physics/graphics/static)
  2. TelemetryEngine       — Thread a 60 Hz que chama get_state() e emite sinais Qt
  3. DashboardMainWindow   — Interface gráfica que reage aos sinais da Engine

NÃO É PRECISO CONFIGURAR NADA NO JOGO.
O Assetto Corsa Competizione publica a telemetria automaticamente em memória
compartilhada (acpmf_physics / acpmf_graphics / acpmf_static). Basta abrir
o jogo e entrar na pista — o dashboard conecta e reconecta sozinho se você
voltar para os boxes, menu ou reiniciar a sessão.
"""

import argparse
import os
import sys
import traceback
from PyQt5.QtWidgets import QApplication

from providers.acc import ACCTelemetryProvider
from providers.mock import MockTelemetryProvider
from core.engine import TelemetryEngine
from core.config import get_config
from ui.main_window import DashboardMainWindow


def _install_crash_guard():
    """Rede de segurança contra travamento no meio da sessão."""
    def hook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        print("[!] Erro não tratado (o dashboard continua rodando):")
        traceback.print_exception(exc_type, exc_value, exc_tb)

    sys.excepthook = hook


def _resolve_mock_mode(argv=None) -> bool:
    parser = argparse.ArgumentParser(
        prog="main.pyw", add_help=True,
        description="ApexView — dashboard de telemetria para Assetto Corsa Competizione (ACC)")
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument("--mock", dest="mock", action="store_true", default=None,
                       help="usa o simulador interno, sem o jogo aberto")
    grupo.add_argument("--no-mock", dest="mock", action="store_false",
                       help="força o provider real, ignorando o config.json")
    args, _desconhecidos = parser.parse_known_args(argv)

    if args.mock is not None:
        return args.mock
    env = os.environ.get("APEXVIEW_MOCK", "").strip().lower()
    if env:
        return env not in ("0", "false", "no", "nao", "não", "")
    return bool(get_config().get("mock_mode"))


def main():
    _install_crash_guard()
    app = QApplication(sys.argv)

    if _resolve_mock_mode():
        print("[*] Modo simulação ativo — telemetria interna (sem o ACC).")
        provider = MockTelemetryProvider()
    else:
        print("[*] Aguardando o Assetto Corsa Competizione (ACC)... (nada a configurar no jogo)")
        provider = ACCTelemetryProvider()

    # Injeta o provider na Engine central (60 Hz)
    engine = TelemetryEngine(provider=provider, hz=60)

    # Passa a Engine para a Interface Gráfica
    window = DashboardMainWindow(engine)
    window.show()

    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
