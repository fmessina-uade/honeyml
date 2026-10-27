# SPDX-FileCopyrightText: 2025 Onder7994
# SPDX-FileCopyrightText: 2025-2026 Michel Oosterhof <michel@oosterhof.net>
#
# SPDX-License-Identifier: BSD-3-Clause
#
# Copia del comando find de Cowrie con dos cambios, montada sobre el original por la composición.
# El original baja por los enlaces simbólicos, y el sistema de archivos simulado tiene enlaces que
# apuntan hacia arriba: desde la raíz, el recorrido crece sin fin dentro del único hilo de Cowrie y
# el sensor deja de atender a todos hasta que lo reinicia el vigilante. Esta versión no baja por los
# enlaces, que es lo que hace el find real por defecto, y corta después de un tope de entradas.

"""Comando find del sensor de acceso remoto."""

from __future__ import annotations

import fnmatch
import os

from cowrie.shell.command import HoneyPotCommand
from cowrie.shell.fs import A_TYPE, T_LINK

commands = {}

# El sistema simulado entero, sin bajar por los enlaces, no llega a treinta mil entradas, así que
# una búsqueda desde la raíz entra completa. El tope solo frena un árbol que crezca por otro lado.
TOPE_DE_ENTRADAS = 40000


class Command_find(HoneyPotCommand):  # noqa: N801 - el nombre del original, para compararlos
    """Busca por nombre y tipo, como el find de GNU sin opciones de enlaces."""

    def start(self) -> None:
        self.maxdepth: int = 20
        self.name_pattern = None
        self.type_filter = None
        self.visitadas = 0

        self.start_path = self.protocol.cwd

        idx = 0
        while idx < len(self.args):
            arg = self.args[idx]

            if arg == "-name":
                idx += 1
                if idx >= len(self.args):
                    self.errorWrite("find: missing argument to `-name`\n")
                    self.exit()
                    return
                self.name_pattern = self.args[idx]

            elif arg == "-type":
                idx += 1
                if idx >= len(self.args):
                    self.errorWrite("find: missing argument to `-type`\n")
                    self.exit()
                    return
                val = self.args[idx]
                if val in ("f", "d"):
                    self.type_filter = val
                else:
                    self.errorWrite("find: unknown argument to -type. Use 'f' or 'd'\n")
                    self.exit()
                    return

            elif arg == "-maxdepth":
                idx += 1
                if idx >= len(self.args):
                    self.errorWrite("find: missing argument to `-maxdepth`\n")
                    self.exit()
                    return
                try:
                    self.maxdepth = int(self.args[idx])
                except ValueError:
                    self.errorWrite("find: maxdepth must be an integer\n")
                    self.exit()
                    return

            elif not arg.startswith("-") and self.start_path == self.protocol.cwd:
                self.start_path = self.fs.resolve_path(arg, self.protocol.cwd)

            else:
                self.errorWrite(f"find: unknown argument '{arg}'\n")
                self.exit()
                return

            idx += 1

        self.find_recursive(self.start_path, 0)
        self.exit()

    def find_recursive(self, path: str, depth: int) -> None:
        if depth > self.maxdepth or self.visitadas >= TOPE_DE_ENTRADAS:
            return
        self.visitadas += 1
        try:
            # un enlace es una hoja: no se resuelve ni se baja por él. El punto de partida sí se
            # sigue aunque sea un enlace, como hace el find real
            enlace = depth > 0 and self._es_enlace(path)
            if not enlace and not self.fs.exists(path):
                return
            if self._match(path, enlace):
                self.write(f"{path}\n")

            if not enlace and self.fs.isdir(path):
                for entry in self.fs.listdir(path):
                    if entry in (".", ".."):
                        continue
                    full_path = os.path.join(path, entry)
                    self.find_recursive(full_path, depth + 1)
        except Exception:
            # el original imprimía el error de Python, que delata la emulación; una entrada que no
            # se puede leer se saltea
            return

    def _es_enlace(self, path: str) -> bool:
        # islink() de Cowrie resuelve el enlace antes de mirar el tipo y nunca da verdadero, así que
        # se lee la entrada sin seguirla
        entrada = self.fs.getfile(path, follow_symlinks=False)
        return entrada is not None and entrada[A_TYPE] == T_LINK

    def _match(self, path: str, enlace: bool = False) -> bool:
        basename = os.path.basename(path)

        if self.name_pattern and not fnmatch.fnmatch(basename, self.name_pattern):
            return False

        # un enlace no es ni archivo ni directorio para -type
        if enlace:
            return self.type_filter is None
        if self.type_filter == "f" and not self.fs.isfile(path):
            return False
        if self.type_filter == "d" and not self.fs.isdir(path):
            return False

        return True


commands["find"] = Command_find
commands["/bin/find"] = Command_find
