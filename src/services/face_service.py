import os
import threading
import time
from dataclasses import dataclass

import cv2
import numpy as np

MODELO = "Facenet512"
UMBRAL = 0.40  # distancia coseno máxima para aceptar la mejor coincidencia (enunciado)
# Si el segundo alumno más cercano está a menos de esta diferencia del primero,
# la coincidencia es ambigua (por ejemplo, hermanos) y no se reconoce a nadie.
MARGEN_AMBIGUEDAD = 0.05


def _umbral():
    """0.40 por defecto. Se puede cambiar para pruebas con la variable
    UMBRAL_RECONOCIMIENTO en el archivo .env (por ejemplo 0.30)."""
    try:
        return float(os.getenv("UMBRAL_RECONOCIMIENTO", UMBRAL))
    except ValueError:
        return UMBRAL


def _margen_ambiguedad():
    """0.05 por defecto. Se puede cambiar con MARGEN_AMBIGUEDAD en el .env."""
    try:
        return max(0.0, float(os.getenv("MARGEN_AMBIGUEDAD", MARGEN_AMBIGUEDAD)))
    except ValueError:
        return MARGEN_AMBIGUEDAD


@dataclass
class ResultadoReconocimiento:
    """Resultado de reconocer().
    - alumno_id / nombre: el alumno reconocido, o None si no se reconoce
      (desconocido, ambiguo o sin referencias).
    - distancia: mejor distancia coseno encontrada (None sin referencias).
    - ambiguo: None, o ((nombre1, d1), (nombre2, d2)) con los dos alumnos
      demasiado parecidos."""
    alumno_id: object = None
    nombre: str = None
    distancia: float = None
    ambiguo: tuple = None


def distancias_por_alumno(matriz, etiquetas, actual):
    """Mejor distancia coseno de cada alumno entre todas sus fotos de
    referencia. Devuelve [(alumno_id, nombre, distancia)] ordenada de menor a
    mayor distancia. matriz y actual ya vienen normalizados."""
    distancias = 1.0 - matriz @ actual
    mejores = {}
    for (alumno_id, nombre), d in zip(etiquetas, distancias):
        d = float(d)
        if alumno_id not in mejores or d < mejores[alumno_id][1]:
            mejores[alumno_id] = (nombre, d)
    return sorted(((a, n, d) for a, (n, d) in mejores.items()), key=lambda r: r[2])


def decidir(ranking, umbral, margen):
    """Aplica el umbral y el margen de ambigüedad al ranking por alumno."""
    if not ranking:
        return ResultadoReconocimiento()

    alumno_id, nombre, distancia = ranking[0]
    if distancia > umbral:
        return ResultadoReconocimiento(distancia=distancia)

    if len(ranking) > 1:
        _id2, nombre2, distancia2 = ranking[1]
        if distancia2 - distancia < margen:
            return ResultadoReconocimiento(
                distancia=distancia,
                ambiguo=((nombre, distancia), (nombre2, distancia2)),
            )

    return ResultadoReconocimiento(alumno_id, nombre, distancia)


class FaceDetector:
    """Detección con OpenCV + Haar Cascade (haarcascade_frontalface_default)."""

    def __init__(self):
        self._cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        if self._cascade.empty():
            raise RuntimeError("No se pudo cargar haarcascade_frontalface_default.xml")

    ANCHO_DETECCION = 640  # se detecta sobre una copia reducida: mucho más rápido

    def detectar(self, frame, permisivo=False):
        """Lista de rectángulos (x, y, w, h) en coordenadas del frame original.
        Con permisivo=True usa parámetros más tolerantes (fotos de referencia
        con el rostro algo girado)."""
        gris = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        factor = min(1.0, self.ANCHO_DETECCION / gris.shape[1])
        if factor < 1.0:
            gris = cv2.resize(gris, None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA)
        gris = cv2.equalizeHist(gris)  # compensa poca luz o luz despareja

        # Tamaño mínimo del rostro, expresado en píxeles del frame original.
        if permisivo:
            escala, vecinos, minimo_original = 1.05, 3, 60
        else:
            escala, vecinos, minimo_original = 1.1, 6, 120
        minimo = max(20, int(minimo_original * factor))

        caras = self._cascade.detectMultiScale(
            gris, scaleFactor=escala, minNeighbors=vecinos, minSize=(minimo, minimo)
        )
        return [tuple(int(v / factor) for v in c) for c in caras]

    @staticmethod
    def filtrar(caras, proporcion=0.35):
        """Descarta detecciones mucho más chicas que la mayor (suelen ser falsos
        positivos de Haar sobre el fondo). Dos rostros reales de tamaño
        parecido se conservan, y entonces no se reconoce."""
        if len(caras) <= 1:
            return caras
        mayor = max(c[2] * c[3] for c in caras)
        return [c for c in caras if c[2] * c[3] >= mayor * proporcion]

    @staticmethod
    def recortar(frame, rect, margen=0.15):
        x, y, w, h = rect
        alto, ancho = frame.shape[:2]
        dx, dy = int(w * margen), int(h * margen)
        x1, y1 = max(0, x - dx), max(0, y - dy)
        x2, y2 = min(ancho, x + w + dx), min(alto, y + h + dy)
        return frame[y1:y2, x1:x2]


def _embedding(rostro_bgr):
    """Embedding de 512 valores con DeepFace + Facenet512. El rostro ya viene
    recortado por Haar, por eso no se ejecuta otro detector."""
    from deepface import DeepFace

    resultado = DeepFace.represent(
        img_path=rostro_bgr,
        model_name=MODELO,
        detector_backend="skip",
        enforce_detection=False,
    )
    return np.asarray(resultado[0]["embedding"], dtype=np.float32)


def _normalizar(v):
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.where(n == 0, 1, n)


class FaceRecognitionService:
    """Genera y cachea los embeddings de referencia (Frontal, Izquierda,
    Derecha de cada alumno) y compara el rostro actual por distancia coseno."""

    def __init__(self, student_repository):
        self._repo = student_repository
        self._detector = FaceDetector()  # instancia propia (se usa fuera del hilo de UI)
        self._lock = threading.Lock()
        self._matriz = None   # embeddings normalizados, una fila por referencia
        self._etiquetas = []  # (alumno_id, "Apellido, Nombre") por fila

    def invalidar(self):
        """Fuerza recargar referencias (por ejemplo, tras registrar alumnos).
        No toma el lock a propósito: se llama desde la interfaz y no debe
        quedarse esperando a una carga en curso."""
        self._matriz = None
        self._etiquetas = []

    def precargar(self):
        """Carga el modelo FaceNet512 y los embeddings de referencia. Se llama
        en segundo plano al abrir la cámara, para que el primer
        reconocimiento no tenga que esperar."""
        with self._lock:
            t0 = time.time()
            print("[Reconocimiento] Cargando modelo Facenet512 (la primera vez descarga ~95 MB)...", flush=True)
            _embedding(np.zeros((160, 160, 3), dtype=np.uint8))
            print(f"[Reconocimiento] Modelo listo en {time.time() - t0:.1f}s", flush=True)
            if self._matriz is None:
                self._cargar_referencias()

    def _cargar_referencias(self):
        t0 = time.time()
        vectores, etiquetas = [], []
        filas = self._repo.obtener_referencias()
        print(f"[Reconocimiento] Procesando {len(filas)} fotos de referencia...", flush=True)
        for alumno_id, apellido, nombre, _angulo, imagen in filas:
            if imagen is None:
                continue
            try:
                img = cv2.imdecode(np.frombuffer(bytes(imagen), np.uint8), cv2.IMREAD_COLOR)
                if img is None:
                    continue
                caras = self._detector.detectar(img) or self._detector.detectar(img, permisivo=True)
                if not caras:
                    print(f"[Reconocimiento] Foto sin rostro detectable (alumno {alumno_id}, {_angulo}): se omite", flush=True)
                    continue  # foto deficiente: no sirve como referencia
                rect = max(caras, key=lambda c: c[2] * c[3])
                vectores.append(_embedding(self._detector.recortar(img, rect)))
                etiquetas.append((alumno_id, f"{apellido}, {nombre}"))
            except Exception as error:
                # Una foto problemática se omite; no impide cargar las demás.
                print(f"[Reconocimiento] No se pudo usar una foto (alumno {alumno_id}, {_angulo}): {error}", flush=True)

        self._matriz = _normalizar(np.vstack(vectores)) if vectores else np.empty((0, 512), np.float32)
        self._etiquetas = etiquetas
        print(f"[Reconocimiento] {len(vectores)} referencias válidas cargadas en {time.time() - t0:.1f}s", flush=True)

    def reconocer(self, rostro_bgr):
        """Devuelve un ResultadoReconocimiento. Se compara la mejor distancia
        de cada alumno (entre todas sus fotos): se reconoce al más cercano sólo
        si no supera el umbral y si el segundo alumno no está demasiado cerca."""
        with self._lock:
            if self._matriz is None:
                self._cargar_referencias()
            matriz, etiquetas = self._matriz, self._etiquetas

        if len(etiquetas) == 0:
            return ResultadoReconocimiento()

        actual = _normalizar(_embedding(rostro_bgr))
        ranking = distancias_por_alumno(matriz, etiquetas, actual)
        detalle = " | ".join(f"{nombre} {d:.3f}" for _id, nombre, d in ranking)
        print(f"[Reconocimiento] Distancias por alumno: {detalle}", flush=True)

        return decidir(ranking, _umbral(), _margen_ambiguedad())
