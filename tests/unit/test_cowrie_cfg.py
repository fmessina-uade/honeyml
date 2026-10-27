"""
Tests unitarios para cowrie.cfg.

Valida que los paths internos son los reales de la imagen cowrie/cowrie:latest.
El CWD del proceso dentro del contenedor es /cowrie/cowrie-git, por lo que
los paths relativos se resuelven desde ahí.
"""

import configparser
import pathlib

import pytest

COWRIE_CFG = pathlib.Path(__file__).parents[2] / "infra/honeypots/cowrie/cowrie.cfg"


@pytest.fixture
def cfg() -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    parser.read(COWRIE_CFG)
    return parser


def test_cowrie_cfg_exists():
    assert COWRIE_CFG.exists(), f"Falta {COWRIE_CFG}"


def test_cowrie_cfg_parseable(cfg):
    assert "honeypot" in cfg, "Sección [honeypot] no encontrada"


def test_contents_path_is_honeyfs(cfg):
    """share/cowrie/txtcmds no existe en la imagen, así que pwd.py llama sys.exit(2)
    si no puede abrir contents_path/etc/passwd."""
    val = cfg.get("honeypot", "contents_path", fallback="")
    assert val == "honeyfs", (
        f"contents_path='{val}' incorrecto. Debe ser 'honeyfs' "
        "(existe en /cowrie/cowrie-git/honeyfs/)"
    )


def test_txtcmds_path(cfg):
    """El directorio real de txtcmds en la imagen es src/cowrie/data/txtcmds."""
    val = cfg.get("honeypot", "txtcmds_path", fallback="")
    assert val == "src/cowrie/data/txtcmds", (
        f"txtcmds_path='{val}' incorrecto. Debe ser 'src/cowrie/data/txtcmds'"
    )


def test_auth_class_is_userdb(cfg):
    val = cfg.get("honeypot", "auth_class", fallback="")
    assert val == "UserDB", f"auth_class='{val}', debe ser 'UserDB' para usar userdb.txt"


def test_ssh_enabled(cfg):
    assert cfg.get("ssh", "enabled", fallback="false") == "true"


def test_telnet_enabled(cfg):
    assert cfg.get("telnet", "enabled", fallback="false") == "true"


def test_json_output_enabled(cfg):
    assert cfg.get("output_jsonlog", "enabled", fallback="false") == "true", (
        "output_jsonlog debe estar habilitado: es la fuente de datos del pipeline ECS"
    )
