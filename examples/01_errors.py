"""דוגמה 1: איך נראה אבחון שגיאה.

הרצה:
    python -m sbpy run examples/01_errors.py
    python examples/01_errors.py            (עובד גם ככה - יש install() בקוד)

כל השגיאות כאן נפתרות מקומית. הרץ עם SBPY_VERBOSE=1 כדי לראות פרטים,
או עם --offline כדי לוודא ששום דבר לא יוצא לרשת.
"""

import sbpy

sbpy.install()


def show(title, func):
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")
    with sbpy.watch(reraise=False):
        func()


# ----------------------------------------------------------------------
def typo_in_variable():
    total_price = 100
    print(total_prcie)  # noqa: F821


def typo_in_dict_key():
    user = {"first_name": "אלי", "last_name": "כהן", "age": 30}
    print(user["first_nmae"])


def typo_in_argument():
    def draw(label, color="blue", width=2):
        return f"{label} {color} {width}"

    print(draw("קו", colour="red"))


def forgot_import():
    print(maht.sqrt(16))  # noqa: F821


def method_returned_none():
    numbers = [3, 1, 2].sort()
    print(numbers.index(1))


def index_out_of_range():
    rows = ["a", "b"]
    print(rows[5])


def wrong_type():
    count = 3
    print("סה\"כ: " + count)


if __name__ == "__main__":
    show("טעות כתיב במשתנה", typo_in_variable)
    show("טעות כתיב במפתח של מילון", typo_in_dict_key)
    show("טעות כתיב בשם פרמטר", typo_in_argument)
    show("import חסר", forgot_import)
    show("מתודה שהחזירה None", method_returned_none)
    show("אינדקס מחוץ לתחום", index_out_of_range)
    show("חיבור מחרוזת למספר", wrong_type)
    print("\nכל האבחונים למעלה נעשו מקומית. בדוק עם: python -m sbpy usage")
