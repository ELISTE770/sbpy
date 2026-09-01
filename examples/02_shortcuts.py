"""דוגמה 2: קיצורי הדרך.

שלוש דרכים להפעיל קיצור:

1. שורת פקודה:      python -m sbpy sfb examples/02_shortcuts.py
2. הנחיה בקוד:      # @SFB   ואז   python -m sbpy scan examples/
3. קריאה מפייתון:   sbpy.SFB(my_function)

הקוד כאן שתול בבאגים בכוונה - כדי שיהיה מה למצוא.
"""

import hashlib
import os
import subprocess

import sbpy


# @SFB
def build_report(rows=[], separator=","):
    """מייצר דוח טקסט מרשימת שורות."""
    output = ""
    for i in range(len(rows)):
        output += separator + str(rows[i])
        if rows[i] in ["skip", "ignore"]:
            rows.remove(rows[i])
    return output
    print("לעולם לא מגיעים לכאן")


# @SEC
def run_command(user_input):
    """מריץ פקודה שהגיעה מהמשתמש."""
    os.system("echo " + user_input)
    subprocess.run(user_input, shell=True)
    return hashlib.md5(user_input.encode()).hexdigest()


# @OPT
def find_duplicates(items, blacklist):
    seen = []
    result = []
    for item in items:
        if item in blacklist:
            continue
        if item in seen:
            result.append(item)
        seen.append(item)
    return sorted(result)[0]


# @CMP
def classify(value, mode, strict, verbose, retries, timeout, fallback):
    if mode == "a":
        if strict:
            for i in range(retries):
                if timeout > i:
                    if verbose and fallback:
                        return "deep"
    elif mode == "b":
        return "b"
    elif mode == "c":
        return "c"
    elif mode == "d":
        return "d"
    elif mode == "e":
        return "e"
    return "unknown"


if __name__ == "__main__":
    # דרך 3 - קריאה ישירה מפייתון. offline מוודא שלא יוצאים לרשת.
    sbpy.configure(offline=True)

    sbpy.SFB(build_report)
    sbpy.SEC(run_command)
    sbpy.OPT(find_duplicates)
    sbpy.CMP(classify)

    print("\nלהרצה של ההנחיות שבקוד:  python -m sbpy scan examples/")
    print("להסלמה מכוונת ל-Gemini:   python -m sbpy sfb examples/02_shortcuts.py --deep")
