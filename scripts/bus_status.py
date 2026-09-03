"""Informa el estado del bus de eventos: stream, grupos de consumidores y entradas pendientes.

Escrito directamente contra el protocolo de Redis sobre un socket, sin biblioteca cliente. El motivo
es el mismo que en el resto de las herramientas del proyecto: esto tiene que correr desde el entorno
virtual pelado, y agregar una dependencia para contestar "¿el bus está vivo y hay alguien atrasado?"
no justifica el pin.

Lo que importa en operación es la cuenta de pendientes. Un grupo de consumidores con entradas
tomadas y nunca confirmadas significa que el motor de triaje levantó eventos y se murió antes de
persistir una decisión. Esos eventos se recuperan, pero solo si alguien se da cuenta.

Uso:
    python scripts/bus_status.py
"""

from __future__ import annotations

import argparse
import socket
from typing import Any

HOST = "127.0.0.1"
PORT = 6379
STREAM = "honeyml:events"


class RedisError(RuntimeError):
    pass


def _encode(*args: str) -> bytes:
    """Arreglo RESP de cadenas, que es la única forma de pedido que necesitamos."""
    out = [f"*{len(args)}\r\n".encode()]
    for a in args:
        raw = a.encode()
        out.append(b"$%d\r\n%s\r\n" % (len(raw), raw))
    return b"".join(out)


def _read_reply(f: Any) -> Any:
    line = f.readline()
    if not line:
        raise RedisError("la conexión se cerró")
    kind, body = line[:1], line[1:].strip()

    if kind == b"+":
        return body.decode()
    if kind == b"-":
        raise RedisError(body.decode())
    if kind == b":":
        return int(body)
    if kind == b"$":
        length = int(body)
        if length == -1:
            return None
        data = f.read(length + 2)[:-2]
        return data.decode(errors="replace")
    if kind == b"*":
        count = int(body)
        if count == -1:
            return None
        return [_read_reply(f) for _ in range(count)]
    raise RedisError(f"respuesta inesperada: {line!r}")


def command(sock_file: Any, sock: socket.socket, *args: str) -> Any:
    sock.sendall(_encode(*args))
    return _read_reply(sock_file)


def as_dict(pairs: list[Any] | None) -> dict[str, Any]:
    """Redis devuelve los mapas como listas planas [k1, v1, k2, v2, ...]."""
    if not pairs:
        return {}
    return {pairs[i]: pairs[i + 1] for i in range(0, len(pairs) - 1, 2)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=HOST)
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--stream", default=STREAM)
    args = ap.parse_args()

    try:
        sock = socket.create_connection((args.host, args.port), timeout=10)
    except OSError as exc:
        print(f"  El bus no responde en {args.host}:{args.port} ({exc}).")
        print("  Levantalo con: make bus-up")
        return 1

    with sock, sock.makefile("rb") as f:
        print(f"  ping: {command(f, sock, 'PING')}")

        info = command(f, sock, "INFO", "memory")
        used = next(
            (
                ln.split(":", 1)[1]
                for ln in str(info).splitlines()
                if ln.startswith("used_memory_human")
            ),
            "?",
        )
        maxmem = next(
            (
                ln.split(":", 1)[1]
                for ln in str(info).splitlines()
                if ln.startswith("maxmemory_human")
            ),
            "?",
        )
        print(f"  memoria: {used.strip()} de {maxmem.strip()}")

        exists = command(f, sock, "EXISTS", args.stream)
        if not exists:
            print(f"\n  El stream '{args.stream}' todavía no existe.")
            print("  Se crea con el primer evento publicado por el pipeline.")
            return 0

        stream = as_dict(command(f, sock, "XINFO", "STREAM", args.stream))

        def entry_id(key: str) -> str:
            entry = stream.get(key)
            return entry[0] if entry else "-"

        print(f"\n  stream '{args.stream}'")
        print(f"    entradas: {stream.get('length', '?')}")
        print(f"    primera:  {entry_id('first-entry')}")
        print(f"    última:   {entry_id('last-entry')}")

        groups = command(f, sock, "XINFO", "GROUPS", args.stream) or []
        if not groups:
            print("\n    sin grupos de consumidores: nadie está consumiendo todavía.")
            return 0

        print(f"\n  grupos de consumidores: {len(groups)}")
        for g in groups:
            gd = as_dict(g)
            pending = gd.get("pending", 0)
            marca = "  <- hay eventos sin confirmar" if pending else ""
            print(f"    {gd.get('name')}")
            print(f"      consumidores: {gd.get('consumers')}   pendientes: {pending}{marca}")
            print(f"      último entregado: {gd.get('last-delivered-id')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
