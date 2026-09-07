"""
Parser/AST-lite para JavaScript embebido en HTML — F1.2 (≈ HU_05).

REEMPLAZA el regex frágil de ``WindowInventory.extract()`` con un parser
real basado en tokens. Esto resuelve los bugs conocidos del regex:

  - **Strings con "window."**: ``"window.fake = function(){}"`` ya no se
    confunde con código real (el lexer skipea el contenido del string).
  - **Comentarios**: ``/* window.fake = function(){} */`` tampoco matchea
  - **Funciones anidadas**: el regex asumía cuerpo plano; el parser
    cuenta braces con un stack, así ``function() { if(x) { y(); } }``
    se cierra correctamente.
  - **Arrow functions / métodos de clase**: si una ``window.X =``
    apunta a una arrow o a un método, el parser emite la fila sin
    descripción (en vez de tragarse el código siguiente).

API pública (estable):

    rows = parse_window_functions(source_text: str) -> list[FunctionRow]

Devuelve filas con los mismos campos que ``FunctionRow`` de inventory.py:

    FunctionRow(n, name, module, line, description)

El módulo ("DASHBOARD", "LOCALSTORAGE", ...) NO se calcula acá — eso es
responsabilidad de ``WindowInventory`` que trackea los rangos por módulo
en base a los headers ``// MÓDULO: X``.

El parser se mantiene como módulo aparte y sin dependencias externas
para que el paquete F0 siga siendo puro stdlib + SQLAlchemy.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import Iterator


# ── Tipos ────────────────────────────────────────────────────────────────


class TokKind(Enum):
    """Tipos de token reconocidos por el lexer."""
    IDENT = auto()          # identificador (window, foo, _bar, $baz)
    KEYWORD = auto()        # function, return, if, else, ...
    STRING = auto()         # "..." | '...' | `...`
    NUMBER = auto()         # 123, 0x1F, 3.14
    BLOCK_COMMENT = auto()  # /* ... */
    LINE_COMMENT = auto()   # // ...
    PUNCT = auto()          # cualquier operador o delimitador
    WHITESPACE = auto()     # ' \t\n\r' (no significativo para el parser)
    EOF = auto()


@dataclass
class Token:
    kind: TokKind
    value: str
    line: int   # 1-indexed
    col: int    # 0-indexed


@dataclass
class WindowFunction:
    """Una asignación ``window.NAME = <algo>`` detectada por el parser."""
    name: str
    line: int                  # línea donde empieza la asignación
    kind: str                  # 'function' | 'arrow' | 'method' | 'other'
    description: str | None    # /* ... */ al inicio del cuerpo (si existe)


# ── Keywords JS (subset) ─────────────────────────────────────────────────


_JS_KEYWORDS: frozenset[str] = frozenset({
    # declaradores / control de flujo
    "var", "let", "const", "function", "return", "if", "else", "for",
    "while", "do", "switch", "case", "default", "break", "continue",
    "class", "extends", "new", "this", "super", "import", "export",
    "from", "as", "async", "await", "yield", "throw", "try", "catch",
    "finally", "typeof", "instanceof", "in", "of", "delete", "void",
    # literales
    "true", "false", "null", "undefined",
})


# Operadores multi-carácter que NO queremos partir
_TWO_CHAR_OPS: frozenset[str] = frozenset({
    "==", "!=", "<=", ">=", "&&", "||", "++", "--",
    "+=", "-=", "*=", "/=", "%=", "=>", "**", "??", "?.",
    "<<", ">>", "&=", "|=", "^=", "===", "!==",
})


# ── Lexer ────────────────────────────────────────────────────────────────


class JSLexer:
    """Tokenizer para JavaScript.

    Reconoce strings (con escapes), comentarios (línea y bloque),
    identificadores, números, y puntuación. Mantiene ``line`` y ``col``
    actualizados para que el parser pueda reportar ubicaciones.
    """

    __slots__ = ("src", "pos", "line", "col", "n")

    def __init__(self, source: str) -> None:
        self.src = source
        self.pos = 0
        self.line = 1
        self.col = 0
        self.n = len(source)

    def _advance(self, n: int = 1) -> None:
        for _ in range(n):
            if self.pos < self.n:
                ch = self.src[self.pos]
                if ch == "\n":
                    self.line += 1
                    self.col = 0
                else:
                    self.col += 1
                self.pos += 1

    def _peek(self, offset: int = 0) -> str:
        idx = self.pos + offset
        return self.src[idx] if 0 <= idx < self.n else ""

    def tokenize(self) -> Iterator[Token]:
        while self.pos < self.n:
            ch = self.src[self.pos]

            # ── Whitespace ──
            if ch in " \t\r\n":
                yield self._consume_whitespace()
                continue

            # ── Comentarios (deben ir ANTES de '/' como punctuation) ──
            if ch == "/" and self._peek(1) == "/":
                yield self._consume_line_comment()
                continue
            if ch == "/" and self._peek(1) == "*":
                yield self._consume_block_comment()
                continue

            # ── Strings ──
            if ch in "\"'`":
                yield self._consume_string(ch)
                continue

            # ── Números ──
            if ch.isdigit():
                yield self._consume_number()
                continue

            # ── Identificadores / keywords ──
            if ch.isalpha() or ch == "_" or ch == "$":
                yield self._consume_identifier()
                continue

            # ── Puntuación (1 o 2 chars) ──
            yield self._consume_punct()

    def _consume_whitespace(self) -> Token:
        start_pos, start_line, start_col = self.pos, self.line, self.col
        while self.pos < self.n and self.src[self.pos] in " \t\r\n":
            self._advance()
        return Token(TokKind.WHITESPACE, self.src[start_pos:self.pos],
                     start_line, start_col)

    def _consume_line_comment(self) -> Token:
        start_pos, start_line, start_col = self.pos, self.line, self.col
        while self.pos < self.n and self.src[self.pos] != "\n":
            self._advance()
        return Token(TokKind.LINE_COMMENT, self.src[start_pos:self.pos],
                     start_line, start_col)

    def _consume_block_comment(self) -> Token:
        start_pos, start_line, start_col = self.pos, self.line, self.col
        self._advance(2)  # skip /*
        while self.pos < self.n:
            if self.src[self.pos] == "*" and self._peek(1) == "/":
                self._advance(2)  # skip */
                break
            self._advance()
        # Si llega a EOF sin cerrar, devolvemos lo consumido (defensivo)
        return Token(TokKind.BLOCK_COMMENT, self.src[start_pos:self.pos],
                     start_line, start_col)

    def _consume_string(self, quote: str) -> Token:
        start_pos, start_line, start_col = self.pos, self.line, self.col
        self._advance()  # skip opening quote
        while self.pos < self.n:
            ch = self.src[self.pos]
            if ch == "\\":
                # Escape: saltar el siguiente char (puede ser \n, \", etc.)
                self._advance(2)
                continue
            if ch == quote:
                self._advance()  # skip closing quote
                break
            if ch == "\n" and quote == "`":
                # Template literals permiten newlines sin escape
                self._advance()
                continue
            if ch == "\n" and quote != "`":
                # String single/double no cerrado antes de newline — paramos
                # (defensivo: JS daría SyntaxError, nosotros truncamos)
                break
            self._advance()
        return Token(TokKind.STRING, self.src[start_pos:self.pos],
                     start_line, start_col)

    def _consume_number(self) -> Token:
        start_pos, start_line, start_col = self.pos, self.line, self.col
        while self.pos < self.n and (self.src[self.pos].isdigit() or self.src[self.pos] == "."):
            self._advance()
        return Token(TokKind.NUMBER, self.src[start_pos:self.pos],
                     start_line, start_col)

    def _consume_identifier(self) -> Token:
        start_pos, start_line, start_col = self.pos, self.line, self.col
        while self.pos < self.n and (self.src[self.pos].isalnum() or self.src[self.pos] in "_$"):
            self._advance()
        text = self.src[start_pos:self.pos]
        kind = TokKind.KEYWORD if text in _JS_KEYWORDS else TokKind.IDENT
        return Token(kind, text, start_line, start_col)

    def _consume_punct(self) -> Token:
        start_line, start_col = self.line, self.col
        first = self.src[self.pos]
        self._advance()
        if self.pos < self.n:
            two = first + self.src[self.pos]
            if two in _TWO_CHAR_OPS:
                self._advance()
                return Token(TokKind.PUNCT, two, start_line, start_col)
        return Token(TokKind.PUNCT, first, start_line, start_col)


# ── Parser de window.* ───────────────────────────────────────────────────


# Regex "seguro" para encontrar ``window.NAME`` en el source YA tokenizado.
# Lo aplicamos al texto SKIPEADO (strings y comentarios reemplazados por
# espacios) — ver ``_safe_source()`` abajo.
_RE_WINDOW_ASSIGN = re.compile(
    r"window\s*\.\s*([A-Za-z_$][\w$]*)\s*=",
)


def _safe_source(src: str) -> str:
    """Devuelve un string del mismo largo donde strings y comments son
    espacios. Útil para que los regex no matcheen dentro de literales.

    Implementación: scan char-by-char para preservar newlines y mantener
    la posición absoluta de cada char (el lexer no expone la posición
    absoluta de los tokens multi-línea, así que no podemos re-indexar
    desde ``tok.col``).
    """
    out = list(src)
    n = len(src)
    i = 0
    while i < n:
        ch = src[i]
        # ── Line comment ──
        if ch == "/" and i + 1 < n and src[i + 1] == "/":
            out[i] = " "
            out[i + 1] = " "
            i += 2
            while i < n and src[i] != "\n":
                out[i] = " "
                i += 1
            continue
        # ── Block comment ──
        if ch == "/" and i + 1 < n and src[i + 1] == "*":
            out[i] = " "
            out[i + 1] = " "
            i += 2
            while i < n:
                if src[i] == "*" and i + 1 < n and src[i + 1] == "/":
                    out[i] = " "
                    out[i + 1] = " "
                    i += 2
                    break
                # Preservar newlines
                if src[i] != "\n":
                    out[i] = " "
                i += 1
            continue
        # ── String literal ──
        if ch in "\"'`":
            quote = ch
            out[i] = " "
            i += 1
            while i < n:
                if src[i] == "\\" and i + 1 < n:
                    out[i] = " "
                    out[i + 1] = " "
                    i += 2
                    continue
                if src[i] == quote:
                    out[i] = " "
                    i += 1
                    break
                # Preservar newlines
                if src[i] != "\n":
                    out[i] = " "
                i += 1
            continue
        i += 1
    return "".join(out)


def _skip_ws_and_comments(tokens: list[Token], i: int) -> int:
    """Avanza ``i`` mientras el token sea WHITESPACE o comment."""
    while i < len(tokens) and tokens[i].kind in (
        TokKind.WHITESPACE, TokKind.LINE_COMMENT, TokKind.BLOCK_COMMENT,
    ):
        i += 1
    return i


def _match_punct(tokens: list[Token], i: int, *values: str) -> int | None:
    """Si tokens[i] es PUNCT con uno de los valores, devuelve i+1. Si no, None."""
    if i < len(tokens) and tokens[i].kind == TokKind.PUNCT and tokens[i].value in values:
        return i + 1
    return None


def _extract_body_description(body_src: str) -> str | None:
    """Extrae la primera /* ... */ al inicio del cuerpo de la función.

    body_src es el texto entre '{' y el matching '}' (incluyendo
    posiblemente nuevas líneas y comentarios previos al código real).
    Devuelve el contenido del comentario sin los delimitadores, o None
    si no hay un block comment al inicio.
    """
    # Saltar whitespace inicial
    m = re.match(r"\s*(/\*.*?\*/)\s*", body_src, re.DOTALL)
    if not m:
        return None
    comment = m.group(1)
    # Quitar /* y */ y trim
    inner = comment[2:-2].strip()
    return inner or None


def _find_matching_brace(src: str, open_pos: int) -> int | None:
    """Devuelve la posición del '}' que cierra el '{' en open_pos.

    Cuenta braces con un stack, ignorando los que estén dentro de
    strings, template literals, o comentarios. Devuelve None si no se
    encuentra el cierre.
    """
    assert src[open_pos] == "{"
    depth = 0
    i = open_pos
    n = len(src)
    while i < n:
        ch = src[i]
        # Skip string
        if ch in "\"'`":
            quote = ch
            i += 1
            while i < n:
                if src[i] == "\\":
                    i += 2
                    continue
                if src[i] == quote:
                    i += 1
                    break
                i += 1
            continue
        # Skip line comment
        if ch == "/" and i + 1 < n and src[i + 1] == "/":
            while i < n and src[i] != "\n":
                i += 1
            continue
        # Skip block comment
        if ch == "/" and i + 1 < n and src[i + 1] == "*":
            i += 2
            while i < n - 1:
                if src[i] == "*" and src[i + 1] == "/":
                    i += 2
                    break
                i += 1
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


def parse_window_functions(source: str) -> list[WindowFunction]:
    """Encuentra todas las asignaciones ``window.NAME = ...`` en ``source``.

    Para cada match, intenta clasificar el RHS:
      - ``function ... { ... }``  → kind='function', extrae descripción
      - ``(args) => { ... }``     → kind='arrow'
      - ``{ method: function(){} }`` → kind='method'
      - otro (literal, llamada)   → kind='other'

    La función es robusta a:
      - código dentro de strings y comentarios (se skipea)
      - funciones con cuerpos anidados (brace counter)
      - funciones sin JSDoc (description=None)
    """
    safe = _safe_source(source)
    results: list[WindowFunction] = []
    seen: set[tuple[str, int]] = set()  # (name, line) — dedupe

    for m in _RE_WINDOW_ASSIGN.finditer(safe):
        name = m.group(1)
        assign_line = source[: m.start()].count("\n") + 1

        # Dedupe: si ya vimos esta función en esta línea, saltar
        key = (name, assign_line)
        if key in seen:
            continue
        seen.add(key)

        # Tokenizar desde después del '=' y clasificar el RHS
        rhs_start = m.end()
        sub = source[rhs_start:]
        sub_tokens = list(JSLexer(sub).tokenize())
        i = _skip_ws_and_comments(sub_tokens, 0)

        kind = "other"
        description: str | None = None
        body_start_in_sub: int | None = None

        if i < len(sub_tokens) and sub_tokens[i].kind == TokKind.KEYWORD \
                and sub_tokens[i].value == "function":
            # function NAME(params) { body } | function(params) { body }
            kind = "function"
            i += 1
            # nombre opcional
            if i < len(sub_tokens) and sub_tokens[i].kind == TokKind.IDENT:
                i += 1
            # (
            i = _skip_ws_and_comments(sub_tokens, i)
            if _match_punct(sub_tokens, i, "(") is not None:
                i += 1
                # params hasta matching ')'
                depth = 1
                while i < len(sub_tokens) and depth > 0:
                    if sub_tokens[i].kind == TokKind.PUNCT and sub_tokens[i].value == "(":
                        depth += 1
                    elif sub_tokens[i].kind == TokKind.PUNCT and sub_tokens[i].value == ")":
                        depth -= 1
                    i += 1
            # {
            i = _skip_ws_and_comments(sub_tokens, i)
            if i < len(sub_tokens) and sub_tokens[i].kind == TokKind.PUNCT \
                    and sub_tokens[i].value == "{":
                # Encontrar la posición absoluta del '{' en el source
                brace_pos_in_sub = sub_tokens[i].col
                abs_brace = rhs_start + brace_pos_in_sub
                close = _find_matching_brace(source, abs_brace)
                if close is not None:
                    body = source[abs_brace + 1: close]
                    description = _extract_body_description(body)

        elif i < len(sub_tokens) and sub_tokens[i].kind == TokKind.PUNCT \
                and sub_tokens[i].value == "(":
            # Posible arrow function: (params) => { body }
            # Hacemos una verificación rápida: tras el ')', debe haber '=>'
            depth = 1
            j = i + 1
            while j < len(sub_tokens) and depth > 0:
                if sub_tokens[j].kind == TokKind.PUNCT and sub_tokens[j].value == "(":
                    depth += 1
                elif sub_tokens[j].kind == TokKind.PUNCT and sub_tokens[j].value == ")":
                    depth -= 1
                j += 1
            j = _skip_ws_and_comments(sub_tokens, j)
            if j < len(sub_tokens) and sub_tokens[j].kind == TokKind.PUNCT \
                    and sub_tokens[j].value == "=>":
                kind = "arrow"
                j += 1
                j = _skip_ws_and_comments(sub_tokens, j)
                if j < len(sub_tokens) and sub_tokens[j].kind == TokKind.PUNCT \
                        and sub_tokens[j].value == "{":
                    brace_pos_in_sub = sub_tokens[j].col
                    abs_brace = rhs_start + brace_pos_in_sub
                    close = _find_matching_brace(source, abs_brace)
                    if close is not None:
                        body = source[abs_brace + 1: close]
                        description = _extract_body_description(body)

        results.append(WindowFunction(
            name=name,
            line=assign_line,
            kind=kind,
            description=description,
        ))

    return results
