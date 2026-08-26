class ApplicationError(Exception):
    """Erro esperado que pode ser apresentado diretamente ao usuário."""


class ValidationError(ApplicationError):
    """Dados de entrada inválidos ou incompatíveis."""


class ExcelAutomationError(ApplicationError):
    """Falha ao manipular o painel pelo Microsoft Excel."""
