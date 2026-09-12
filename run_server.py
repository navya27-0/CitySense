import sys
import os
import subprocess

# Auto-relaunch using project virtual environment if run from global python
venv_python = os.path.join(os.path.dirname(os.path.abspath(__file__)), "venv", "Scripts", "python.exe")
if os.path.exists(venv_python) and os.path.abspath(sys.executable).lower() != os.path.abspath(venv_python).lower():
    sys.exit(subprocess.call([venv_python, os.path.abspath(__file__)] + sys.argv[1:]))

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

if __name__ == "__main__":
    import uvicorn
    print("\n=======================================================")
    print("  Starting CitySense AI Fleet & Urban Intelligence API")
    print("  Dashboard: http://127.0.0.1:8000")
    print("  API Docs:  http://127.0.0.1:8000/docs")
    print("=======================================================\n")
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True, reload_dirs=["backend", "frontend"])
