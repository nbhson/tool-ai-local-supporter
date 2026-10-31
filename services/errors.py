"""Application error types mapped to HTTP responses by the Flask errorhandler."""

class AppError(Exception):
    status_code = 400

    def __init__(self, message, status_code=None, payload=None):
        super().__init__()
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.payload = payload

    def to_dict(self):
        rv = dict(self.payload or ())
        rv['error'] = self.message
        return rv

class SessionNotFoundError(AppError):
    status_code = 404
    def __init__(self, message="Session not found", payload=None):
        super().__init__(message, status_code=404, payload=payload)

class InvalidRequestError(AppError):
    status_code = 400

class FileProcessingError(AppError):
    status_code = 400

class ToolExecutionError(AppError):
    status_code = 400
