"""Datos del gimnasio: el único lugar con el nombre, la dirección y el logo.
Los usan el login, los informes exportados y el resto de la interfaz."""
from pathlib import Path

NOMBRE = "ZebraGym"
CALLE = "Av. Corrientes 2833"
CODIGO_POSTAL = "Y4600"
CIUDAD = "San Salvador de Jujuy"
PROVINCIA = "Jujuy"
BARRIO = "San Pedrito"

# "Av. Corrientes 2833 · San Pedrito, San Salvador de Jujuy" (pie del login)
DIRECCION_CORTA = f"{CALLE} · {BARRIO}, {CIUDAD}"
# "Av. Corrientes 2833, Y4600 San Salvador de Jujuy, Jujuy (barrio San Pedrito)"
DIRECCION_COMPLETA = f"{CALLE}, {CODIGO_POSTAL} {CIUDAD}, {PROVINCIA} (barrio {BARRIO})"

LOGO = Path(__file__).resolve().parents[2] / "assets" / "logo.png"
