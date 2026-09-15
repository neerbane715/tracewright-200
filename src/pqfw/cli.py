"""PQ-FORENSIC command line interface.

This is the product. The web layer is a client of these same functions -- if it
fails, every capability remains available here.
"""
from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import pipeline
from .forensics.investigate import Outcome, investigate
from .identity import Keystore
from .ledger.node import LedgerNode
from .watermark import engine, tardos

app = typer.Typer(add_completion=False, help=__doc__)
ident_app = typer.Typer(help="Manage offline post-quantum identities")
ledger_app = typer.Typer(help="Inspect and verify the audit ledger")
app.add_typer(ident_app, name="id")
app.add_typer(ledger_app, name="ledger")

con = Console()
DEFAULT_HOME = Path("./pqfw-data")


def _ks(home: Path) -> Keystore:
    return Keystore(home / "keys")


def _led(home: Path) -> LedgerNode:
    return LedgerNode(home / "ledger.db")


# --------------------------------------------------------------------------

@ident_app.command("create")
def id_create(user_id: str,
              home: Path = typer.Option(DEFAULT_HOME, "--home")):
    """Generate a new ML-KEM + ML-DSA identity."""
    ident = _ks(home).create(user_id)
    con.print(f"[green]created[/] identity [bold]{user_id}[/]")
    con.print(f"  fingerprint : [cyan]{ident.fingerprint}[/]")
    con.print(f"  ML-KEM-768  : {len(ident.kem_public)} byte public key")
    con.print(f"  ML-DSA-65   : {len(ident.sig_public)} byte public key")


@ident_app.command("list")
def id_list(home: Path = typer.Option(DEFAULT_HOME, "--home")):
    """List identities in the local keystore."""
    ks = _ks(home)
    t = Table("user", "fingerprint", "secret key")
    for u in ks.list_identities():
        t.add_row(u, ks.public(u).fingerprint,
                  "[green]yes[/]" if ks.has_secret(u) else "[dim]public only[/]")
    con.print(t)


# --------------------------------------------------------------------------

@app.command()
def encrypt(document: Path,
            recipients: str = typer.Option(..., "--recipients", "-r",
                                           help="comma-separated user ids"),
            out: Path = typer.Option(None, "--out", "-o"),
            home: Path = typer.Option(DEFAULT_HOME, "--home")):
    """Encrypt a document once for many recipients (PS step 1)."""
    ks = _ks(home)
    users = [u.strip() for u in recipients.split(",") if u.strip()]
    idents = [ks.public(u) for u in users]
    out = out or document.with_suffix(".pqfw")

    need = tardos.required_length(len(idents), 3)
    have = engine.capacity(str(document))
    if have < need:
        con.print(Panel(
            f"[yellow]capacity warning[/]\n"
            f"document carries [bold]{have}[/] bits; "
            f"[bold]{need}[/] needed for {len(idents)} recipients vs 3 colluders.\n"
            f"Decryption will refuse this document.",
            border_style="yellow"))

    b = pipeline.encrypt(document, idents, out)
    con.print(f"[green]encrypted[/] {document.name} -> {out}")
    con.print(f"  doc id     : [cyan]{b.doc_id}[/]")
    con.print(f"  recipients : {', '.join(users)}")
    con.print(f"  capacity   : {have} bits (need {need})")


@app.command()
def decrypt(bundle: Path,
            identity: str = typer.Option(..., "--identity", "-i"),
            out: Path = typer.Option(None, "--out", "-o"),
            home: Path = typer.Option(DEFAULT_HOME, "--home")):
    """Decrypt, watermark, sign and commit (PS steps 2-6)."""
    ks, led = _ks(home), _led(home)
    out = out or Path(f"{identity}-{bundle.stem}.pdf")
    try:
        r = pipeline.decrypt(bundle, identity, ks, led, out,
                             progress=lambda m: con.print(f"  [dim]>[/] {m}"))
    except pipeline.PipelineError as e:
        con.print(f"[red]refused:[/] {e}")
        raise typer.Exit(1)
    except engine.CapacityError as e:
        con.print(f"[red]refused:[/] {e}")
        raise typer.Exit(1)
    con.print(Panel(
        f"[green]decrypted[/] -> [bold]{out}[/]\n"
        f"session   : {r.record.session_id}\n"
        f"watermark : {r.bits_embedded} bits, invisible\n"
        f"ledger    : index {r.ledger_index}, "
        f"root {led.root().hex()[:24]}...",
        title="decryption complete", border_style="green"))


@app.command()
def investigate_(leaked: Path = typer.Argument(..., metavar="LEAKED_PDF"),
                 home: Path = typer.Option(DEFAULT_HOME, "--home"),
                 json_out: bool = typer.Option(False, "--json")):
    """Attribute a leaked document (PS steps 7-10)."""
    v = investigate(leaked, _led(home))
    if json_out:
        con.print_json(json.dumps(v.to_dict()))
        return

    colour = {Outcome.IDENTIFIED: "green", Outcome.INCONCLUSIVE: "yellow",
              Outcome.NO_WATERMARK: "yellow",
              Outcome.LEDGER_COMPROMISED: "red"}[v.outcome]

    body = [f"[bold {colour}]{v.outcome.value}[/]"]
    if v.recipient_user_id:
        body += [f"recipient  : [bold]{v.recipient_user_id}[/] "
                 f"({v.recipient_fingerprint})",
                 f"session    : {v.session_id}",
                 f"decrypted  : {v.timestamp}",
                 f"ledger     : index {v.ledger_index}"]
    if v.score is not None:
        body.append(f"detection  : score {v.score:.0f} / threshold "
                    f"{v.threshold:.0f}, margin {v.margin:.2f}, "
                    f"{v.bits_recovered}/{v.bits_expected} bits")
    con.print(Panel("\n".join(body), title="forensic verdict",
                    border_style=colour))

    t = Table("evidence", "status")
    for label, ok in [("recipient ML-DSA signature", v.signature_valid),
                      ("ledger inclusion proof", v.inclusion_valid),
                      ("watermark commitment", v.commitment_valid),
                      ("ledger integrity", v.ledger_intact)]:
        t.add_row(label, "[green]VERIFIED[/]" if ok else "[red]FAILED[/]")
    con.print(t)

    if v.ranking and v.outcome == Outcome.INCONCLUSIVE:
        rt = Table("rank", "recipient", "score")
        for i, (u, s) in enumerate(v.ranking, 1):
            rt.add_row(str(i), str(u), f"{s:.0f}")
        con.print(rt)
    for n in v.notes:
        con.print(f"[dim]note:[/] {n}")


app.command(name="investigate")(investigate_)


# --------------------------------------------------------------------------

@ledger_app.command("list")
def ledger_list(home: Path = typer.Option(DEFAULT_HOME, "--home")):
    """Show every decryption record."""
    led = _led(home)
    t = Table("#", "recipient", "doc", "session", "when")
    for i, sr in led.all_records():
        r = sr.record
        t.add_row(str(i), r.recipient_user_id, r.doc_id[:10],
                  r.session_id[:10], r.timestamp[:19])
    con.print(t)
    con.print(f"tree size [bold]{led.size()}[/]  root [cyan]{led.root().hex()}[/]")


@ledger_app.command("verify")
def ledger_verify(home: Path = typer.Option(DEFAULT_HOME, "--home")):
    """Check the ledger has not been tampered with."""
    led = _led(home)
    tampered, idx, msg = led.detect_tamper()
    if tampered:
        con.print(Panel(f"[bold red]TAMPER DETECTED[/]\n{msg}"
                        + (f"\n\nfirst affected record: [bold]#{idx}[/]"
                           if idx is not None else ""),
                        border_style="red"))
        raise typer.Exit(2)
    sth = led.latest_sth()
    con.print(Panel(
        f"[green]ledger intact[/]\n{msg}\n"
        f"tree size : {sth['tree_size']}\n"
        f"root      : {sth['root'].hex()}\n"
        f"STH sig   : ML-DSA-65, {len(sth['signature'])} bytes "
        f"[green]verified[/]" if led.verify_sth(sth) else "[red]INVALID[/]",
        border_style="green"))


if __name__ == "__main__":
    app()
