#!/usr/import/env python3
"""Map-Reduce Manuscript Compiler.

Compiles parallel markdown sections into a final PDF/HTML using Pandoc.
"""

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Optional

from research_copilot.utils.common import find_project_root


@dataclass
class ManuscriptSection:
    section_id: str
    title: str
    markdown_path: Path
    order: int
    figure_paths: List[Path] = field(default_factory=list)


class ManuscriptCompiler:
    def __init__(self, root: Optional[Path] = None):
        self.root = root or find_project_root()
        self.sections_dir = self.root / "03_synthesis" / "sections"
        self.output_dir = self.root / "03_synthesis" / "manuscript"

    def discover_sections(self) -> List[ManuscriptSection]:
        if not self.sections_dir.exists():
            return []

        sections = []
        for md_file in self.sections_dir.glob("*.md"):
            content = md_file.read_text()
            order = 99
            title = md_file.stem.capitalize()
            figures = []

            # Parse simple YAML frontmatter
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    frontmatter = parts[1]
                    for line in frontmatter.splitlines():
                        if line.startswith("order:"):
                            try:
                                order = int(line.split(":", 1)[1].strip())
                            except ValueError:
                                pass
                        elif line.startswith("title:"):
                            title = line.split(":", 1)[1].strip()

            sections.append(
                ManuscriptSection(
                    section_id=md_file.stem,
                    title=title,
                    markdown_path=md_file,
                    order=order,
                    figure_paths=figures,
                )
            )

        return sorted(sections, key=lambda s: s.order)

    def compile_markdown(self, sections: List[ManuscriptSection], output_path: Optional[Path] = None) -> Path:
        if output_path is None:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            output_path = self.output_dir / "draft.md"
        else:
            output_path.parent.mkdir(parents=True, exist_ok=True)

        content_parts = []
        for s in sections:
            md = s.markdown_path.read_text()
            # Strip frontmatter
            if md.startswith("---"):
                parts = md.split("---", 2)
                if len(parts) >= 3:
                    md = parts[2].strip()
            content_parts.append(md)

        output_path.write_text("\n\n---\n\n".join(content_parts))
        return output_path

    def compile_pdf(self, markdown_path: Path, output_path: Optional[Path] = None) -> dict:
        if output_path is None:
            output_path = markdown_path.with_suffix(".pdf")

        try:
            cmd = [
                "pandoc",
                str(markdown_path),
                "-o", str(output_path),
                "--pdf-engine=xelatex",
                "-V", "geometry:margin=1in"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return {
                "status": "success",
                "output_path": output_path,
                "stderr": result.stderr,
                "pandoc_available": True
            }
        except FileNotFoundError:
            return {
                "status": "pandoc_missing",
                "output_path": None,
                "stderr": "Pandoc is not installed.",
                "pandoc_available": False
            }
        except subprocess.CalledProcessError as e:
            # Fallback to pdflatex
            try:
                cmd[4] = "--pdf-engine=pdflatex"
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                return {
                    "status": "success",
                    "output_path": output_path,
                    "stderr": result.stderr,
                    "pandoc_available": True
                }
            except subprocess.CalledProcessError as e2:
                return {
                    "status": "failed",
                    "output_path": None,
                    "stderr": e2.stderr,
                    "pandoc_available": True
                }

    def compile_html(self, markdown_path: Path, output_path: Optional[Path] = None) -> dict:
        if output_path is None:
            output_path = markdown_path.with_suffix(".html")

        try:
            cmd = [
                "pandoc",
                str(markdown_path),
                "-o", str(output_path),
                "--standalone",
                "--toc"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return {
                "status": "success",
                "output_path": output_path,
                "stderr": result.stderr,
                "pandoc_available": True
            }
        except FileNotFoundError:
            return {
                "status": "pandoc_missing",
                "output_path": None,
                "stderr": "Pandoc is not installed.",
                "pandoc_available": False
            }
        except subprocess.CalledProcessError as e:
            return {
                "status": "failed",
                "output_path": None,
                "stderr": e.stderr,
                "pandoc_available": True
            }

    def run_map_reduce(self, formats: List[str] = None) -> dict:
        if formats is None:
            formats = ["pdf", "html"]

        sections = self.discover_sections()
        if not sections:
            return {"sections_found": 0, "markdown_path": None, "outputs": {}, "errors": ["No sections found."]}

        md_path = self.compile_markdown(sections)
        outputs = {}
        errors = []

        if "pdf" in formats:
            pdf_res = self.compile_pdf(md_path)
            outputs["pdf"] = pdf_res
            if pdf_res["status"] != "success":
                errors.append(f"PDF compile failed: {pdf_res['stderr']}")

        if "html" in formats:
            html_res = self.compile_html(md_path)
            outputs["html"] = html_res
            if html_res["status"] != "success":
                errors.append(f"HTML compile failed: {html_res['stderr']}")

        return {
            "sections_found": len(sections),
            "markdown_path": md_path,
            "outputs": outputs,
            "errors": errors
        }

    def get_section_prompt(self, section_id: str) -> str:
        prompts = {
            "intro": "Write a compelling Introduction section. Provide background and context.",
            "methods": "Write a detailed Methods section describing the approach used.",
            "results": "Write a Results section with all statistics and findings.",
            "discussion": "Write a Discussion section interpreting the results and limitations.",
            "abstract": "Write a 250-word Abstract summarizing the entire study."
        }
        return prompts.get(section_id, f"Write the {section_id} section.")


def cmd_compile(args) -> int:
    formats = args.formats.split(",") if hasattr(args, "formats") and args.formats else ["pdf", "html"]
    mc = ManuscriptCompiler()
    result = mc.run_map_reduce(formats=formats)
    print(f"Sections discovered: {result['sections_found']}")
    if result["sections_found"] == 0:
        return 0

    print(f"Compiled markdown: {result['markdown_path']}")
    for fmt, res in result["outputs"].items():
        if res["status"] == "pandoc_missing":
            print(f"Pandoc missing. Cannot compile {fmt}. Install pandoc to enable.")
        else:
            print(f"Format {fmt}: {res['status']}")
            if res["status"] == "success":
                print(f"  -> {res['output_path']}")
    return 0 if not result["errors"] else 1
