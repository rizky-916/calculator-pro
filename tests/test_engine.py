"""Unit tests for the Calculator Pro engine (no GUI needed).

Run:  python -m unittest discover -s tests -v
"""

import os
import sys
import time
import unittest
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from calculator_pro import Calculator, CalculatorError, evaluate, format_number  # noqa: E402
from calculator_pro.engine import MAX_EXPRESSION_LENGTH, MAX_HISTORY  # noqa: E402


def calc(expr: str) -> str:
    return format_number(evaluate(expr))


class TestArithmetic(unittest.TestCase):
    def test_basic_operations(self):
        self.assertEqual(calc("1+2"), "3")
        self.assertEqual(calc("7-10"), "-3")
        self.assertEqual(calc("6*7"), "42")
        self.assertEqual(calc("9/3"), "3")
        self.assertEqual(calc("2+3*4"), "14")
        self.assertEqual(calc("(2+3)*4"), "20")

    def test_decimal_precision(self):
        self.assertEqual(calc("0.1+0.2"), "0.3")
        self.assertEqual(calc("1/3"), "0.333333333333333")

    def test_percent_and_implicit_multiplication(self):
        self.assertEqual(calc("50%"), "0.5")
        self.assertEqual(calc("200*10%"), "20")
        self.assertEqual(calc("2(3)"), "6")
        self.assertEqual(calc("2√9"), "6")

    def test_power(self):
        self.assertEqual(calc("2^10"), "1024")
        self.assertEqual(calc("2^3^2"), "512")        # right-associative
        self.assertEqual(calc("-2^2"), "-4")          # power before unary minus
        self.assertEqual(calc("(-2)^2"), "4")
        self.assertEqual(calc("2^-1"), "0.5")
        self.assertEqual(calc("4^0.5"), "2")

    def test_square_and_root(self):
        self.assertEqual(calc("3²"), "9")
        self.assertEqual(calc("3²²"), "81")
        self.assertEqual(calc("√16"), "4")
        self.assertEqual(calc("√(9+16)"), "5")
        self.assertEqual(calc("√√16"), "2")
        self.assertEqual(calc("√2"), "1.4142135623731")

    def test_formatting(self):
        self.assertEqual(format_number(Decimal("-0")), "0")
        self.assertEqual(format_number(Decimal("1E+2")), "100")
        self.assertEqual(format_number(Decimal("1E+20")), "1e+20")
        self.assertEqual(calc("10^-20000"), "0")


class TestErrors(unittest.TestCase):
    def assertCalcError(self, expr, message=None):
        with self.assertRaises(CalculatorError) as ctx:
            evaluate(expr)
        if message:
            self.assertEqual(str(ctx.exception), message)

    def test_math_errors(self):
        self.assertCalcError("1/0", "Cannot divide by zero")
        self.assertCalcError("0^-1", "Cannot divide by zero")
        self.assertCalcError("0^0", "0^0 is undefined")
        self.assertCalcError("√(0-4)", "Invalid input for √")
        self.assertCalcError("(-8)^(1/3)", "Invalid power")

    def test_huge_numbers_do_not_freeze(self):
        start = time.perf_counter()
        for expr in ("9^9^9", "9^9^9^9^9", "10^99999", "9e9999*9e9999", "(9^999)²²²²"):
            with self.subTest(expr=expr):
                self.assertCalcError(expr, "Number too large")
        self.assertLess(time.perf_counter() - start, 1.0)

    def test_invalid_syntax(self):
        for expr in ("", "1+", "(", "1.2.3", ")", "*2", "2 3", "9**9", "2^", "√", "^2"):
            with self.subTest(expr=expr):
                self.assertCalcError(expr)


class TestSecurity(unittest.TestCase):
    """Inputs that would be dangerous with eval() must be rejected."""

    MALICIOUS = [
        "__import__('os').system('echo hacked')",
        "open('secret.txt').read()",
        "().__class__.__bases__[0].__subclasses__()",
        "exec('print(1)')",
        "lambda: 1",
        "1; import os",
        "[1,2,3]",
        "0x1F",
        "1_000",
        "٣+1",   # Arabic-Indic digit three
        "2⁵",    # superscript five
        "1e",
        "e5",
    ]

    def test_code_injection_is_rejected(self):
        for expr in self.MALICIOUS:
            with self.subTest(expr=expr):
                with self.assertRaises(CalculatorError):
                    evaluate(expr)

    def test_limits(self):
        with self.assertRaises(CalculatorError):
            evaluate("1+" * MAX_EXPRESSION_LENGTH + "1")
        with self.assertRaises(CalculatorError):
            evaluate("(" * 60 + "1" + ")" * 60)
        with self.assertRaises(CalculatorError):
            evaluate("2^" * 60 + "1")
        with self.assertRaises(CalculatorError):
            evaluate("√" * 60 + "1")
        with self.assertRaises(CalculatorError):
            evaluate(None)  # type: ignore[arg-type]

    def test_insert_value_only_accepts_numbers(self):
        c = Calculator()
        for bad in ("__import__('os')", "1+1", "", "abc", None):
            c.insert_value(bad)  # type: ignore[arg-type]
        self.assertEqual(c.expression, "")

    def test_nothing_is_written_to_disk(self):
        before = set(os.listdir("."))
        c = Calculator()
        for key in "12+3=M+":
            c.press(key)
        self.assertEqual(before, set(os.listdir(".")))


class TestCalculatorInput(unittest.TestCase):
    def keys(self, *keys):
        c = Calculator()
        for key in keys:
            c.press(key)
        return c

    def test_simple_flow_and_history(self):
        c = self.keys("1", "2", "+", "3", "=")
        self.assertEqual(c.display, "15")
        self.assertEqual(c.previous, "12+3 =")
        self.assertEqual(c.history[0].expression, "12+3")
        self.assertEqual(c.history[0].result, "15")

    def test_history_is_limited(self):
        c = Calculator()
        for _ in range(MAX_HISTORY + 10):
            for key in ("1", "+", "1", "="):
                c.press(key)
        self.assertEqual(len(c.history), MAX_HISTORY)

    def test_lone_number_equals_adds_no_history(self):
        c = self.keys("5", "=")
        self.assertEqual(c.history, [])

    def test_new_number_after_equals_starts_fresh(self):
        self.assertEqual(self.keys("2", "+", "3", "=", "7").display, "7")
        self.assertEqual(self.keys("2", "+", "3", "=", "*", "2", "=").display, "10")

    def test_operators_cannot_double(self):
        self.assertEqual(self.keys("9", "*", "*", "9").expression, "9*9")
        self.assertEqual(self.keys("9", "^", "^", "9").expression, "9^9")
        self.assertEqual(self.keys("9", "*", "^", "2").expression, "9^2")
        self.assertEqual(self.keys("2", "^", "-", "1", "=").display, "0.5")

    def test_digits_and_decimal_point(self):
        self.assertEqual(self.keys("0", "0", "7").expression, "7")
        self.assertEqual(self.keys(".", "5", ".", "5").expression, "0.55")

    def test_scientific_keys(self):
        self.assertEqual(self.keys("9", "²", "=").display, "81")
        self.assertEqual(self.keys("√", "8", "1", "=").display, "9")
        self.assertEqual(self.keys("√", "(", "9", "+", "1", "6", "=").display, "5")
        self.assertEqual(self.keys("4", "INV").display, "0.25")
        self.assertEqual(self.keys("4", "INV").previous, "1/4 =")
        self.assertEqual(self.keys("2", "+", "2", "INV").previous, "1/(2+2) =")
        self.assertEqual(self.keys("0", "INV").error, "Cannot divide by zero")

    def test_negate(self):
        self.assertEqual(self.keys("5", "NEG").expression, "-5")
        self.assertEqual(self.keys("5", "NEG", "NEG").expression, "5")
        self.assertEqual(self.keys("3", "+", "5", "NEG").expression, "3+(-5")
        self.assertEqual(self.keys("3", "+", "5", "NEG", "=").display, "-2")
        self.assertEqual(self.keys("3", "+", "5", "NEG", "NEG").expression, "3+5")
        self.assertEqual(self.keys("2", "+", "3", "=", "NEG").display, "-5")

    def test_memory(self):
        c = self.keys("5", "M+", "3", "M+")
        self.assertEqual(c.memory_text, "8")
        c.press("2")
        c.press("M-")
        self.assertEqual(c.memory_text, "6")
        c.press("C")
        for key in ("1", "0", "-", "MR", "="):
            c.press(key)
        self.assertEqual(c.display, "4")
        c.press("MC")
        self.assertEqual(c.memory_text, "")
        c.press("MR")  # nothing stored: no change
        self.assertEqual(c.display, "4")

    def test_memory_add_evaluates_expression(self):
        c = self.keys("2", "+", "3", "M+")
        self.assertEqual(c.memory_text, "5")
        self.assertEqual(c.display, "5")

    def test_memory_with_invalid_expression_reports_error(self):
        c = self.keys("1", "/", "0", "M+")
        self.assertIsNone(c.memory)
        self.assertEqual(c.error, "Cannot divide by zero")

    def test_insert_value_from_history(self):
        c = self.keys("6", "*", "7", "=")
        c.press("C")
        c.press("1")
        c.press("+")
        c.insert_value(c.history[0].result)
        self.assertEqual(c.expression, "1+42")
        c.insert_value("-3")
        self.assertEqual(c.expression, "1+-3")
        self.assertEqual(self.keys("2", ")").expression, "2")

    def test_insert_negative_after_root(self):
        c = self.keys("√")
        c.insert_value("-4")
        self.assertEqual(c.expression, "√(-4)")

    def test_backspace_and_clear(self):
        self.assertEqual(self.keys("1", "2", "3", "BACK").expression, "12")
        self.assertEqual(self.keys("1", "+", "1", "=", "BACK").display, "0")
        self.assertEqual(self.keys("1", "2", "C").display, "0")

    def test_auto_close_parentheses(self):
        self.assertEqual(self.keys("(", "2", "+", "3", "*", "2", "=").display, "8")

    def test_error_keeps_input(self):
        c = self.keys("1", "/", "0", "=")
        self.assertEqual(c.error, "Cannot divide by zero")
        self.assertEqual(c.expression, "1/0")

    def test_unknown_keys_are_ignored(self):
        c = self.keys("a", "_", "import", "", None, "**", "1")
        self.assertEqual(c.expression, "1")

    def test_input_length_limit(self):
        c = self.keys(*["1"] * (MAX_EXPRESSION_LENGTH + 50))
        self.assertEqual(len(c.expression), MAX_EXPRESSION_LENGTH)
        self.assertEqual(c.error, "Input limit reached")

    def test_copy_text(self):
        self.assertEqual(Calculator().copy_text(), "0")
        self.assertEqual(self.keys("6", "*", "7", "=").copy_text(), "42")


if __name__ == "__main__":
    unittest.main()
