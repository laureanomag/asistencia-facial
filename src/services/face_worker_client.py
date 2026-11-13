import json
import os
import queue
import subprocess
import sys
import threading


class FaceWorkerClient:
    """Lanza y se comunica con el proceso de reconocimiento (face_worker.py).
    Las respuestas llegan por senales.terminado (señal de Qt). Los envíos
    nunca bloquean la interfaz: se encolan y los escribe un hilo aparte."""

    def __init__(self, senales):
        self._senales = senales
        self._proc = None
        self._cola = None
        self._cerrando = False

    def _vivo(self):
        return self._proc is not None and self._proc.poll() is None

    def iniciar(self):
        if self._vivo():
            return
        self._cerrando = False
        ruta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "face_worker.py")
        # En Windows se baja la prioridad para que la ventana siga fluida.
        flags = getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
        proc = subprocess.Popen(
            [sys.executable, "-u", ruta],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,  # los logs del proceso salen en la misma consola
            text=True,
            encoding="utf-8",
            bufsize=1,
            creationflags=flags,
        )
        self._adoptar(proc)

    def _adoptar(self, proc):
        self._proc = proc
        self._cola = queue.Queue()
        threading.Thread(target=self._escribir, args=(proc, self._cola), daemon=True).start()
        threading.Thread(target=self._leer, args=(proc,), daemon=True).start()

    def enviar(self, mensaje):
        """No bloquea: deja el mensaje en una cola."""
        if self._cola is None:
            return
        self._cola.put(json.dumps(mensaje) + "\n")

    def detener(self):
        self._cerrando = True
        proc, cola = self._proc, self._cola
        self._proc, self._cola = None, None
        if cola is not None:
            cola.put(None)
        if proc is None:
            return
        try:
            proc.kill()  # no guarda estado propio: cada operación ya está confirmada en la base
            proc.wait(timeout=5)   # espera a que termine: no quedan procesos colgados
        except Exception:
            pass
        for canal in (proc.stdin, proc.stdout):
            try:
                if canal is not None:
                    canal.close()
            except Exception:
                pass

    def _escribir(self, proc, cola):
        try:
            while True:
                linea = cola.get()
                if linea is None:
                    break
                proc.stdin.write(linea)
                proc.stdin.flush()
        except (OSError, ValueError):
            if not self._cerrando and self._proc is proc:
                self._senales.terminado.emit({
                    "estado": "ERROR",
                    "mensaje": "No se pudo comunicar con el proceso de reconocimiento.",
                })

    def _leer(self, proc):
        try:
            for linea in proc.stdout:
                linea = linea.strip()
                if not linea.startswith("{"):
                    continue
                try:
                    datos = json.loads(linea)
                except ValueError:
                    continue  # una línea ajena al protocolo no debe cortar la lectura
                self._senales.terminado.emit(datos)
        except (OSError, ValueError):
            pass
        if not self._cerrando and self._proc is proc:
            self._senales.terminado.emit({
                "estado": "ERROR",
                "mensaje": "El proceso de reconocimiento se detuvo inesperadamente.",
            })
