from __future__ import annotations

from importlib import resources
from typing import Any, Dict

from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path


def get_templates_dir() -> Path:
    return Path(__file__).with_suffix("").parent / "templates"


def create_jinja_env() -> Environment:
    templates_dir = get_templates_dir()
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(enabled_extensions=(".j2",)),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return env


def render_template(template_name: str, context: Dict[str, Any]) -> str:
    env = create_jinja_env()
    template = env.get_template(template_name)
    return template.render(**context)


