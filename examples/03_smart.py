"""דוגמה 3: ‎@smart‎ - אבחון, ולפעמים גם תיקון אוטומטי והרצה חוזרת.

התיקון האוטומטי מופעל רק על שגיאות דטרמיניסטיות ובטוחות. כרגע:
שם פרמטר עם טעות כתיב. כל השאר מאובחן בלבד ונזרק הלאה.

הרצה:
    python examples/03_smart.py
"""

import sbpy

sbpy.configure(offline=True)


def create_user(name, role="viewer", active=True):
    return {"name": name, "role": role, "active": active}


# ----------------------------------------------------------------------
@sbpy.smart
def register(name, **options):
    """נרשם משתמש חדש. שים לב ל-**options - זה מה שמאפשר תיקון אוטומטי."""
    return create_user(name, **options)


@sbpy.smart(show=False, reraise=False, default={})
def safe_parse(raw):
    """מחזיר {} במקום להתפוצץ, ועדיין מאבחן ברקע."""
    import json

    return json.loads(raw)


@sbpy.SFB.on
def suspicious(items=[]):
    """הדקורטור סורק את הפונקציה בזמן ההגדרה ומחזיר אותה כמו שהיא."""
    return items


if __name__ == "__main__":
    print("=" * 60)
    print("1. תיקון אוטומטי של שם פרמטר")
    print("=" * 60)
    print(register("אלי", rol="admin"))

    print("\n" + "=" * 60)
    print("2. כישלון רך - מחזיר ברירת מחדל במקום לזרוק")
    print("=" * 60)
    print("תוצאה:", safe_parse("{לא JSON תקין}"))

    print("\n" + "=" * 60)
    print("3. אבחון ידני של חריגה שנתפסה")
    print("=" * 60)
    try:
        settings = {"width": 100}
        settings["hieght"]
    except KeyError as exc:
        report = sbpy.explain(exc)
        print("מקור האבחנה:", report.best.source, "· ביטחון:", report.best.confidence)
