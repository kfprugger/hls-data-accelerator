class RuntimeUtilities:

    @staticmethod
    def is_runtime_environment() -> bool:

        try:
            import notebookutils  # noqa: F401
        except ModuleNotFoundError:
            return False
        return True
