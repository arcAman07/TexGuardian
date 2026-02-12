"""Compile command."""

from __future__ import annotations

from typing import TYPE_CHECKING

from texguardian.cli.commands.registry import Command

if TYPE_CHECKING:
    from rich.console import Console

    from texguardian.core.session import SessionState


class CompileCommand(Command):
    """Compile the LaTeX document."""

    name = "compile"
    description = "Compile the LaTeX document using latexmk"
    aliases = ["c", "build"]
    usage = "/compile [--clean] — compile the document (--clean removes build artifacts first)"

    async def execute(
        self,
        session: SessionState,
        args: str,
        console: Console,
    ) -> None:
        """Execute the compile command.

        Supported args:
            --clean   Run ``latexmk -C`` to remove build artifacts before compiling.
        """
        from texguardian.latex.compiler import LatexCompiler

        # Parse args
        clean = "--clean" in args if args else False

        compiler = LatexCompiler(session.config)

        # Optional clean step
        if clean:
            console.print("[dim]Cleaning build artifacts...[/dim]")
            await compiler.clean(session.main_tex_path, session.output_dir)

        with console.status(f"[bold cyan]Compiling {session.config.project.main_tex}...", spinner="dots"):
            result = await compiler.compile(
                session.main_tex_path,
                session.output_dir,
            )

        session.last_compilation = result

        if result.success:
            paper_name = session.config.project.main_tex.replace(".tex", "")
            console.print(f"\n[green]Successfully compiled '{paper_name}'[/green]")
            if result.pdf_path:
                console.print(f"  PDF: [cyan]{result.pdf_path}[/cyan]")
            if result.page_count is not None:
                console.print(f"  Pages: {result.page_count}")

            # Show warnings if any
            if result.warnings:
                console.print(f"\n[yellow]{len(result.warnings)} warning(s):[/yellow]")
                for warning in result.warnings[:5]:
                    console.print(f"  - {warning}")
                if len(result.warnings) > 5:
                    console.print(f"  ... and {len(result.warnings) - 5} more")
        else:
            console.print("[red]Compilation failed![/red]")
            if result.errors:
                console.print("\n[red]Errors:[/red]")
                for error in result.errors:
                    console.print(f"  {error}")
            else:
                # Show last ~500 chars of log, aligned to line boundaries
                tail = result.log_output[-500:]
                newline_pos = tail.find("\n")
                if newline_pos != -1 and newline_pos < len(tail) - 1:
                    tail = tail[newline_pos + 1:]
                console.print(f"\n[dim]{tail}[/dim]")
