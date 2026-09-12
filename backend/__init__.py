"""Backend application package for BusSense-AI."""

import sys

# Suppress harmless Windows asyncio Proactor connection reset tracebacks during HTTP Range video streaming
if sys.platform == 'win32':
    try:
        import socket
        import asyncio.proactor_events as pe

        def _safe_call_connection_lost(self, exc):
            if getattr(self, '_called_connection_lost', False):
                return
            try:
                if hasattr(self, '_protocol') and self._protocol:
                    self._protocol.connection_lost(exc)
            except Exception:
                pass
            finally:
                if hasattr(self, '_sock') and self._sock is not None:
                    if hasattr(self._sock, 'shutdown') and getattr(self._sock, 'fileno', lambda: -1)() != -1:
                        try:
                            self._sock.shutdown(socket.SHUT_RDWR)
                        except (ConnectionResetError, OSError):
                            pass
                    try:
                        self._sock.close()
                    except (ConnectionResetError, OSError):
                        pass
                    self._sock = None
                server = getattr(self, '_server', None)
                if server is not None:
                    try:
                        server._detach(self)
                    except Exception:
                        pass
                    self._server = None
                self._called_connection_lost = True

        pe._ProactorBasePipeTransport._call_connection_lost = _safe_call_connection_lost
    except Exception:
        pass
