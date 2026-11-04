"""Small validator: collects every problem, then raises one 400 with details."""

from errors import bad


def _label(f):
    return f.replace("_", " ").capitalize()


class V:
    def __init__(self, data):
        self.d = data if isinstance(data, dict) else {}
        self.errors = {}
        self.clean = {}

    def _raw(self, f):
        v = self.d.get(f)
        return v.strip() if isinstance(v, str) else v

    def text(self, f, required=True, max=255, label=None, default=None):
        label = label or _label(f)
        v = self._raw(f)
        if v is None or v == "":
            if required:
                self.errors[f] = f"{label} is required."
            else:
                self.clean[f] = default
            return self
        if not isinstance(v, str):
            self.errors[f] = f"{label} must be text."
        elif len(v) > max:
            self.errors[f] = f"{label} must be {max} characters or fewer."
        elif any(ord(c) < 32 and c not in "\n\t" for c in v):
            self.errors[f] = f"{label} contains characters that aren't allowed."
        else:
            self.clean[f] = v
        return self

    def choice(self, f, options, required=True, label=None, default=None):
        label = label or _label(f)
        v = self._raw(f)
        if v is None or v == "":
            if required:
                self.errors[f] = f"{label} is required."
            else:
                self.clean[f] = default
        elif v not in options:
            self.errors[f] = f"{label} must be one of: {', '.join(options)}."
        else:
            self.clean[f] = v
        return self

    def multi(self, f, options, required=True, label=None, max=None):
        label = label or _label(f)
        v = self.d.get(f)
        if isinstance(v, str):
            v = [s.strip() for s in v.split(",") if s.strip()]
        if v is None or (isinstance(v, list) and not v):
            if required:
                self.errors[f] = f"Pick at least one {label.lower().rstrip('s')}."
            else:
                self.clean[f] = []
            return self
        if not isinstance(v, list) or any(not isinstance(x, str) for x in v):
            self.errors[f] = f"{label} must be a list."
            return self
        unknown = [x for x in v if x not in options]
        if unknown:
            self.errors[f] = f"Unknown {label.lower()}: {', '.join(unknown[:3])}."
        elif max and len(v) > max:
            self.errors[f] = f"Pick at most {max}."
        else:
            self.clean[f] = [o for o in options if o in v]
        return self

    def number(self, f, lo, hi, label=None):
        label = label or _label(f)
        v = self.d.get(f)
        try:
            n = float(v) if not isinstance(v, bool) and v not in (None, "") else None
        except (TypeError, ValueError):
            n = float("nan")
        if n is None:
            self.errors[f] = f"{label} is required."
        elif n != n or n in (float("inf"), float("-inf")):
            self.errors[f] = f"{label} must be a number."
        elif not lo <= n <= hi:
            self.errors[f] = f"{label} must be between {lo} and {hi}."
        else:
            self.clean[f] = round(n, 1)
        return self

    def email(self, f="email"):
        import re
        v = self._raw(f)
        if not v:
            self.errors[f] = "Email is required."
        elif not isinstance(v, str) or len(v) > 254 or not re.fullmatch(r"[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}", v):
            self.errors[f] = "Enter a valid email address."
        else:
            self.clean[f] = v.lower()
        return self

    def done(self, message="Some fields need attention."):
        if self.errors:
            raise bad(message, self.errors)
        return self.clean
