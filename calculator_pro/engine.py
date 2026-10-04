"""Safe arithmetic engine for Calculator Pro (no GUI code).

The engine never uses ``eval``/``exec``. Input is tokenized and parsed by a
small recursive-descent parser that only understands numbers and the
calculator's own operators. Calculations use :mod:`decimal`, so results such
as ``0.1 + 0.2`` come out as ``0.3``.

Supported syntax::

    +  -  *  /      basic operators (the symbols \u00d7 \u00f7 \u2212 also work)
    ^               power, right-associative (2^3^2 = 2^9)
    %               percent, postfix (50% = 0.5)
    ²               square, postfix (3² = 9)
    √               square root, prefix (√9 = 3, √(9+16) = 5)
    ( )             parentheses; a value followed by "(" or "√" multiplies

Grammar::

    expression := term (("+" | "-") term)*
    term       := factor (("*" | "/") factor | implicit_mul)*
    factor     := ("+" | "-") factor | power
    power      := postfix ("^" factor)?
    postfix    := primary ("%" | "²")*
    primary    := NUMBER | "(" expression ")" | "√" postfix
"""

from __future__ import annotations

import decimal
import re
from dataclasses import dataclass
from decimal import Decimal

__all__ = [
    "Calculator",
    "CalculatorError",
    "HistoryEntry",
    "evaluate",
    "format_number",
    "MAX_EXPRESSION_LENGTH",
    "MAX_HISTORY",
]

# ---------------------------------------------------------------------------
# Safety limits
# ---------------------------------------------------------------------------
MAX_EXPRESSION_LENGTH = 200   # characters accepted by the parser
MAX_NESTING_DEPTH = 50        # nested parentheses / unary signs / powers
MAX_EXPONENT = 10_000         # |result| must stay below 10**MAX_EXPONENT
DISPLAY_DIGITS = 15           # significant digits shown to the user
MAX_HISTORY = 50              # entries kept in the (in-memory) history

SQRT = "√"
SQUARE = "²"
TIMES = "×"
DIVIDE = "÷"
MINUS = "−"

_CONTEXT = decimal.Context(
    prec=34,
    Emax=MAX_EXPONENT,
    Emin=-MAX_EXPONENT,
    rounding=decimal.ROUND_HALF_UP,
    traps=[decimal.DivisionByZero, decimal.InvalidOperation, decimal.Overflow],
)

_SYMBOL_MAP = str.maketrans({TIMES: "*", DIVIDE: "/", MINUS: "-"})
_OPERATOR_CHARS = "+-*/^%()" + SQRT + SQUARE
_NUMBER_RE = re.compile(r"-?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?", re.IGNORECASE)


class CalculatorError(Exception):
    """Raised for any expression the calculator cannot evaluate.

    The message is short and safe to show directly to the user.
    """


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class _Token:
    kind: str          # "num" or "op"
    value: object      # Decimal for numbers, str for operators


def _tokenize(text: str) -> list[_Token]:
    tokens: list[_Token] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if ch in _OPERATOR_CHARS:
            tokens.append(_Token("op", ch))
            i += 1
            continue
        if ch in "0123456789.":
            start = i
            while i < n and text[i] in "0123456789.":
                i += 1
            # Optional exponent so displayed results like 1.5e+20 can be reused.
            if i < n and text[i] in "eE":
                j = i + 1
                if j < n and text[j] in "+-":
                    j += 1
                if j < n and text[j] in "0123456789":
                    while j < n and text[j] in "0123456789":
                        j += 1
                    i = j
            literal = text[start:i]
            if not _NUMBER_RE.fullmatch(literal):
                raise CalculatorError("Invalid number")
            tokens.append(_Token("num", Decimal(literal)))
            continue
        raise CalculatorError("Invalid character")
    return tokens


# ---------------------------------------------------------------------------
# Parser / evaluator
# ---------------------------------------------------------------------------
def _safe_power(base: Decimal, exponent: Decimal) -> Decimal:
    if base.is_zero() and exponent < 0:
        raise CalculatorError("Cannot divide by zero")
    if base.is_zero() and exponent.is_zero():
        raise CalculatorError("0^0 is undefined")
    if base < 0 and exponent != exponent.to_integral_value():
        raise CalculatorError("Invalid power")
    try:
        return base ** exponent   # Decimal power: fast, traps on overflow
    except decimal.InvalidOperation:
        raise CalculatorError("Invalid power") from None


def _safe_sqrt(value: Decimal) -> Decimal:
    if value < 0:
        raise CalculatorError("Invalid input for √")
    return value.sqrt()


class _Parser:
    def __init__(self, tokens: list[_Token]) -> None:
        self.tokens = tokens
        self.pos = 0
        self.depth = 0

    # -- helpers ----------------------------------------------------------
    def _peek(self) -> _Token | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def _is_op(self, *ops: str) -> bool:
        tok = self._peek()
        return tok is not None and tok.kind == "op" and tok.value in ops

    def _advance(self) -> _Token:
        tok = self._peek()
        if tok is None:
            raise CalculatorError("Incomplete expression")
        self.pos += 1
        return tok

    def _nested(self, parse_fn):
        self.depth += 1
        if self.depth > MAX_NESTING_DEPTH:
            raise CalculatorError("Expression too complex")
        try:
            return parse_fn()
        finally:
            self.depth -= 1

    # -- grammar ----------------------------------------------------------
    def parse(self) -> Decimal:
        if not self.tokens:
            raise CalculatorError("Empty expression")
        value = self._expression()
        if self._peek() is not None:
            raise CalculatorError("Invalid expression")
        return value

    def _expression(self) -> Decimal:
        value = self._term()
        while self._is_op("+", "-"):
            op = self._advance().value
            rhs = self._term()
            value = value + rhs if op == "+" else value - rhs
        return value

    def _term(self) -> Decimal:
        value = self._factor()
        while True:
            if self._is_op("*", "/"):
                op = self._advance().value
                rhs = self._factor()
                if op == "*":
                    value = value * rhs
                else:
                    if rhs.is_zero():
                        raise CalculatorError("Cannot divide by zero")
                    value = value / rhs
            elif self._is_op("(", SQRT):
                # Implicit multiplication: 2(3), (2)(3), 2√9
                value = value * self._power()
            else:
                return value

    def _factor(self) -> Decimal:
        if self._is_op("+", "-"):
            op = self._advance().value
            operand = self._nested(self._factor)
            return operand if op == "+" else -operand
        return self._power()

    def _power(self) -> Decimal:
        base = self._postfix()
        if self._is_op("^"):
            self._advance()
            exponent = self._nested(self._factor)  # right-associative
            return _safe_power(base, exponent)
        return base

    def _postfix(self) -> Decimal:
        value = self._primary()
        while self._is_op("%", SQUARE):
            op = self._advance().value
            value = value / 100 if op == "%" else value * value
        return value

    def _primary(self) -> Decimal:
        tok = self._advance()
        if tok.kind == "num":
            return tok.value  # type: ignore[return-value]
        if tok.value == "(":
            value = self._nested(self._expression)
            if not self._is_op(")"):
                raise CalculatorError("Missing closing parenthesis")
            self._advance()
            return value
        if tok.value == SQRT:
            return _safe_sqrt(self._nested(self._postfix))
        raise CalculatorError("Invalid expression")


def _check_result(value: Decimal) -> Decimal:
    with decimal.localcontext(_CONTEXT):
        value = +value  # apply precision/limits
    if not value.is_finite():
        raise CalculatorError("Number too large")
    return value


def evaluate(expression: str) -> Decimal:
    """Safely evaluate an arithmetic expression and return a ``Decimal``.

    Raises :class:`CalculatorError` with a user-friendly message on any
    problem (syntax error, division by zero, overflow, input too long...).
    """
    if not isinstance(expression, str):
        raise CalculatorError("Invalid expression")
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise CalculatorError("Expression too long")
    tokens = _tokenize(expression.translate(_SYMBOL_MAP))
    try:
        with decimal.localcontext(_CONTEXT):
            result = _Parser(tokens).parse()
        return _check_result(result)
    except decimal.DivisionByZero:
        raise CalculatorError("Cannot divide by zero") from None
    except decimal.Overflow:
        raise CalculatorError("Number too large") from None
    except decimal.InvalidOperation:
        raise CalculatorError("Invalid expression") from None
    except RecursionError:
        raise CalculatorError("Expression too complex") from None


def format_number(value: Decimal) -> str:
    """Format a result for display (max ``DISPLAY_DIGITS`` significant digits).

    Uses plain notation for "normal" sizes and scientific notation
    (e.g. ``1.5e+20``) for very large or very small numbers.
    """
    if value.is_zero():
        return "0"  # also hides "-0"
    ctx = _CONTEXT.copy()
    ctx.prec = DISPLAY_DIGITS
    rounded = ctx.plus(value)
    if rounded.is_zero():
        return "0"
    exponent = rounded.adjusted()
    if -7 <= exponent < DISPLAY_DIGITS:
        text = format(rounded, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text
    mantissa, _, exp = format(rounded, f".{DISPLAY_DIGITS - 1}e").partition("e")
    if "." in mantissa:
        mantissa = mantissa.rstrip("0").rstrip(".")
    sign = "-" if exp.startswith("-") else "+"
    return f"{mantissa}e{sign}{int(exp.lstrip('+-'))}"


def pretty(expression: str) -> str:
    """Replace ASCII operators with display symbols (\u00d7 and \u00f7)."""
    return expression.replace("*", TIMES).replace("/", DIVIDE)


# ---------------------------------------------------------------------------
# Calculator state (what happens when a key/button is pressed)
# ---------------------------------------------------------------------------
_BINARY_OPS = "+-*/^"
_VALUE_END = ")%" + SQUARE   # characters that end a value but are not digits


@dataclass(frozen=True)
class HistoryEntry:
    expression: str   # pretty expression, e.g. "12×3"
    result: str       # formatted result, e.g. "36"


class Calculator:
    """Keeps the text being typed, the memory and the history.

    Character keys accepted by :meth:`press`::

        "0"-"9" "." "+" "-" "*" "/" "^" "%" "(" ")" "√" "²"

    Command keys::

        "=" "C" "BACK" "NEG" (±) "INV" (1/x) "MC" "MR" "M+" "M-"

    Anything else is ignored, so the UI can safely forward raw key presses.
    Nothing is written to disk: memory and history live only in RAM.
    """

    def __init__(self) -> None:
        self.expression = ""            # ASCII expression being built
        self.previous = ""              # line above the display, e.g. "12+3 ="
        self.error = ""                 # last error message ("" if none)
        self.history: list[HistoryEntry] = []   # newest first
        self.memory: Decimal | None = None
        self._just_evaluated = False

    # -- public API -------------------------------------------------------
    @property
    def display(self) -> str:
        return pretty(self.expression) if self.expression else "0"

    @property
    def memory_text(self) -> str:
        return "" if self.memory is None else format_number(self.memory)

    def press(self, key: str) -> None:
        if not isinstance(key, str):
            return
        command = self._COMMANDS.get(key)
        if command is not None:
            command(self)
            return
        if len(key) != 1 or key not in "0123456789." + _OPERATOR_CHARS:
            return  # ignore unknown keys
        self._type_char(key)

    def clear(self) -> None:
        self.expression = ""
        self.previous = ""
        self.error = ""
        self._just_evaluated = False

    def clear_history(self) -> None:
        self.history.clear()

    def insert_value(self, text: str) -> None:
        """Insert a number (from memory or history) at the current position."""
        if not isinstance(text, str) or not _NUMBER_RE.fullmatch(text):
            return
        self.error = ""
        expr = self.expression
        if self._just_evaluated or not expr:
            self.expression = text
            self.previous = ""
            self._just_evaluated = True   # typing a digit starts fresh
            return
        last = expr[-1]
        number = self._current_number()
        if number:
            head = expr[: len(expr) - len(number)]
            new = head + text
        elif last == SQRT and text.startswith("-"):
            new = expr + "(" + text + ")"
        elif last in _BINARY_OPS or last in "(" + SQRT:
            new = expr + text
        elif last in _VALUE_END:
            new = expr + "*" + text
        else:
            return
        self._set_if_fits(new)

    def copy_text(self) -> str:
        """Text to put on the clipboard (the result or current expression)."""
        return self.expression if self.expression else "0"

    # -- character input --------------------------------------------------
    def _type_char(self, key: str) -> None:
        self.error = ""
        if self._just_evaluated:
            self._just_evaluated = False
            if key in "0123456789.(" + SQRT:
                self.expression = ""      # a new number starts fresh
            self.previous = ""

        if len(self.expression) >= MAX_EXPRESSION_LENGTH:
            self.error = "Input limit reached"
            return

        expr = self.expression
        last = expr[-1:]
        # Note: "" is "in" every string, so check `last` before membership tests.
        ends_value = bool(last) and last in _VALUE_END
        if key.isdigit():
            if ends_value:
                return  # an operator is needed first
            if self._current_number() == "0":
                self.expression = expr[:-1] + key   # no leading zeros
            else:
                self.expression += key
        elif key == ".":
            number = self._current_number()
            if "." in number or "e" in number.lower() or ends_value:
                return
            self.expression += "." if number else "0."
        elif key in _BINARY_OPS:
            self._append_operator(key)
        elif key in "%" + SQUARE:
            if last.isdigit() or ends_value:
                self.expression += key
            elif last == ".":
                self.expression = expr[:-1] + key if expr[:-1] else expr
        elif key == "(":
            self.expression += "("
        elif key == SQRT:
            if last == ".":
                expr = expr[:-1]
            self.expression = expr + SQRT
        elif key == ")":
            opened = expr.count("(") - expr.count(")")
            if opened > 0 and last not in ("(", SQRT, *_BINARY_OPS):
                self.expression += ")"

    def _append_operator(self, op: str) -> None:
        expr = self.expression
        last = expr[-1:]
        if not expr or last in "(" + SQRT:
            if op == "-":  # negative numbers: "-5", "(-5", "√-" is rejected later
                if last != SQRT:
                    self.expression += op
            return
        if last in _BINARY_OPS:
            if op == "-" and last in "*/^":
                self.expression += op  # allow "5*-2", "2^-1"
                return
            # Replace trailing operator(s): "5*" + "+" -> "5+". "**" can't form.
            stripped = expr.rstrip(_BINARY_OPS)
            if not stripped or stripped[-1] in "(" + SQRT:
                return
            self.expression = stripped + op
            return
        if last == ".":
            expr = expr[:-1]
        self.expression = expr + op

    def _current_number(self) -> str:
        """Return the number literal at the end of the expression ('' if none)."""
        expr = self.expression
        i = len(expr)
        while i > 0 and (expr[i - 1].isdigit() or expr[i - 1] in ".eE"):
            i -= 1
        if i > 1 and expr[i - 1] in "+-" and expr[i - 2] in "eE":   # "1e+5"
            i -= 2
            while i > 0 and (expr[i - 1].isdigit() or expr[i - 1] == "."):
                i -= 1
        return expr[i:]

    def _set_if_fits(self, new_expression: str) -> None:
        if len(new_expression) > MAX_EXPRESSION_LENGTH:
            self.error = "Input limit reached"
        else:
            self.expression = new_expression
            self._just_evaluated = False

    # -- commands ---------------------------------------------------------
    def _closed_expression(self) -> str:
        expr = self.expression
        missing = expr.count("(") - expr.count(")")
        if missing > 0 and expr[-1] not in _BINARY_OPS + "(" + SQRT:
            expr += ")" * missing
        return expr

    def _evaluate_current(self) -> tuple[str, Decimal] | None:
        """Evaluate the expression; on failure set ``error`` and return None."""
        if not self.expression:
            return None
        expr = self._closed_expression()
        try:
            return expr, evaluate(expr)
        except CalculatorError as exc:
            self.error = str(exc)
            return None

    def _show_result(self, label: str, value: Decimal) -> None:
        result = format_number(value)
        self.previous = f"{label} ="
        self.history.insert(0, HistoryEntry(label, result))
        del self.history[MAX_HISTORY:]
        self.expression = result
        self.error = ""
        self._just_evaluated = True

    def _equals(self) -> None:
        if _NUMBER_RE.fullmatch(self.expression):
            return  # a lone number: nothing to calculate, keep history clean
        evaluated = self._evaluate_current()
        if evaluated is not None:
            expr, value = evaluated
            self._show_result(pretty(expr), value)

    def _inverse(self) -> None:
        evaluated = self._evaluate_current()
        if evaluated is None:
            return
        expr, value = evaluated
        if value.is_zero():
            self.error = "Cannot divide by zero"
            return
        try:
            result = _check_result(Decimal(1) / value)
        except (decimal.Overflow, CalculatorError):
            self.error = "Number too large"
            return
        label = f"1/{expr}" if _NUMBER_RE.fullmatch(expr) and not expr.startswith("-") \
            else f"1/({pretty(expr)})"
        self._show_result(label, result)

    def _negate(self) -> None:
        self.error = ""
        expr = self.expression
        if _NUMBER_RE.fullmatch(expr):           # the whole display is one number
            if expr in ("0", "-0"):
                return
            self.expression = expr[1:] if expr.startswith("-") else "-" + expr
            return
        number = self._current_number()
        if number:
            head = expr[: len(expr) - len(number)]
            if head.endswith("(-"):
                self.expression = head[:-2] + number
            else:
                self._set_if_fits(head + "(-" + number)
        elif not expr:
            self.expression = "-"
        elif expr[-1] in _BINARY_OPS + "(" + SQRT:
            self._set_if_fits(expr + "(-")

    def _backspace(self) -> None:
        self.error = ""
        if self._just_evaluated:
            self.clear()
        else:
            self.expression = self.expression[:-1]

    def _memory_add(self, sign: int) -> None:
        evaluated = self._evaluate_current()
        if evaluated is None:
            return
        _, value = evaluated
        current = self.memory if self.memory is not None else Decimal(0)
        try:
            with decimal.localcontext(_CONTEXT):
                new_memory = _check_result(current + value if sign > 0 else current - value)
        except (decimal.Overflow, CalculatorError):
            self.error = "Number too large"
            return
        self.memory = new_memory
        self.expression = format_number(value)
        self.previous = ""
        self._just_evaluated = True

    def _memory_recall(self) -> None:
        if self.memory is not None:
            self.insert_value(format_number(self.memory))

    def _memory_clear(self) -> None:
        self.memory = None

    _COMMANDS = {
        "C": clear,
        "=": _equals,
        "BACK": _backspace,
        "NEG": _negate,
        "INV": _inverse,
        "MC": _memory_clear,
        "MR": _memory_recall,
        "M+": lambda self: self._memory_add(+1),
        "M-": lambda self: self._memory_add(-1),
    }
