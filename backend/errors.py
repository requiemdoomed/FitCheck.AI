"""One error shape for the whole API: {"error": {code, message, details}}."""


class ApiError(Exception):
    def __init__(self, status, code, message, details=None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details

    def body(self):
        err = {"code": self.code, "message": self.message}
        if self.details:
            err["details"] = self.details
        return {"error": err}


def bad(message, details=None):
    return ApiError(400, "validation_error", message, details)


def not_found(what="That item"):
    return ApiError(404, "not_found", f"{what} couldn't be found.")
