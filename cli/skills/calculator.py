"""
Calculator + unit conversion skill.
Uses sympy for math and pint for units. Both free.

Voice commands:
    "what's 15 percent of 800"
    "calculate 25 times 8 plus 100"
    "convert 5 kilometers to miles"
    "how many pounds in 60 kg"
"""
import re

MATH_TRIGGERS = ["calculate", "what is", "what's", "compute", "solve",
                 "plus", "minus", "times", "divided by", "percent of",
                 "square root of", "squared"]
CONVERT_TRIGGERS = ["convert", "how many", "how much"]


def can_handle(query: str) -> bool:
    q = query.lower()
    if any(t in q for t in CONVERT_TRIGGERS) and _has_units(q):
        return True
    if any(t in q for t in MATH_TRIGGERS) and _has_numbers(q):
        return True
    return False


def handle(query: str, agent_name: str, language: str) -> str:
    q = query.lower()

    # Try unit conversion first
    if any(t in q for t in CONVERT_TRIGGERS) and _has_units(q):
        result = _convert_units(q)
        if result:
            return result

    # Percentage: "20 percent of 500"
    m = re.search(r"(\d+(?:\.\d+)?)\s*percent\s*of\s*(\d+(?:\.\d+)?)", q)
    if m:
        pct, val = float(m.group(1)), float(m.group(2))
        return f"{pct}% of {val:g} is {pct * val / 100:g}."

    # General math — replace English words with operators, then eval
    expr = _text_to_expression(q)
    if expr:
        try:
            result = eval(expr, {"__builtins__": {}}, _safe_math_funcs())
            if isinstance(result, float) and result.is_integer():
                result = int(result)
            return f"That's {result}."
        except Exception:
            pass

    return None


def _has_numbers(query: str) -> bool:
    return bool(re.search(r"\d", query))


def _has_units(query: str) -> bool:
    common_units = ["km", "kilometer", "mile", "meter", "cm", "inch", "foot", "feet",
                    "kg", "kilogram", "gram", "pound", "ounce",
                    "celsius", "fahrenheit", "kelvin",
                    "liter", "gallon", "cup", "ml",
                    "second", "minute", "hour", "day"]
    return any(u in query.lower() for u in common_units)


def _convert_units(query: str) -> str:
    try:
        import pint
        ureg = pint.UnitRegistry()

        # Try to parse: "5 kilometers to miles" or "60 kg in pounds"
        # Extract: number, from_unit, to_unit
        pattern = r"(\d+(?:\.\d+)?)\s*([a-z]+(?:\s+[a-z]+)?)\s+(?:to|in|into)\s+([a-z]+)"
        m = re.search(pattern, query.lower())
        if not m:
            # Try alternate: "how many pounds in 60 kg"
            pattern2 = r"how\s+many\s+([a-z]+)\s+(?:in|is)\s+(\d+(?:\.\d+)?)\s*([a-z]+)"
            m2 = re.search(pattern2, query.lower())
            if m2:
                to_unit, value, from_unit = m2.group(1), float(m2.group(2)), m2.group(3)
            else:
                return None
        else:
            value, from_unit, to_unit = float(m.group(1)), m.group(2).strip(), m.group(3)

        # Normalise common variants
        unit_map = {
            "kilometer": "km", "kilometers": "km",
            "meter": "m", "meters": "m",
            "mile": "mile", "miles": "mile",
            "foot": "ft", "feet": "ft",
            "inch": "inch", "inches": "inch",
            "kilogram": "kg", "kilograms": "kg",
            "pound": "pound", "pounds": "pound",
            "gram": "g", "grams": "g",
            "celsius": "degC", "fahrenheit": "degF", "kelvin": "kelvin",
        }
        from_unit = unit_map.get(from_unit, from_unit)
        to_unit   = unit_map.get(to_unit, to_unit)

        quantity = value * ureg(from_unit)
        converted = quantity.to(to_unit)
        return f"{value:g} {from_unit} is {converted.magnitude:.2f} {to_unit}."
    except ImportError:
        return "Install pint for unit conversion: pip install pint"
    except Exception:
        return None


def _text_to_expression(query: str) -> str:
    """Convert natural language math to Python expression."""
    q = query.lower()
    # Remove noise words
    for kw in ["what is", "what's", "calculate", "compute", "solve", "the answer to",
              "how much is", "please"]:
        q = q.replace(kw, "")

    # Replace English operators
    replacements = {
        r"\bplus\b": "+", r"\bminus\b": "-",
        r"\btimes\b": "*", r"\bmultiplied by\b": "*",
        r"\bdivided by\b": "/", r"\bover\b": "/",
        r"\bto the power of\b": "**", r"\bsquared\b": "**2", r"\bcubed\b": "**3",
        r"\bsquare root of\b": "sqrt",
    }
    for pattern, replacement in replacements.items():
        q = re.sub(pattern, replacement, q)

    # Keep only math-safe characters
    q = re.sub(r"[^\d\+\-\*\/\(\)\.\s\*sqrtabs]", "", q)
    q = q.strip()

    # Sanity check
    if re.search(r"[\d\)]\s*[\d\(]", q):
        # Two numbers adjacent — bad parse
        return None
    if not re.search(r"[\+\-\*\/]", q):
        return None
    return q


def _safe_math_funcs():
    import math
    return {
        "sqrt": math.sqrt, "abs": abs, "round": round,
        "log":  math.log,  "sin": math.sin, "cos": math.cos, "tan": math.tan,
        "pi":   math.pi,   "e": math.e,
    }