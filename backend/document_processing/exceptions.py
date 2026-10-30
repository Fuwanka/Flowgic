class ProcessingError(Exception):
    def __init__(self, detail, *, code='document_processing_error', status=400):
        self.detail, self.code, self.status = detail, code, status
        super().__init__(detail)
