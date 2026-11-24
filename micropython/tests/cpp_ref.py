# cpp_ref.py - read numeric codes from the C++ reference headers (laptop tests only).
# Used to check that the port keeps the same enum / bit values as firmware/.
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
FIRMWARE = os.path.join(REPO, "firmware")


def read(rel):
    with open(os.path.join(FIRMWARE, rel)) as f:
        return f.read()


def _int(s):
    return int(s.strip().rstrip(",").strip().rstrip("uU"), 0)


def _value(expr):
    e = expr.strip().rstrip(",")
    if "<<" in e:
        a, b = e.split("<<")
        return _int(a) << _int(b)
    return _int(e)


def enum_values(text, enum_name):
    """{name: value} for `enum [class] <enum_name> [: type] { A = 1, ... };`."""
    start = text.find("enum class " + enum_name)
    if start < 0:
        start = text.find("enum " + enum_name)
    if start < 0:
        raise KeyError(enum_name)
    body = text[text.index("{", start) + 1:text.index("};", start)]
    out = {}
    for line in body.split("\n"):
        line = line.split("//")[0].strip()
        if "=" not in line:
            continue
        for part in line.split(","):
            if "=" in part:
                k, v = part.split("=", 1)
                out[k.strip()] = _value(v)
    return out


def param_members(text, struct_name):
    """Ordered member names declared as Param<...> in a C++ struct."""
    start = text.index("struct " + struct_name)
    body = text[text.index("{", start):text.index("};", start)]
    out = []
    for line in body.split("\n"):
        s = line.split("//")[0].strip()
        if s.startswith("Param<") and s.endswith(";"):
            out.append(s.split(">", 1)[1].strip().rstrip(";").strip())
    return out
