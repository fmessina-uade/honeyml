"""La marca de sin saldo: qué guarda, que se renueva sin perder el inicio, y que nunca levanta."""

from __future__ import annotations

import json

import redis

from honeyml.agent.adapters.saldo import CLAVE, LARGO_DEL_MOTIVO, VIGENCIA_S, MarcaSinSaldo


class _RedisFalso:
    """Lo único que la marca le pide al bus, en memoria. Con `falla`, el bus no responde."""

    def __init__(self, falla: Exception | None = None) -> None:
        self.datos: dict[str, str] = {}
        self.vencimientos: dict[str, int | None] = {}
        self.falla = falla

    def get(self, clave: str) -> str | None:
        if self.falla:
            raise self.falla
        return self.datos.get(clave)

    def set(self, clave: str, valor: str, ex: int | None = None) -> None:
        if self.falla:
            raise self.falla
        self.datos[clave] = valor
        self.vencimientos[clave] = ex

    def delete(self, clave: str) -> None:
        if self.falla:
            raise self.falla
        self.datos.pop(clave, None)


def test_la_marca_se_pone_se_lee_y_se_saca() -> None:
    r = _RedisFalso()
    marca = MarcaSinSaldo(r)  # type: ignore[arg-type]

    marca.poner("El proveedor no tiene crédito para este pedido.")
    leida = marca.leer()

    assert leida is not None
    assert leida["motivo"] == "El proveedor no tiene crédito para este pedido."
    assert leida["desde"] == leida["ultimo_intento"]
    # Vence sola, para que un motor apagado con la marca puesta no deje el aviso para siempre.
    assert r.vencimientos[CLAVE] == VIGENCIA_S

    marca.quitar()
    assert marca.leer() is None


def test_renovarla_conserva_desde_cuando_falta_el_saldo() -> None:
    r = _RedisFalso()
    r.datos[CLAVE] = json.dumps({"desde": "2026-10-13T09:00:00+00:00", "motivo": "viejo"})
    marca = MarcaSinSaldo(r)  # type: ignore[arg-type]

    marca.poner("nuevo")
    leida = marca.leer()

    assert leida is not None
    assert leida["desde"] == "2026-10-13T09:00:00+00:00"
    assert leida["ultimo_intento"] != "2026-10-13T09:00:00+00:00"
    assert leida["motivo"] == "nuevo"


def test_el_motivo_se_recorta() -> None:
    marca = MarcaSinSaldo(_RedisFalso())  # type: ignore[arg-type]
    marca.poner("x" * 1000)
    leida = marca.leer()
    assert leida is not None
    assert len(leida["motivo"]) == LARGO_DEL_MOTIVO


def test_con_el_bus_caido_no_levanta_y_no_inventa_el_aviso() -> None:
    marca = MarcaSinSaldo(_RedisFalso(falla=redis.ConnectionError("sin bus")))  # type: ignore[arg-type]
    marca.poner("sin crédito")
    marca.quitar()
    assert marca.leer() is None


def test_una_marca_ilegible_cuenta_como_ausente() -> None:
    r = _RedisFalso()
    r.datos[CLAVE] = "no es json"
    assert MarcaSinSaldo(r).leer() is None  # type: ignore[arg-type]
