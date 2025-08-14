from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
from typing import Any, Dict

class PromptBuilder:
    def __init__(self, base_dir: Path):
        self.base = base_dir
        self.env = Environment(
            loader=FileSystemLoader(str(base_dir)),
            autoescape=select_autoescape()
        )

    def read(self, name: str) -> str:
        path = self.base / name
        return path.read_text(encoding="utf-8")

    def render(self, template_name: str, **kwargs: Dict[str, Any]) -> str:
        tpl = self.env.get_template(template_name)
        return tpl.render(**kwargs)