"""La lectura de las cuentas del sistema y su modificación caen en tácticas distintas.

La regla de cuentas busca `passwd` como palabra, y la ruta `/etc/passwd` también la contiene. Sin la
regla de lectura, el panel le explicaría a quien mira una repetición que un `cat` crea una cuenta.
"""

import pytest

from honeyml.education.annotations import annotate


@pytest.mark.parametrize(
    "comando",
    [
        "cat /etc/passwd",
        "cat /etc/passwd 2>/dev/null",
        "grep root /etc/passwd",
        "head -n 5 /etc/group",
        "uname -a; cat /etc/passwd",
    ],
)
def test_leer_las_cuentas_es_descubrimiento(comando: str) -> None:
    assert annotate(comando).tactic == "Descubrimiento"


@pytest.mark.parametrize(
    "comando",
    [
        'echo "x:x:0:0::/root:/bin/bash" >> /etc/passwd',
        'echo "x:x:0:0::/root:/bin/bash" | tee -a /etc/passwd',
        'echo "root\\nclave\\nclave\\n" | passwd',
        "useradd -m -s /bin/bash admin1",
        "usermod -aG sudo admin1",
    ],
)
def test_modificar_las_cuentas_sigue_siendo_persistencia(comando: str) -> None:
    anotacion = annotate(comando)
    assert anotacion.tactic == "Persistencia"
    assert anotacion.technique == "T1136"


def test_la_lectura_lleva_la_tecnica_de_cuentas_locales() -> None:
    assert annotate("cat /etc/passwd").technique == "T1087.001"
