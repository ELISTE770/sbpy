"""בדיקות לשכבת הניתוח הסטטי (@SFB / @SEC / @OPT / @CMP)."""

from __future__ import annotations

import textwrap
import unittest

from sbpy.static.checks import (
    CATEGORY_BUG,
    CATEGORY_COMPLEXITY,
    CATEGORY_DOC,
    CATEGORY_OPT,
    CATEGORY_SEC,
    CATEGORY_STYLE,
    CATEGORY_TODO,
    CATEGORY_TYPE,
    SourceUnit,
    analyze,
    cyclomatic_complexity,
    rules_by_category,
)


def rules(source: str, *categories: str) -> set[str]:
    unit = SourceUnit.from_source(textwrap.dedent(source), "sample.py")
    return {finding.rule for finding in analyze(unit, categories or (CATEGORY_BUG, CATEGORY_STYLE))}


class BugCheckTest(unittest.TestCase):
    def test_mutable_default_argument(self) -> None:
        self.assertIn("mutable-default-arg", rules("def f(items=[]):\n    return items\n"))

    def test_clean_default_is_not_flagged(self) -> None:
        self.assertNotIn("mutable-default-arg", rules("def f(items=None):\n    return items\n"))

    def test_call_in_default_argument(self) -> None:
        source = "import datetime\ndef f(when=datetime.datetime.now()):\n    return when\n"
        self.assertIn("call-in-default-arg", rules(source))

    def test_bare_except(self) -> None:
        self.assertIn("bare-except", rules("try:\n    x = 1\nexcept:\n    pass\n"))

    def test_silent_except(self) -> None:
        self.assertIn("silent-except", rules("try:\n    x = 1\nexcept ValueError:\n    pass\n"))

    def test_except_order(self) -> None:
        source = """
        try:
            pass
        except Exception:
            pass
        except ValueError:
            pass
        """
        self.assertIn("except-order", rules(source))

    def test_compare_none_with_eq(self) -> None:
        self.assertIn("compare-none-with-eq", rules("x = 1\nif x == None:\n    pass\n"))

    def test_is_with_literal(self) -> None:
        self.assertIn("is-with-literal", rules("x = 'a'\nif x is 'a':\n    pass\n"))

    def test_missing_f_prefix(self) -> None:
        source = "name = 'eli'\nprint('hello {name}')\n"
        self.assertIn("missing-f-prefix", rules(source))

    def test_format_call_is_not_flagged(self) -> None:
        source = "name = 'eli'\nprint('hello {name}'.format(name=name))\n"
        self.assertNotIn("missing-f-prefix", rules(source))

    def test_percent_format_is_not_flagged(self) -> None:
        source = "value = 1\nprint('a {b} c' % value)\n"
        self.assertNotIn("missing-f-prefix", rules(source))

    def test_duplicate_dict_key(self) -> None:
        self.assertIn("duplicate-dict-key", rules("d = {'a': 1, 'a': 2}\n"))

    def test_assert_on_tuple(self) -> None:
        self.assertIn("assert-on-tuple", rules("assert (1, 'boom')\n"))

    def test_unreachable_code(self) -> None:
        source = "def f():\n    return 1\n    print('x')\n"
        self.assertIn("unreachable-code", rules(source))

    def test_self_assignment(self) -> None:
        self.assertIn("self-assignment", rules("x = 1\nx = x\n"))

    def test_shadows_builtin(self) -> None:
        self.assertIn("shadows-builtin", rules("list = [1, 2]\n"))

    def test_mutable_class_attribute(self) -> None:
        self.assertIn("mutable-class-attribute", rules("class A:\n    items = []\n"))

    def test_method_missing_self(self) -> None:
        self.assertIn("method-missing-self", rules("class A:\n    def go(value):\n        return value\n"))

    def test_staticmethod_is_allowed(self) -> None:
        source = "class A:\n    @staticmethod\n    def go(value):\n        return value\n"
        self.assertNotIn("method-missing-self", rules(source))

    def test_loop_variable_capture(self) -> None:
        source = """
        handlers = []
        for name in ['a', 'b']:
            handlers.append(lambda: print(name))
        """
        self.assertIn("loop-variable-capture", rules(source))

    def test_default_argument_binding_is_allowed(self) -> None:
        source = """
        handlers = []
        for name in ['a', 'b']:
            handlers.append(lambda name=name: print(name))
        """
        self.assertNotIn("loop-variable-capture", rules(source))

    def test_mutate_while_iterating(self) -> None:
        source = """
        items = [1, 2, 3]
        for value in items:
            items.remove(value)
        """
        self.assertIn("mutate-while-iterating", rules(source))

    def test_return_in_finally(self) -> None:
        source = """
        def f():
            try:
                return 1
            finally:
                return 2
        """
        self.assertIn("return-in-finally", rules(source))

    def test_boolop_constant(self) -> None:
        self.assertIn("comparison-against-constant-chain", rules("x = 1\nif x == 1 or 2:\n    pass\n"))

    def test_float_equality(self) -> None:
        self.assertIn("float-equality", rules("x = 0.1\nif x == 0.3:\n    pass\n"))

    def test_redefined_function(self) -> None:
        self.assertIn("redefined-name", rules("def f():\n    pass\ndef f():\n    pass\n"))

    def test_open_without_encoding_and_with(self) -> None:
        found = rules("data = open('a.txt').read()\n")
        self.assertIn("open-without-encoding", found)
        self.assertIn("open-without-with", found)

    def test_binary_open_needs_no_encoding(self) -> None:
        source = "with open('a.bin', 'rb') as handle:\n    data = handle.read()\n"
        self.assertNotIn("open-without-encoding", rules(source))

    def test_unused_import(self) -> None:
        self.assertIn("unused-import", rules("import os\nprint('hi')\n"))

    def test_used_import_is_clean(self) -> None:
        self.assertNotIn("unused-import", rules("import os\nprint(os.getcwd())\n"))

    def test_clean_file_has_no_findings(self) -> None:
        source = """
        import math


        def area(radius: float) -> float:
            \"\"\"שטח מעגל.\"\"\"
            if radius is None:
                raise ValueError('radius required')
            return math.pi * radius ** 2
        """
        self.assertEqual(rules(source), set())


class SecurityCheckTest(unittest.TestCase):
    def test_eval(self) -> None:
        self.assertIn("dangerous-eval", rules("value = input()\neval(value)\n", CATEGORY_SEC))

    def test_shell_true(self) -> None:
        source = "import subprocess\nsubprocess.run('ls', shell=True)\n"
        self.assertIn("shell-injection", rules(source, CATEGORY_SEC))

    def test_os_system(self) -> None:
        self.assertIn("shell-injection", rules("import os\nos.system('ls')\n", CATEGORY_SEC))

    def test_pickle(self) -> None:
        source = "import pickle\npickle.loads(b'x')\n"
        self.assertIn("unsafe-deserialization", rules(source, CATEGORY_SEC))

    def test_yaml_load(self) -> None:
        source = "import yaml\nyaml.load('a: 1')\n"
        self.assertIn("unsafe-yaml-load", rules(source, CATEGORY_SEC))

    def test_safe_yaml_is_clean(self) -> None:
        source = "import yaml\nyaml.safe_load('a: 1')\n"
        self.assertNotIn("unsafe-yaml-load", rules(source, CATEGORY_SEC))

    def test_weak_hash(self) -> None:
        source = "import hashlib\nhashlib.md5(b'x')\n"
        self.assertIn("weak-hash", rules(source, CATEGORY_SEC))

    def test_verify_disabled(self) -> None:
        source = "import requests\nrequests.get('https://x', verify=False)\n"
        self.assertIn("tls-verification-disabled", rules(source, CATEGORY_SEC))

    def test_sql_string_building(self) -> None:
        source = "def q(cur, name):\n    cur.execute(f'SELECT * FROM t WHERE n = {name}')\n"
        self.assertIn("sql-string-building", rules(source, CATEGORY_SEC))

    def test_parameterized_sql_is_clean(self) -> None:
        source = "def q(cur, name):\n    cur.execute('SELECT * FROM t WHERE n = ?', (name,))\n"
        self.assertNotIn("sql-string-building", rules(source, CATEGORY_SEC))

    def test_hardcoded_secret(self) -> None:
        source = 'API_KEY = "sk-abcdefghij1234567890abcdef"\n'
        self.assertIn("hardcoded-secret", rules(source, CATEGORY_SEC))

    def test_env_secret_is_clean(self) -> None:
        source = 'import os\nAPI_KEY = os.environ["KEY"]\n'
        self.assertNotIn("hardcoded-secret", rules(source, CATEGORY_SEC))

    def test_weak_random_for_token(self) -> None:
        source = "import random\ntoken = random.randint(0, 9999)\n"
        self.assertIn("weak-random-for-secret", rules(source, CATEGORY_SEC))


class PerformanceCheckTest(unittest.TestCase):
    def test_string_concat_in_loop(self) -> None:
        source = "out = ''\nfor i in range(3):\n    out += 'x'\n"
        self.assertIn("string-concat-in-loop", rules(source, CATEGORY_OPT))

    def test_membership_on_list_in_loop(self) -> None:
        source = "for i in range(3):\n    if i in [1, 2, 3]:\n        pass\n"
        self.assertIn("membership-on-list-in-loop", rules(source, CATEGORY_OPT))

    def test_range_len(self) -> None:
        source = "items = [1]\nfor i in range(len(items)):\n    print(i)\n"
        self.assertIn("range-len", rules(source, CATEGORY_OPT))

    def test_len_compare_zero(self) -> None:
        source = "items = []\nif len(items) == 0:\n    pass\n"
        self.assertIn("len-compare-zero", rules(source, CATEGORY_OPT))

    def test_list_comprehension_in_sum(self) -> None:
        self.assertIn("list-comprehension-in-aggregate", rules("sum([x for x in range(3)])\n", CATEGORY_OPT))

    def test_keys_membership(self) -> None:
        source = "d = {}\nif 'a' in d.keys():\n    pass\n"
        self.assertIn("keys-membership", rules(source, CATEGORY_OPT))

    def test_sorted_then_index(self) -> None:
        self.assertIn("sorted-then-index", rules("items = [3, 1]\nsmallest = sorted(items)[0]\n", CATEGORY_OPT))

    def test_re_compile_in_func(self) -> None:
        source = "import re\ndef match(text):\n    pattern = re.compile('^[a-z]+$')\n    return pattern.match(text)\n"
        self.assertIn("re-compile-in-func", rules(source, CATEGORY_OPT))


class ModernizerCheckTest(unittest.TestCase):
    def test_use_pathlib(self) -> None:
        from sbpy.static.checks import CATEGORY_MOD
        source = "import os\np = os.path.join('a', 'b')\n"
        self.assertIn("use-pathlib", rules(source, CATEGORY_MOD))

    def test_modern_type_annotations(self) -> None:
        from sbpy.static.checks import CATEGORY_MOD
        source = "import typing\ndef f(x: typing.List[int]) -> typing.Optional[str]:\n    return None\n"
        self.assertIn("modern-type-annotations", rules(source, CATEGORY_MOD))


class ComplexityTest(unittest.TestCase):
    def test_simple_function_scores_one(self) -> None:
        unit = SourceUnit.from_source("def f():\n    return 1\n")
        assert unit.tree is not None
        self.assertEqual(cyclomatic_complexity(unit.tree.body[0]), 1)

    def test_branches_increase_score(self) -> None:
        source = textwrap.dedent(
            """
            def f(x):
                if x > 1 and x < 10:
                    return 1
                for i in range(x):
                    if i:
                        return i
                return 0
            """
        )
        unit = SourceUnit.from_source(source)
        assert unit.tree is not None
        self.assertGreater(cyclomatic_complexity(unit.tree.body[0]), 4)

    def test_high_complexity_is_reported(self) -> None:
        body = "\n".join(f"    if x == {i}:\n        return {i}" for i in range(14))
        source = f"def f(x):\n{body}\n    return -1\n"
        self.assertIn("high-complexity", rules(source, CATEGORY_COMPLEXITY))

    def test_deep_nesting_is_reported(self) -> None:
        source = textwrap.dedent(
            """
            def f(x):
                if x:
                    for a in x:
                        while a:
                            with open('f') as h:
                                if h:
                                    return 1
                return 0
            """
        )
        self.assertIn("deep-nesting", rules(source, CATEGORY_COMPLEXITY))


class DocsAndTodosTest(unittest.TestCase):
    def test_missing_docstring(self) -> None:
        self.assertIn("missing-docstring", rules("def public():\n    return 1\n", CATEGORY_DOC))

    def test_private_function_is_exempt(self) -> None:
        self.assertNotIn("missing-docstring", rules("def _private():\n    return 1\n", CATEGORY_DOC))

    def test_missing_type_hints(self) -> None:
        self.assertIn("missing-type-hints", rules("def f(a):\n    return a\n", CATEGORY_TYPE))

    def test_annotated_function_is_clean(self) -> None:
        self.assertNotIn("missing-type-hints", rules("def f(a: int) -> int:\n    return a\n", CATEGORY_TYPE))

    def test_todo_comment(self) -> None:
        self.assertIn("todo-comment", rules("# TODO: לסדר את זה\nx = 1\n", CATEGORY_TODO))


class FalsePositiveTest(unittest.TestCase):
    """מקרים שנראים כמו באג אבל הם ניב לגיטימי - אסור לדווח עליהם."""

    def test_or_default_is_not_a_constant_chain(self) -> None:
        source = "def f(payload):\n    return str(payload.get('title') or '').strip()\n"
        self.assertNotIn("comparison-against-constant-chain", rules(source))

    def test_and_default_is_not_a_constant_chain(self) -> None:
        self.assertNotIn("comparison-against-constant-chain", rules("x = None\ny = x and 0\n"))

    def test_real_constant_chain_is_still_caught(self) -> None:
        self.assertIn("comparison-against-constant-chain", rules("x = 1\nif x == 1 or 2:\n    pass\n"))

    def test_dict_template_is_not_a_missing_fstring(self) -> None:
        source = "name = 'x'\nCATALOG = {'greet': 'hello {name}'}\n"
        self.assertNotIn("missing-f-prefix", rules(source))

    def test_real_missing_fstring_is_still_caught(self) -> None:
        self.assertIn("missing-f-prefix", rules("name = 'x'\nprint('hello {name}')\n"))


class SuppressionTest(unittest.TestCase):
    def test_noqa_silences_the_line(self) -> None:
        source = "try:\n    pass\nexcept:  # noqa\n    pass\n"
        self.assertNotIn("bare-except", rules(source))

    def test_sbpy_ignore_silences_the_line(self) -> None:
        source = "try:\n    pass\nexcept:  # sbpy: ignore\n    pass\n"
        self.assertNotIn("bare-except", rules(source))

    def test_named_rule_silences_only_that_rule(self) -> None:
        source = "def f(items=[]):  # sbpy: ignore=shadows-builtin\n    return items\n"
        self.assertIn("mutable-default-arg", rules(source))

    def test_named_rule_matches(self) -> None:
        source = "def f(items=[]):  # sbpy: ignore=mutable-default-arg\n    return items\n"
        self.assertNotIn("mutable-default-arg", rules(source))

    def test_marker_after_another_comment(self) -> None:
        source = "try:\n    pass\nexcept:  # deliberate - sbpy: ignore=bare-except\n    pass\n"
        self.assertNotIn("bare-except", rules(source))


class RegistryTest(unittest.TestCase):
    def test_every_rule_has_a_category(self) -> None:
        grouped = rules_by_category()
        self.assertIn(CATEGORY_BUG, grouped)
        self.assertIn(CATEGORY_SEC, grouped)
        total = sum(len(items) for items in grouped.values())
        self.assertGreater(total, 40)

    def test_syntax_error_does_not_crash(self) -> None:
        unit = SourceUnit.from_source("def f(:\n")
        self.assertIsNone(unit.tree)
        self.assertIsNotNone(unit.syntax_error)
        self.assertEqual(analyze(unit, [CATEGORY_BUG]), [])


if __name__ == "__main__":
    unittest.main()
