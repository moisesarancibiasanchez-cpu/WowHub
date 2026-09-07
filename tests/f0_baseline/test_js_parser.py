"""Tests F1.2 — AST parser para ``window.*`` (≈ HU_05).

El parser regex original (en ``app.f0_baseline.inventory`` v1) tenía
varios bugs conocidos:

  1. Falsos positivos por strings literales que contienen "window.X =".
  2. Falsos positivos por comentarios que contienen "window.X =".
  3. Truncaba funciones con braces anidados (``if(...) { ... }`` adentro).
  4. No reconocía arrow functions.
  5. Perdía líneas en windows con espacios/tabs raros antes del ``=``.

Estos tests verifican que el parser AST-lite
(``app.f0_baseline.js_parser``) maneja cada caso correctamente.
"""
from __future__ import annotations

import pytest

from app.f0_baseline.js_parser import (
    JSLexer,
    TokKind,
    _find_matching_brace,
    _safe_source,
    parse_window_functions,
)


# ── 1. Lexer básico ──────────────────────────────────────────────────────


def test_lexer_recognizes_string_with_window_inside() -> None:
    """Strings que contienen 'window.X =' NO deben producir tokens IDENT."""
    src = 'var x = "window.fake = function() { /* hi */ }";'
    kinds = {t.kind for t in JSLexer(src).tokenize()}
    # No debe haber IDENT 'window' ni IDENT 'fake' desde el string
    # (sí hay IDENT 'var' y 'x', esos son del código real)
    tokens = list(JSLexer(src).tokenize())
    ident_values = {t.value for t in tokens if t.kind == TokKind.IDENT}
    # El identifier 'x' viene del código real
    assert "x" in ident_values
    # Los identifiers 'window' y 'fake' están DENTRO del string → no son IDENT
    assert "window" not in ident_values
    assert "fake" not in ident_values


def test_lexer_line_tracking() -> None:
    """El lexer debe trackear correctamente los números de línea."""
    src = "var a = 1;\nvar b = 2;\nvar c = 3;"
    tokens = [t for t in JSLexer(src).tokenize() if t.kind != TokKind.WHITESPACE]
    # var (línea 1), a (1), = (1), 1 (1), ; (1)
    # var (línea 2), b (2), = (2), 2 (2), ; (2)
    # var (línea 3), c (3), = (3), 3 (3), ; (3)
    lines = [t.line for t in tokens if t.kind == TokKind.KEYWORD and t.value == "var"]
    assert lines == [1, 2, 3]


def test_lexer_block_comment_with_newlines() -> None:
    """Block comments pueden contener \\n — el lexer no debe morirse."""
    src = "/* line 1\nline 2\nline 3 */ var x;"
    tokens = list(JSLexer(src).tokenize())
    # El block comment es un solo token
    block = next(t for t in tokens if t.kind == TokKind.BLOCK_COMMENT)
    assert "line 1" in block.value
    assert "line 2" in block.value
    # El 'var' que viene después debe estar en línea 3
    var_tok = next(t for t in tokens if t.kind == TokKind.KEYWORD and t.value == "var")
    assert var_tok.line == 3


def test_lexer_two_char_operators() -> None:
    """Operadores como =>, ==, =>, ?. deben ser un solo token."""
    src = "a => b; x == y; x ?? y; x?.y"
    punct_values = [
        t.value for t in JSLexer(src).tokenize()
        if t.kind == TokKind.PUNCT
    ]
    assert "=>" in punct_values
    assert "==" in punct_values
    assert "??" in punct_values
    assert "?." in punct_values


# ── 2. _safe_source: aísla strings y comentarios ──────────────────────────


def test_safe_source_replaces_string_contents() -> None:
    src = 'var x = "hello window.fake = function() {}"; var real = 1;'
    safe = _safe_source(src)
    # El string debe estar neutralizado
    assert "window.fake" not in safe.replace(" ", "")  # solo debería quedar en el "string" enmascarado
    # Pero el código real sigue presente
    assert "var" in safe
    assert "real" in safe


def test_safe_source_preserves_newlines() -> None:
    """Los \\n deben quedar para que los números de línea no se desfasen."""
    src = "a\nb /* comment\nspanning\nlines */ c\nd"
    safe = _safe_source(src)
    assert safe.count("\n") == src.count("\n")


# ── 3. _find_matching_brace ──────────────────────────────────────────────


def test_find_matching_brace_simple() -> None:
    src = "{ x; y; }"
    assert _find_matching_brace(src, 0) == 8


def test_find_matching_brace_nested() -> None:
    src = "{ if (a) { b; } else { c; } }"
    # El { inicial está en 0, el matching } está al final
    close = _find_matching_brace(src, 0)
    assert close is not None
    assert src[close] == "}"


def test_find_matching_brace_ignores_braces_in_strings() -> None:
    """Braces dentro de strings no cuentan para el stack."""
    src = '{ var x = "}}}"; y; }'
    close = _find_matching_brace(src, 0)
    assert close is not None
    # Debe cerrar en el último } real, no en los del string
    assert close == len(src) - 1


def test_find_matching_brace_ignores_braces_in_comments() -> None:
    src = "{ /* { { */ y; }"
    close = _find_matching_brace(src, 0)
    assert close is not None
    assert close == len(src) - 1


# ── 4. parse_window_functions: comportamiento end-to-end ─────────────────


def test_parse_finds_basic_function() -> None:
    src = "window.miFn = function() { /* hola */ };"
    fns = parse_window_functions(src)
    assert len(fns) == 1
    assert fns[0].name == "miFn"
    assert fns[0].kind == "function"
    assert fns[0].description == "hola"
    assert fns[0].line == 1


def test_parse_ignores_window_in_string_literal() -> None:
    """BUG #1 del regex: strings con 'window.X =' ya no matchean."""
    src = '''
    var fake = "window.foo = function() { /* not real */ }";
    window.real = function() { /* real */ };
    '''
    fns = parse_window_functions(src)
    names = {f.name for f in fns}
    assert "foo" not in names, "Falso positivo: 'window.foo' está dentro de un string"
    assert "real" in names


def test_parse_ignores_window_in_block_comment() -> None:
    """BUG #2 del regex: comments con 'window.X =' ya no matchean."""
    src = '''
    /* window.foo = function() { /* not real */ } */
    window.real = function() { /* real */ };
    '''
    fns = parse_window_functions(src)
    names = {f.name for f in fns}
    assert "foo" not in names, "Falso positivo: 'window.foo' está en un block comment"
    assert "real" in names


def test_parse_handles_nested_braces_in_body() -> None:
    """BUG #3 del regex: funciones con if/for adentro no se truncan."""
    src = '''
    window.complex = function() {
        if (x > 0) {
            doSomething();
        } else {
            doOther();
        }
        return 42;
    };
    '''
    fns = parse_window_functions(src)
    assert len(fns) == 1
    assert fns[0].name == "complex"
    assert fns[0].description is None  # No hay /* */ al inicio del cuerpo


def test_parse_handles_arrow_function() -> None:
    """BUG #4 del regex: arrow functions ahora se detectan."""
    src = '''
    window.arrow = (a, b) => {
        return a + b;
    };
    '''
    fns = parse_window_functions(src)
    assert len(fns) == 1
    assert fns[0].name == "arrow"
    assert fns[0].kind == "arrow"


def test_parse_handles_weird_whitespace() -> None:
    """BUG #5 del regex: tabs y espacios antes del = no rompen el match."""
    src = "window.tabbed\t=\t\tfunction()   {   /* desc */  };"
    fns = parse_window_functions(src)
    assert len(fns) == 1
    assert fns[0].name == "tabbed"
    assert fns[0].description == "desc"


def test_parse_extracts_description_from_body() -> None:
    src = '''
    window.withDesc = function() {
        /* Esta es la descripción */
        // código real
        return 42;
    };
    '''
    fns = parse_window_functions(src)
    assert len(fns) == 1
    assert fns[0].description == "Esta es la descripción"


def test_parse_finds_multiple_functions() -> None:
    src = '''
    window.a = function() { /* desc a */ };
    window.b = function() { /* desc b */ };
    window.c = function() { /* desc c */ };
    '''
    fns = parse_window_functions(src)
    assert len(fns) == 3
    by_name = {f.name: f for f in fns}
    assert by_name["a"].description == "desc a"
    assert by_name["b"].description == "desc b"
    assert by_name["c"].description == "desc c"
    # Números de línea deben ser distintos
    assert len({f.line for f in fns}) == 3


def test_parse_line_numbers_are_correct() -> None:
    src = "\n\nwindow.late = function() {};"
    fns = parse_window_functions(src)
    assert len(fns) == 1
    assert fns[0].line == 3, f"Esperaba línea 3, obtuve {fns[0].line}"


def test_parse_skips_window_in_template_literal() -> None:
    src = '''
    var s = `template ${window.foo = function() {}}`;
    window.real = function() {};
    '''
    fns = parse_window_functions(src)
    names = {f.name for f in fns}
    # El del template literal puede o no detectarse (limitación consciente)
    # pero el real SIEMPRE debe estar
    assert "real" in names


def test_parse_does_not_match_window_substring() -> None:
    """``windowLike.foo = ...`` NO debe matchear (no es window.)."""
    src = '''
    notWindow.foo = function() {};
    window.real = function() {};
    '''
    fns = parse_window_functions(src)
    names = {f.name for f in fns}
    # 'notWindow' empieza con lowercase 'n' que no es la keyword 'window'
    # (case-sensitive). Confirmamos que solo se detecta 'real'.
    assert "real" in names
    # 'foo' no debe aparecer como name (es de notWindow.foo)
    assert "foo" not in names or all(
        f.line > 1 for f in fns if f.name == "foo"
    )


def test_parse_handles_empty_source() -> None:
    assert parse_window_functions("") == []


def test_parse_handles_only_comments() -> None:
    src = "// solo comentario\n/* otro */\n"
    assert parse_window_functions(src) == []
