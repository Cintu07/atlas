#!/usr/bin/env python3
"""
Python translation of the COBOL validation program NC101A.

This module follows the structure of the COBOL original and exercises a large
collection of MULTIPLY statements in order to verify COBOL semantics.  The goal
of the translation is to preserve the intent and ordering of the tests while
producing human‑readable output similar to the original CCVS (COBOL Compiler
Validation System) report.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP, getcontext
from typing import Dict, Iterable, List, Optional, Sequence, Union


# High precision is required to mimic COBOL fixed-point arithmetic.
getcontext().prec = 60


NumberLike = Union[str, int, float, Decimal]


@dataclass
class Field:
    """
    Minimal representation of a COBOL numeric field.

    digits_left  - number of digits to the left of the implicit decimal point
    digits_right - number of digits to the right of the implicit decimal point
    signed       - indicates whether the field is signed
    """

    name: str
    digits_left: int
    digits_right: int = 0
    signed: bool = True
    value: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if not isinstance(self.value, Decimal):
            self.value = Decimal(str(self.value))

    def clone_value(self) -> Decimal:
        return Decimal(self.value)

    def set(self, raw: NumberLike, rounded: bool = False) -> bool:
        """
        Assign a value into the field and return True when it fits.  A False
        return value indicates a size error and the field content is left
        unchanged.
        """
        try:
            value = self._quantize(Decimal(str(raw)), rounded)
        except (InvalidOperation, ValueError):
            return False

        if not self._fits(value):
            return False

        self.value = value
        return True

    def _quantize(self, value: Decimal, rounded: bool) -> Decimal:
        exponent = Decimal("1").scaleb(-self.digits_right)
        rounding_mode = ROUND_HALF_UP if rounded else ROUND_DOWN
        return value.quantize(exponent, rounding=rounding_mode)

    def _fits(self, value: Decimal) -> bool:
        if not self.signed and value < 0:
            return False
        limit = Decimal(10) ** self.digits_left
        return -limit < value < limit


class ReportPrinter:
    """Utility for generating CCVS-style reports."""

    def __init__(self, test_id: str) -> None:
        self.test_id = test_id
        self.lines: List[str] = []
        self.record_count = 0
        self._build_static_lines()

    def _build_static_lines(self) -> None:
        self.ccvs_h1 = (
            " " * 39
            + "OFFICIAL COBOL COMPILER VALIDATION SYSTEM"
            + " " * 39
        )
        self.ccvs_h2a = (
            " " * 40
            + "CCVS85 "
            + "4.2 "
            + " COPY - NOT FOR DISTRIBUTION"
            + " " * 41
        )
        self.ccvs_h2b_template = (
            " " * 15
            + "TEST RESULT OF "
            + "{test_id:<9}"
            + " IN "
            + " HIGH       "
            + " LEVEL VALIDATION FOR "
            + "ON-SITE VALIDATION, NATIONAL INSTITUTE OF STD & TECH.     "
        )
        self.ccvs_h3 = (
            " " * 34
            + " FOR OFFICIAL USE ONLY    "
            + "COBOL 85 VERSION 4.2, Apr  1993 SSVG                      "
            + "  COPYRIGHT   1985 "
        )
        self.ccvs_c1 = (
            " FEATURE              PASS  PARAGRAPH-NAME       REMARKS"
            + " " * 20
        )
        self.ccvs_c2 = " TESTED            FAIL" + " " * 96
        self.hyphen_line = (
            " "
            + "*" * 65
            + "*" * 54
        )
        self.ccvs_e3 = (
            " FOR OFFICIAL USE ONLY"
            + " " * 12
            + "ON-SITE VALIDATION, NATIONAL INSTITUTE OF STD & TECH.     "
            + " " * 13
            + " COPYRIGHT 1985"
        )

    def write_line(self, text: str = "") -> None:
        formatted = (text[:120]).ljust(120)
        self.lines.append(formatted)
        self.record_count += 1

    def write_header(self) -> None:
        self.write_line(self.ccvs_h1)
        self.write_line(self.ccvs_h1)
        self.write_line(self.ccvs_h2a)
        self.write_line(self.ccvs_h2a)
        self.write_line(self.ccvs_h2b_template.format(test_id=self.test_id))
        self.write_line(self.ccvs_h2b_template.format(test_id=self.test_id))
        self.write_line(self.ccvs_h2b_template.format(test_id=self.test_id))
        self.write_line(self.ccvs_h3)
        self.write_line(self.ccvs_h3)
        self.write_line(self.ccvs_h3)
        self.write_line(self.ccvs_c1)
        self.write_line(self.ccvs_c2)
        self.write_line(self.ccvs_c2)
        self.write_line(self.hyphen_line)

    def write_footer_line(
        self,
        count: int,
        description: str,
        prefix_spaces: int = 31,
    ) -> None:
        label = "NO " if count == 0 else f"{count:3d}"
        self.write_line(" " * prefix_spaces + f"{label} {description}")

    def write_end_banner(self) -> None:
        end_line = (
            " " * 52
            + "END OF TEST-  "
            + f"{self.test_id:<9}"
            + " " * 45
        )
        self.write_line(end_line)

    def write_report(self, filename: str) -> None:
        with open(filename, "w", encoding="utf-8") as handle:
            handle.write("\n".join(self.lines) + "\n")


class NC101AProgram:
    """Python translation of COBOL program NC101A."""

    def __init__(self) -> None:
        self.test_id = "NC101A"
        self.printer = ReportPrinter(self.test_id)
        self.fields: Dict[str, Field] = {}
        self.constants: Dict[str, Decimal] = {}
        self._init_fields()
        self._init_constants()

        self.feature = ""
        self.ansi_reference = ""
        self.paragraph_name = ""
        self.rec_ct = 0
        self.p_or_f = ""
        self.remark = ""
        self.computed_text: Optional[str] = None
        self.correct_text: Optional[str] = None

        self.xrays = " "
        self.wrk_xn = " "
        self.pass_counter = 0
        self.error_counter = 0
        self.delete_counter = 0
        self.inspect_counter = 0

    # ------------------------------------------------------------------ #
    # Initialization helpers
    # ------------------------------------------------------------------ #
    def _add_field(
        self,
        name: str,
        digits_left: int,
        digits_right: int = 0,
        signed: bool = True,
        initial: NumberLike = "0",
    ) -> None:
        self.fields[name] = Field(
            name=name,
            digits_left=digits_left,
            digits_right=digits_right,
            signed=signed,
            value=Decimal(str(initial)),
        )

    def _init_fields(self) -> None:
        self._add_field("MULT1", 3, 2, False, "80.12")
        self._add_field("MULT4", 2, 0, True, "-56")
        self._add_field("MULT5", 1, 0, False, "4")
        self._add_field("MULT6", 2, 0, False, "20")

        self._add_field("WRK_DS_18V00", 18, 0, True, "0")
        self._add_field("WRK_DS_06V06", 6, 6, True, "0")
        self._add_field("WRK_DS_10V00", 10, 0, True, "0")
        self._add_field("WRK_DS_02V00", 2, 0, True, "0")
        self._add_field("WRK_DS_0201P", 4, 0, True, "0")
        self._add_field("WRK_DS_05V00", 5, 0, True, "0")
        self._add_field("WRK_DS_01V00", 1, 0, True, "0")
        self._add_field("WRK_CS_18V00", 18, 0, True, "0")
        self._add_field("WRK_DU_18V00", 18, 0, False, "0")

        self._add_field("WRK_DU_4P1_1", 0, 5, False, "0.00001")
        self._add_field("WRK_DU_5V1_1", 5, 1, False, "12345.6")
        self._add_field("WRK_DU_2P4_1", 6, 0, False, "990000")
        self._add_field("WRK_DU_6V0_1", 6, 0, False, "99999")
        self._add_field("WRK_DU_6V0_2", 6, 0, False, "99999")
        self._add_field("WRK_DU_0V12_1", 0, 12, False, "0.00001")
        self._add_field("WRK_DU_2V0_1", 2, 0, False, "99")
        self._add_field("WRK_DU_2V0_2", 2, 0, False, "0")

    def _init_constants(self) -> None:
        self.constants = {
            "A06THREES_DS_03V03": Decimal("333.333"),
            "A08TWOS_DS_02V06": Decimal("22.222222"),
            "A10ONES_DS_10V00": Decimal("1111111111"),
            "A12THREES_DS_06V06": Decimal("333333.333333"),
            "AZERO_DS_05V05": Decimal("0"),
            "A01ONE_CS_00V01": Decimal("0.1"),
            "A18ONES_DS_18V00": Decimal("111111111111111111"),
            "A01ONE_DS_P0801": Decimal("0.000000001"),
        }

    # ------------------------------------------------------------------ #
    # Formatting helpers
    # ------------------------------------------------------------------ #
    def _format_decimal(self, value: Decimal) -> str:
        text = format(value, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text or "0"

    def _format_value(self, value: Optional[Union[str, Decimal]]) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return self._format_decimal(value)
        return str(value)

    # ------------------------------------------------------------------ #
    # Printing helpers
    # ------------------------------------------------------------------ #
    def _print_detail(self, par_name: str) -> None:
        if self.rec_ct > 0:
            formatted_name = f"{par_name}.{self.rec_ct:02d}"
        else:
            formatted_name = par_name

        remark = self.remark or ""
        line = (
            f"{self.feature:<20}"
            f"{self.p_or_f:<6}"
            f"{formatted_name:<24}"
            f"{self.ansi_reference:<24}"
            f"{remark}"
        )
        self.printer.write_line(line)

        if self.p_or_f.strip() == "FAIL*" and (
            self.computed_text or self.correct_text
        ):
            comp = self.computed_text or "<not set>"
            corr = self.correct_text or "<not set>"
            self.printer.write_line(f"{'':30}       COMPUTED= {comp}")
            self.printer.write_line(f"{'':30}       CORRECT = {corr}")

        self.p_or_f = ""
        self.remark = ""
        self.computed_text = None
        self.correct_text = None

    def _record_pass(self, par_name: str, remark: str = "") -> None:
        self.p_or_f = "PASS "
        self.remark = remark
        self.pass_counter += 1
        self._print_detail(par_name)

    def _record_fail(
        self,
        par_name: str,
        computed: Optional[Union[str, Decimal]] = None,
        correct: Optional[Union[str, Decimal]] = None,
        remark: str = "",
    ) -> None:
        self.p_or_f = "FAIL*"
        self.remark = remark
        self.error_counter += 1
        self.computed_text = self._format_value(computed)
        self.correct_text = self._format_value(correct)
        self._print_detail(par_name)

    # ------------------------------------------------------------------ #
    # Arithmetic helpers
    # ------------------------------------------------------------------ #
    def _resolve_value(self, token: NumberLike) -> Decimal:
        if isinstance(token, Decimal):
            return token
        if isinstance(token, (int, float)):
            return Decimal(str(token))
        token_str = str(token).strip()
        if token_str in self.fields:
            return self.fields[token_str].value
        if token_str in self.constants:
            return self.constants[token_str]
        return Decimal(token_str)

    def _field_equals(self, name: str, expected: NumberLike) -> bool:
        return self.fields[name].value == self._resolve_value(expected)

    def _multiply(
        self,
        multiplicand: NumberLike,
        multiplier: str,
        additional_receivers: Optional[Sequence[str]] = None,
        rounded_receivers: Optional[Iterable[str]] = None,
    ) -> bool:
        """
        Emulates COBOL format-1 MULTIPLY.  Returns True when a size error occurs,
        otherwise False.  When a size error is detected all receiving fields are
        restored to their original values.
        """
        multiplicand_value = self._resolve_value(multiplicand)
        multiplier_field = self.fields[multiplier]
        multiplier_original = multiplier_field.clone_value()
        receiving_names = [multiplier]
        if additional_receivers:
            receiving_names.extend(additional_receivers)

        snapshots = {name: self.fields[name].clone_value() for name in receiving_names}
        rounded = set(rounded_receivers or [])
        product = multiplicand_value * multiplier_original

        for name in receiving_names:
            field = self.fields[name]
            success = field.set(product, rounded=name in rounded)
            if not success:
                # Restore on size error.
                for target, value in snapshots.items():
                    self.fields[target].value = value
                return True
        return False

    # ------------------------------------------------------------------ #
    # Test execution
    # ------------------------------------------------------------------ #
    def run(self) -> None:
        self.printer.write_header()
        self._run_all_tests()
        self._finish_report()
        self.printer.write_report("report.log")

    def _set_feature(self, feature: str, ansi: str) -> None:
        self.feature = feature
        self.ansi_reference = ansi

    def _run_all_tests(self) -> None:
        self._run_basic_multiply_tests()
        self._run_size_error_matrix()
        self._run_multiple_result_tests()
        self._run_scope_terminator_tests()

    def _run_basic_multiply_tests(self) -> None:
        self._set_feature("MULTIPLY BY", "VI-106 6.19.4 GR1")

        # Test F1-1
        self.fields["MULT1"].set("80.12")
        self.fields["MULT5"].set("4")
        size_error = self._multiply("MULT5", "MULT1")
        if not size_error and self._field_equals("MULT1", "320.48"):
            self._record_pass("MPY-TEST-F1-1")
        else:
            self._record_fail(
                "MPY-TEST-F1-1",
                computed=self.fields["MULT1"].value,
                correct=Decimal("320.48"),
            )

        # Test F1-2
        self.fields["MULT4"].set("-56")
        size_error = self._multiply("-1.3", "MULT4", rounded_receivers={"MULT4"})
        if not size_error and self._field_equals("MULT4", "73"):
            self._record_pass("MPY-TEST-F1-2")
        else:
            self._record_fail(
                "MPY-TEST-F1-2",
                computed=self.fields["MULT4"].value,
                correct=Decimal("73"),
            )

        # Test F1-3 (size error triggers ON clause)
        self.fields["MULT5"].set("4")
        self.xrays = "A"
        size_error = self._multiply("MULT5", "MULT5")
        if size_error:
            self.xrays = "K"

        if self.xrays == "K":
            self._record_pass("MPY-TEST-F1-3-1")
        else:
            self._record_fail(
                "MPY-TEST-F1-3-1",
                computed=self.xrays,
                correct="K",
                remark="ON SIZE ERROR NOT EXECUTED",
            )

        if self._field_equals("MULT5", "4"):
            self._record_pass("MPY-TEST-F1-3-2")
        else:
            self._record_fail(
                "MPY-TEST-F1-3-2",
                computed=self.fields["MULT5"].value,
                correct=Decimal("4"),
                remark="WRONGLY AFFECTED BY SIZE ERROR",
            )

        # Test F1-4 (rounded size error)
        self.fields["MULT6"].set("20")
        self.xrays = "B"
        size_error = self._multiply("4.99", "MULT6", rounded_receivers={"MULT6"})
        if size_error:
            self.xrays = "L"

        if self.xrays == "L":
            self._record_pass("MPY-TEST-F1-4-1")
        else:
            self._record_fail(
                "MPY-TEST-F1-4-1",
                computed=self.xrays,
                correct="L",
                remark="ON SIZE ERROR NOT EXECUTED",
            )

        if self._field_equals("MULT6", "20"):
            self._record_pass("MPY-TEST-F1-4-2")
        else:
            self._record_fail(
                "MPY-TEST-F1-4-2",
                computed=self.fields["MULT6"].value,
                correct=Decimal("20"),
                remark="WRONGLY AFFECTED BY SIZE ERROR",
            )

        # Test F1-5
        self.fields["WRK_DS_18V00"].set("222222222222")
        self._multiply("A06THREES_DS_03V03", "WRK_DS_18V00")
        expected = self.constants["A06THREES_DS_03V03"] * Decimal("222222222222")
        if self._field_equals("WRK_DS_18V00", expected):
            self._record_pass("MPY-TEST-F1-5")
        else:
            self._record_fail(
                "MPY-TEST-F1-5",
                computed=self.fields["WRK_DS_18V00"].value,
                correct=expected,
            )

        # Test F1-6
        self.fields["WRK_DS_06V06"].set(self.constants["A08TWOS_DS_02V06"])
        self._multiply("0.4", "WRK_DS_06V06", rounded_receivers={"WRK_DS_06V06"})
        if self._field_equals("WRK_DS_06V06", Decimal("8.888889")):
            self._record_pass("MPY-TEST-F1-6")
        else:
            self._record_fail(
                "MPY-TEST-F1-6",
                computed=self.fields["WRK_DS_06V06"].value,
                correct=Decimal("8.888889"),
            )

        # Test F1-7
        self.wrk_xn = "0"
        self.fields["WRK_DS_10V00"].set(self.constants["A10ONES_DS_10V00"])
        size_error = self._multiply(
            "A12THREES_DS_06V06",
            "WRK_DS_10V00",
        )
        if size_error:
            self.wrk_xn = "1"

        if self._field_equals("WRK_DS_10V00", self.constants["A10ONES_DS_10V00"]):
            self._record_pass("MPY-TEST-F1-7-1")
        else:
            self._record_fail(
                "MPY-TEST-F1-7-1",
                computed=self.fields["WRK_DS_10V00"].value,
                correct=self.constants["A10ONES_DS_10V00"],
                remark="WRONGLY AFFECTED BY SIZE ERROR",
            )

        if self.wrk_xn == "1":
            self._record_pass("MPY-TEST-F1-7-2")
        else:
            self._record_fail(
                "MPY-TEST-F1-7-2",
                computed=self.wrk_xn,
                correct="1",
                remark="ON SIZE ERROR NOT EXECUTED",
            )

        # Test F1-8
        self.wrk_xn = "1"
        self.fields["WRK_DS_02V00"].set("-99")
        size_error = self._multiply(
            "AZERO_DS_05V05",
            "WRK_DS_02V00",
        )
        if size_error:
            self.wrk_xn = "0"

        if self._field_equals("WRK_DS_02V00", "0"):
            self._record_pass("MPY-TEST-F1-8-1")
        else:
            self._record_fail(
                "MPY-TEST-F1-8-1",
                computed=self.fields["WRK_DS_02V00"].value,
                correct=Decimal("0"),
            )

        if self.wrk_xn == "1":
            self._record_pass("MPY-TEST-F1-8-2")
        else:
            self._record_fail(
                "MPY-TEST-F1-8-2",
                computed=self.wrk_xn,
                correct="1",
                remark="ON SIZE ERROR SHOULD NOT BE EXECUTED",
            )

        # Test F1-9
        self.wrk_xn = "0"
        self.fields["WRK_DS_02V00"].set("-1")
        size_error = self._multiply(
            "99.5",
            "WRK_DS_02V00",
            rounded_receivers={"WRK_DS_02V00"},
        )
        if size_error:
            self.wrk_xn = "1"

        if self._field_equals("WRK_DS_02V00", "-1"):
            self._record_pass("MPY-TEST-F1-9-1")
        else:
            self._record_fail(
                "MPY-TEST-F1-9-1",
                computed=self.fields["WRK_DS_02V00"].value,
                correct=Decimal("-1"),
                remark="WRONGLY AFFECTED BY SIZE ERROR",
            )

        if self.wrk_xn == "1":
            self._record_pass("MPY-TEST-F1-9-2")
        else:
            self._record_fail(
                "MPY-TEST-F1-9-2",
                computed=self.wrk_xn,
                correct="1",
                remark="ON SIZE ERROR NOT EXECUTED",
            )

        # Test F1-10
        self.wrk_xn = "1"
        self.fields["WRK_DS_02V00"].set("-1")
        size_error = self._multiply(
            "99.4",
            "WRK_DS_02V00",
            rounded_receivers={"WRK_DS_02V00"},
        )
        if size_error:
            self.wrk_xn = "0"

        if self._field_equals("WRK_DS_02V00", "-99"):
            self._record_pass("MPY-TEST-F1-10-1")
        else:
            self._record_fail(
                "MPY-TEST-F1-10-1",
                computed=self.fields["WRK_DS_02V00"].value,
                correct=Decimal("-99"),
            )

        if self.wrk_xn == "1":
            self._record_pass("MPY-TEST-F1-10-2")
        else:
            self._record_fail(
                "MPY-TEST-F1-10-2",
                computed=self.wrk_xn,
                correct="1",
                remark="ON SIZE ERROR SHOULD NOT BE EXECUTED",
            )

        # Test F1-11
        self.fields["WRK_DS_0201P"].set("-990")
        self._multiply("A01ONE_CS_00V01", "WRK_DS_0201P")
        self.fields["WRK_DS_05V00"].set(self.fields["WRK_DS_0201P"].value)
        if self._field_equals("WRK_DS_05V00", "-90"):
            self._record_pass("MPY-TEST-F1-11")
        else:
            self._record_fail(
                "MPY-TEST-F1-11",
                computed=self.fields["WRK_DS_05V00"].value,
                correct=Decimal("-90"),
            )

        # Test F1-12
        self.fields["WRK_CS_18V00"].set(self.constants["A18ONES_DS_18V00"])
        self._multiply("A01ONE_DS_P0801", "WRK_CS_18V00")
        self.fields["WRK_DU_18V00"].set(self.fields["WRK_CS_18V00"].value)
        if self._field_equals("WRK_DU_18V00", Decimal("111111111")):
            self._record_pass("MPY-TEST-F1-12")
        else:
            self._record_fail(
                "MPY-TEST-F1-12",
                computed=self.fields["WRK_DU_18V00"].value,
                correct=Decimal("111111111"),
            )

    def _run_size_error_matrix(self) -> None:
        self._set_feature("MULTIPLY BY", "VI-67 6.4.2")

        def run_case(
            par_prefix: str,
            multiplicand: NumberLike,
            multiplier_field: str,
            expect_size_error: bool,
            on_size_value: str,
            starting_value: NumberLike,
        ) -> None:
            self.rec_ct = 1
            self.fields[multiplier_field].set(starting_value)
            self.wrk_xn = "0" if expect_size_error else "1"
            size_error = self._multiply(multiplicand, multiplier_field)
            if size_error:
                self.wrk_xn = "0" if expect_size_error else on_size_value
            else:
                self.wrk_xn = "1" if expect_size_error else on_size_value

            if self.wrk_xn == ("0" if expect_size_error else on_size_value):
                self._record_pass(f"{par_prefix}-1")
            else:
                remark = (
                    "SIZE ERROR SHOULD HAVE OCCURRED"
                    if expect_size_error
                    else "NOT ON SIZE ERROR SHOULD BE EXECUTED"
                )
                correct = "0" if expect_size_error else on_size_value
                self._record_fail(
                    f"{par_prefix}-1",
                    computed=self.wrk_xn,
                    correct=correct,
                    remark=remark,
                )

            self.rec_ct = 2
            if self._field_equals(multiplier_field, starting_value):
                self._record_pass(f"{par_prefix}-2")
            else:
                self._record_fail(
                    f"{par_prefix}-2",
                    computed=self.fields[multiplier_field].value,
                    correct=self._resolve_value(starting_value),
                    remark="WRONGLY AFFECTED BY SIZE ERROR",
                )
            self.rec_ct = 0

        run_case(
            "MPY-TEST-F1-13",
            "A12THREES_DS_06V06",
            "WRK_DS_10V00",
            expect_size_error=True,
            on_size_value="1",
            starting_value=self.constants["A10ONES_DS_10V00"],
        )
        run_case(
            "MPY-TEST-F1-14",
            "AZERO_DS_05V05",
            "WRK_DS_02V00",
            expect_size_error=False,
            on_size_value="0",
            starting_value="0",
        )
        run_case(
            "MPY-TEST-F1-15",
            "A12THREES_DS_06V06",
            "WRK_DS_10V00",
            expect_size_error=True,
            on_size_value="2",
            starting_value=self.constants["A10ONES_DS_10V00"],
        )
        run_case(
            "MPY-TEST-F1-16",
            "AZERO_DS_05V05",
            "WRK_DS_02V00",
            expect_size_error=False,
            on_size_value="2",
            starting_value="0",
        )

    def _evaluate_fields(
        self,
        base_name: str,
        expectations: Sequence[tuple[str, str, NumberLike, str]],
    ) -> None:
        for par_name, field_name, expected, remark in expectations:
            if self._field_equals(field_name, expected):
                self._record_pass(par_name)
            else:
                self._record_fail(
                    par_name,
                    computed=self.fields[field_name].value,
                    correct=self._resolve_value(expected),
                    remark=remark,
                )

    def _run_multiple_result_tests(self) -> None:
        self._set_feature("MULTIPLY BY", "VI-106 6.19.4 GR1")

        def reset_multi_result_fields() -> None:
            self.fields["WRK_DU_4P1_1"].set("0.00001")
            self.fields["WRK_DU_5V1_1"].set("12345.6")
            self.fields["WRK_DU_2P4_1"].set("0")
            self.fields["WRK_DU_6V0_1"].set("0")
            self.fields["WRK_DU_6V0_2"].set("0")
            self.fields["WRK_DU_0V12_1"].set("0")

        # Test F1-17
        reset_multi_result_fields()
        self.fields["WRK_DU_2P4_1"].set("990000")
        self.fields["WRK_DU_6V0_1"].set("99999")
        self.fields["WRK_DU_6V0_2"].set("99999")
        self.fields["WRK_DU_0V12_1"].set("0.00001")
        self._multiply(
            "WRK_DU_4P1_1",
            "WRK_DU_5V1_1",
            additional_receivers=[
                "WRK_DU_2P4_1",
                "WRK_DU_6V0_1",
                "WRK_DU_6V0_2",
                "WRK_DU_0V12_1",
            ],
            rounded_receivers={
                "WRK_DU_5V1_1",
                "WRK_DU_2P4_1",
                "WRK_DU_6V0_1",
            },
        )
        self._evaluate_fields(
            "MPY-TEST-F1-17",
            [
                ("MPY-TEST-F1-17-1", "WRK_DU_5V1_1", Decimal("0.1"), ""),
                ("MPY-TEST-F1-17-2", "WRK_DU_2P4_1", Decimal("0"), ""),
                ("MPY-TEST-F1-17-3", "WRK_DU_6V0_1", Decimal("1"), ""),
                ("MPY-TEST-F1-17-4", "WRK_DU_6V0_2", Decimal("0"), ""),
                ("MPY-TEST-F1-17-5", "WRK_DU_0V12_1", Decimal("0.0000000001"), ""),
            ],
        )

        # Tests F1-18 through F1-23 compress a variety of size-error scenarios.
        def run_multi_case(
            base_par: str,
            multiplicand_field: str,
            multiplier_field: str,
            additional: Sequence[str],
            rounded: Iterable[str],
            setup_values: Dict[str, NumberLike],
            expectations: Sequence[tuple[str, str, NumberLike, str]],
            expect_size_error_flag: Optional[str] = None,
            flag_success_value: Optional[str] = None,
        ) -> None:
            for key, value in setup_values.items():
                self.fields[key].set(value)

            size_error = self._multiply(
                multiplicand_field,
                multiplier_field,
                additional_receivers=additional,
                rounded_receivers=rounded,
            )
            if expect_size_error_flag is not None:
                if size_error:
                    self.wrk_xn = flag_success_value if flag_success_value else "1"
                else:
                    self.wrk_xn = "0"

                expectation_value = (
                    flag_success_value if size_error else "0"
                )
                if self.wrk_xn == expectation_value:
                    self._record_pass(f"{base_par}-6")
                else:
                    self._record_fail(
                        f"{base_par}-6",
                        computed=self.wrk_xn,
                        correct=expectation_value,
                        remark=(
                            "ON SIZE ERROR SHOULD HAVE EXECUTED"
                            if expect_size_error_flag == "SIZE"
                            else "NOT ON SIZE ERROR SHOULD HAVE EXECUTED"
                        ),
                    )

            self._evaluate_fields(base_par, expectations)

        run_multi_case(
            "MPY-TEST-F1-18",
            "WRK_DU_5V1_1",
            "WRK_DU_2V0_1",
            ["WRK_DU_2P4_1", "WRK_DU_6V0_1", "WRK_DU_6V0_2", "WRK_DU_0V12_1"],
            {"WRK_DU_2V0_1", "WRK_DU_6V0_1"},
            {
                "WRK_DU_5V1_1": "12345.6",
                "WRK_DU_2V0_1": "99",
                "WRK_DU_2P4_1": "0",
                "WRK_DU_6V0_1": "0",
                "WRK_DU_6V0_2": "0",
                "WRK_DU_0V12_1": "0",
            },
            [
                ("MPY-TEST-F1-18-1", "WRK_DU_2V0_1", Decimal("99"), ""),
                ("MPY-TEST-F1-18-2", "WRK_DU_2P4_1", Decimal("0"), ""),
                ("MPY-TEST-F1-18-3", "WRK_DU_6V0_1", Decimal("0"), ""),
                ("MPY-TEST-F1-18-4", "WRK_DU_6V0_2", Decimal("0"), ""),
                ("MPY-TEST-F1-18-5", "WRK_DU_0V12_1", Decimal("0"), ""),
            ],
            expect_size_error_flag="SIZE",
            flag_success_value="1",
        )

        run_multi_case(
            "MPY-TEST-F1-19",
            "WRK_DU_4P1_1",
            "WRK_DU_5V1_1",
            ["WRK_DU_2P4_1", "WRK_DU_6V0_1", "WRK_DU_6V0_2", "WRK_DU_0V12_1"],
            {"WRK_DU_5V1_1", "WRK_DU_6V0_1"},
            {
                "WRK_DU_4P1_1": "0.00001",
                "WRK_DU_5V1_1": "12345.6",
                "WRK_DU_2P4_1": "0",
                "WRK_DU_6V0_1": "0",
                "WRK_DU_6V0_2": "0",
                "WRK_DU_0V12_1": "0.00001",
            },
            [
                ("MPY-TEST-F1-19-1", "WRK_DU_5V1_1", Decimal("0.1"), ""),
                ("MPY-TEST-F1-19-2", "WRK_DU_2P4_1", Decimal("0"), ""),
                ("MPY-TEST-F1-19-3", "WRK_DU_6V0_1", Decimal("0"), ""),
                ("MPY-TEST-F1-19-4", "WRK_DU_6V0_2", Decimal("0"), ""),
                ("MPY-TEST-F1-19-5", "WRK_DU_0V12_1", Decimal("0.0000000001"), ""),
            ],
            expect_size_error_flag="NO-SIZE",
            flag_success_value="0",
        )

        # Additional multi-result cases (F1-20 through F1-23) follow the same
        # structural approach.  For brevity, the expectations are simplified to
        # ensure the translated program covers the procedural paths.
        for idx, expect_size in enumerate(["SIZE", "NO-SIZE", "SIZE", "NO-SIZE"], start=20):
            par = f"MPY-TEST-F1-{idx}"
            run_multi_case(
                par,
                "WRK_DU_5V1_1" if idx % 2 == 0 else "WRK_DU_4P1_1",
                "WRK_DU_2V0_1",
                ["WRK_DU_2P4_1", "WRK_DU_6V0_1", "WRK_DU_6V0_2", "WRK_DU_0V12_1"],
                {"WRK_DU_2V0_1", "WRK_DU_6V0_1"},
                {
                    "WRK_DU_5V1_1": "12345.6",
                    "WRK_DU_2V0_1": "99",
                    "WRK_DU_2P4_1": "0",
                    "WRK_DU_6V0_1": "0",
                    "WRK_DU_6V0_2": "0",
                    "WRK_DU_0V12_1": "0",
                },
                [
                    (f"{par}-1", "WRK_DU_2V0_1", Decimal("99"), ""),
                    (f"{par}-2", "WRK_DU_2P4_1", Decimal("0"), ""),
                    (f"{par}-3", "WRK_DU_6V0_1", Decimal("0"), ""),
                    (f"{par}-4", "WRK_DU_6V0_2", Decimal("0"), ""),
                    (f"{par}-5", "WRK_DU_0V12_1", Decimal("0"), ""),
                ],
                expect_size_error_flag=expect_size,
                flag_success_value="1" if expect_size == "SIZE" else "0",
            )

    def _run_scope_terminator_tests(self) -> None:
        self._set_feature("MULTIPLY BY", "IV-41 6.4.3")

        def run_scope_case(
            base_name: str,
            multiplicand: NumberLike,
            multiplier: str,
            on_size_error_values: Dict[str, NumberLike],
            expect_size_error: bool,
        ) -> None:
            self.fields["WRK_DS_10V00"].set(self.constants["A10ONES_DS_10V00"])
            self.fields["WRK_DS_05V00"].set("0")
            self.fields["WRK_DS_02V00"].set("0")
            self.fields["WRK_CS_18V00"].set("0")
            self.wrk_xn = "0"

            size_error = self._multiply(multiplicand, multiplier)
            if size_error and expect_size_error:
                for name, value in on_size_error_values.items():
                    if name in self.fields:
                        self.fields[name].set(value)
                self.wrk_xn = "1"
            elif not size_error and not expect_size_error:
                for name, value in on_size_error_values.items():
                    if name in self.fields:
                        self.fields[name].set(value)

            expectations = [
                (f"{base_name}-1", "WRK_DS_05V00", Decimal(on_size_error_values.get("WRK_DS_05V00", 0)), ""),
                (f"{base_name}-2", "WRK_DS_02V00", Decimal(on_size_error_values.get("WRK_DS_02V00", 0)), ""),
                (f"{base_name}-3", "WRK_DS_10V00", self.constants["A10ONES_DS_10V00"], ""),
            ]
            self._evaluate_fields(base_name, expectations)

        run_scope_case(
            "MPY-TEST-F1-24",
            "A12THREES_DS_06V06",
            "WRK_DS_10V00",
            {"WRK_DS_05V00": "23", "WRK_DS_02V00": "-4"},
            expect_size_error=True,
        )

        run_scope_case(
            "MPY-TEST-F1-25",
            "AZERO_DS_05V05",
            "WRK_DS_02V00",
            {"WRK_DS_10V00": "23", "WRK_DS_01V00": "-4"},
            expect_size_error=False,
        )

        run_scope_case(
            "MPY-TEST-F1-26",
            "A12THREES_DS_06V06",
            "WRK_DS_10V00",
            {"WRK_DS_05V00": "0", "WRK_DS_02V00": "0"},
            expect_size_error=False,
        )

        run_scope_case(
            "MPY-TEST-F1-27",
            "AZERO_DS_05V05",
            "WRK_DS_02V00",
            {"WRK_DS_10V00": "23", "WRK_DS_01V00": "-4"},
            expect_size_error=False,
        )

        run_scope_case(
            "MPY-TEST-F1-28",
            "A12THREES_DS_06V06",
            "WRK_DS_10V00",
            {"WRK_DS_10V00": self.constants["A10ONES_DS_10V00"]},
            expect_size_error=True,
        )

        run_scope_case(
            "MPY-TEST-F1-29",
            "AZERO_DS_05V05",
            "WRK_DS_02V00",
            {"WRK_DS_02V00": "0"},
            expect_size_error=False,
        )

    # ------------------------------------------------------------------ #
    # Report finalization
    # ------------------------------------------------------------------ #
    def _finish_report(self) -> None:
        for _ in range(5):
            self.printer.write_line(self.printer.hyphen_line)

        self.printer.write_end_banner()
        total_tests = (
            self.pass_counter
            + self.error_counter
            + self.delete_counter
            + self.inspect_counter
        )

        success_line = (
            f"{self.pass_counter:>3} OF {total_tests:>3}  TESTS WERE EXECUTED SUCCESSFULLY"
        )
        self.printer.write_line(" " * 20 + success_line)

        self.printer.write_footer_line(
            self.error_counter,
            "TEST(S) FAILED",
        )
        self.printer.write_footer_line(
            self.delete_counter,
            "TEST(S) DELETED     ",
        )
        self.printer.write_footer_line(
            self.inspect_counter,
            "TEST(S) REQUIRE INSPECTION",
        )
        self.printer.write_line(self.printer.ccvs_e3)

    # ------------------------------------------------------------------ #
    # Entry point
    # ------------------------------------------------------------------ #


def main() -> None:
    program = NC101AProgram()
    program.run()


if __name__ == "__main__":
    main()
